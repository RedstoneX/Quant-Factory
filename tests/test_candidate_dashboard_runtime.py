"""Deterministic dashboard coverage for the approved candidate runtime seam."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import time
from typing import Any

import pandas as pd
import pytest
from dash import html

import dashboard.application as dashboard_application
import orchestration
from dashboard.app import create_app
from dashboard.run_adapter import ConfigurationReadinessView, SavedConfigurationView
from dashboard.run_detail_adapter import _fields
from orchestration import (
    CANDIDATE_SCREENING_LAUNCH_CONTRACT,
    CandidateRunService,
    DurableResearchLaunchService,
    FixtureRunService,
    ResearchLaunchRequest,
    FilterChainOutcome,
    VALIDATION_RUNTIME_KEY,
    new_dispatcher_instance_id,
)
from persistence import (
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    ResearchLaunchOperation,
    ResearchSubmissionState,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.models import normalized_configuration_document
from persistence.service import (
    RUNTIME_LINEAGE_ENVIRONMENT_KEY,
    capture_runtime_lineage_document,
)
from strategies.rsi_mean_reversion import RSI_MEAN_REVERSION_SPEC
from tests.test_candidate_pipeline_runtime import _definition


STRATEGY_ID = "candidate_dashboard_fixture"
STRATEGY_VERSION = "1.0.0"
EXECUTION = {"mode": "deterministic-test", "fees": 0.0, "slippage": 0.0}


def _component_text(component: object) -> str:
    if component is None:
        return ""
    if isinstance(component, (str, int, float)):
        return str(component)
    if isinstance(component, (list, tuple)):
        return " ".join(_component_text(child) for child in component)
    return _component_text(getattr(component, "children", None))


def test_candidate_parameter_grid_renders_as_bounded_variant_summary() -> None:
    fields = _fields([{"window": value, "direction": "long"} for value in range(12)])

    rendered = {field.label: field.value for field in fields}
    assert rendered == {
        "Parameter Combinations": "12",
        "Direction": "long",
        "Window": "0, 1, 2, 3, 4, 5, 6, 7, +4 more",
    }


def _callback(app, output_fragment: str) -> Callable[..., Any]:
    entry = next(
        value for key, value in app.callback_map.items() if output_fragment in key
    )
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def prepare_candidate_database(database: Path) -> str:
    """Persist one active candidate contract without executable strategy work."""

    persistence = PersistenceService(database)
    try:
        persistence.register_strategy(
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            display_name="Candidate Dashboard Fixture",
            description="Deterministic dashboard routing fixture",
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        document = normalized_configuration_document(
            experiment_id="candidate_dashboard_runtime",
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            market_data={
                "provider": "deterministic-test",
                "symbol": "TEST",
                "interval": "1 minute",
            },
            parameters={"window": 10},
            execution=EXECUTION,
            ranking={"columns": ["total_return"], "ascending": [False]},
            screening={"minimum_trades": 1},
        )
        document[VALIDATION_RUNTIME_KEY] = {"test_runtime": "injected"}
        return persistence.upsert_configuration(document).configuration_id
    finally:
        persistence.close()


def prepare_strict_candidate_database(database: Path, workspace: Path) -> str:
    """Persist the exact typed candidate contract and compatible local cache."""

    definition = _definition(workspace)
    persistence = PersistenceService(database)
    try:
        spec = RSI_MEAN_REVERSION_SPEC
        persistence.register_strategy(
            strategy_id=spec.identity.strategy_id,
            strategy_version=spec.identity.version,
            display_name=spec.identity.name,
            description="Deterministic default-dashboard runtime fixture",
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        return persistence.upsert_configuration(
            definition.configuration_document()
        ).configuration_id
    finally:
        persistence.close()


def candidate_readiness(configuration: SavedConfigurationView) -> ConfigurationReadinessView:
    return ConfigurationReadinessView(
        configuration_id=configuration.configuration_id,
        experiment_id=configuration.experiment_id,
        strategy_name=configuration.strategy_name,
        strategy_identity=f"{configuration.strategy_id}@{configuration.strategy_version}",
        lifecycle=configuration.lifecycle,
        config_hash=configuration.config_hash,
        provider="deterministic-test",
        dataset="Synthetic dashboard fixture",
        instrument="TEST",
        timeframe="1 minute",
        requested_coverage="Deterministic fixture",
        actual_coverage="Deterministic fixture",
        local_availability="Available",
        local_validation="Injected deterministic evidence",
        parameters=(),
        execution_assumptions=(),
        blockers=(),
        state="ready",
    )


def readiness_by_id(
    configurations: tuple[SavedConfigurationView, ...],
    _catalog_snapshot: object,
) -> dict[str, ConfigurationReadinessView]:
    return {
        configuration.configuration_id: candidate_readiness(configuration)
        for configuration in configurations
    }


def _provenance(run_id: str) -> DataProvenanceRecord:
    return DataProvenanceRecord(
        run_id=run_id,
        provider="deterministic-test",
        provider_implementation="injected-dashboard-launcher",
        symbol="TEST",
        interval="1 minute",
        timezone="UTC",
        requested_coverage="2026-01-01T14:30:00Z..2026-01-01T14:31:00Z",
        actual_coverage="2026-01-01T14:30:00Z..2026-01-01T14:31:00Z",
        adjusted=False,
        row_count=2,
        cache_action="fixture",
        validation_summary_json=canonical_json(
            {
                "duplicate_timestamp_count": 0,
                "missing_open_count": 0,
                "missing_high_count": 0,
                "missing_low_count": 0,
                "missing_close_count": 0,
                "missing_volume_count": 0,
                "expected_session_gap_count": 0,
                "unexpected_session_gaps": [],
            }
        ),
        manifest_reference="tests/deterministic-candidate-dashboard",
        checksum="candidate-dashboard-dataset-checksum",
    )


def _market_provenance(run_id: str, audit: object) -> DataProvenanceRecord:
    """Describe the exact cache loaded by the default-runtime browser proof."""

    validation_summary = {
        "duplicate_timestamp_count": audit.duplicate_timestamp_count,
        "missing_open_count": audit.missing_open_count,
        "missing_high_count": audit.missing_high_count,
        "missing_low_count": audit.missing_low_count,
        "missing_close_count": audit.missing_close_count,
        "missing_volume_count": audit.missing_volume_count,
        "expected_session_gap_count": audit.expected_session_gap_count,
        "unexpected_session_gaps": audit.unexpected_session_gaps,
        "provider_warnings": audit.provider_warnings,
    }
    return DataProvenanceRecord(
        run_id=run_id,
        provider=audit.provider,
        provider_implementation=audit.provider_implementation,
        symbol=audit.symbol,
        interval=audit.interval,
        timezone=audit.download_timezone,
        requested_coverage=audit.requested_start,
        actual_coverage=(
            f"{audit.actual_first_row_date}..{audit.actual_last_row_date}"
        ),
        adjusted=audit.prices_adjusted,
        row_count=audit.row_count,
        cache_action=audit.cache_action,
        validation_summary_json=canonical_json(validation_summary),
        manifest_reference=None,
        checksum=None,
    )


def deterministic_candidate_launcher(
    *,
    database: str | Path,
    configuration_id: str,
    idempotency_key: str,
    operation: ResearchLaunchOperation,
    source_run_id: str | None,
    source_lineage: dict[str, str] | None,
    result_status: str | None = "passed",
) -> object:
    """Exercise the real candidate claim seam and persist synthetic evidence only."""

    database = Path(database)

    def acknowledge_and_finish(submission, claims):
        claims.bind_prefect_identity(
            idempotency_key=submission.idempotency_key,
            run_id=submission.run_id,
            configuration_id=submission.configuration_id,
            canonical_request_json=submission.canonical_request_json,
            request_fingerprint=submission.request_fingerprint,
            prefect_flow_run_id=f"deterministic-{submission.run_id}",
        )
        persistence = PersistenceService(database)
        try:
            with transaction(persistence.connection):
                persistence.results.set_data_provenance(_provenance(submission.run_id))
                persistence.results.set_execution_assumptions(
                    ExecutionAssumptionsRecord(
                        run_id=submission.run_id,
                        assumptions_json=canonical_json(EXECUTION),
                    )
                )
                if result_status is not None:
                    persistence.results.add_parameter_result(
                        run_id=submission.run_id,
                        row_id="deterministic-variant",
                        normalized_parameters={"window": 10},
                        metrics={
                            "total_return": 0.01 if result_status == "passed" else -0.01,
                            "number_of_trades": 2,
                        },
                        ranking_position=1,
                        screening_status=result_status,
                        rejection_reasons=(
                            "" if result_status == "passed" else "deterministic rejection"
                        ),
                    )
            persistence.persist_run_manifest(
                persistence.build_run_manifest(submission.run_id)
            )
            persistence.transition_run(submission.run_id, RunStatus.SUCCEEDED)
        finally:
            persistence.close()
        return submission.run_id

    service = CandidateRunService(
        database=database,
        screening_adapter=acknowledge_and_finish,
        dispatcher_instance_id=new_dispatcher_instance_id(),
    )
    return service.launch_screening(
        idempotency_key=idempotency_key,
        configuration_id=configuration_id,
        environment={
            RUNTIME_LINEAGE_ENVIRONMENT_KEY: capture_runtime_lineage_document()
        },
        operation=operation,
        source_run_id=source_run_id,
        source_lineage=source_lineage,
    )


def deterministic_default_runtime_adapter(
    runtime,
    submission,
    claims,
    *,
    delay_seconds: float = 0.0,
) -> FilterChainOutcome:
    """Replace only prohibited strategy computation behind the real runtime seam."""

    from market_data import load_market_data

    market = load_market_data(
        runtime.definition.experiment.market_data,
        now=pd.Timestamp(runtime.definition.validation.data_as_of),
        allow_download=False,
    )
    assert runtime.cache_only is True
    assert not market.data.empty
    claims.bind_prefect_identity(
        idempotency_key=submission.idempotency_key,
        run_id=submission.run_id,
        configuration_id=submission.configuration_id,
        canonical_request_json=submission.canonical_request_json,
        request_fingerprint=submission.request_fingerprint,
        prefect_flow_run_id=f"deterministic-{submission.run_id}",
    )
    if delay_seconds:
        time.sleep(delay_seconds)
    persistence = PersistenceService(runtime.database)
    try:
        execution = runtime.definition.configuration_document()["execution"]
        with transaction(persistence.connection):
            persistence.results.set_data_provenance(
                _market_provenance(submission.run_id, market.audit)
            )
            persistence.results.set_execution_assumptions(
                ExecutionAssumptionsRecord(
                    run_id=submission.run_id,
                    assumptions_json=canonical_json(execution),
                )
            )
            persistence.results.add_parameter_result(
                run_id=submission.run_id,
                row_id="deterministic-variant",
                normalized_parameters={"window": 14},
                metrics={"total_return": 0.0, "number_of_trades": 2},
                ranking_position=1,
                screening_status="passed",
            )
        persistence.persist_run_manifest(
            persistence.build_run_manifest(submission.run_id)
        )
        persistence.transition_run(submission.run_id, RunStatus.SUCCEEDED)
    finally:
        persistence.close()
    return FilterChainOutcome(
        status="ready_for_protected_test",
        screening_run_id=submission.run_id,
        completed=(),
        stopped_at=None,
        reasons=("Deterministic dashboard mechanics fixture; no edge evidence.",),
    )


def _app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    launcher: Callable[..., object] | None,
):
    database = tmp_path / "state" / "candidate-dashboard.sqlite3"
    configuration_id = prepare_candidate_database(database)
    monkeypatch.setattr(
        dashboard_application,
        "configuration_readiness_by_id",
        readiness_by_id,
    )
    monkeypatch.setattr("dashboard.candidate_launch_context.candidate_selection_blocker", lambda *_args, **_kwargs: None)
    app = create_app(
        review_database=database,
        run_service=FixtureRunService(database=database),
        approved_configuration_launcher=launcher,
    )
    return app, database, configuration_id

def _intent_run_id(database: Path, store: dict[str, Any]) -> str:
    submitted = store.get("submitted")
    assert isinstance(submitted, dict)
    service = DurableResearchLaunchService(
        database=database,
        launch_contract=CANDIDATE_SCREENING_LAUNCH_CONTRACT,
    )
    submission = service.get(str(submitted["idempotency_key"]))
    assert submission is not None
    return submission.run_id


def test_candidate_run_test_historical_relaunch_and_reproduction_route_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[ResearchLaunchOperation, str | None]] = []

    def launcher(**kwargs):
        calls.append((kwargs["operation"], kwargs["source_run_id"]))
        return deterministic_candidate_launcher(database=database, **kwargs)

    app, database, configuration_id = _app(
        tmp_path,
        monkeypatch,
        launcher=launcher,
    )
    launch = _callback(app, "launch-message.children")
    launch_store, launch_message, *_ = launch(
        1,
        configuration_id,
        None,
        "/research/run-test",
    )
    source_run_id = _intent_run_id(database, launch_store)
    assert "Succeeded" in _component_text(html.Div(launch_message))

    historical = _callback(app, "historical-launch-message.children")
    historical_store, historical_message, *_ = historical(
        1,
        source_run_id,
        None,
        "/research/backtest-results",
    )
    historical_run_id = _intent_run_id(database, historical_store)
    assert historical_run_id != source_run_id
    assert "Succeeded" in _component_text(html.Div(historical_message))

    reproduce = _callback(app, "reproduction-message.children")
    reproduction_store, reproduction_message, *_ = reproduce(
        1,
        source_run_id,
        None,
        "/research/backtest-results",
    )
    reproduction_run_id = _intent_run_id(database, reproduction_store)
    assert reproduction_run_id not in {source_run_id, historical_run_id}
    assert "Succeeded" in _component_text(html.Div(reproduction_message))
    assert calls == [
        (ResearchLaunchOperation.RUN_TEST, None),
        (ResearchLaunchOperation.HISTORICAL_RELAUNCH, source_run_id),
        (ResearchLaunchOperation.REPRODUCTION, source_run_id),
    ]


def test_default_create_app_bridge_builds_cache_only_candidate_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class DeterministicRuntime:
        def __init__(self, **kwargs):
            captured["construction"] = kwargs

        @classmethod
        def from_saved_configuration(cls, **kwargs):
            return cls(**kwargs)

        def launch(self, **kwargs):
            captured["launch"] = kwargs
            return deterministic_candidate_launcher(
                database=captured["construction"]["database"],
                configuration_id=captured["construction"]["configuration_id"],
                **kwargs,
            )

    monkeypatch.setattr(
        orchestration,
        "CandidatePipelineRuntime",
        DeterministicRuntime,
    )
    app, database, configuration_id = _app(
        tmp_path,
        monkeypatch,
        launcher=None,
    )
    launch = _callback(app, "launch-message.children")
    store, message, *_ = launch(
        1,
        configuration_id,
        None,
        "/research/run-test",
    )

    assert _intent_run_id(database, store)
    assert "Succeeded" in _component_text(html.Div(message))
    assert captured["construction"]["database"] == database
    assert captured["construction"]["configuration_id"] == configuration_id
    assert captured["construction"]["cache_only"] is True
    assert captured["launch"]["operation"] == ResearchLaunchOperation.RUN_TEST
    assert captured["launch"]["source_run_id"] is None


@pytest.mark.parametrize(
    ("result_status", "expected"),
    (
        ("screened_out", "terminal rejection"),
        (None, "no complete parameter evidence"),
    ),
)
def test_candidate_terminal_and_incomplete_sources_disable_followup_launches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result_status: str | None,
    expected: str,
) -> None:
    calls: list[ResearchLaunchOperation] = []

    def launcher(**kwargs):
        calls.append(kwargs["operation"])
        return deterministic_candidate_launcher(
            database=database,
            result_status=result_status,
            **kwargs,
        )

    app, database, configuration_id = _app(
        tmp_path,
        monkeypatch,
        launcher=launcher,
    )
    launch = _callback(app, "launch-message.children")
    launch_store, *_ = launch(1, configuration_id, None, "/research/run-test")
    source_run_id = _intent_run_id(database, launch_store)
    assert calls == [ResearchLaunchOperation.RUN_TEST]

    historical = _callback(app, "historical-launch-message.children")
    historical_result = historical(
        1,
        source_run_id,
        None,
        "/research/backtest-results",
    )
    assert historical_result[3] is True
    assert expected in _component_text(html.Div(historical_result[1]))

    reproduce = _callback(app, "reproduction-message.children")
    reproduction_result = reproduce(
        1,
        source_run_id,
        None,
        "/research/backtest-results",
    )
    assert reproduction_result[3] is True
    assert expected in _component_text(html.Div(reproduction_result[1]))
    assert calls == [ResearchLaunchOperation.RUN_TEST]


def test_screening_stage_reconciliation_uses_candidate_claim_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "state" / "candidate-dashboard.sqlite3"
    configuration_id = prepare_candidate_database(database)
    claims = DurableResearchLaunchService(
        database=database,
        launch_contract=CANDIDATE_SCREENING_LAUNCH_CONTRACT,
    )
    claim = claims.claim(
        idempotency_key="candidate_dashboard_unknown_claim",
        request=ResearchLaunchRequest(
            operation=ResearchLaunchOperation.RUN_TEST,
            configuration_id=configuration_id,
        ),
        environment={
            RUNTIME_LINEAGE_ENVIRONMENT_KEY: capture_runtime_lineage_document()
        },
    )
    dispatcher_id = new_dispatcher_instance_id()
    claims.begin_dispatch(
        idempotency_key=claim.submission.idempotency_key,
        dispatcher_instance_id=dispatcher_id,
    )
    claims.mark_invocation_unknown(
        idempotency_key=claim.submission.idempotency_key,
        dispatcher_instance_id=dispatcher_id,
    )

    monkeypatch.setattr(
        dashboard_application,
        "configuration_readiness_by_id",
        readiness_by_id,
    )
    app = create_app(
        review_database=database,
        run_service=FixtureRunService(database=database),
        approved_configuration_launcher=lambda **_kwargs: None,
    )
    reconcile = _callback(app, "claim-recovery-message.children")
    message, class_name = reconcile(
        1,
        0,
        claim.run.run_id,
        "candidate-dashboard-prefect-confirmed",
        None,
        None,
        "/research/backtest-results",
    )

    resolved = claims.get(claim.submission.idempotency_key)
    assert resolved is not None
    assert resolved.state == ResearchSubmissionState.ACKNOWLEDGED
    assert resolved.prefect_flow_run_id == "candidate-dashboard-prefect-confirmed"
    assert "Submission reconciled" in message
    assert class_name == "stale-recovery-message success-state"
