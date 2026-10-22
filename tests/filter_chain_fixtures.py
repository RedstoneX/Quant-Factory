"""Neutral deterministic evidence fixtures for filter-chain tests."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from backtesting.monte_carlo import MonteCarloConfig, SourceSeries, run_monte_carlo
from backtesting.out_of_sample.models import DataPartition, ParameterLock
from backtesting.robustness.models import RobustnessResult
from backtesting.validation import WalkForwardWindowRules
from backtesting.walk_forward.models import (
    WalkForwardFoldResult,
    WalkForwardResult,
    WalkForwardWindow,
)


FIXTURE_LABEL = "connected_filter_chain"
SOURCE_LOCK_ARTIFACT_ID = f"{FIXTURE_LABEL}_source_lock"


def walk_forward_rules() -> WalkForwardWindowRules:
    return WalkForwardWindowRules(
        training_window_size=10,
        selection_window_size=5,
        test_window_size=5,
        step_size=5,
        training_mode="rolling",
        minimum_rows_per_window=2,
        incomplete_final_window="drop",
    )


def _partition(name: str, start: int, rows: int) -> DataPartition:
    index = pd.date_range("2020-01-01", periods=start + rows, freq="D", tz="UTC")[start:]
    return DataPartition(
        name=name,
        data=pd.DataFrame({"Close": range(rows)}, index=index),
        start=str(index[0].date()),
        end=str(index[-1].date()),
        row_count=rows,
    )


def walk_forward_result(
    *,
    experiment_id: str,
    strategy_id: str,
    strategy_version: str,
    parameters: dict[str, Any],
) -> WalkForwardResult:
    fold_id = f"{FIXTURE_LABEL}_fold_001"
    return WalkForwardResult(
        folds=(
            WalkForwardFoldResult(
                fold_id=fold_id,
                status="successful",
                window=WalkForwardWindow(
                    fold_id=fold_id,
                    train=_partition(f"{fold_id}:train", 0, 10),
                    selection=_partition(f"{fold_id}:selection", 10, 5),
                    test=_partition(f"{fold_id}:test", 15, 5),
                ),
                training_result=None,
                selection_result=None,
                test_result=None,
                shortlist_parameters=(),
                parameter_lock=ParameterLock(
                    lock_id=f"{FIXTURE_LABEL}_parameter_lock",
                    experiment_id=experiment_id,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    normalized_parameters=tuple(sorted(parameters.items())),
                    selection_parameter_row_id=f"{FIXTURE_LABEL}_selected_row",
                    selection_start="2020-01-11",
                    selection_end="2020-01-15",
                    ranking_columns=("score",),
                    ranking_ascending=(False,),
                ),
                selected_parameters=parameters,
                test_metrics={"total_return": 0.01},
                failure_reason=None,
            ),
        ),
        total_fold_count=1,
        successful_fold_count=1,
        failed_fold_count=0,
        selected_parameters_by_fold=(),
        unique_parameter_set_count=0,
        parameter_frequencies=(),
        parameter_change_percentage=0.0,
        maximum_consecutive_persistence=0,
        failed_fold_ids=(),
        failure_reasons=(),
        fold_test_metrics=pd.DataFrame(),
        average_fold_metrics={},
        median_fold_metrics={},
        out_of_sample_returns=pd.Series(dtype=float),
        out_of_sample_equity=pd.Series(dtype=float),
        compounded_return=None,
        endpoint_max_drawdown=None,
        fold_return_sharpe=None,
        total_trades=0,
    )


def monte_carlo_result(
    *, experiment_id: str, strategy_id: str, strategy_version: str
):
    return run_monte_carlo(
        SourceSeries(
            source_id=SOURCE_LOCK_ARTIFACT_ID,
            source_kind="period_returns",
            experiment_id=experiment_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            values=(0.04, 0.03, 0.02, 0.01),
            provenance={"fixture": FIXTURE_LABEL},
            execution_assumptions={"fixture": FIXTURE_LABEL},
            period_frequency="daily",
        ),
        MonteCarloConfig(
            simulation_count=20,
            minimum_observations=3,
            maximum_loss_probability=1.0,
            maximum_drawdown_breach_probability=1.0,
            minimum_lower_percentile_return=-1.0,
        ),
    )


def robustness_result(
    *,
    experiment_id: str,
    strategy_id: str,
    strategy_version: str,
    parameters: dict[str, Any],
    target_source: Mapping[str, Any],
    provider: str,
    execution: dict[str, Any],
) -> RobustnessResult:
    return RobustnessResult(
        schema_version=1,
        status="passed",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        experiment_id=experiment_id,
        source_artifact_id=SOURCE_LOCK_ARTIFACT_ID,
        locked_parameters=parameters,
        data_provenance={
            "dataset_identity": target_source["data_identity"],
            "provider": provider,
        },
        execution_assumptions=execution,
        neighborhood_construction=None,
        parameter_points=(),
        neighborhood_summary=None,
        regime_metadata=None,
        regime_results=(),
        component_statuses={"parameter_neighborhood": "passed", "regimes": "passed"},
        reasons=(),
        warnings=("Deterministic connected-filter infrastructure fixture.",),
        timestamp="2026-07-18T00:00:00+00:00",
    )
