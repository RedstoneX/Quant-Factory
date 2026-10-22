"""Service/flow integration proofs for ADR 0011 durable research launches."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from orchestration import FixtureRunService
from orchestration.research_launch_claims import (
    DurableResearchLaunchService,
    ResearchLaunchInvocationError,
    ResearchLaunchInvocationUnknownError,
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
from persistence.models import normalized_configuration_document
from prefect_spike.fixture_flow import deterministic_fixture_body
import prefect_spike.fixture_flow as fixture_flow_module
import orchestration.run_service as run_service_module


def _configuration(database: Path) -> str:
    service = PersistenceService(database)
    try:
        service.register_strategy(
            strategy_id="durable_fixture",
            strategy_version="1.0.0",
            display_name="Durable fixture",
            description="ADR 0011 service fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        return service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="durable_fixture",
                strategy_id="durable_fixture",
                strategy_version="1.0.0",
                market_data={"kind": "none"},
                parameters={"fixture": True},
                execution={"kind": "deterministic"},
                ranking={"columns": ["deterministic_value"], "ascending": [False]},
                screening={"kind": "none"},
            )
        ).configuration_id
    finally:
        service.close()


def _acknowledging_launcher(calls: list[str]):
    def launch(**kwargs):
        calls.append(str(kwargs["quant_factory_run_id"]))
        kwargs.pop("attempt_marker_path")
        return deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id="prefect-durable-flow",
        )

    return launch


def test_same_key_replay_invokes_once_and_preserves_claim_identity(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)
    calls: list[str] = []

    def launcher(**kwargs):
        calls.append(kwargs["quant_factory_run_id"])
        kwargs.pop("attempt_marker_path")
        return deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        )

    service = FixtureRunService(
        database=database,
        fixture_launcher=launcher,
    )

    first = service.launch_fixture(
        idempotency_key="launch_service_replay_0001",
        configuration_id=configuration_id,
        run_id="durable-service-run",
    )
    replay = service.launch_fixture(
        idempotency_key="launch_service_replay_0001",
        configuration_id=configuration_id,
        run_id="a-different-id-must-not-be-used",
    )

    assert calls == ["durable-service-run"]
    assert first.invoked is True
    assert replay.invoked is False
    assert replay.run.run_id == first.run.run_id == "durable-service-run"
    assert replay.submission == first.submission
    assert first.submission.state == ResearchSubmissionState.ACKNOWLEDGED
    assert first.run.status == RunStatus.SUCCEEDED.value


def test_historical_launch_carries_canonical_operation_and_source_lineage(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)
    observed: list[tuple[str, str | None, dict[str, str]]] = []

    def launcher(**kwargs):
        kwargs.pop("attempt_marker_path")
        observed.append(
            (
                kwargs["operation_kind"],
                kwargs["source_run_id"],
                kwargs["source_lineage"],
            )
        )
        return deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        )

    service = FixtureRunService(database=database, fixture_launcher=launcher)
    source = service.launch_fixture(
        idempotency_key="launch_historical_source_001",
        configuration_id=configuration_id,
        run_id="historical-source",
    )
    historical = service.launch_fixture(
        idempotency_key="launch_historical_child_0001",
        configuration_id=configuration_id,
        operation=ResearchLaunchOperation.HISTORICAL_RELAUNCH,
        source_run_id=source.run.run_id,
        run_id="historical-child",
    )

    assert historical.run.status == RunStatus.SUCCEEDED.value
    assert observed[-1] == (
        ResearchLaunchOperation.HISTORICAL_RELAUNCH.value,
        "historical-source",
        {"parent_run_id": "historical-source"},
    )


def test_terminal_replay_does_not_recapture_runtime_or_revalidate_launchability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)
    service = FixtureRunService(
        database=database,
        fixture_launcher=_acknowledging_launcher([]),
    )
    first = service.launch_fixture(
        idempotency_key="launch_terminal_reopen_0001",
        configuration_id=configuration_id,
        run_id="durable-terminal-reopen",
    )
    persistence = PersistenceService(database)
    try:
        persistence.update_strategy_lifecycle(
            first.run.strategy_id,
            first.run.strategy_version,
            lifecycle=StrategyLifecycle.RETIRED,
            active=False,
        )
    finally:
        persistence.close()
    monkeypatch.setattr(
        run_service_module,
        "capture_runtime_lineage_document",
        lambda: pytest.fail("terminal replay recaptured current runtime"),
    )

    replay = service.launch_fixture(
        idempotency_key="launch_terminal_reopen_0001",
        configuration_id=configuration_id,
    )
    assert replay.invoked is False
    assert replay.run.run_id == first.run.run_id


def test_dispatcher_identity_rotates_after_fork_but_not_within_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_service_module, "_DISPATCHER_ID_PID", None)
    monkeypatch.setattr(run_service_module, "_DISPATCHER_ID", None)
    monkeypatch.setattr(run_service_module.os, "getpid", lambda: 101)
    first = run_service_module._boot_dispatcher_instance_id()
    assert run_service_module._boot_dispatcher_instance_id() == first
    monkeypatch.setattr(run_service_module.os, "getpid", lambda: 202)
    assert run_service_module._boot_dispatcher_instance_id() != first


def test_exception_after_acknowledgement_is_typed_and_claim_stays_acknowledged(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)

    def failing_after_ack(**kwargs):
        kwargs.pop("attempt_marker_path")
        kwargs["fail_after_run_start"] = True
        return deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id="prefect-acknowledged-failure",
        )

    with pytest.raises(ResearchLaunchInvocationError):
        FixtureRunService(
            database=database,
            fixture_launcher=failing_after_ack,
        ).launch_fixture(
            idempotency_key="launch_after_ack_failure_01",
            configuration_id=configuration_id,
            run_id="durable-ack-failure",
        )

    submission = DurableResearchLaunchService(database=database).get(
        "launch_after_ack_failure_01"
    )
    assert submission is not None
    assert submission.state == ResearchSubmissionState.ACKNOWLEDGED
    run = FixtureRunService(database=database).get_run(submission.run_id)
    assert run is not None and run.status == RunStatus.FAILED.value


def test_pre_ack_exception_becomes_unknown_and_replay_never_invokes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)
    calls = 0

    def fail_before_ack(**_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("controlled pre-ack loss")

    service = FixtureRunService(database=database, fixture_launcher=fail_before_ack)
    with pytest.raises(ResearchLaunchInvocationUnknownError):
        service.launch_fixture(
            idempotency_key="launch_pre_ack_unknown_001",
            configuration_id=configuration_id,
            run_id="durable-pre-ack-loss",
        )
    replay = service.launch_fixture(
        idempotency_key="launch_pre_ack_unknown_001",
        configuration_id=configuration_id,
        run_id="ignored-replay-id",
    )

    assert calls == 1
    assert replay.invoked is False
    assert replay.submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN
    assert replay.run.status == RunStatus.CREATED.value


def test_request_timeout_is_unknown_not_failed_and_does_not_reinvoke(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)
    release = threading.Event()
    calls = 0

    def blocking_before_ack(**_kwargs):
        nonlocal calls
        calls += 1
        assert release.wait(2)
        raise RuntimeError("request worker was released")

    service = FixtureRunService(database=database, fixture_launcher=blocking_before_ack)
    try:
        with pytest.raises(ResearchLaunchInvocationUnknownError):
            service.launch_fixture(
                idempotency_key="launch_timeout_unknown_0001",
                configuration_id=configuration_id,
                run_id="durable-timeout-loss",
                timeout_seconds=0.02,
            )
        replay = service.launch_fixture(
            idempotency_key="launch_timeout_unknown_0001",
            configuration_id=configuration_id,
        )
        assert replay.invoked is False
        assert replay.submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN
        assert replay.run.status == RunStatus.CREATED.value
        assert calls == 1
    finally:
        release.set()


def test_outer_launcher_retry_is_rejected_before_claim(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)
    from orchestration.run_service import FixtureRetryPolicy

    with pytest.raises(ValueError, match="outer fixture-launch retries are disabled"):
        FixtureRunService(database=database).launch_fixture(
            idempotency_key="launch_outer_retry_disabled",
            configuration_id=configuration_id,
            retry_policy=FixtureRetryPolicy(max_attempts=2),
        )
    assert DurableResearchLaunchService(database=database).get(
        "launch_outer_retry_disabled"
    ) is None


def test_flow_rejects_operation_source_tuple_mismatch_before_binding(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)
    claims = DurableResearchLaunchService(database=database)
    claim = claims.claim(
        idempotency_key="launch_tuple_mismatch_0001",
        request=run_service_module.ResearchLaunchRequest(
            operation=ResearchLaunchOperation.RUN_TEST,
            configuration_id=configuration_id,
        ),
    )
    claims.begin_dispatch(
        idempotency_key=claim.submission.idempotency_key,
        dispatcher_instance_id=run_service_module.new_dispatcher_instance_id(),
    )
    with pytest.raises(ValueError, match="tuple does not match"):
        deterministic_fixture_body(
            database_path=database,
            idempotency_key=claim.submission.idempotency_key,
            configuration_id=configuration_id,
            quant_factory_run_id=claim.run.run_id,
            canonical_request_json=claim.submission.canonical_request_json,
            request_fingerprint=claim.submission.request_fingerprint,
            operation_kind=ResearchLaunchOperation.HISTORICAL_RELAUNCH.value,
            source_run_id=None,
            source_lineage={},
            prefect_flow_run_id="prefect-mismatched-tuple",
        )
    assert claims.get(claim.submission.idempotency_key).state == (
        ResearchSubmissionState.INVOKING
    )


def test_direct_unclaimed_fixture_body_is_not_callable(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="idempotency_key"):
        deterministic_fixture_body(
            database_path=tmp_path / "state.sqlite3",
            configuration_id="missing",
            quant_factory_run_id="unclaimed-run",
            prefect_flow_run_id="prefect-unclaimed",
        )


def test_reproduction_replay_repairs_missing_manifest_without_reinvoking(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)
    calls: list[str] = []

    def launcher(**kwargs):
        calls.append(kwargs["quant_factory_run_id"])
        kwargs.pop("attempt_marker_path")
        return deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        )

    service = FixtureRunService(
        database=database,
        fixture_launcher=launcher,
    )
    source = service.launch_fixture(
        idempotency_key="launch_reproduction_source_001",
        configuration_id=configuration_id,
        run_id="reproduction-source",
    )
    persistence = PersistenceService(database)
    try:
        persistence.results.set_data_provenance(
            DataProvenanceRecord(
                run_id=source.run.run_id,
                provider="deterministic_fixture",
                provider_implementation="prefect_fixture",
                symbol="SPY",
                interval="1 day",
                timezone="America/New_York",
                requested_coverage="fixture",
                actual_coverage="fixture",
                adjusted=True,
                row_count=1,
                cache_action="fixture",
                validation_summary_json=canonical_json({"valid": True}),
                manifest_reference="data/manifests/deterministic_fixture.json",
                checksum="fixture-dataset-checksum",
            )
        )
        configuration = persistence.configurations.get(configuration_id)
        assert configuration is not None
        persistence.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=source.run.run_id,
                assumptions_json=canonical_json(
                    json.loads(configuration.canonical_config_json)["execution"]
                ),
            )
        )
        persistence.connection.commit()
        persistence.persist_run_manifest(
            persistence.build_run_manifest(source.run.run_id)
        )
    finally:
        persistence.close()
    child = service.launch_fixture(
        idempotency_key="launch_reproduction_child_001",
        configuration_id=configuration_id,
        operation=ResearchLaunchOperation.REPRODUCTION,
        source_run_id=source.run.run_id,
        run_id="reproduction-child",
    )
    persistence = PersistenceService(database)
    try:
        persistence.results.set_data_provenance(
            DataProvenanceRecord(
                run_id=child.run.run_id,
                provider="deterministic_fixture",
                provider_implementation="prefect_fixture",
                symbol="SPY",
                interval="1 day",
                timezone="America/New_York",
                requested_coverage="fixture",
                actual_coverage="fixture",
                adjusted=True,
                row_count=1,
                cache_action="fixture",
                validation_summary_json=canonical_json({"valid": True}),
                manifest_reference="data/manifests/deterministic_fixture.json",
                checksum="fixture-dataset-checksum",
            )
        )
        configuration = persistence.configurations.get(configuration_id)
        assert configuration is not None
        persistence.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=child.run.run_id,
                assumptions_json=canonical_json(
                    json.loads(configuration.canonical_config_json)["execution"]
                ),
            )
        )
        persistence.connection.commit()
        assert persistence.read_persisted_run_manifest(child.run.run_id) is None
    finally:
        persistence.close()

    replay = service.reproduce_fixture_run(
        source.run.run_id,
        idempotency_key="launch_reproduction_child_001",
        artifact_root=tmp_path / "artifacts",
    )

    persistence = PersistenceService(database)
    try:
        assert persistence.read_persisted_run_manifest(child.run.run_id) is not None
    finally:
        persistence.close()
    assert replay.reproduction.run_id == child.run.run_id
    assert calls == ["reproduction-source", "reproduction-child"]


def test_operator_error_summary_does_not_persist_exception_controlled_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "state.sqlite3"
    configuration_id = _configuration(database)
    sensitive = "token=do-not-store /private/provider/account.json"
    monkeypatch.setattr(
        fixture_flow_module,
        "_persist_fixture_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(sensitive)),
    )

    with pytest.raises(ResearchLaunchInvocationError):
        FixtureRunService(
            database=database,
            fixture_launcher=_acknowledging_launcher([]),
        ).launch_fixture(
            idempotency_key="launch_sanitized_error_001",
            configuration_id=configuration_id,
            run_id="sanitized-error-run",
        )

    run = FixtureRunService(database=database).get_run("sanitized-error-run")
    assert run is not None
    assert run.error_summary == (
        "Prefect fixture execution failed; inspect approved technical diagnostics."
    )
    assert sensitive not in run.error_summary
