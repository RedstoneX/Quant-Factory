"""Focused tests for deterministic cheap strategy screening."""

from dataclasses import replace

import pandas as pd
import pytest

import backtesting.experiments.chunking as chunking
import backtesting.experiments.runner as experiment_runner
from backtesting.experiments import execute_experiment
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.screening import (
    ScreeningConfig,
    parameter_row_identity,
    screen_metrics,
)
from market_data import DataAudit


def _metrics() -> dict[str, float | int]:
    return {
        "number_of_trades": 20,
        "total_return": 0.01,
        "annualized_return": 0.01,
        "sharpe_ratio": 0.5,
        "max_drawdown": -0.35,
        "win_rate": 0.5,
    }


def _screen(metrics: dict[str, object], config: ScreeningConfig | None = None):
    return screen_metrics(
        experiment_id="screening_test",
        strategy_id="rsi_mean_reversion",
        strategy_version="1.0.0",
        parameters={"window": 7, "entry_threshold": 25, "exit_threshold": 60},
        execution_assumptions={"execution_mode": "next_bar_open"},
        metrics=metrics,
        config=config or ScreeningConfig.provisional_defaults(),
    )


def _data() -> pd.DataFrame:
    """Ten-bar declines and recoveries so RSI(7) crosses the entry and exit bands."""
    index = pd.date_range("2024-01-01", periods=80, freq="D")
    phase = pd.Series(range(len(index)), index=index) % 20
    close = 100.0 - 3.0 * phase.where(phase < 10, 20 - phase)
    return pd.DataFrame({"Open": close - 1.0, "Close": close})


def _audit(data: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="test",
        interval="1 day",
        requested_start="2024-01-01",
        requested_dynamic_end_policy="test",
        latest_completed_exchange_session="2024-03-20",
        prices_adjusted=True,
        adjustment_verification="test",
        download_time="2024-03-20T17:00:00-04:00",
        download_timezone="America/New_York",
        actual_first_row_date="2024-01-01",
        actual_last_row_date="2024-03-20",
        row_count=len(data),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
    )


# On _data(), RSI(7) entry 25 / exit 60 completes 3 round trips; RSI(14) entry 30 / exit 50 completes 1.
TRADING = {"window": 7, "entry_threshold": 25, "exit_threshold": 60}
ONE_TRADE = {"window": 14, "entry_threshold": 30, "exit_threshold": 50}


def _experiment_config(*combinations: dict[str, int]):
    return replace(
        EXPERIMENT_CONFIG,
        parameter_combinations=combinations,
        screening=replace(ScreeningConfig.provisional_defaults(), minimum_trades=2),
    )


def test_all_rules_pass_at_inclusive_boundaries() -> None:
    result = _screen(_metrics())
    assert result.passed
    assert result.failed_rule_count == 0
    assert result.passed_rule_count == len(result.rule_results)
    assert not result.rejection_reasons


@pytest.mark.parametrize(
    ("metric", "value", "rule_id"),
    [
        ("number_of_trades", 19, "trades.minimum"),
        ("total_return", 0.0, "return.total_minimum"),
        ("annualized_return", 0.0, "return.annualized_minimum"),
        ("sharpe_ratio", 0.49, "risk.sharpe_minimum"),
        ("max_drawdown", -0.351, "risk.drawdown_maximum"),
    ],
)
def test_each_performance_rule_can_fail(
    metric: str, value: float | int, rule_id: str
) -> None:
    metrics = _metrics()
    metrics[metric] = value
    result = _screen(metrics)
    assert not result.passed
    assert rule_id in {
        rule.rule_id for rule in result.rule_results if not rule.passed
    }


