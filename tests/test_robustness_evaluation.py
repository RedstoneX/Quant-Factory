from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments import execute_experiment
from backtesting.robustness import (
    CandidateDerivation,
    EvaluatedParameterPoint,
    NeighborhoodConfig,
    NeighborhoodConstructionResult,
    ParameterNeighborhoodDefinition,
    RegimeConfig,
    RobustnessConfig,
    build_neighborhood,
    combine_statuses,
    evaluate_neighborhood,
    summarize_neighborhood,
    build_robustness_result,
    read_robustness_report,
    write_robustness_report,
)
from backtesting.robustness.models import RegimeEvaluationResult, RegimeLabelMetadata
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from market_data.models import DataAudit
from strategies import get_strategy


LOCKED = {"window": 14, "entry_threshold": 25, "exit_threshold": 55}


def robustness_config(**kwargs) -> RobustnessConfig:
    values = dict(
        strategy_id="rsi_mean_reversion",
        strategy_version="1.0.0",
        locked_parameters=LOCKED,
        experiment_id="experiment",
        source_artifact_id="artifact",
        source_start="2020-01-01",
        source_end="2020-04-09",
        data_provenance={"provider": "fixture"},
        execution_assumptions={
            "execution_mode": "next_bar_open",
            "fees": 0.0005,
            "slippage": 0.0002,
            "initial_cash": 10_000,
            "direction": "longonly",
            "leverage": 1.0,
            "accumulate": False,
        },
        neighborhood=NeighborhoodConfig(
            definitions=(
                ParameterNeighborhoodDefinition(
                    "window", "explicit_values", explicit_values=(7, 14, 21)
                ),
            ),
            minimum_valid_neighbors=3,
            required_pass_proportion=0.6,
            maximum_absolute_degradation=0.05,
            maximum_relative_degradation=0.5,
        ),
        regimes=RegimeConfig(trend_window=3, volatility_window=3, minimum_observations=2),
    )
    values.update(kwargs)
    return RobustnessConfig(**values)


def derivation(window: int) -> tuple[CandidateDerivation, ...]:
    return (
        CandidateDerivation(
            parameter_name="window",
            locked_value=14,
            method="explicit_values",
            source_value=window,
            raw_value=window,
            normalized_value=window,
            status="accepted",
        ),
    )


def point(window: int, total_return: float, status="passed", drawdown=-0.1, sharpe=1.0):
    parameters = {"window": window, "entry_threshold": 25, "exit_threshold": 55}
    absolute = 0.10 - total_return
    relative = absolute / 0.10
    return EvaluatedParameterPoint(
        normalized_parameters=parameters,
        derivations=derivation(window),
        is_locked_point=window == 14,
        status=status,
        total_return=total_return,
        maximum_drawdown=drawdown,
        sharpe_ratio=sharpe,
        trade_count=25,
        screening_status="passed" if status == "passed" else "screened_out",
        hygiene_status="passed",
        absolute_degradation=absolute,
        relative_degradation=relative,
        degradation_unit="decimal return difference",
        degradation_interpretation="positive is worse",
        threshold_results=(),
        reasons=() if status == "passed" else ("fixture failure",),
        warnings=(),
        source_run_identity="run",
    )


def construction(count=3) -> NeighborhoodConstructionResult:
    return NeighborhoodConstructionResult(count, count, count, count, 0, 0, (), ())


def test_stable_plateau_summary_passes_and_is_complete():
    points = (point(7, 0.08), point(14, 0.10), point(21, 0.09))
    summary = summarize_neighborhood(robustness_config(), construction(), points)
    assert summary.status == "passed"
    assert summary.passing_proportion == 1.0
    assert summary.proportion_within_degradation_limit == 1.0
    assert summary.median_total_return == pytest.approx(0.09)
    assert summary.worst_total_return == pytest.approx(0.08)
    assert summary.locked_point_rank == 1
    assert summary.dimension_stability[0].tested_values == (7, 14, 21)


def test_brittle_optimum_and_locked_failure_fail_component():
    brittle = (point(7, -0.5, "failed"), point(14, 0.10), point(21, -0.4, "failed"))
    assert summarize_neighborhood(robustness_config(), construction(), brittle).status == "failed"
    locked_failed = (point(7, 0.08), point(14, 0.10, "failed"), point(21, 0.09))
    summary = summarize_neighborhood(robustness_config(), construction(), locked_failed)
    assert summary.status == "failed"
    assert summary.locked_point_status == "failed"


def test_insufficient_neighbors_and_status_precedence():
    summary = summarize_neighborhood(
        robustness_config(),
        construction(1),
        (point(14, 0.10),),
    )
    assert summary.status == "insufficient_evidence"
    assert combine_statuses(("failed", "insufficient_evidence")) == "failed"


def data_and_audit():
    index = pd.date_range("2020-01-01", periods=100, freq="D", tz="UTC")
    # Flat, then 15 straight down days (RSI falls through 25 for every window), then 15
    # straight up days (RSI rises through 55), repeated: each window trades, at its own timing.
    daily_returns = np.tile(np.concatenate([np.zeros(5), np.full(15, -0.01), np.full(15, 0.01)]), 3)[:100]
    close = pd.Series(100 * np.cumprod(1 + daily_returns), index=index)
    data = pd.DataFrame(
        {"Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Volume": 1000},
        index=index,
    )
    audit = DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="fixture",
        provider_implementation="fixture",
        interval="1 day",
        requested_start="2020-01-01",
        requested_dynamic_end_policy="fixture",
        latest_completed_exchange_session="2020-04-09",
        prices_adjusted=True,
        adjustment_verification="fixture",
        download_time="2020-04-10",
        download_timezone="UTC",
        actual_first_row_date="2020-01-01",
        actual_last_row_date="2020-04-09",
        row_count=100,
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
    )
    return data, audit


