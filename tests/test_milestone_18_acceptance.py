"""Integrated acceptance coverage for Milestone 18 run orchestration."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from orchestration import FixtureRunService, RunServiceError
from orchestration.research_launch_claims import (
    ResearchLaunchError,
    ResearchLaunchInvocationError,
)
from orchestration.run_service import FixtureRetryPolicy
from persistence import (
    EventSeverity,
    PersistenceService,
    RunEventType,
    RunStage,
    RunStatus,
    StrategyLifecycle,
)
from persistence.models import normalized_configuration_document
from persistence.service import RunCompletionRejectedError
from prefect_spike.fixture_flow import (
    ControlledFixtureCancellation,
    PrefectFixtureResult,
    PrefectRunReference,
    _persist_fixture_result,
    _validated_claim_boundary,
    acknowledge_fixture_cancellation,
    deterministic_fixture_body,
    reconcile_quant_factory_run_status,
)
from tests.test_run_service import _configuration
from tests.test_run_stale_recovery import FRESH, OLD, STALE_BEFORE, _create_run


def _saved_launcher(captured: dict[str, object]):
    def launch(**kwargs):
        captured["parameters"] = kwargs["saved_parameters"]
        captured["execution"] = kwargs["saved_execution_assumptions"]
        kwargs.pop("attempt_marker_path", None)
        return deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
            prefect_api_url="http://127.0.0.1:4200/api",
        )

    return launch


def _retry_launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def _blocking_launcher(
    *,
    prefect_flow_run_id: str,
    started: threading.Event,
    release: threading.Event,
    finished: threading.Event,
    after_release,
):
    def launch(**kwargs):
        _validated_claim_boundary(
            database_path=kwargs["database_path"],
            idempotency_key=kwargs["idempotency_key"],
            configuration_id=kwargs["configuration_id"],
            quant_factory_run_id=kwargs["quant_factory_run_id"],
            canonical_request_json=kwargs["canonical_request_json"],
            request_fingerprint=kwargs["request_fingerprint"],
            operation_kind=kwargs["operation_kind"],
            source_run_id=kwargs["source_run_id"],
            source_lineage=kwargs["source_lineage"],
            prefect_reference=PrefectRunReference(flow_run_id=prefect_flow_run_id),
        )
        persistence = PersistenceService(kwargs["database_path"])
        try:
            run = persistence.increment_run_attempt(kwargs["quant_factory_run_id"])
            started.set()
            assert release.wait(timeout=5)
            after_release(persistence, kwargs, run.attempt_count)
            return PrefectFixtureResult(
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_flow_run_id=prefect_flow_run_id,
                configuration_id=kwargs["configuration_id"],
                deterministic_value=1729,
                attempt_count=run.attempt_count,
            )
        finally:
            persistence.close()
            finished.set()

    return launch


def _attempt_late_completion(persistence, kwargs, attempt_count: int, prefect_flow_run_id: str) -> None:
    _persist_fixture_result(
        persistence,
        quant_factory_run_id=kwargs["quant_factory_run_id"],
        configuration_id=kwargs["configuration_id"],
        prefect_flow_run_id=prefect_flow_run_id,
        deterministic_value=1729,
        attempt_count=attempt_count,
    )
    reconcile_quant_factory_run_status(
        persistence,
        quant_factory_run_id=kwargs["quant_factory_run_id"],
        prefect_state="Completed",
    )


def test_saved_launch_failure_replay_and_restart_acceptance(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    captured: dict[str, object] = {}
    service = FixtureRunService(database=database, fixture_launcher=_saved_launcher(captured))
    persistence = PersistenceService(database)
    try:
        configuration = persistence.configurations.get(configuration_id)
        assert configuration is not None
        canonical = configuration.canonical_config_json
        document = json.loads(canonical)
    finally:
        persistence.close()

    successful = service.launch_fixture(configuration_id=configuration_id, run_id="qf-accept-success")
    assert successful.run.status == RunStatus.SUCCEEDED.value
    assert successful.run.configuration_id == configuration_id
    assert successful.run.strategy_id == document["strategy_id"]
    assert successful.run.strategy_version == document["strategy_version"]
    assert successful.run.prefect_flow_run_id == "prefect-qf-accept-success"
    assert successful.run.prefect_flow_run_id != successful.run.run_id
    assert captured == {"parameters": document["parameters"], "execution": document["execution"]}
    assert [event.event_type for event in service.events_for_run("qf-accept-success")] == [
        "run_created",
        "run_started",
        "run_succeeded",
    ]

    with pytest.raises(ResearchLaunchInvocationError):
        service.launch_fixture(
            configuration_id=configuration_id,
            run_id="qf-accept-failure",
            fail_after_run_start=True,
        )
    failed = service.get_run("qf-accept-failure")
    assert failed is not None and failed.status == RunStatus.FAILED.value
    assert failed.error_summary == "controlled Prefect fixture failure"
    assert failed.attempt_count == 1
    assert [event.event_type for event in service.events_for_run("qf-accept-failure")].count(
        "run_failed"
    ) == 1

    retry_service = FixtureRunService(database=database, fixture_launcher=_retry_launcher)
    with pytest.raises(ValueError, match="outer fixture-launch retries are disabled"):
        retry_service.launch_fixture(
            configuration_id=configuration_id,
            run_id="qf-accept-retry",
            retry_policy=FixtureRetryPolicy(max_attempts=2),
            controlled_transient_failures=1,
        )
    assert retry_service.get_run("qf-accept-retry") is None

    del service
    restarted = FixtureRunService(database=database)
    persisted_success = restarted.get_run("qf-accept-success")
    assert persisted_success == successful.run
    replay = restarted.launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-accept-success",
    )
    assert replay.invoked is False
    persistence = PersistenceService(database)
    try:
        assert persistence.results.list_parameter_results("qf-accept-success")
        unchanged = persistence.configurations.get(configuration_id)
        assert unchanged is not None
        assert unchanged.canonical_config_json == canonical
    finally:
        persistence.close()


def test_timeout_and_cancellation_acceptance_prevent_late_completion(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)

    timeout_started = threading.Event()
    timeout_release = threading.Event()
    timeout_finished = threading.Event()

    def timeout_after_release(persistence, kwargs, attempt_count):
        _attempt_late_completion(persistence, kwargs, attempt_count, "prefect-accept-timeout")

    timeout_service = FixtureRunService(
        database=database,
        fixture_launcher=_blocking_launcher(
            prefect_flow_run_id="prefect-accept-timeout",
            started=timeout_started,
            release=timeout_release,
            finished=timeout_finished,
            after_release=timeout_after_release,
        ),
    )
    try:
        with pytest.raises(ResearchLaunchInvocationError):
            timeout_service.launch_fixture(
                configuration_id=configuration_id,
                run_id="qf-accept-timeout",
                timeout_seconds=0.01,
            )
    finally:
        timeout_release.set()
    assert timeout_started.is_set()
    assert timeout_finished.wait(timeout=5)
    timeout = timeout_service.get_run("qf-accept-timeout")
    assert timeout is not None and timeout.status == RunStatus.SUCCEEDED.value
    assert timeout.error_summary is None
    assert [event.event_type for event in timeout_service.events_for_run("qf-accept-timeout")] == [
        "run_created",
        "run_started",
        "run_succeeded",
    ]

    cancel_started = threading.Event()
    cancel_release = threading.Event()
    cancel_finished = threading.Event()

    def cancel_after_release(persistence, kwargs, attempt_count):
        try:
            acknowledge_fixture_cancellation(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
            )
        except ControlledFixtureCancellation:
            with pytest.raises(RunCompletionRejectedError, match="cannot accept completion"):
                _attempt_late_completion(
                    persistence,
                    kwargs,
                    attempt_count,
                    "prefect-accept-cancel",
                )

    cancel_service = FixtureRunService(
        database=database,
        fixture_launcher=_blocking_launcher(
            prefect_flow_run_id="prefect-accept-cancel",
            started=cancel_started,
            release=cancel_release,
            finished=cancel_finished,
            after_release=cancel_after_release,
        ),
    )
    errors: list[BaseException] = []

    def launch_cancellable() -> None:
        try:
            cancel_service.launch_fixture(configuration_id=configuration_id, run_id="qf-accept-cancel")
        except BaseException as exc:  # assertion follows below
            errors.append(exc)

    worker = threading.Thread(target=launch_cancellable)
    worker.start()
    assert cancel_started.wait(timeout=5)
    cancel_service.request_fixture_cancellation("qf-accept-cancel")
    cancel_service.request_fixture_cancellation("qf-accept-cancel")
    cancel_release.set()
    assert cancel_finished.wait(timeout=5)
    worker.join(timeout=5)
    assert errors == []
    cancelled = cancel_service.get_run("qf-accept-cancel")
    assert cancelled is not None and cancelled.status == RunStatus.CANCELLED.value
    assert [event.event_type for event in cancel_service.events_for_run("qf-accept-cancel")] == [
        "run_created",
        "run_started",
        "run_cancellation_requested",
        "run_cancelled",
    ]

    persistence = PersistenceService(database)
    try:
        assert persistence.results.list_parameter_results("qf-accept-timeout")
        assert persistence.results.list_parameter_results("qf-accept-cancel") == ()
        for run_id in ("qf-accept-timeout", "qf-accept-cancel"):
            assert persistence.results.list_artifacts(run_id) == ()
    finally:
        persistence.close()


def test_stale_recovery_invalid_launch_and_cross_scenario_integrity(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    _create_run(database, configuration_id, run_id="qf-accept-stale-created", status=RunStatus.CREATED, old=True)
    _create_run(database, configuration_id, run_id="qf-accept-stale-running", status=RunStatus.RUNNING, old=True)
    _create_run(database, configuration_id, run_id="qf-accept-fresh", status=RunStatus.RUNNING, old=False)
    persistence = PersistenceService(database)
    try:
        persistence.connection.execute(
            "UPDATE experiment_runs SET created_at=?, started_at=? WHERE run_id='qf-accept-fresh'",
            (FRESH, FRESH),
        )
        persistence.connection.commit()
    finally:
        persistence.close()
    service = FixtureRunService(database=database, fixture_launcher=_saved_launcher({}))

    with pytest.raises(RunServiceError, match="age-only fixture recovery is disabled"):
        service.recover_stale_fixture_runs(stale_before=STALE_BEFORE)
    assert service.get_run("qf-accept-stale-created").status == RunStatus.CREATED.value
    assert service.get_run("qf-accept-stale-running").status == RunStatus.RUNNING.value
    assert service.get_run("qf-accept-fresh").status == RunStatus.RUNNING.value

    with pytest.raises(KeyError, match="unknown Quant Factory configuration"):
        service.launch_fixture(configuration_id="missing", run_id="qf-accept-missing")
    assert service.get_run("qf-accept-missing") is None

    persistence = PersistenceService(database)
    try:
        persistence.register_strategy(
            strategy_id="candidate_strategy",
            strategy_version="1.0.0",
            display_name="Candidate",
            description="not launchable",
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        rejected = persistence.upsert_configuration(
            normalized_configuration_document(
                experiment_id="rejected",
                strategy_id="candidate_strategy",
                strategy_version="1.0.0",
                market_data={"kind": "none"},
                parameters={"fixture": True},
                execution={"kind": "fixture"},
                ranking={"columns": (), "ascending": ()},
                screening={"kind": "none"},
            )
        )
    finally:
        persistence.close()
    with pytest.raises(ResearchLaunchError, match="not an approved"):
        service.launch_fixture(configuration_id=rejected.configuration_id, run_id="qf-accept-rejected")
    assert service.get_run("qf-accept-rejected") is None

    initial = service.launch_fixture(configuration_id=configuration_id, run_id="qf-accept-duplicate")
    duplicate = service.launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-accept-duplicate",
    )
    assert duplicate.invoked is False
    assert service.get_run("qf-accept-duplicate") == initial.run
