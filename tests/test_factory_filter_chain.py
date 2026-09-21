"""Bounded, synthetic mechanics proof for the factory filter chain.

This file deliberately uses the real stage runners and evidence services with
deterministic evaluator seams. It does not load market data or execute a
candidate strategy; the fixture proves routing, evaluation, persistence, and
fail-closed mechanics only, not screening profitability.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
from backtesting.robustness import evaluation as robustness_evaluation
from backtesting.screening import parameter_row_identity
from backtesting.screening.models import ScreeningResult, ScreeningRuleResult
from backtesting.validation import WalkForwardWindowRules
from backtesting.validation.lockbox_gate import evaluate_lockbox_prerequisites
from backtesting.walk_forward import WalkForwardConfig, execute_walk_forward
from market_data import DataAudit, MarketDataConfig
from persistence.evidence_service import ValidationEvidenceArtifactService
from strategies import get_strategy
from strategies.models import SignalResult
from tests.test_lockbox_gate import _service
from tests.test_review_context_artifacts import _source_lock_artifact, _target_run


FIXTURE_ID = "factory-filter-chain-fixture-v1"
STRATEGY_ID = "rsi_mean_reversion"
STRATEGY_VERSION = "1.0.0"
LOCKED_PARAMETERS = {
    "window": 14,
    "entry_threshold": 25,
    "exit_threshold": 55,
}


def _data(rows: int = 50) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    close = pd.Series(100.0 + np.arange(rows, dtype=float), index=index)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": 1_000,
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
        parameter_combinations=(LOCKED_PARAMETERS,),
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
    )


def _evaluator(calls: list[dict[str, object]], *, fail_stages: set[str] = ()):
    """Synthetic screening evaluator seam; this proves mechanics, not edge evidence."""

    def evaluate(config, data, audit, *, write_output):
        assert write_output is False
        stage = config.experiment_id.rsplit(":", 1)[-1]
        calls.append(
            {
                "experiment_id": config.experiment_id,
                "stage": stage,
                "start": str(data.index[0].date()),
                "end": str(data.index[-1].date()),
                "parameters": tuple(dict(item) for item in config.parameter_combinations),
            }
        )
        passed = stage not in fail_stages
        rows: list[dict[str, object]] = []
        screenings: list[ScreeningResult] = []
        for parameters in config.parameter_combinations:
            normalized = dict(parameters)
            row_id = parameter_row_identity(
                config.experiment_id,
                config.strategy_id,
                normalized,
            )
            rows.append(
                {
                    "parameter_row_id": row_id,
                    "screening_status": "passed" if passed else "screened_out",
                    "total_return": 0.02,
                    "annualized_return": 0.04,
                    "sharpe_ratio": 1.0,
                    "max_drawdown": -0.05,
                    "number_of_trades": 25,
                    "win_rate": 0.60,
                    **normalized,
                }
            )
            rule = ScreeningRuleResult(
                rule_id="fixture_survivor",
                metric="number_of_trades",
                observed_value=25,
                threshold=1,
                status="passed" if passed else "failed",
                message=(
                    "synthetic survivor admitted"
                    if passed
                    else "synthetic survivor rejected for stop test"
                ),
            )
            screenings.append(
                ScreeningResult(
                    parameter_row_id=row_id,
                    passed=passed,
                    rule_results=(rule,),
                    passed_rule_count=1 if passed else 0,
                    failed_rule_count=0 if passed else 1,
                    strategy_id=config.strategy_id,
                    strategy_version=STRATEGY_VERSION,
                    normalized_parameters=normalized,
                    execution_assumptions={"fixture": FIXTURE_ID},
                    rejection_reasons=()
                    if passed
                    else ("synthetic survivor rejected for stop test",),
                )
            )
        ranked = pd.DataFrame(rows)
        passing = ranked.loc[ranked["screening_status"] == "passed"].reset_index(
            drop=True
        )
        screened_out = ranked.loc[
            ranked["screening_status"] == "screened_out"
        ].reset_index(drop=True)
        return SimpleNamespace(
            ranked_results=ranked,
            passing_results=passing,
            screened_out_results=screened_out,
            experiment_id=config.experiment_id,
            strategy_id=config.strategy_id,
            strategy_name="Synthetic RSI fixture",
            strategy_version=STRATEGY_VERSION,
            normalized_parameters=tuple(dict(item) for item in config.parameter_combinations),
            market_data_audit=audit,
            execution_assumptions={"fixture": FIXTURE_ID},
            screening_results=tuple(screenings),
        )

    return evaluate


def _walk_forward_rules() -> WalkForwardWindowRules:
    return WalkForwardWindowRules(
        training_window_size=10,
        selection_window_size=5,
        test_window_size=5,
        step_size=5,
        training_mode="rolling",
        minimum_rows_per_window=2,
        incomplete_final_window="drop",
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
    monkeypatch: pytest.MonkeyPatch,
    experiment: ExperimentConfig,
    data: pd.DataFrame,
    audit: DataAudit,
    *,
    source_artifact_id: str,
):
    """Use the real robustness runner with deterministic, non-backtest seams."""

    def deterministic_execute(config, received_data, received_audit, *, write_output):
        del received_audit
        assert write_output is False
        rows = []
        screenings = []
        for parameters in config.parameter_combinations:
            normalized = dict(parameters)
            row_id = parameter_row_identity(
                config.experiment_id,
                config.strategy_id,
                normalized,
            )
            rows.append(
                {
                    "parameter_row_id": row_id,
                    "total_return": 0.10 if normalized == LOCKED_PARAMETERS else 0.09,
                    "max_drawdown": -0.10,
                    "sharpe_ratio": 1.0,
                    "number_of_trades": 25,
                }
            )
            screenings.append(
                ScreeningResult(
                    parameter_row_id=row_id,
                    passed=True,
                    rule_results=(),
                    passed_rule_count=0,
                    failed_rule_count=0,
                    strategy_id=config.strategy_id,
                    strategy_version=STRATEGY_VERSION,
                    normalized_parameters=normalized,
                    execution_assumptions={"fixture": FIXTURE_ID},
                    rejection_reasons=(),
                )
            )
        return SimpleNamespace(
            ranked_results=pd.DataFrame(rows),
            screening_results=tuple(screenings),
        )

    strategy = get_strategy(STRATEGY_ID)

    def deterministic_signals(received_data, parameters):
        false = pd.Series(False, index=received_data.index)
        return SignalResult(
            entries=false,
            exits=false.copy(),
            parameters=dict(parameters),
        )

    def deterministic_portfolio(received_data, signals, config):
        del signals, config
        return SimpleNamespace(
            returns=pd.Series(0.01, index=received_data.index, name="strategy_return")
        )

    monkeypatch.setattr(robustness_evaluation, "execute_experiment", deterministic_execute)
    monkeypatch.setattr(robustness_evaluation, "build_portfolio", deterministic_portfolio)
    monkeypatch.setattr(strategy, "generate_signals", deterministic_signals)

    neighborhood = NeighborhoodConfig(
        definitions=(
            ParameterNeighborhoodDefinition(
                "window", "explicit_values", explicit_values=(7, 14, 21)
            ),
            ParameterNeighborhoodDefinition(
                "entry_threshold", "explicit_values", explicit_values=(20, 25, 30)
            ),
            ParameterNeighborhoodDefinition(
                "exit_threshold", "explicit_values", explicit_values=(50, 55, 60)
            ),
        ),
        minimum_valid_neighbors=3,
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
        source_start="2020-01-01",
        source_end="2020-02-19",
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
    result = run_robustness_pipeline(
        config,
        construction,
        experiment,
        data,
        audit,
    )
    assert result.parameter_points
    assert result.regime_results
    return result


def test_synthetic_survivor_advances_through_real_filter_mechanics_and_persists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove Steps 5–9 routing/evaluation mechanics without edge evidence."""
    data = _data()
    audit = _audit(data)
    experiment = _experiment(tmp_path)
    calls: list[dict[str, object]] = []

    oos = execute_out_of_sample(
        OutOfSampleConfig(
            experiment=experiment,
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
        audit,
        evaluator=_evaluator(calls),
        write_output=False,
    )
    assert oos.selected_parameters == LOCKED_PARAMETERS
    assert oos.parameter_lock.normalized_parameters == tuple(sorted(LOCKED_PARAMETERS.items()))
    assert [item["stage"] for item in calls[:3]] == ["train", "selection", "test"]

    rules = _walk_forward_rules()
    walk_forward = execute_walk_forward(
        WalkForwardConfig(
            experiment=experiment,
            training_window_size=10,
            selection_window_size=5,
            test_window_size=5,
            step_size=5,
            training_mode="rolling",
            minimum_rows_per_window=2,
            shortlist_size=1,
            incomplete_final_window="drop",
            output_path=tmp_path / "walk_forward.json",
        ),
        data,
        audit,
        evaluator=_evaluator(calls),
        write_output=False,
    )
    assert walk_forward.successful_fold_count == walk_forward.total_fold_count
    assert all(fold.selected_parameters == LOCKED_PARAMETERS for fold in walk_forward.folds)
    assert all(fold.parameter_lock is not None for fold in walk_forward.folds)
    assert tuple(walk_forward.out_of_sample_returns) == (0.02,) * walk_forward.total_fold_count

    robustness = _robustness_result(
        monkeypatch,
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
            source_start="2020-01-01",
            source_end="2020-02-19",
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


def test_filter_chain_stops_before_downstream_stage_when_unseen_data_has_no_survivor(
    tmp_path: Path,
) -> None:
    data = _data()
    calls: list[dict[str, object]] = []
    experiment = _experiment(tmp_path)
    with pytest.raises(
        OutOfSampleProgressionError,
        match="selection screening produced no passing candidates; parameters were not locked",
    ):
        execute_out_of_sample(
            OutOfSampleConfig(
                experiment=experiment,
                split=ChronologicalSplitConfig(minimum_rows_per_partition=10),
                output_path=tmp_path / "oos-stop.json",
                shortlist_size=1,
            ),
            data,
            _audit(data),
            evaluator=_evaluator(calls, fail_stages={"selection"}),
            write_output=False,
        )
    assert [call["stage"] for call in calls] == ["train", "selection"]
    assert all(call["stage"] != "test" for call in calls)


def test_walk_forward_records_failed_fold_without_evaluating_its_test_window(
    tmp_path: Path,
) -> None:
    data = _data()
    calls: list[dict[str, object]] = []
    result = execute_walk_forward(
        WalkForwardConfig(
            experiment=_experiment(tmp_path),
            training_window_size=10,
            selection_window_size=5,
            test_window_size=5,
            step_size=5,
            training_mode="rolling",
            minimum_rows_per_window=2,
            shortlist_size=1,
            incomplete_final_window="drop",
            output_path=tmp_path / "walk-forward-stop.json",
        ),
        data,
        _audit(data),
        evaluator=_evaluator(calls, fail_stages={"train"}),
        write_output=False,
    )
    first_fold_calls = [
        call for call in calls if str(call["experiment_id"]).endswith("fold_001:train")
    ]
    assert first_fold_calls
    assert result.folds[0].status == "failed"
    assert result.folds[0].test_result is None
    assert "training screening" in (result.folds[0].failure_reason or "")
