"""Factory filter chain (Steps 5-9) driven by the real experiment engine.

The price series is a 12-bar sawtooth (ten bars of -2, two bars of +11) so the
real RSI mean-reversion strategy enters once per cycle near the trough and exits
on the rebound.  Flattening a region removes every trade in it, which is how
screening failures are triggered with real inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments import ExecutionConfig, ExperimentConfig
from backtesting.monte_carlo import MonteCarloConfig, SourceSeries, run_monte_carlo
from backtesting.out_of_sample import (
    ChronologicalSplitConfig,
    OutOfSampleConfig,
    OutOfSampleProgressionError,
    execute_out_of_sample,
)
from backtesting.robustness import (
    NeighborhoodConfig,
    ParameterNeighborhoodDefinition,
    RegimeConfig,
    RobustnessConfig,
    build_neighborhood,
    run_robustness_pipeline,
)
from backtesting.screening import ScreeningConfig
from backtesting.validation import WalkForwardWindowRules
from backtesting.validation.lockbox_gate import evaluate_lockbox_prerequisites
from backtesting.walk_forward import WalkForwardConfig, execute_walk_forward
from market_data import DataAudit, MarketDataConfig
from backtesting.validation.evidence_service import ValidationEvidenceArtifactService
from strategies import get_strategy
from tests.test_lockbox_gate import _service
from tests.test_review_context_artifacts import _source_lock_artifact, _target_run

licensed = pytest.mark.licensed_vectorbt

FIXTURE_ID = "factory-filter-chain-fixture-v1"
STRATEGY_ID = "rsi_mean_reversion"
STRATEGY_VERSION = get_strategy(STRATEGY_ID).spec.identity.version
LOCKED_PARAMETERS = {"window": 7, "entry_threshold": 30, "exit_threshold": 50}
SLOW_EXIT = {"window": 7, "entry_threshold": 30, "exit_threshold": 60}
SCREENING = ScreeningConfig(
    minimum_trades=1,
    minimum_total_return=0.0,
    minimum_annualized_return=0.0,
    minimum_sharpe_ratio=None,
    maximum_drawdown=0.35,
)
# 120 rows split 60/20/20: train bars 0-72, selection 72-96, test 96-120.
SELECTION = (72, 96)
# Rolling walk-forward 24/12/12 stepping 36: fold 1 trains on bars 0-24.
FIRST_TRAINING = (0, 24)


def _data(rows: int = 120, flat: tuple[tuple[int, int], ...] = ()) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    steps = np.tile(np.array([-2.0] * 10 + [11.0] * 2), rows // 12 + 1)[:rows]
    close = pd.Series(100 + np.cumsum(steps), index=index)
    for start, end in flat:
        close.iloc[start:end] = close.iloc[start]
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": 1_000.0,
        },
        index=index,
    )


def _audit(data: pd.DataFrame) -> DataAudit:
    first = str(data.index[0].date())
    last = str(data.index[-1].date())
    return DataAudit(
        cache_schema_version=2,
        symbol="SYNTHETIC",
        provider="fixture",
        provider_implementation="factory-filter-chain-fixture",
        interval="1 day",
        requested_start=first,
        requested_dynamic_end_policy="fixed synthetic fixture",
        latest_completed_exchange_session=last,
        prices_adjusted=True,
        adjustment_verification="synthetic fixture",
        download_time="2026-01-01T00:00:00Z",
        download_timezone="UTC",
        actual_first_row_date=first,
        actual_last_row_date=last,
        row_count=len(data),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
        cache_path="synthetic-fixture",
        cache_action="synthetic-fixture",
        cache_decision_reason="mechanics proof only",
    )


def _experiment(tmp_path: Path) -> ExperimentConfig:
    market_data = MarketDataConfig(
        symbol="SYNTHETIC",
        provider="fixture",
        provider_implementation="factory-filter-chain-fixture",
        interval="1 day",
        requested_start="2020-01-01",
        end_date_policy="fixed synthetic fixture",
        adjusted=True,
        exchange_calendar="NYSE",
        market_timezone="UTC",
        cache_path=tmp_path / "synthetic.csv",
    )
    return ExperimentConfig(
        experiment_id=FIXTURE_ID,
        strategy_id=STRATEGY_ID,
        parameter_combinations=(LOCKED_PARAMETERS, SLOW_EXIT),
        market_data=market_data,
        execution=ExecutionConfig.next_bar_open(
            initial_cash=10_000,
            fees=0.0,
            slippage=0.0,
            direction="longonly",
            leverage=1.0,
            accumulate=False,
        ),
        ranking_columns=("total_return", "sharpe_ratio"),
        ranking_ascending=(False, False),
        output_path=tmp_path / "unused.csv",
        screening=SCREENING,
    )


def _out_of_sample(tmp_path: Path, data: pd.DataFrame, *, write_output: bool = False):
    return execute_out_of_sample(
        OutOfSampleConfig(
            experiment=_experiment(tmp_path),
            split=ChronologicalSplitConfig(
                train_fraction=0.60,
                selection_fraction=0.20,
                test_fraction=0.20,
                minimum_rows_per_partition=10,
            ),
            output_path=tmp_path / "oos.json",
            shortlist_size=1,
        ),
        data,
        _audit(data),
        write_output=write_output,
    )


def _walk_forward_rules() -> WalkForwardWindowRules:
    return WalkForwardWindowRules(
        training_window_size=24,
        selection_window_size=12,
        test_window_size=12,
        step_size=36,
        training_mode="rolling",
        minimum_rows_per_window=2,
        incomplete_final_window="drop",
    )


def _walk_forward(tmp_path: Path, data: pd.DataFrame):
    rules = _walk_forward_rules()
    return execute_walk_forward(
        WalkForwardConfig(
            experiment=_experiment(tmp_path),
            training_window_size=rules.training_window_size,
            selection_window_size=rules.selection_window_size,
            test_window_size=rules.test_window_size,
            step_size=rules.step_size,
            training_mode=rules.training_mode,
            minimum_rows_per_window=rules.minimum_rows_per_window,
            shortlist_size=1,
            incomplete_final_window=rules.incomplete_final_window,
            output_path=tmp_path / "walk_forward.json",
        ),
        data,
        _audit(data),
        write_output=False,
    )


def _execution_assumptions(experiment: ExperimentConfig) -> dict[str, object]:
    execution = experiment.execution
    return {
        "kind": "fixture",
        "execution_mode": execution.mode,
        "fees": execution.fees,
        "slippage": execution.slippage,
        "initial_cash": execution.initial_cash,
        "direction": execution.direction,
        "leverage": execution.leverage,
        "accumulate": execution.accumulate,
    }


def _robustness_result(
    experiment: ExperimentConfig,
    data: pd.DataFrame,
    audit: DataAudit,
    *,
    source_artifact_id: str,
):
    """Run the real robustness pipeline: every neighbour is a real backtest.

    Only the exit level is varied: RSI(14)/RSI(21) never reach 30 on the sawtooth
    and entry 25 catches a fraction of the troughs, so those neighbours are real
    degradations rather than a stable neighbourhood.
    """
    strategy = get_strategy(STRATEGY_ID)
    neighborhood = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "exit_threshold", "explicit_values", explicit_values=(50, 55, 60)
            ),
        ),
        minimum_valid_neighbors=2,
        required_pass_proportion=0.60,
        maximum_absolute_degradation=0.25,
        maximum_relative_degradation=0.50,
    )
    config = RobustnessConfig(
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        locked_parameters=LOCKED_PARAMETERS,
        experiment_id=FIXTURE_ID,
        source_artifact_id=source_artifact_id,
        source_start=audit.actual_first_row_date,
        source_end=audit.actual_last_row_date,
        data_provenance={"provider": "fixture"},
        execution_assumptions=_execution_assumptions(experiment),
        neighborhood=neighborhood,
        regimes=RegimeConfig(
            trend_window=3,
            volatility_window=3,
            minimum_observations=2,
        ),
        minimum_return=0.0,
        maximum_drawdown=0.35,
    )
    construction = build_neighborhood(strategy, LOCKED_PARAMETERS, neighborhood)
    result = run_robustness_pipeline(config, construction, experiment, data, audit)
    assert result.parameter_points
    assert result.regime_results
    return result


@licensed
def test_synthetic_survivor_advances_through_real_filter_mechanics_and_persists(
    tmp_path: Path,
) -> None:
    """Prove Steps 5-9 routing/evaluation mechanics without edge evidence."""
    data = _data()
    audit = _audit(data)
    experiment = _experiment(tmp_path)

    oos = _out_of_sample(tmp_path, data)
    assert oos.selected_parameters == LOCKED_PARAMETERS
    assert oos.parameter_lock.normalized_parameters == tuple(sorted(LOCKED_PARAMETERS.items()))
    stages = (oos.training_result, oos.selection_result, oos.test_result)
    assert [stage.experiment_id.rsplit(":", 1)[-1] for stage in stages] == [
        "train",
        "selection",
        "test",
    ]
    assert oos.test_result.ranked_results.iloc[0]["number_of_trades"] >= 1

    rules = _walk_forward_rules()
    walk_forward = _walk_forward(tmp_path, data)
    assert walk_forward.total_fold_count == 3
    assert walk_forward.successful_fold_count == walk_forward.total_fold_count
    assert all(fold.selected_parameters == LOCKED_PARAMETERS for fold in walk_forward.folds)
    assert all(fold.parameter_lock is not None for fold in walk_forward.folds)
    assert all(value > 0 for value in walk_forward.out_of_sample_returns)

    robustness = _robustness_result(
        experiment,
        data,
        audit,
        source_artifact_id=oos.parameter_lock.lock_id,
    )
    assert robustness.status == "passed"
    assert robustness.neighborhood_summary is not None
    assert robustness.neighborhood_summary.evaluated_count > 0
    assert robustness.regime_results

    monte_carlo = run_monte_carlo(
        SourceSeries(
            source_id=f"{FIXTURE_ID}:walk-forward-returns",
            source_kind="fold_endpoint_returns",
            experiment_id=FIXTURE_ID,
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            values=tuple(float(value) for value in walk_forward.out_of_sample_returns),
            provenance={"fixture": FIXTURE_ID},
            execution_assumptions={"kind": "fixture"},
            period_frequency="synthetic-fold",
        ),
        MonteCarloConfig(
            simulation_count=20,
            minimum_observations=3,
            percentiles=(5, 50, 95),
            maximum_loss_probability=1.0,
            maximum_drawdown_breach_probability=1.0,
            minimum_lower_percentile_return=-1.0,
        ),
    )
    assert monte_carlo.status == "passed"
    assert monte_carlo.observation_count == walk_forward.total_fold_count

    persistence = _service(
        tmp_path,
        experiment_id=FIXTURE_ID,
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        parameters=LOCKED_PARAMETERS,
    )
    artifact_root = tmp_path / "artifacts"
    try:
        evidence = ValidationEvidenceArtifactService(persistence)
        _target_run(persistence, run_id="oos-run")
        source_artifact_db_id = _source_lock_artifact(
            persistence,
            artifact_root,
            run_id="oos-run",
            artifact_id=oos.parameter_lock.lock_id,
            locked_parameters=LOCKED_PARAMETERS,
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            experiment_id=FIXTURE_ID,
            source_start=audit.actual_first_row_date,
            source_end=audit.actual_last_row_date,
            execution_assumptions=_execution_assumptions(experiment),
            parameter_lock_id=oos.parameter_lock.lock_id,
        )
        _, target_configuration, _ = evidence._review_context_target_state("oos-run")
        retrieved_source_lock = evidence._retrieve_validated_source_lock(
            source_lock_run_id="oos-run",
            source_lock_artifact_id=source_artifact_db_id,
            target_configuration=target_configuration,
            artifact_root=artifact_root,
        )
        assert retrieved_source_lock.status == "passed"
        assert retrieved_source_lock.artifact_id == oos.parameter_lock.lock_id
        assert retrieved_source_lock.parameter_lock_id == oos.parameter_lock.lock_id
        assert retrieved_source_lock.locked_parameters == LOCKED_PARAMETERS

        persisted_walk_forward = evidence.persist_walk_forward(
            run_id="wf-run",
            result=walk_forward,
            rules=rules,
            artifact_root=artifact_root,
        )
        persisted_monte_carlo = evidence.persist_monte_carlo(
            run_id="mc-run",
            result=monte_carlo,
            artifact_root=artifact_root,
        )
        persisted_robustness = evidence.persist_robustness(
            run_id="robust-run",
            result=robustness,
            artifact_root=artifact_root,
        )

        retrieved_walk_forward = evidence.retrieve_walk_forward(
            "wf-run", artifact_root=artifact_root
        )
        retrieved_monte_carlo = evidence.retrieve_monte_carlo(
            "mc-run", artifact_root=artifact_root
        )
        retrieved_robustness = evidence.retrieve_robustness(
            "robust-run", artifact_root=artifact_root
        )
        assert retrieved_walk_forward.evidence_identity == persisted_walk_forward.evidence_identity
        assert retrieved_monte_carlo.evidence_identity == persisted_monte_carlo.evidence_identity
        assert retrieved_robustness.evidence_identity == persisted_robustness.evidence_identity

        outcomes = {
            stage: evidence.stage_outcome(run_id, artifact_root=artifact_root)
            for stage, run_id in (
                ("walk_forward", "wf-run"),
                ("monte_carlo", "mc-run"),
                ("robustness", "robust-run"),
            )
        }
        assert outcomes["walk_forward"].status == "insufficient_evidence"
        assert outcomes["monte_carlo"].status == "passed"
        assert outcomes["robustness"].status == "passed"
        assert all(not outcome.eligible_to_progress for outcome in outcomes.values())

        gate = evaluate_lockbox_prerequisites(
            walk_forward=retrieved_walk_forward,
            monte_carlo=retrieved_monte_carlo,
            robustness=retrieved_robustness,
            source_lock=retrieved_source_lock,
            protected_data_state="unspent",
        )
        assert gate.status == "failed", gate.reasons
        assert gate.eligible_to_execute_lockbox is False
        assert gate.eligible_to_progress is False
    finally:
        persistence.close()


@licensed
def test_filter_chain_stops_before_downstream_stage_when_unseen_data_has_no_survivor(
    tmp_path: Path,
) -> None:
    # A flat selection slice has no trade, so the real screen rejects every candidate.
    with pytest.raises(
        OutOfSampleProgressionError,
        match="parameters were not locked",
    ):
        _out_of_sample(tmp_path, _data(flat=(SELECTION,)), write_output=True)
    report = json.loads((tmp_path / "oos.json").read_text())
    assert report["training_status"] == "passed"
    assert report["selection_status"] == "screened_out"
    assert report["test_status"] == "not_run"
    assert report["parameter_lock"] is None


@licensed
def test_walk_forward_records_failed_fold_without_evaluating_its_test_window(
    tmp_path: Path,
) -> None:
    # A flat first training slice has no trade, so fold 1 fails at training.
    result = _walk_forward(tmp_path, _data(flat=(FIRST_TRAINING,)))
    first = result.folds[0]
    assert first.status == "failed"
    assert first.training_result is not None
    assert first.selection_result is None
    assert first.test_result is None
    assert "selection was not evaluated" in (first.failure_reason or "")
    assert result.failed_fold_ids == ("fold_001",)
    assert result.successful_fold_count == result.total_fold_count - 1