@pytest.mark.licensed_vectorbt
def test_pipeline_adapter_evaluates_only_valid_candidates_with_same_assumptions():
    config = robustness_config()
    neighborhood = build_neighborhood(
        get_strategy(config.strategy_id), LOCKED, config.neighborhood
    )
    data, audit = data_and_audit()
    result = evaluate_neighborhood(
        config, neighborhood, EXPERIMENT_CONFIG, data, audit
    )
    assert len(result.points) == neighborhood.accepted_count == 3
    assert [item.normalized_parameters for item in result.points] == [
        candidate.normalized_parameters for candidate in neighborhood.candidates
    ]
    locked = [item for item in result.points if item.is_locked_point]
    assert len(locked) == 1 and locked[0].normalized_parameters == LOCKED
    assert all(item.trade_count > 0 for item in result.points)
    assert {item.total_return for item in result.points} != {locked[0].total_return}
    for item in result.points:
        assert item.absolute_degradation == pytest.approx(locked[0].total_return - item.total_return)
    # The same locked execution assumptions are applied to every neighbour.
    expected = execute_experiment(
        replace(EXPERIMENT_CONFIG, parameter_combinations=(dict(LOCKED),)),
        data, audit, write_output=False,
    )
    assert locked[0].total_return == pytest.approx(float(expected.ranked_results.iloc[0]["total_return"]))


@pytest.mark.licensed_vectorbt
def test_zero_locked_return_marks_relative_degradation_unavailable():
    config = replace(robustness_config(), neighborhood=replace(robustness_config().neighborhood, degradation_mode="absolute"))
    neighborhood = build_neighborhood(get_strategy(config.strategy_id), LOCKED, config.neighborhood)
    data, audit = data_and_audit()
    # A flat price never crosses an RSI threshold, so every point returns exactly zero.
    for column in ("Open", "High", "Low", "Close"):
        data[column] = 100.0
    result = evaluate_neighborhood(config, neighborhood, EXPERIMENT_CONFIG, data, audit)
    assert all(item.total_return == 0.0 for item in result.points)
    assert all(item.relative_degradation is None for item in result.points)
    assert all(item.warnings for item in result.points)


def regime_result(status: str) -> RegimeEvaluationResult:
    return RegimeEvaluationResult(
        regime_id="bullish|low_volatility",
        trend_component="bullish",
        volatility_component="low_volatility",
        first_timestamp="2020-01-01T00:00:00+00:00",
        last_timestamp="2020-02-01T00:00:00+00:00",
        observation_count=20,
        trade_count=None,
        total_return=0.1 if status == "passed" else -0.2 if status == "failed" else None,
        maximum_drawdown=-0.1 if status != "insufficient_evidence" else None,
        sharpe_ratio=1.0 if status == "passed" else None,
        win_rate=0.6 if status != "insufficient_evidence" else None,
        minimum_observations=20,
        minimum_trades=None,
        threshold_results=(),
        status=status,
        reasons=() if status == "passed" else ("fixture regime reason",),
        warnings=(),
    )


def metadata() -> RegimeLabelMetadata:
    return RegimeLabelMetadata(
        first_usable_timestamp="2020-01-01T00:00:00+00:00",
        warmup_observation_count=3,
        trend_rule="trailing fixture",
        volatility_rule="trailing fixture",
        annualization_factor=252.0,
        attribution_policy="start of period",
    )


def test_combined_failure_precedes_insufficient_regime():
    points = (point(7, -0.5, "failed"), point(14, 0.1), point(21, -0.5, "failed"))
    summary = summarize_neighborhood(robustness_config(), construction(), points)
    result = build_robustness_result(
        robustness_config(),
        construction(),
        points,
        summary,
        metadata(),
        (regime_result("insufficient_evidence"),),
    )
    assert result.status == "failed"


def test_combined_insufficient_and_complete_pass():
    points = (point(7, 0.08), point(14, 0.10), point(21, 0.09))
    summary = summarize_neighborhood(robustness_config(), construction(), points)
    insufficient = build_robustness_result(
        robustness_config(), construction(), points, summary, metadata(), ()
    )
    assert insufficient.status == "insufficient_evidence"
    passed = build_robustness_result(
        robustness_config(),
        construction(),
        points,
        summary,
        metadata(),
        (regime_result("passed"),),
    )
    assert passed.status == "passed"
    assert passed.locked_parameters == LOCKED


def test_successful_combined_result_strict_report_round_trip(tmp_path):
    points = (point(7, 0.08), point(14, 0.10), point(21, 0.09))
    summary = summarize_neighborhood(robustness_config(), construction(), points)
    result = build_robustness_result(
        robustness_config(),
        construction(),
        points,
        summary,
        metadata(),
        (regime_result("passed"),),
    )
    path = tmp_path / "successful-robustness.json"
    write_robustness_report(path, result.to_dict())
    payload = read_robustness_report(path)
    assert payload["status"] == "passed"
    assert "NaN" not in path.read_text()
