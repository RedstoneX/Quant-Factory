"""Past-only trend and volatility labels plus indexed regime evaluation."""

from __future__ import annotations

import math
from typing import Mapping

import numpy as np
import pandas as pd

from backtesting.monte_carlo.metrics import cumulative_return, maximum_drawdown
from backtesting.robustness.models import (
    RegimeConfig,
    RegimeEvaluationResult,
    RegimeLabelMetadata,
    RegimeLabels,
    ThresholdResult,
)

UNKNOWN_REGIME = "unknown|unknown"


def _validate_indexed_series(name: str, series: pd.Series) -> None:
    if not isinstance(series, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")
    if series.empty:
        raise ValueError(f"{name} must not be empty")
    if not series.index.is_unique:
        raise ValueError(f"{name} index must be unique")
    if not series.index.is_monotonic_increasing:
        raise ValueError(f"{name} index must be increasing")


def label_regimes(close: pd.Series, config: RegimeConfig) -> RegimeLabels:
    """Label each close using trailing observations available at that timestamp."""
    _validate_indexed_series("close", close)
    if close.isna().any() or not np.isfinite(close.to_numpy(dtype=float)).all():
        raise ValueError("close must contain only finite values")
    if (close <= 0).any():
        raise ValueError("close must be positive")

    moving_average = close.rolling(
        config.trend_window,
        min_periods=config.trend_window,
        center=False,
    ).mean()
    relative_distance = close / moving_average - 1.0
    trend = pd.Series("unknown", index=close.index, dtype="object")
    usable_trend = moving_average.notna()
    trend.loc[usable_trend & (relative_distance > config.trend_neutral_tolerance)] = "bullish"
    trend.loc[usable_trend & (relative_distance < -config.trend_neutral_tolerance)] = "bearish"
    trend.loc[usable_trend & (relative_distance.abs() <= config.trend_neutral_tolerance)] = "neutral"

    period_returns = close.pct_change(fill_method=None)
    realized_volatility = period_returns.rolling(
        config.volatility_window,
        min_periods=config.volatility_window,
        center=False,
    ).std(ddof=1) * math.sqrt(config.annualization_factor)
    volatility = pd.Series("unknown", index=close.index, dtype="object")
    usable_volatility = realized_volatility.notna()
    volatility.loc[usable_volatility & (realized_volatility <= config.volatility_threshold)] = "low_volatility"
    volatility.loc[usable_volatility & (realized_volatility > config.volatility_threshold)] = "high_volatility"

    usable = usable_trend & usable_volatility
    labels = pd.Series(UNKNOWN_REGIME, index=close.index, dtype="object")
    labels.loc[usable] = trend.loc[usable] + "|" + volatility.loc[usable]
    first_usable = labels.index[usable.argmax()] if usable.any() else None
    metadata = RegimeLabelMetadata(
        first_usable_timestamp=(
            first_usable.isoformat() if first_usable is not None else None
        ),
        warmup_observation_count=int((~usable).sum()),
        trend_rule=(
            f"close versus trailing {config.trend_window}-bar mean with "
            f"neutral tolerance {config.trend_neutral_tolerance}"
        ),
        volatility_rule=(
            f"trailing {config.volatility_window}-return sample volatility "
            f"annualized by {config.annualization_factor} against fixed "
            f"threshold {config.volatility_threshold}"
        ),
        annualization_factor=config.annualization_factor,
        attribution_policy=(
            "period return at timestamp t is attributed to the regime label "
            "known at timestamp t-1"
        ),
    )
    return RegimeLabels(
        labels=labels,
        trend=trend,
        volatility=volatility,
        realized_volatility=realized_volatility,
        metadata=metadata,
    )


def attribute_returns_to_regimes(
    returns: pd.Series,
    labels: pd.Series,
) -> pd.DataFrame:
    """Align period returns with the regime known at the period start."""
    _validate_indexed_series("returns", returns)
    _validate_indexed_series("labels", labels)
    if not returns.index.equals(labels.index):
        raise ValueError("returns and regime labels must have identical indexes")
    if returns.isna().any() or not np.isfinite(returns.to_numpy(dtype=float)).all():
        raise ValueError("returns must contain only finite values")
    attributed = labels.shift(1).fillna(UNKNOWN_REGIME)
    return pd.DataFrame({"return": returns, "regime": attributed}, index=returns.index)


def _sharpe(values: np.ndarray, annualization_factor: float) -> float | None:
    if len(values) < 2:
        return None
    standard_deviation = float(values.std(ddof=1))
    if standard_deviation == 0 or not math.isfinite(standard_deviation):
        return None
    return float(values.mean() / standard_deviation * math.sqrt(annualization_factor))


def evaluate_regimes(
    returns: pd.Series,
    labels: RegimeLabels,
    config: RegimeConfig,
    *,
    minimum_return: float,
    maximum_drawdown_limit: float,
    minimum_sharpe: float | None,
    trade_entries: pd.Series | None = None,
) -> tuple[RegimeEvaluationResult, ...]:
    """Evaluate indexed locked-strategy period returns by start label."""
    attributed = attribute_returns_to_regimes(returns, labels.labels)
    if trade_entries is not None:
        _validate_indexed_series("trade_entries", trade_entries)
        if not trade_entries.index.equals(returns.index):
            raise ValueError("trade entries must align with returns")
        if trade_entries.isna().any():
            raise ValueError("trade entries must not contain nulls")

    results: list[RegimeEvaluationResult] = []
    regime_ids = sorted(set(attributed["regime"]) - {UNKNOWN_REGIME})
    for regime_id in regime_ids:
        mask = attributed["regime"] == regime_id
        regime_returns = attributed.loc[mask, "return"]
        values = regime_returns.to_numpy(dtype=float)
        trend_component, volatility_component = regime_id.split("|", 1)
        if trade_entries is not None:
            entry_mask = labels.labels == regime_id
            trade_count = int(trade_entries.loc[entry_mask].astype(bool).sum())
        else:
            trade_count = None
        threshold_results: list[ThresholdResult] = []
        reasons: list[str] = []
        warnings: list[str] = []

        observation_ok = len(values) >= config.minimum_observations
        threshold_results.append(
            ThresholdResult(
                "minimum_observations",
                "passed" if observation_ok else "insufficient_evidence",
                len(values),
                config.minimum_observations,
                "regime observation count",
            )
        )
        trade_ok = True
        if config.minimum_trades is not None:
            if trade_count is None:
                trade_ok = False
                reasons.append("trade evidence is unavailable")
            else:
                trade_ok = trade_count >= config.minimum_trades
            threshold_results.append(
                ThresholdResult(
                    "minimum_trades",
                    "passed" if trade_ok else "insufficient_evidence",
                    trade_count,
                    config.minimum_trades,
                    "regime trade count",
                )
            )

        if not observation_ok or not trade_ok:
            if not observation_ok:
                reasons.append("regime has insufficient observations")
            results.append(
                RegimeEvaluationResult(
                    regime_id=regime_id,
                    trend_component=trend_component,
                    volatility_component=volatility_component,
                    first_timestamp=regime_returns.index[0].isoformat() if len(values) else None,
                    last_timestamp=regime_returns.index[-1].isoformat() if len(values) else None,
                    observation_count=len(values),
                    trade_count=trade_count,
                    total_return=None,
                    maximum_drawdown=None,
                    sharpe_ratio=None,
                    win_rate=None,
                    minimum_observations=config.minimum_observations,
                    minimum_trades=config.minimum_trades,
                    threshold_results=tuple(threshold_results),
                    status="insufficient_evidence",
                    reasons=tuple(reasons),
                    warnings=(),
                )
            )
            continue

        total_return = cumulative_return(values)
        max_drawdown = maximum_drawdown(values)
        sharpe = _sharpe(values, config.annualization_factor)
        win_rate = float(np.mean(values > 0)) if len(values) else None
        checks = [
            ("minimum_return", total_return >= minimum_return, total_return, minimum_return),
            ("maximum_drawdown", abs(max_drawdown) <= maximum_drawdown_limit, abs(max_drawdown), maximum_drawdown_limit),
        ]
        if minimum_sharpe is not None:
            if sharpe is None:
                warnings.append("Sharpe is undefined")
                checks.append(("minimum_sharpe", False, None, minimum_sharpe))
            else:
                checks.append(("minimum_sharpe", sharpe >= minimum_sharpe, sharpe, minimum_sharpe))
        for rule_id, passed, observed, threshold in checks:
            threshold_results.append(
                ThresholdResult(
                    rule_id,
                    "passed" if passed else "failed",
                    observed,
                    threshold,
                    f"{rule_id}: observed {observed!r}, threshold {threshold!r}",
                )
            )
            if not passed:
                reasons.append(f"{rule_id} threshold failed")
        status = "passed" if not reasons else "failed"
        results.append(
            RegimeEvaluationResult(
                regime_id=regime_id,
                trend_component=trend_component,
                volatility_component=volatility_component,
                first_timestamp=regime_returns.index[0].isoformat(),
                last_timestamp=regime_returns.index[-1].isoformat(),
                observation_count=len(values),
                trade_count=trade_count,
                total_return=total_return,
                maximum_drawdown=max_drawdown,
                sharpe_ratio=sharpe,
                win_rate=win_rate,
                minimum_observations=config.minimum_observations,
                minimum_trades=config.minimum_trades,
                threshold_results=tuple(threshold_results),
                status=status,
                reasons=tuple(reasons),
                warnings=tuple(warnings),
            )
        )
    return tuple(results)
