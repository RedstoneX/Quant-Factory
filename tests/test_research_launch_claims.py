"""Focused schema, concurrency, crash-window, and recovery tests for ADR 0011."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import threading
import time

import pytest

import orchestration.research_launch_claims as claims_module
from orchestration.research_launch_claims import (
    DurableResearchLaunchService,
    ResearchLaunchConflictError,
    ResearchLaunchContentionError,
    ResearchLaunchIntegrityError,
    ResearchLaunchInvocationError,
    ResearchLaunchInvocationUnknownError,
    ResearchLaunchRequest,
    new_dispatcher_instance_id,
)
from persistence import (
    LATEST_SCHEMA_VERSION,
    PersistenceService,
    ResearchLaunchOperation,
    ResearchSubmissionState,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
    initialize_database,
)
import persistence.database as database_module
from persistence.models import normalized_configuration_document
from tests.test_run_lineage import _service_with_lineage_run


def _database(tmp_path: Path, name: str = "claims.sqlite3") -> Path:
    return tmp_path / "state" / name


def _configuration(
    path: Path,
    *,
    experiment_id: str = "fixture_experiment",
    strategy_id: str = "fixture_strategy",
) -> str:
    service = PersistenceService(path)
    try:
        service.register_strategy(
            strategy_id=strategy_id,
            strategy_version="1.0.0",
            display_name="Fixture Strategy",
            description="Deterministic durable-claim fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        record = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id=experiment_id,
                strategy_id=strategy_id,
                strategy_version="1.0.0",
                market_data={"symbol": "SPY", "provider": "fixture"},
                parameters={"window": 10},
                execution={"mode": "fixture"},
                ranking={"columns": ["total_return"], "ascending": [False]},
                screening={"minimum_trades": 1},
            )
        )
        return record.configuration_id
    finally:
        service.close()


def _request(configuration_id: str) -> ResearchLaunchRequest:
    return ResearchLaunchRequest(
        operation=ResearchLaunchOperation.RUN_TEST,
        configuration_id=configuration_id,
    )


def _key(suffix: str) -> str:
    return f"launch_{suffix:0<24}"


def _counts(path: Path) -> tuple[int, int, int]:
    connection = sqlite3.connect(path)
    try:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "experiment_runs",
                "run_operator_events",
                "research_run_submissions",
            )
        )
    finally:
        connection.close()


def _bind(
    service: DurableResearchLaunchService,
    submission,
    *,
    prefect_flow_run_id: str = "prefect-flow-1",
):
    return service.bind_prefect_identity(
        idempotency_key=submission.idempotency_key,
        run_id=submission.run_id,
        configuration_id=submission.configuration_id,
        canonical_request_json=submission.canonical_request_json,
        request_fingerprint=submission.request_fingerprint,
        prefect_flow_run_id=prefect_flow_run_id,
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def _reproduction_source(tmp_path: Path) -> tuple[Path, str, str]:
    run_id = "source-succeeded-run"
    service, configuration_id = _service_with_lineage_run(tmp_path, run_id=run_id)
    path = tmp_path / "state" / f"{run_id}.sqlite3"
    try:
        service.transition_run(run_id, RunStatus.RUNNING)
        service.transition_run(run_id, RunStatus.SUCCEEDED)
        service.persist_run_manifest(service.build_run_manifest(run_id))
    finally:
        service.close()
    return path, configuration_id, run_id


def test_default_constructor_initializes_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_calls: list[str] = []

    class InitializedConnection:
        def close(self) -> None:
            default_calls.append("close")

    def record_initialize(_path):
        default_calls.append("initialize")
        return InitializedConnection()

    monkeypatch.setattr(claims_module, "initialize_database", record_initialize)
    DurableResearchLaunchService(database=_database(tmp_path, "default.sqlite3"))
    assert default_calls == ["initialize", "close"]


def test_no_init_mode_defers_all_database_access_until_atomic_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _database(tmp_path, "bind-first.sqlite3")
    configuration_id = _configuration(path)
    setup = DurableResearchLaunchService(database=path)
    claim = setup.claim(
        idempotency_key=_key("bind-first-operation"),
        request=_request(configuration_id),
    )
    setup.begin_dispatch(
        idempotency_key=claim.submission.idempotency_key,
        dispatcher_instance_id=new_dispatcher_instance_id(),
    )

    access: list[str] = []
    real_connect = claims_module.connect

    def forbidden_initialize(_path):
        access.append("initialize")
        raise AssertionError("schema initialization must not run inside the flow")

    def tracked_connect(path_arg):
        access.append("bind_connection")
        return real_connect(path_arg)

    monkeypatch.setattr(claims_module, "initialize_database", forbidden_initialize)
    monkeypatch.setattr(claims_module, "connect", tracked_connect)
    binder = DurableResearchLaunchService(database=path, initialize_schema=False)
    assert access == []

    acknowledged = _bind(binder, claim.submission)
    assert access == ["bind_connection"]
    assert acknowledged.state == ResearchSubmissionState.ACKNOWLEDGED


def test_initialize_schema_requires_an_explicit_boolean(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a boolean"):
        DurableResearchLaunchService(
            database=_database(tmp_path),
            initialize_schema=1,  # type: ignore[arg-type]
        )


def test_fresh_schema_five_and_v4_to_v5_migration_preserve_existing_rows(tmp_path: Path) -> None:
    fresh = _database(tmp_path, "fresh.sqlite3")
    connection = initialize_database(fresh)
    try:
        assert connection.execute(
            "SELECT schema_version FROM schema_metadata"
        ).fetchone()["schema_version"] == LATEST_SCHEMA_VERSION == 5
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='research_run_submissions'"
        ).fetchone() is not None
    finally:
        connection.close()

    migrated = _database(tmp_path, "migrated.sqlite3")
    migrated.parent.mkdir(parents=True, exist_ok=True)
    v4 = sqlite3.connect(migrated)
    v4.row_factory = sqlite3.Row
    v4.execute("PRAGMA foreign_keys = ON")
    database_module._migrate_empty_to_v1(v4)
    database_module._migrate_v1_to_v2(v4)
    database_module._migrate_v2_to_v3(v4)
    database_module._migrate_v3_to_v4(v4)
    v4.execute(
        """
        INSERT INTO strategies VALUES
        ('fixture', '1.0.0', 'Fixture', 'Preserved', 'infrastructure_fixture', 1,
         '2026-09-18T00:00:00Z', '2026-09-18T00:00:00Z')
        """
    )
    v4.commit()
    v4.close()

    upgraded = initialize_database(migrated)
    try:
        assert upgraded.execute(
            "SELECT schema_version FROM schema_metadata"
        ).fetchone()["schema_version"] == 5
        assert upgraded.execute(
            "SELECT display_name FROM strategies WHERE strategy_id='fixture'"
        ).fetchone()["display_name"] == "Fixture"
        assert upgraded.execute(
            "SELECT COUNT(*) FROM research_run_submissions"
        ).fetchone()[0] == 0
    finally:
        upgraded.close()


def test_v4_to_v5_migration_failure_rolls_back_every_schema_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _database(tmp_path, "migration-rollback.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    v4 = sqlite3.connect(path)
    v4.row_factory = sqlite3.Row
    database_module._migrate_empty_to_v1(v4)
    database_module._migrate_v1_to_v2(v4)
    database_module._migrate_v2_to_v3(v4)
    database_module._migrate_v3_to_v4(v4)
    v4.close()
    statements = database_module.MIGRATION_005_STATEMENTS
    monkeypatch.setattr(
        database_module,
        "MIGRATION_005_STATEMENTS",
        statements[:2] + ("INSERT INTO missing_migration_table VALUES (1)",) + statements[2:],
    )
    with pytest.raises(sqlite3.Error):
        initialize_database(path)

    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT schema_version FROM schema_metadata"
        ).fetchone()[0] == 4
        names = {
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE name LIKE 'research_run_submissions%'
                   OR name LIKE 'idx_research_submissions%'
                """
            )
        }
        assert names == set()
    finally:
        connection.close()


