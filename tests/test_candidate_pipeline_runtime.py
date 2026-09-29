"""Decisive deterministic proof for the generic candidate runtime path."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pandas as pd
import pytest

import backtesting.experiments.runner as experiment_runner
import orchestration.candidate_pipeline_runtime as candidate_runtime_module
import strategies.rsi_mean_reversion as rsi_strategy
from backtesting.experiments import ExecutionConfig, ExperimentConfig
from backtesting.monte_carlo import MonteCarloConfig
from backtesting.out_of_sample import ChronologicalSplitConfig
from backtesting.robustness import (
    NeighborhoodConfig,
    ParameterNeighborhoodDefinition,
    RegimeConfig,
)
from backtesting.screening import ScreeningConfig
from backtesting.validation import WalkForwardWindowRules
from market_data import DataAudit, MarketDataConfig
from market_data.cache import write_cache
from orchestration import (
    CandidatePipelineDefinition,
    CandidatePipelineReplayIncompleteError,
    CandidatePipelineRuntime,
    CandidateValidationPlan,
    ResearchLaunchInvocationError,
)
from persistence import (
    PersistenceService,
    ResearchSubmissionState,
    RunStage,
    RunStatus,
    StrategyLifecycle,
)
from strategies.rsi_mean_reversion import RSI_MEAN_REVERSION_SPEC


class _FakeTrades:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count

    @property
    def win_rate(self) -> float:
        return 0.60


class _FakePortfolioResult:
    def __init__(self, index: pd.Index, trade_count: int) -> None:
        self.total_return = 0.05
        self.annualized_return = 0.10
        self.sharpe_ratio = 1.0
        self.max_drawdown = -0.02
        self.trades = _FakeTrades(max(1, trade_count))
        self.returns = pd.Series(0.001, index=index, dtype=float)


class _FakePortfolio:
    @staticmethod
    def from_signals(*, close, entries, exits, short_entries=None, **_kwargs):
        trade_count = int(entries.sum())
        if short_entries is not None:
            trade_count += int(short_entries.sum())
        _ = exits
        return _FakePortfolioResult(close.index, trade_count)


class _FakeRSIResult:
    def __init__(self, index: pd.Index) -> None:
        self._index = index

    def rsi_crossed_below(self, _threshold: int) -> pd.Series:
        values = pd.Series(False, index=self._index, dtype=bool)
        values.iloc[2::8] = True
        return values

    def rsi_crossed_above(self, _threshold: int) -> pd.Series:
        values = pd.Series(False, index=self._index, dtype=bool)
        values.iloc[5::8] = True
        return values


class _FakeRSI:
    @staticmethod
    def run(close: pd.Series, *, window: int) -> _FakeRSIResult:
        _ = window
        return _FakeRSIResult(close.index)


FAKE_VECTORBT = SimpleNamespace(Portfolio=_FakePortfolio, RSI=_FakeRSI)


def _cached_market_data(tmp_path: Path) -> MarketDataConfig:
    config = MarketDataConfig(
        symbol="SYNTHETIC",
        provider="Yahoo Finance",
        provider_implementation="vectorbtpro.YFData.pull",
        interval="1 day",
        requested_start="2020-01-02",
        end_date_policy="fixed deterministic backend fixture",
        adjusted=True,
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        cache_path=tmp_path / "market" / "synthetic.csv",
    )
    import pandas_market_calendars as mcal

    sessions = mcal.get_calendar("NYSE").schedule(
        start_date=config.requested_start,
        end_date="2020-06-30",
    ).index
    index = sessions.tz_localize(config.market_timezone)
    close = pd.Series(
        100.0 + np.sin(np.arange(len(index)) * np.pi / 4.0) * 4.0,
        index=index,
    )
    frame = pd.DataFrame(
        {
            "Open": close - 0.25,
            "High": close + 0.50,
            "Low": close - 0.50,
            "Close": close,
            "Volume": 1_000,
        },
        index=index,
    )
    audit = DataAudit(
        cache_schema_version=2,
        symbol=config.symbol,
        provider=config.provider,
        provider_implementation=config.provider_implementation,
        interval=config.interval,
        requested_start=config.requested_start,
        requested_dynamic_end_policy=config.end_date_policy,
        latest_completed_exchange_session="2020-06-30",
        prices_adjusted=True,
        adjustment_verification="deterministic infrastructure fixture",
        download_time="2020-06-30T18:00:00-04:00",
        download_timezone=config.market_timezone,
        actual_first_row_date=str(index[0].date()),
        actual_last_row_date=str(index[-1].date()),
        row_count=len(frame),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
        cache_path=str(config.cache_path),
        cache_action="created",
        cache_decision_reason="deterministic backend fixture",
    )
    write_cache(frame, audit, config)
    return config


def _definition(tmp_path: Path, *, robustness_minimum_return: float = -1.0):
    experiment = ExperimentConfig(
        experiment_id="backend-completion-deterministic-fixture",
        strategy_id=RSI_MEAN_REVERSION_SPEC.identity.strategy_id,
        parameter_combinations=(
            {"window": 14, "entry_threshold": 25, "exit_threshold": 55},
        ),
        market_data=_cached_market_data(tmp_path),
        execution=ExecutionConfig.next_bar_open(
            initial_cash=10_000.0,
            fees=0.0,
            slippage=0.0,
            direction="longonly",
            leverage=1.0,
            accumulate=False,
            position_sizing="fixed_units",
            order_size=1.0,
        ),
        ranking_columns=("total_return",),
        ranking_ascending=(False,),
        output_path=tmp_path / "unused.csv",
        screening=ScreeningConfig(
            minimum_trades=1,
            minimum_total_return=-1.0,
            minimum_annualized_return=-1.0,
            minimum_sharpe_ratio=-1.0,
            maximum_drawdown=1.0,
        ),
    )
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
        required_pass_proportion=0.0,
        maximum_absolute_degradation=1.0,
        maximum_relative_degradation=1.0,
    )
    validation = CandidateValidationPlan(
        out_of_sample_split=ChronologicalSplitConfig(
            train_fraction=0.60,
            selection_fraction=0.20,
            test_fraction=0.20,
            minimum_rows_per_partition=10,
        ),
        out_of_sample_shortlist_size=1,
        walk_forward_rules=WalkForwardWindowRules(
            training_window_size=30,
            selection_window_size=10,
            test_window_size=10,
            step_size=10,
            training_mode="rolling",
            minimum_rows_per_window=5,
            incomplete_final_window="drop",
        ),
        walk_forward_shortlist_size=1,
        robustness_neighborhood=neighborhood,
        robustness_regimes=RegimeConfig(
            trend_window=2,
            volatility_window=2,
            minimum_observations=1,
        ),
        robustness_maximum_drawdown=1.0,
        robustness_minimum_return=robustness_minimum_return,
        robustness_minimum_sharpe=None,
        monte_carlo=MonteCarloConfig(
            simulation_count=20,
            minimum_observations=3,
            percentiles=(5, 50, 95),
            maximum_loss_probability=1.0,
            maximum_drawdown_breach_probability=1.0,
            minimum_lower_percentile_return=-1.0,
        ),
        data_as_of="2020-06-30T18:00:00-04:00",
    )
    return CandidatePipelineDefinition(
        experiment=experiment,
        strategy_version=RSI_MEAN_REVERSION_SPEC.identity.version,
        validation=validation,
    )


def _runtime(
    tmp_path: Path,
    *,
    robustness_minimum_return: float = -1.0,
) -> CandidatePipelineRuntime:
    database = tmp_path / "state" / "factory.sqlite3"
    definition = _definition(
        tmp_path,
        robustness_minimum_return=robustness_minimum_return,
    )
    persistence = PersistenceService(database)
    try:
        spec = RSI_MEAN_REVERSION_SPEC
        persistence.register_strategy(
            strategy_id=spec.identity.strategy_id,
            strategy_version=spec.identity.version,
            display_name=spec.identity.name,
            description="Deterministic non-profitability backend fixture",
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        configuration = persistence.upsert_configuration(
            definition.configuration_document()
        )
    finally:
        persistence.close()
    return CandidatePipelineRuntime(
        database=database,
        artifact_root=tmp_path / "artifacts",
        configuration_id=configuration.configuration_id,
        definition=definition,
        dispatcher_instance_id="aa5f06ca-2909-4b59-9c15-cb7f3a6421e7",
    )


def test_real_runtime_path_reaches_protected_ready_and_replays_without_work(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """One decisive proof: real runners, persistence, coordinator, and gate."""
    monkeypatch.setattr(experiment_runner, "require_vectorbtpro", lambda: FAKE_VECTORBT)
    monkeypatch.setattr(rsi_strategy, "require_vectorbtpro", lambda: FAKE_VECTORBT)
    runtime = _runtime(tmp_path)
    key = "backend_completion_decisive_fixture"

    first = runtime.launch(idempotency_key=key)
    assert first.chain.status == "ready_for_protected_test", first.chain
    assert first.chain.stopped_at is None
    assert first.chain.protected_test_gate.status == "passed"
    assert first.chain.protected_test_gate.protected_data_state == "gated"
    assert first.chain.protected_test_gate.eligible_to_execute_lockbox is True
    assert first.chain.protected_test_gate.eligible_to_progress is False
    second = runtime.launch(idempotency_key=key)
    assert second.chain == first.chain
    assert first.launch.dispatch.invoked is True
    assert second.launch.dispatch.invoked is False
    assert first.launch.dispatch.submission.state == ResearchSubmissionState.ACKNOWLEDGED
    UUID(first.launch.dispatch.submission.prefect_flow_run_id or "")

    persistence = PersistenceService(runtime.database)
    try:
        runs = persistence.runs.list()
        assert len(runs) == 5
        assert {run.stage for run in runs} == {
            RunStage.SCREENING,
            RunStage.OOS,
            RunStage.WALK_FORWARD,
            RunStage.ROBUSTNESS,
            RunStage.MONTE_CARLO,
        }
        assert all(run.status == RunStatus.SUCCEEDED for run in runs)
        assert all(persistence.read_persisted_run_manifest(run.run_id) for run in runs)
        assert len(persistence.list_run_artifacts(first.chain.completed[0].run_id)) == 1
        assert all(
            persistence.list_run_artifacts(handoff.run_id)
            for handoff in first.chain.completed[1:]
        )
    finally:
        persistence.close()


def test_persisted_robustness_failure_stops_before_monte_carlo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(experiment_runner, "require_vectorbtpro", lambda: FAKE_VECTORBT)
    monkeypatch.setattr(rsi_strategy, "require_vectorbtpro", lambda: FAKE_VECTORBT)
    runtime = _runtime(tmp_path, robustness_minimum_return=2.0)

    result = runtime.launch(idempotency_key="backend_completion_stop_fixture")
    replay = runtime.launch(idempotency_key="backend_completion_stop_fixture")

    assert result.chain.status == "stopped"
    assert replay.chain == result.chain
    assert replay.launch.dispatch.invoked is False
    assert result.chain.stopped_at == "robustness"
    assert tuple(item.stage for item in result.chain.completed) == (
        RunStage.OOS,
        RunStage.WALK_FORWARD,
        RunStage.ROBUSTNESS,
    )
    persistence = PersistenceService(runtime.database)
    try:
        assert all(run.stage != RunStage.MONTE_CARLO for run in persistence.runs.list())
        robustness = result.chain.completed[-1]
        assert robustness.status == "failed"
        assert persistence.runs.get(robustness.run_id).status == RunStatus.SUCCEEDED
        assert persistence.read_persisted_run_manifest(robustness.run_id) is not None
    finally:
        persistence.close()


def test_post_ack_screening_failure_is_terminal_and_never_reinvoked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = _runtime(tmp_path)
    calls = 0

    def fail_screening(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("controlled screening failure")

    monkeypatch.setattr(candidate_runtime_module, "execute_experiment", fail_screening)
    key = "backend_completion_fail_closed"

    with pytest.raises(ResearchLaunchInvocationError):
        runtime.launch(idempotency_key=key)
    with pytest.raises(CandidatePipelineReplayIncompleteError):
        runtime.launch(idempotency_key=key)

    assert calls == 1
    persistence = PersistenceService(runtime.database)
    try:
        runs = persistence.runs.list()
        assert len(runs) == 1
        assert runs[0].stage == RunStage.SCREENING
        assert runs[0].status == RunStatus.FAILED
        assert runs[0].error_summary == "controlled screening failure"
        submission = persistence.connection.execute(
            "SELECT state FROM research_run_submissions WHERE run_id=?",
            (runs[0].run_id,),
        ).fetchone()
        assert submission["state"] == ResearchSubmissionState.ACKNOWLEDGED.value
    finally:
        persistence.close()


def test_post_ack_stage_failure_is_terminal_and_never_reinvoked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(experiment_runner, "require_vectorbtpro", lambda: FAKE_VECTORBT)
    monkeypatch.setattr(rsi_strategy, "require_vectorbtpro", lambda: FAKE_VECTORBT)
    runtime = _runtime(tmp_path)
    calls = 0

    def fail_walk_forward(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("controlled walk-forward failure")

    monkeypatch.setattr(
        candidate_runtime_module,
        "execute_walk_forward",
        fail_walk_forward,
    )
    key = "backend_completion_stage_fail_closed"

    with pytest.raises(ResearchLaunchInvocationError):
        runtime.launch(idempotency_key=key)
    with pytest.raises(
        CandidatePipelineReplayIncompleteError,
        match="persisted walk_forward stage is failed",
    ):
        runtime.launch(idempotency_key=key)

    assert calls == 1
    persistence = PersistenceService(runtime.database)
    try:
        runs = persistence.runs.list()
        assert {run.stage for run in runs} == {
            RunStage.SCREENING,
            RunStage.OOS,
            RunStage.WALK_FORWARD,
        }
        walk_forward = next(run for run in runs if run.stage == RunStage.WALK_FORWARD)
        assert walk_forward.status == RunStatus.FAILED
    finally:
        persistence.close()