def test_multiple_failures_are_retained_in_deterministic_order() -> None:
    metrics = _metrics()
    metrics.update(
        number_of_trades=1,
        total_return=-0.2,
        annualized_return=-0.1,
        sharpe_ratio=-1.0,
        max_drawdown=-0.8,
    )
    first = _screen(metrics)
    second = _screen(dict(reversed(tuple(metrics.items()))))
    assert first == second
    assert first.failed_rule_count == 5
    assert first.rejection_reasons == second.rejection_reasons


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_required_metrics_fail(bad_value: float) -> None:
    metrics = _metrics()
    metrics["sharpe_ratio"] = bad_value
    result = _screen(metrics)
    assert not result.passed
    assert "metrics.finite" in {
        rule.rule_id for rule in result.rule_results if not rule.passed
    }


def test_missing_metric_fails_availability() -> None:
    metrics = _metrics()
    del metrics["annualized_return"]
    result = _screen(metrics)
    assert not result.passed
    availability = next(
        rule for rule in result.rule_results if rule.rule_id == "metrics.available"
    )
    assert availability.details["missing"] == ("annualized_return",)


def test_screening_does_not_mutate_metrics_and_identity_is_stable() -> None:
    metrics = _metrics()
    original = dict(metrics)
    _screen(metrics)
    assert metrics == original
    identity_a = parameter_row_identity(
        "experiment",
        "strategy",
        {"window": 7, "entry": 25, "exit": 60},
    )
    identity_b = parameter_row_identity(
        "experiment",
        "strategy",
        {"exit": 60, "window": 7, "entry": 25},
    )
    assert identity_a == identity_b


@pytest.mark.licensed_vectorbt
def test_experiment_preserves_passing_and_screened_rows() -> None:
    config = _experiment_config(TRADING, ONE_TRADE)
    data = _data()
    result = execute_experiment(config, data, _audit(data), write_output=False)
    assert len(result.ranked_results) == 2
    assert len(result.passing_results) == 1
    assert len(result.screened_out_results) == 1
    assert result.ranked_results["screening_status"].tolist() == [
        "passed",
        "screened_out",
    ]
    assert result.ranked_results["number_of_trades"].tolist() == [3, 1]
    assert "trades" in result.screened_out_results.loc[0, "screening_rejection_reasons"]
    assert len(result.screening_results) == 2


@pytest.mark.licensed_vectorbt
def test_invalid_parameters_remain_distinct_from_screening_failures() -> None:
    config = _experiment_config(TRADING, TRADING | {"window": 0})
    data = _data()
    result = execute_experiment(config, data, _audit(data), write_output=False)
    assert result.rejected_combinations == 1
    assert len(result.screening_results) == 1
    assert result.screening_results[0].passed


@pytest.mark.licensed_vectorbt
def test_screening_occurs_after_simulation_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pass-through recorders around the real engine, metrics and screen calls."""
    events: list[str] = []
    real_construct = experiment_runner._construct_portfolio
    real_metrics = chunking.extract_sweep_metrics
    real_screen = experiment_runner.screen_metrics

    def recording_construct(data, aligned, config):
        events.append("simulate")
        return real_construct(data, aligned, config)

    def recording_metrics(portfolio, count, **kwargs):
        events.append("metrics")
        return real_metrics(portfolio, count, **kwargs)

    def recording_screen(**kwargs):
        events.append("screen")
        return real_screen(**kwargs)

    monkeypatch.setattr(experiment_runner, "_construct_portfolio", recording_construct)
    monkeypatch.setattr(chunking, "extract_sweep_metrics", recording_metrics)
    monkeypatch.setattr(experiment_runner, "screen_metrics", recording_screen)
    data = _data()
    result = execute_experiment(_experiment_config(TRADING), data, _audit(data), write_output=False)
    assert events == ["simulate", "metrics", "screen"]
    assert result.ranked_results.loc[0, "number_of_trades"] == 3


@pytest.mark.licensed_vectorbt
def test_complete_output_contains_screening_columns() -> None:
    data = _data()
    result = execute_experiment(_experiment_config(TRADING), data, _audit(data), write_output=False)
    assert {
        "parameter_row_id",
        "screening_status",
        "screening_passed_rule_count",
        "screening_failed_rule_count",
        "screening_rejection_reasons",
    }.issubset(result.ranked_results.columns)