def test_schema_rejects_non_sha256_submission_fingerprint(tmp_path: Path) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    persistence = PersistenceService(path)
    try:
        configuration = persistence.configurations.get(configuration_id)
        assert configuration is not None
        run = persistence.create_run(
            configuration_id=configuration_id,
            strategy_id=configuration.strategy_id,
            strategy_version=configuration.strategy_version,
            stage="fixture",
            run_id="run_invalid_fingerprint",
        )
        with pytest.raises(sqlite3.IntegrityError):
            persistence.connection.execute(
                """
                INSERT INTO research_run_submissions
                (idempotency_key, run_id, configuration_id, canonical_request_json,
                 request_fingerprint, state, claimed_at, updated_at)
                VALUES (?, ?, ?, '{}', ?, 'claimed', ?, ?)
                """,
                (
                    _key("invalid-fingerprint"),
                    run.run_id,
                    configuration_id,
                    "G" * 64,
                    "2026-09-18T00:00:00Z",
                    "2026-09-18T00:00:00Z",
                ),
            )
    finally:
        persistence.connection.rollback()
        persistence.close()


@pytest.mark.parametrize(
    "failure_step",
    ["after_run_create", "after_run_created_event", "after_submission_create"],
)
def test_injected_failure_after_each_claim_write_rolls_back_everything(
    tmp_path: Path,
    failure_step: str,
) -> None:
    path = _database(tmp_path, f"rollback-{failure_step}.sqlite3")
    configuration_id = _configuration(path)

    def fail(step: str) -> None:
        if step == failure_step:
            raise RuntimeError(f"controlled failure at {step}")

    service = DurableResearchLaunchService(
        database=path,
        run_id_factory=lambda: f"run_{failure_step}",
        claim_failure_injector=fail,
    )
    with pytest.raises(RuntimeError, match="controlled failure"):
        service.claim(
            idempotency_key=_key(failure_step),
            request=_request(configuration_id),
        )
    assert _counts(path) == (0, 0, 0)


