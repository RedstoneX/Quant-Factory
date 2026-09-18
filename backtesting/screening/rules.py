"""Cheap deterministic screening rules over existing experiment metrics."""

import math
from typing import Any, Callable

from backtesting.screening.models import ScreeningConfig, ScreeningRuleResult

REQUIRED_METRICS = (
    "number_of_trades",
    "total_return",
    "annualized_return",
    "sharpe_ratio",
    "max_drawdown",
)


def _rule(
    rule_id: str,
    metric: str,
    observed: Any,
    threshold: Any,
    passed: bool,
    condition: str,
    *,
    details: dict[str, Any] | None = None,
) -> ScreeningRuleResult:
    message = (
        f"{metric} passed: {condition}."
        if passed
        else f"{metric} failed: expected {condition}; observed {observed!r}."
    )
    return ScreeningRuleResult(
        rule_id=rule_id,
        metric=metric,
        observed_value=observed,
        threshold=threshold,
        status="passed" if passed else "failed",
        message=message,
        details=details or {},
    )


def _numeric_rule(
    metrics: dict[str, Any],
    *,
    rule_id: str,
    metric: str,
    threshold: float | int,
    comparison: Callable[[float, float], bool],
    condition: str,
) -> ScreeningRuleResult:
    observed = metrics.get(metric)
    valid = isinstance(observed, (int, float)) and not isinstance(observed, bool)
    valid = valid and math.isfinite(float(observed))
    passed = bool(valid and comparison(float(observed), float(threshold)))
    return _rule(rule_id, metric, observed, threshold, passed, condition)


def evaluate_rules(
    metrics: dict[str, Any], config: ScreeningConfig
) -> tuple[ScreeningRuleResult, ...]:
    """Evaluate rules in a fixed order; decision is conjunction of all results."""
    required = list(REQUIRED_METRICS)
    if config.minimum_win_rate is not None:
        required.append("win_rate")
    missing = tuple(metric for metric in required if metric not in metrics)
    non_finite = tuple(
        metric
        for metric in required
        if metric in metrics
        and (
            not isinstance(metrics[metric], (int, float))
            or isinstance(metrics[metric], bool)
            or not math.isfinite(float(metrics[metric]))
        )
    )
    results = [
        _rule(
            "metrics.available",
            "required_metrics",
            tuple(sorted(metrics)),
            tuple(required),
            not missing,
            "all required metrics are available",
            details={"missing": missing},
        ),
        _rule(
            "metrics.finite",
            "required_metrics",
            {metric: metrics.get(metric) for metric in required},
            "all finite",
            not non_finite,
            "all available required metrics are finite",
            details={"non_finite": non_finite},
        ),
        _numeric_rule(
            metrics,
            rule_id="trades.minimum",
            metric="number_of_trades",
            threshold=config.minimum_trades,
            comparison=lambda observed, threshold: observed >= threshold,
            condition=f">= {config.minimum_trades} (inclusive)",
        ),
        _numeric_rule(
            metrics,
            rule_id="return.total_minimum",
            metric="total_return",
            threshold=config.minimum_total_return,
            comparison=lambda observed, threshold: observed > threshold,
            condition=f"> {config.minimum_total_return} (exclusive)",
        ),
        _numeric_rule(
            metrics,
            rule_id="return.annualized_minimum",
            metric="annualized_return",
            threshold=config.minimum_annualized_return,
            comparison=lambda observed, threshold: observed > threshold,
            condition=f"> {config.minimum_annualized_return} (exclusive)",
        ),
        _numeric_rule(
            metrics,
            rule_id="risk.sharpe_minimum",
            metric="sharpe_ratio",
            threshold=config.minimum_sharpe_ratio,
            comparison=lambda observed, threshold: observed >= threshold,
            condition=f">= {config.minimum_sharpe_ratio} (inclusive)",
        ),
        _numeric_rule(
            {"drawdown_magnitude": abs(metrics["max_drawdown"])}
            if isinstance(metrics.get("max_drawdown"), (int, float))
            and not isinstance(metrics.get("max_drawdown"), bool)
            else {},
            rule_id="risk.drawdown_maximum",
            metric="drawdown_magnitude",
            threshold=config.maximum_drawdown,
            comparison=lambda observed, threshold: observed <= threshold,
            condition=f"<= {config.maximum_drawdown} (inclusive)",
        ),
    ]
    if config.minimum_win_rate is not None:
        results.append(
            _numeric_rule(
                metrics,
                rule_id="trades.win_rate_minimum",
                metric="win_rate",
                threshold=config.minimum_win_rate,
                comparison=lambda observed, threshold: observed >= threshold,
                condition=f">= {config.minimum_win_rate} (inclusive)",
            )
        )
    return tuple(results)
