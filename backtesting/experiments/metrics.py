"""Metric policies and calculations for reproducible experiments."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any

import numpy as np
import pandas as pd

from backtesting.experiments.models import ExperimentConfig, MetricPolicy
from market_data.calendars import get_exchange_calendar


def _as_float(value: object) -> float:
    if hasattr(value, "iloc"):
        value = value.iloc[0]
    return float(value)


def configure_candidate_metric_policy(
    experiment: ExperimentConfig,
    annualization_factor: float,
    data_as_of: str | None,
) -> ExperimentConfig:
    """Derive intraday screening metrics from the saved session contract."""
    try:
        interval = pd.Timedelta(experiment.market_data.interval)
    except (TypeError, ValueError) as exc:
        raise ValueError("Candidate interval must be a fixed duration") from exc
    if interval <= pd.Timedelta(0):
        raise ValueError("Candidate interval must be positive")
    if interval >= pd.Timedelta(days=1):
        return experiment
    calendar = get_exchange_calendar(experiment.market_data)
    end = (
        pd.Timestamp(data_as_of).date()
        if data_as_of
        else pd.Timestamp("2024-03-31").date()
    )
    schedule = calendar.schedule(
        start_date=end - pd.Timedelta(days=60),
        end_date=end,
    )
    if schedule.empty:
        raise ValueError("Candidate exchange calendar produced no sessions")
    full_session = (schedule["market_close"] - schedule["market_open"]).max()
    bars_per_session = full_session / interval
    rounded_bars = round(float(bars_per_session))
    if rounded_bars < 1 or not math.isclose(float(bars_per_session), rounded_bars):
        raise ValueError("Candidate interval does not divide its full exchange session")
    periods_per_year = float(annualization_factor) / rounded_bars
    rounded_periods = round(periods_per_year)
    if rounded_periods < 1 or not math.isclose(periods_per_year, rounded_periods):
        raise ValueError(
            "Candidate annualization factor does not resolve to whole exchange sessions"
        )
    policy = MetricPolicy(
        sampling="exchange_session_close",
        periods_per_year=float(rounded_periods),
        risk_free_rate=0.0,
        basis=(
            "complete exchange-session-close portfolio equity, or the final "
            "deterministically unchanged cash equity across a verified-flat data gap"
        ),
        source=(
            "saved robustness annualization factor divided by full-session bars "
            f"({annualization_factor:g}/{rounded_bars})"
        ),
    )
    if experiment.metric_policy is not None and experiment.metric_policy != policy:
        raise ValueError("Candidate screening metric policy conflicts with its saved contract")
    return replace(experiment, metric_policy=policy)


def _portfolio_value_series(portfolio: Any) -> pd.Series:
    value = portfolio.value() if callable(portfolio.value) else portfolio.value
    if isinstance(value, pd.DataFrame):
        if value.shape[1] != 1:
            raise RuntimeError("portfolio value must contain exactly one column")
        value = value.iloc[:, 0]
    if not isinstance(value, pd.Series) or value.empty:
        raise RuntimeError("portfolio value must be a nonempty Series")
    if not isinstance(value.index, pd.DatetimeIndex) or value.index.tz is None:
        raise RuntimeError("session metrics require timezone-aware portfolio timestamps")
    if not value.index.is_monotonic_increasing or not value.index.is_unique:
        raise RuntimeError("portfolio timestamps must be unique and chronological")
    values = value.astype(float)
    if not values.map(math.isfinite).all() or (values <= 0).any():
        raise RuntimeError("portfolio values must be positive and finite")
    return values


def _portfolio_asset_series(portfolio: Any) -> pd.Series | None:
    """Return aligned net asset units when the engine exposes them."""
    assets = getattr(portfolio, "assets", None)
    if assets is None:
        return None
    assets = assets() if callable(assets) else assets
    if isinstance(assets, pd.DataFrame):
        if assets.shape[1] != 1:
            return None
        assets = assets.iloc[:, 0]
    if not isinstance(assets, pd.Series):
        return None
    return assets.astype(float)


def _missing_session_close_value(
    value: pd.Series,
    assets: pd.Series | None,
    session_label: object,
    market_open: pd.Timestamp,
    market_close: pd.Timestamp,
    closing_bar: pd.Timestamp,
) -> float:
    """Equity for a session whose closing bar is absent, or raise."""
    missing = RuntimeError(
        f"source data is missing the closing bar for exchange session {session_label}"
    )
    observed = value.loc[(value.index >= market_open) & (value.index < market_close)]
    if observed.empty:
        before = value.index[value.index < market_open]
        after = value.index[value.index >= market_close]
        if (
            assets is not None
            and len(before)
            and len(after)
            and float(assets.loc[before[-1]]) == 0.0
            and float(assets.loc[after[0]]) == 0.0
        ):
            # A wholly absent exchange session bracketed by verified
            # flat exposure has the same exact cash equity as the last
            # observation before it. Retain the zero-return session in
            # the annualization sample instead of shrinking the sample.
            return float(value.loc[before[-1]])
        raise missing
    if assets is None:
        raise missing
    last_observed = observed.index[-1]
    if last_observed >= closing_bar or float(assets.loc[last_observed]) != 0.0:
        raise missing
    # With zero asset exposure, portfolio equity is cash and cannot vary
    # with the missing market-price observation before the session close.
    return float(observed.iloc[-1])


def session_close_metrics_frame(
    value: pd.DataFrame,
    assets: pd.DataFrame | None,
    data: pd.DataFrame,
    config: ExperimentConfig,
) -> list[tuple[float, float, float]]:
    """Return, annualized return and Sharpe per column from exact session closes.

    Sampling (which bar closes each exchange session) is ours; the statistics
    are VectorBT PRO ReturnsAccessor total, annualized and sharpe_ratio.

    The exchange calendar is queried once and the session-close bar index is
    built once; every column is then read with one DataFrame.loc selection.
    """
    policy = config.metric_policy
    if policy is None or policy.sampling != "exchange_session_close":
        raise RuntimeError("exchange-session metric policy is required")
    if value.empty or value.shape[1] == 0:
        raise RuntimeError("portfolio value must be a nonempty Series")
    if not isinstance(value.index, pd.DatetimeIndex) or value.index.tz is None:
        raise RuntimeError("session metrics require timezone-aware portfolio timestamps")
    if not value.index.is_monotonic_increasing or not value.index.is_unique:
        raise RuntimeError("portfolio timestamps must be unique and chronological")
    value = value.astype(float)
    if not np.isfinite(value.to_numpy()).all() or (value.to_numpy() <= 0).any():
        raise RuntimeError("portfolio values must be positive and finite")
    if not data.index.equals(value.index):
        raise RuntimeError("portfolio values must align exactly with source data")
    schedule = get_exchange_calendar(config.market_data).schedule(
        start_date=value.index[0].date(),
        end_date=value.index[-1].date(),
    )
    try:
        interval = pd.Timedelta(config.market_data.interval)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("session metrics require a fixed source interval") from exc
    # Bars are labelled by their open, so the last bar is observed through its end.
    observed_through = value.index[-1] + interval
    completed = schedule.loc[schedule["market_close"] <= observed_through]
    partial = schedule.loc[
        (schedule["market_open"] <= value.index[-1])
        & (schedule["market_close"] > observed_through)
    ]
    if not partial.empty:
        raise RuntimeError("session metrics cannot include a partially observed final session")
    if len(completed) < 2:
        raise RuntimeError("session metrics require at least two completed sessions")
    opens = pd.DatetimeIndex(completed["market_open"]).tz_convert(value.index.tz)
    closes = pd.DatetimeIndex(completed["market_close"]).tz_convert(value.index.tz)
    closing_idx = closes - interval
    present = closing_idx.isin(value.index)
    equity = pd.DataFrame(
        np.nan, index=completed.index, columns=value.columns, dtype=float
    )
    equity.iloc[present] = value.loc[closing_idx[present]].to_numpy()
    if not present.all():
        aligned = assets is not None and assets.index.equals(value.index)
        for row in np.flatnonzero(~present):
            for col in range(value.shape[1]):
                equity.iloc[row, col] = _missing_session_close_value(
                    value.iloc[:, col],
                    assets.iloc[:, col].astype(float) if aligned else None,
                    completed.index[row],
                    opens[row],
                    closes[row],
                    closing_idx[row],
                )
    # Statistics come from VectorBT PRO's ReturnsAccessor on the session-close
    # equity: one row per exchange session, so freq is one day and year_freq is
    # periods_per_year days, giving ann_factor == periods_per_year. The library
    # converts the annual risk-free rate to a per-session rate itself.
    import vectorbtpro as vbt

    periods = float(policy.periods_per_year)
    returns = vbt.ReturnsAccessor.from_value(
        equity.reset_index(drop=True),
        init_value=float(config.execution.initial_cash),
        freq="1D",
        year_freq=pd.Timedelta(days=periods),
        defaults=dict(risk_free=float(policy.risk_free_rate), ddof=1),
    )
    total = np.atleast_1d(np.asarray(returns.total(), dtype=float))
    annualized = np.atleast_1d(np.asarray(returns.annualized(), dtype=float))
    sharpe = np.atleast_1d(np.asarray(returns.sharpe_ratio(), dtype=float))
    if not np.isfinite(annualized).all():
        raise RuntimeError("session annualized return must be finite")
    return list(zip(total.tolist(), annualized.tolist(), sharpe.tolist()))


def session_close_metrics(
    portfolio: Any,
    data: pd.DataFrame,
    config: ExperimentConfig,
) -> tuple[float, float, float]:
    """Calculate return and Sharpe from exact completed session closes."""
    policy = config.metric_policy
    if policy is None or policy.sampling != "exchange_session_close":
        raise RuntimeError("exchange-session metric policy is required")
    value = _portfolio_value_series(portfolio)
    assets = _portfolio_asset_series(portfolio)
    return session_close_metrics_frame(
        value.to_frame(),
        None if assets is None else assets.to_frame(),
        data,
        config,
    )[0]


def extract_metrics(
    portfolio: Any,
    *,
    data: pd.DataFrame | None = None,
    config: ExperimentConfig | None = None,
) -> dict[str, float | int]:
    """Extract metrics using the declared observation basis when configured."""
    if config is not None and config.metric_policy is not None:
        if data is None:
            raise ValueError("declared metric policy requires source data")
        total_return, annualized_return, sharpe_ratio = session_close_metrics(
            portfolio, data, config
        )
    else:
        total_return = _as_float(portfolio.total_return)
        annualized_return = _as_float(portfolio.annualized_return)
        sharpe_ratio = _as_float(portfolio.sharpe_ratio)
    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": _as_float(portfolio.max_drawdown),
        "number_of_trades": int(_as_float(portfolio.trades.count())),
        "win_rate": _as_float(portfolio.trades.win_rate),
    }


def _per_setting(value: Any, count: int) -> list[float]:
    """Split one library property read on the whole sweep into one float per setting."""
    values = np.asarray(value.to_numpy() if hasattr(value, "to_numpy") else value, dtype=float).reshape(-1)
    if values.size != count:
        raise RuntimeError(f"sweep metric has {values.size} values for {count} settings")
    return values.tolist()


def _sweep_frame(portfolio: Any, name: str) -> pd.DataFrame | None:
    frame = getattr(portfolio, name, None)
    frame = frame() if callable(frame) else frame
    return frame if isinstance(frame, pd.DataFrame) else None


def extract_sweep_metrics(
    portfolio: Any,
    count: int,
    *,
    data: pd.DataFrame | None = None,
    config: ExperimentConfig | None = None,
) -> list[dict[str, float | int]]:
    """Every setting's metrics from one multi-column VectorBT PRO portfolio.

    Each library property (total_return, annualized_return, sharpe_ratio, max_drawdown,
    trades.count(), trades.win_rate) is read once and returns one value per column.
    A declared session policy reads value and assets once and computes
    session_close_metrics_frame once for all columns.
    """
    if config is not None and config.metric_policy is not None:
        if data is None:
            raise ValueError("declared metric policy requires source data")
        value = _sweep_frame(portfolio, "value")
        if value is None or value.shape[1] != count:
            raise RuntimeError("sweep portfolio value must have one column per setting")
        assets = _sweep_frame(portfolio, "assets")
        session = session_close_metrics_frame(value, assets, data, config)
        total_return, annualized_return, sharpe_ratio = (list(column) for column in zip(*session))
    else:
        total_return = _per_setting(portfolio.total_return, count)
        annualized_return = _per_setting(portfolio.annualized_return, count)
        sharpe_ratio = _per_setting(portfolio.sharpe_ratio, count)
    max_drawdown = _per_setting(portfolio.max_drawdown, count)
    trade_counts = _per_setting(portfolio.trades.count(), count)
    win_rate = _per_setting(portfolio.trades.win_rate, count)
    return [
        {
            "total_return": total_return[position],
            "annualized_return": annualized_return[position],
            "sharpe_ratio": sharpe_ratio[position],
            "max_drawdown": max_drawdown[position],
            "number_of_trades": int(trade_counts[position]),
            "win_rate": win_rate[position],
        }
        for position in range(count)
    ]
