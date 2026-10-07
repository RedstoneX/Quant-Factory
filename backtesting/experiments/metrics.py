"""Metric policies and calculations for reproducible experiments."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any

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
        basis="complete exchange-session-close portfolio equity and session returns",
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
    if not data.index.equals(value.index):
        raise RuntimeError("portfolio values must align exactly with source data")
    schedule = get_exchange_calendar(config.market_data).schedule(
        start_date=value.index[0].date(),
        end_date=value.index[-1].date(),
    )
    completed = schedule.loc[schedule["market_close"] <= value.index[-1]]
    partial = schedule.loc[
        (schedule["market_open"] <= value.index[-1])
        & (schedule["market_close"] > value.index[-1])
    ]
    if not partial.empty:
        raise RuntimeError("session metrics cannot include a partially observed final session")
    if len(completed) < 2:
        raise RuntimeError("session metrics require at least two completed sessions")
    try:
        interval = pd.Timedelta(config.market_data.interval)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("session metrics require a fixed source interval") from exc
    session_values: list[float] = []
    session_labels: list[object] = []
    for session_label, row in completed.iterrows():
        market_close = pd.Timestamp(row["market_close"]).tz_convert(value.index.tz)
        closing_bar = market_close - interval
        try:
            closing_value = value.loc[closing_bar]
        except KeyError as exc:
            raise RuntimeError(
                f"source data is missing the closing bar for exchange session {session_label}"
            ) from exc
        session_labels.append(session_label)
        session_values.append(float(closing_value))
    equity = pd.Series(session_values, index=session_labels, dtype=float)
    previous = pd.Series(
        [config.execution.initial_cash, *equity.iloc[:-1].tolist()],
        index=equity.index,
        dtype=float,
    )
    returns = equity / previous - 1.0
    periods = float(policy.periods_per_year)
    final_ratio = float(equity.iloc[-1]) / config.execution.initial_cash
    annualized_return = final_ratio ** (periods / len(equity)) - 1.0
    period_risk_free = (1.0 + float(policy.risk_free_rate)) ** (1.0 / periods) - 1.0
    excess = returns - period_risk_free
    volatility = float(excess.std(ddof=1))
    if not math.isfinite(volatility):
        raise RuntimeError("session-return sample standard deviation must be finite")
    sharpe = (
        float("nan")
        if volatility == 0.0
        else float(excess.mean()) / volatility * math.sqrt(periods)
    )
    if not math.isfinite(annualized_return):
        raise RuntimeError("session annualized return must be finite")
    return final_ratio - 1.0, annualized_return, sharpe


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