def test_same_key_replays_across_restart_and_mismatches_fail_without_mutation(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    first_configuration = _configuration(path)
    second_configuration = _configuration(
        path,
        experiment_id="other_fixture",
        strategy_id="other_fixture_strategy",
    )
    key = _key("restart")
    service = DurableResearchLaunchService(
        database=path,
        run_id_factory=lambda: "run_stable_identity",
    )
    claimed = service.claim(idempotency_key=key, request=_request(first_configuration))
    assert claimed.created is True
    assert claimed.run.status == RunStatus.CREATED

    restarted = DurableResearchLaunchService(
        database=path,
        run_id_factory=lambda: "run_must_not_be_allocated",
    )
    replay = restarted.claim(idempotency_key=key, request=_request(first_configuration))
    assert replay.created is False
    assert replay.run.run_id == "run_stable_identity"
    assert replay.submission == claimed.submission

    with pytest.raises(ResearchLaunchConflictError, match="different request"):
        restarted.claim(idempotency_key=key, request=_request(second_configuration))
    with pytest.raises(ResearchLaunchConflictError, match="different request"):
        restarted.claim(
            idempotency_key=key,
            request=ResearchLaunchRequest(
                operation=ResearchLaunchOperation.REPRODUCTION,
                configuration_id=first_configuration,
                source_run_id="source-run",
                source_lineage={"reproduction_of_run_id": "source-run"},
            ),
        )
    assert _counts(path) == (1, 1, 1)


def test_submitted_key_reopens_after_strategy_retirement_but_cannot_start_later(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    key = _key("retired-replay")
    service = DurableResearchLaunchService(database=path)
    original = service.claim(idempotency_key=key, request=_request(configuration_id))
    persistence = PersistenceService(path)
    try:
        persistence.update_strategy_lifecycle(
            original.run.strategy_id,
            original.run.strategy_version,
            lifecycle=StrategyLifecycle.RETIRED,
            active=False,
        )
    finally:
        persistence.close()

    reopened = service.claim(idempotency_key=key, request=_request(configuration_id))
    assert reopened.created is False
    assert reopened.submission == original.submission
    with pytest.raises(ResearchLaunchIntegrityError, match="no longer launchable"):
        service.begin_dispatch(
            idempotency_key=key,
            dispatcher_instance_id=new_dispatcher_instance_id(),
        )
    assert service.get(key).state == ResearchSubmissionState.CLAIMED


def test_historical_and_reproduction_lineage_is_derived_from_persisted_source(
    tmp_path: Path,
) -> None:
    path, configuration_id, source_run_id = _reproduction_source(tmp_path)
    service = DurableResearchLaunchService(database=path)
    historical = service.claim(
        idempotency_key=_key("historical"),
        request=ResearchLaunchRequest(
            operation=ResearchLaunchOperation.HISTORICAL_RELAUNCH,
            configuration_id=configuration_id,
            source_run_id=source_run_id,
        ),
    )
    historical_request = json.loads(historical.submission.canonical_request_json)
    assert historical_request["source_lineage"] == {"parent_run_id": source_run_id}

    reproduced = service.claim(
        idempotency_key=_key("reproduction"),
        request=ResearchLaunchRequest(
            operation=ResearchLaunchOperation.REPRODUCTION,
            configuration_id=configuration_id,
            source_run_id=source_run_id,
        ),
    )
    reproduction_request = json.loads(reproduced.submission.canonical_request_json)
    lineage = reproduction_request["source_lineage"]
    assert lineage["reproduction_of_run_id"] == source_run_id
    assert len(lineage["source_manifest_checksum"]) == 64
    assert len(lineage["source_runtime_identity"]) == 64
    assert len(lineage["source_dataset_identity"]) == 64
    assert len(lineage["source_execution_assumptions_identity"]) == 64


def test_nonexistent_mismatched_or_fabricated_source_lineage_fails_closed(
    tmp_path: Path,
) -> None:
    path, configuration_id, source_run_id = _reproduction_source(tmp_path)
    service = DurableResearchLaunchService(database=path)
    before = _counts(path)
    with pytest.raises(ResearchLaunchIntegrityError, match="does not exist"):
        service.claim(
            idempotency_key=_key("missing-source"),
            request=ResearchLaunchRequest(
                operation=ResearchLaunchOperation.REPRODUCTION,
                configuration_id=configuration_id,
                source_run_id="missing-source-run",
            ),
        )
    with pytest.raises(ResearchLaunchIntegrityError, match="does not match"):
        service.claim(
            idempotency_key=_key("fake-lineage"),
            request=ResearchLaunchRequest(
                operation=ResearchLaunchOperation.REPRODUCTION,
                configuration_id=configuration_id,
                source_run_id=source_run_id,
                source_lineage={
                    "reproduction_of_run_id": source_run_id,
                    "source_manifest_checksum": "0" * 64,
                    "source_runtime_identity": "1" * 64,
                    "source_dataset_identity": "2" * 64,
                    "source_execution_assumptions_identity": "3" * 64,
                },
            ),
        )
    other_configuration = _configuration(
        path,
        experiment_id="other-source-target",
        strategy_id="other-source-strategy",
    )
    with pytest.raises(ResearchLaunchIntegrityError, match="does not match"):
        service.claim(
            idempotency_key=_key("mismatched-source"),
            request=ResearchLaunchRequest(
                operation=ResearchLaunchOperation.HISTORICAL_RELAUNCH,
                configuration_id=other_configuration,
                source_run_id=source_run_id,
            ),
        )
    assert _counts(path) == before


def test_two_connections_claim_same_key_create_one_run_event_and_submission(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    barrier = threading.Barrier(2)

    def claim(run_id: str):
        service = DurableResearchLaunchService(
            database=path,
            busy_timeout_seconds=2,
            run_id_factory=lambda: run_id,
        )
        barrier.wait()
        return service.claim(
            idempotency_key=_key("concurrent"),
            request=_request(configuration_id),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            executor.map(claim, ("run_concurrent_a", "run_concurrent_b"))
        )
    assert {result.run.run_id for result in results} in (
        {"run_concurrent_a"},
        {"run_concurrent_b"},
    )
    assert sorted(result.created for result in results) == [False, True]
    assert _counts(path) == (1, 1, 1)


def test_begin_immediate_contention_is_bounded_typed_and_creates_nothing(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(
        database=path,
        busy_timeout_seconds=0.05,
        run_id_factory=lambda: "run_after_contention",
    )
    blocker = sqlite3.connect(path)
    blocker.execute("BEGIN IMMEDIATE")
    started = time.monotonic()
    try:
        with pytest.raises(ResearchLaunchContentionError):
            service.claim(
                idempotency_key=_key("contention"),
                request=_request(configuration_id),
            )
    finally:
        elapsed = time.monotonic() - started
        blocker.rollback()
        blocker.close()
    assert elapsed < 0.5
    assert _counts(path) == (0, 0, 0)

    retry = service.claim(
        idempotency_key=_key("contention"),
        request=_request(configuration_id),
    )
    assert retry.run.run_id == "run_after_contention"


def test_dispatch_contention_expires_without_invocation_or_state_change(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path, busy_timeout_seconds=0.05)
    key = _key("dispatch-contention")
    service.claim(idempotency_key=key, request=_request(configuration_id))
    blocker = sqlite3.connect(path)
    blocker.execute("BEGIN IMMEDIATE")
    calls = 0

    def invoke(_submission):
        nonlocal calls
        calls += 1

    try:
        with pytest.raises(ResearchLaunchContentionError):
            service.dispatch(
                idempotency_key=key,
                dispatcher_instance_id=new_dispatcher_instance_id(),
                invoke=invoke,
            )
    finally:
        blocker.rollback()
        blocker.close()
    assert calls == 0
    assert service.get(key).state == ResearchSubmissionState.CLAIMED


def test_dispatch_compare_and_set_invokes_once_and_binding_is_idempotent(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    key = _key("dispatch-once")
    service.claim(idempotency_key=key, request=_request(configuration_id))
    dispatcher_a = new_dispatcher_instance_id()
    dispatcher_b = new_dispatcher_instance_id()
    invocation_entered = threading.Event()
    release_invocation = threading.Event()
    calls: list[str] = []

    def invoke(submission):
        calls.append(submission.run_id)
        invocation_entered.set()
        assert release_invocation.wait(2)
        _bind(service, submission)
        return "acknowledged"

    with ThreadPoolExecutor(max_workers=2) as executor:
        winner_future = executor.submit(
            service.dispatch,
            idempotency_key=key,
            dispatcher_instance_id=dispatcher_a,
            invoke=invoke,
        )
        assert invocation_entered.wait(2)
        loser = service.dispatch(
            idempotency_key=key,
            dispatcher_instance_id=dispatcher_b,
            invoke=lambda _submission: pytest.fail("dispatch loser invoked"),
        )
        release_invocation.set()
        winner = winner_future.result(timeout=2)

    assert calls == [winner.submission.run_id]
    assert winner.invoked is True and winner.value == "acknowledged"
    assert loser.invoked is False
    assert winner.submission.state == ResearchSubmissionState.ACKNOWLEDGED
    assert service.get_for_run(winner.submission.run_id) == winner.submission

    replay = _bind(service, winner.submission)
    assert replay == winner.submission
    persistence = PersistenceService(path)
    try:
        run = persistence.runs.get(winner.submission.run_id)
        assert run is not None and run.status == RunStatus.RUNNING
        event_types = [event.event_type.value for event in persistence.events.list_for_run(run.run_id)]
        assert event_types == ["run_created", "run_started"]
        environment = json.loads(run.environment_json)
        assert environment["prefect_flow_run_id"] == "prefect-flow-1"
    finally:
        persistence.close()


def test_invocation_exception_or_missing_binding_becomes_unknown_and_never_reinvokes(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    dispatcher = new_dispatcher_instance_id()
    exception_key = _key("exception")
    service.claim(idempotency_key=exception_key, request=_request(configuration_id))
    calls = 0

    def broken(_submission):
        nonlocal calls
        calls += 1
        raise RuntimeError("ambiguous external failure")

    with pytest.raises(ResearchLaunchInvocationUnknownError):
        service.dispatch(
            idempotency_key=exception_key,
            dispatcher_instance_id=dispatcher,
            invoke=broken,
        )
    replay = service.dispatch(
        idempotency_key=exception_key,
        dispatcher_instance_id=new_dispatcher_instance_id(),
        invoke=broken,
    )
    assert replay.invoked is False
    assert replay.submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN
    assert calls == 1

    missing_binding_key = _key("missing-binding")
    service.claim(idempotency_key=missing_binding_key, request=_request(configuration_id))
    with pytest.raises(ResearchLaunchInvocationUnknownError, match="without durable acknowledgement"):
        service.dispatch(
            idempotency_key=missing_binding_key,
            dispatcher_instance_id=new_dispatcher_instance_id(),
            invoke=lambda _submission: "returned without binding",
        )
    assert service.get(missing_binding_key).state == ResearchSubmissionState.SUBMISSION_UNKNOWN


def test_exception_after_in_flow_binding_keeps_acknowledgement_and_propagates_error(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    key = _key("ack-then-error")
    service.claim(idempotency_key=key, request=_request(configuration_id))

    def acknowledge_then_raise(submission):
        _bind(service, submission)
        raise RuntimeError("failure after durable acknowledgement")

    with pytest.raises(ResearchLaunchInvocationError) as caught:
        service.dispatch(
            idempotency_key=key,
            dispatcher_instance_id=new_dispatcher_instance_id(),
            invoke=acknowledge_then_raise,
        )
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert service.get(key).state == ResearchSubmissionState.ACKNOWLEDGED


def test_foreign_dispatcher_is_not_liveness_proof_but_explicit_exit_barrier_is(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    key = _key("exit-barrier")
    service.claim(idempotency_key=key, request=_request(configuration_id))
    owner = new_dispatcher_instance_id()
    foreign = new_dispatcher_instance_id()
    assert service.begin_dispatch(
        idempotency_key=key,
        dispatcher_instance_id=owner,
    ).should_invoke

    with pytest.raises(ResearchLaunchConflictError, match="marker winner"):
        service.mark_invocation_unknown(
            idempotency_key=key,
            dispatcher_instance_id=foreign,
        )
    with pytest.raises(ResearchLaunchConflictError, match="does not name"):
        service.recover_invoking_after_process_exit(
            idempotency_key=key,
            departed_dispatcher_instance_id=foreign,
            process_exit_evidence_reference="stop-start-proof:wrong-generation",
        )
    assert service.get(key).state == ResearchSubmissionState.INVOKING

    recovered = service.recover_invoking_after_process_exit(
        idempotency_key=key,
        departed_dispatcher_instance_id=owner,
        process_exit_evidence_reference="stop-start-proof:all-old-processes-exited",
    )
    assert recovered.state == ResearchSubmissionState.SUBMISSION_UNKNOWN
    assert recovered.unknown_evidence_reference == (
        "stop-start-proof:all-old-processes-exited"
    )
    assert recovered.resolution_evidence_reference is None
    with pytest.raises(ResearchLaunchConflictError, match="does not match"):
        service.recover_invoking_after_process_exit(
            idempotency_key=key,
            departed_dispatcher_instance_id=owner,
            process_exit_evidence_reference="stop-start-proof:different",
        )
    abandoned = service.abandon_unknown(
        idempotency_key=key,
        resolution_evidence_reference="operator-resolution:case-19",
    )
    assert abandoned.unknown_evidence_reference == (
        "stop-start-proof:all-old-processes-exited"
    )
    assert abandoned.resolution_evidence_reference == "operator-resolution:case-19"


def test_binding_mismatch_fails_closed_and_records_sanitized_integrity_event(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    key = _key("bind-mismatch")
    claim = service.claim(idempotency_key=key, request=_request(configuration_id))
    service.begin_dispatch(
        idempotency_key=key,
        dispatcher_instance_id=new_dispatcher_instance_id(),
    )

    with pytest.raises(ResearchLaunchIntegrityError, match="did not match"):
        service.bind_prefect_identity(
            idempotency_key=key,
            run_id=claim.run.run_id,
            configuration_id=configuration_id,
            canonical_request_json=claim.submission.canonical_request_json,
            request_fingerprint="0" * 64,
            prefect_flow_run_id="prefect-wrong",
        )
    with pytest.raises(ResearchLaunchIntegrityError, match="did not match"):
        service.bind_prefect_identity(
            idempotency_key=key,
            run_id=claim.run.run_id,
            configuration_id=configuration_id,
            canonical_request_json=claim.submission.canonical_request_json,
            request_fingerprint="0" * 64,
            prefect_flow_run_id="prefect-wrong",
        )
    assert service.get(key).state == ResearchSubmissionState.INVOKING
    persistence = PersistenceService(path)
    try:
        events = persistence.events.list_for_run(claim.run.run_id)
        assert [event.event_type.value for event in events] == [
            "run_created",
            "service_integrity_error",
        ]
        assert "0" * 64 not in events[-1].message
        assert len(events) == 2
    finally:
        persistence.close()


@pytest.mark.parametrize(
    ("assignment", "value"),
    [
        ("stage", "screening"),
        ("strategy_version", "9.9.9"),
        ("configuration_id", "corrupt-configuration"),
    ],
)
def test_dispatch_and_binding_reject_mutated_persisted_run_identity(
    tmp_path: Path,
    assignment: str,
    value: str,
) -> None:
    path = _database(tmp_path, f"mutated-{assignment}.sqlite3")
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    key = _key(f"dispatch-{assignment}")
    claim = service.claim(idempotency_key=key, request=_request(configuration_id))
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            f"UPDATE experiment_runs SET {assignment}=? WHERE run_id=?",
            (value, claim.run.run_id),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ResearchLaunchIntegrityError, match="run identity"):
        service.begin_dispatch(
            idempotency_key=key,
            dispatcher_instance_id=new_dispatcher_instance_id(),
        )
    assert service.get(key).state == ResearchSubmissionState.CLAIMED


def test_binding_revalidates_persisted_run_identity_after_dispatch(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    key = _key("bind-run-mutated")
    claim = service.claim(idempotency_key=key, request=_request(configuration_id))
    service.begin_dispatch(
        idempotency_key=key,
        dispatcher_instance_id=new_dispatcher_instance_id(),
    )
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE experiment_runs SET stage='screening' WHERE run_id=?",
            (claim.run.run_id,),
        )
        connection.commit()
    finally:
        connection.close()
    for _ in range(2):
        with pytest.raises(ResearchLaunchIntegrityError, match="run identity"):
            _bind(service, claim.submission)
    persistence = PersistenceService(path)
    try:
        assert [event.event_type.value for event in persistence.events.list_for_run(claim.run.run_id)] == [
            "run_created",
            "service_integrity_error",
        ]
    finally:
        persistence.close()


def test_dispatch_rejects_externally_terminal_claimed_run(tmp_path: Path) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    key = _key("terminal-before-dispatch")
    claim = service.claim(idempotency_key=key, request=_request(configuration_id))
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE experiment_runs SET status='failed', completed_at=? WHERE run_id=?",
            ("2026-09-18T00:00:00Z", claim.run.run_id),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ResearchLaunchIntegrityError, match="not in Created"):
        service.begin_dispatch(
            idempotency_key=key,
            dispatcher_instance_id=new_dispatcher_instance_id(),
        )
    assert service.get(key).state == ResearchSubmissionState.CLAIMED


def test_at_rest_operation_source_invariants_fail_with_typed_integrity_error(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    key = _key("corrupt-source")
    claim = service.claim(idempotency_key=key, request=_request(configuration_id))
    document = json.loads(claim.submission.canonical_request_json)
    document["source_run_id"] = "prohibited-source"
    corrupted = canonical_json(document)
    fingerprint = __import__("hashlib").sha256(corrupted.encode("utf-8")).hexdigest()
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER research_run_submissions_immutable_identity")
        connection.execute(
            """
            UPDATE research_run_submissions
            SET canonical_request_json=?, request_fingerprint=?
            WHERE idempotency_key=?
            """,
            (corrupted, fingerprint, key),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ResearchLaunchIntegrityError, match="prohibited source lineage"):
        service.begin_dispatch(
            idempotency_key=key,
            dispatcher_instance_id=new_dispatcher_instance_id(),
        )


def test_failed_before_submission_and_abandoned_are_atomic_idempotent_terminal_outcomes(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)

    failed_key = _key("failed-before")
    failed_claim = service.claim(idempotency_key=failed_key, request=_request(configuration_id))
    failed = service.fail_before_submission(
        idempotency_key=failed_key,
        error_summary="Local launch preparation failed before Prefect submission.",
    )
    assert failed.state == ResearchSubmissionState.FAILED_BEFORE_SUBMISSION
    assert service.fail_before_submission(
        idempotency_key=failed_key,
        error_summary="Local launch preparation failed before Prefect submission.",
    ) == failed

    abandoned_key = _key("abandoned")
    abandoned_claim = service.claim(
        idempotency_key=abandoned_key,
        request=_request(configuration_id),
    )
    dispatcher = new_dispatcher_instance_id()
    service.begin_dispatch(
        idempotency_key=abandoned_key,
        dispatcher_instance_id=dispatcher,
    )
    service.mark_invocation_unknown(
        idempotency_key=abandoned_key,
        dispatcher_instance_id=dispatcher,
    )
    abandoned = service.abandon_unknown(
        idempotency_key=abandoned_key,
        resolution_evidence_reference="operator-reconciliation:case-17",
    )
    assert abandoned.state == ResearchSubmissionState.ABANDONED
    assert service.abandon_unknown(
        idempotency_key=abandoned_key,
        resolution_evidence_reference="operator-reconciliation:case-17",
    ) == abandoned
    assert abandoned.unknown_evidence_reference is None

    persistence = PersistenceService(path)
    try:
        for run_id in (failed_claim.run.run_id, abandoned_claim.run.run_id):
            run = persistence.runs.get(run_id)
            assert run is not None and run.status == RunStatus.FAILED
            assert [event.event_type.value for event in persistence.events.list_for_run(run_id)] == [
                "run_created",
                "run_failed",
            ]
    finally:
        persistence.close()


@pytest.mark.parametrize("terminal_action", ["fail_before", "abandon"])
def test_terminal_submission_resolution_revalidates_full_persisted_identity(
    tmp_path: Path,
    terminal_action: str,
) -> None:
    path = _database(tmp_path, f"terminal-integrity-{terminal_action}.sqlite3")
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    key = _key(f"terminal-{terminal_action}")
    claim = service.claim(idempotency_key=key, request=_request(configuration_id))
    if terminal_action == "abandon":
        dispatcher = new_dispatcher_instance_id()
        service.begin_dispatch(
            idempotency_key=key,
            dispatcher_instance_id=dispatcher,
        )
        service.mark_invocation_unknown(
            idempotency_key=key,
            dispatcher_instance_id=dispatcher,
        )
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE experiment_runs SET stage='screening' WHERE run_id=?",
            (claim.run.run_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ResearchLaunchIntegrityError, match="run identity"):
        if terminal_action == "fail_before":
            service.fail_before_submission(
                idempotency_key=key,
                error_summary="Known pre-submission failure.",
            )
        else:
            service.abandon_unknown(
                idempotency_key=key,
                resolution_evidence_reference="operator-resolution:corrupt-run",
            )
    persistence = PersistenceService(path)
    try:
        run = persistence.runs.get(claim.run.run_id)
        assert run is not None and run.status == RunStatus.CREATED
        assert [event.event_type.value for event in persistence.events.list_for_run(run.run_id)] == [
            "run_created"
        ]
    finally:
        persistence.close()


def test_submission_identity_is_immutable_and_durable_rows_cannot_be_deleted(
    tmp_path: Path,
) -> None:
    path = _database(tmp_path)
    configuration_id = _configuration(path)
    service = DurableResearchLaunchService(database=path)
    claim = service.claim(
        idempotency_key=_key("immutable"),
        request=_request(configuration_id),
    )
    connection = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="identity is immutable"):
            connection.execute(
                "UPDATE research_run_submissions SET request_fingerprint=? WHERE idempotency_key=?",
                ("f" * 64, claim.submission.idempotency_key),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="durable evidence"):
            connection.execute(
                "DELETE FROM research_run_submissions WHERE idempotency_key=?",
                (claim.submission.idempotency_key,),
            )
    finally:
        connection.rollback()
        connection.close()
