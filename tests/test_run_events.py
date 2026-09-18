"""Focused Slice 18B tests for append-only operator-visible run events."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from orchestration import FixtureRunService
from orchestration.research_launch_claims import ResearchLaunchInvocationError
from persistence import LATEST_SCHEMA_VERSION, PersistenceService, initialize_database
from persistence import database as database_module
from prefect_spike.fixture_flow import (
    PrefectFixtureResult,
    PrefectRunReference,
    _persist_fixture_result,
    _validated_claim_boundary,
    reconcile_quant_factory_run_status,
)
from tests.test_run_service import _configuration, _launcher


def test_existing_v1_database_migrates_to_append_only_event_schema(tmp_path: Path) -> None:
    database = tmp_path / "state" / "v1.sqlite3"
    connection = database_module.connect(database)
    try:
        database_module._migrate_empty_to_v1(connection)
    finally:
        connection.close()

    migrated = initialize_database(database)
    try:
        version = migrated.execute(
            "SELECT schema_version FROM schema_metadata"
        ).fetchone()["schema_version"]
        table = migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='run_operator_events'"
        ).fetchone()
    finally:
        migrated.close()

    assert version == LATEST_SCHEMA_VERSION == 5
    assert table is not None


def test_successful_run_records_concise_lifecycle_events(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)

    service.launch_fixture(configuration_id=configuration_id, run_id="qf-events-success")

    events = service.events_for_run("qf-events-success")
    assert [event.event_type for event in events] == [
        "run_created",
        "run_started",
        "run_succeeded",
    ]
    assert all(event.run_id == "qf-events-success" for event in events)
    assert all(event.timestamp for event in events)
    assert [event.severity for event in events] == ["info", "info", "info"]
    assert all(event.source == "quant_factory" for event in events)


def test_created_and_started_events_are_visible_before_launcher_completes(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    started = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def blocking_launcher(**kwargs):
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
            prefect_reference=PrefectRunReference(flow_run_id="prefect-active-run"),
        )
        persistence = PersistenceService(kwargs["database_path"])
        try:
            started.set()
            assert release.wait(timeout=5)
            _persist_fixture_result(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                configuration_id=kwargs["configuration_id"],
                prefect_flow_run_id="prefect-active-run",
                deterministic_value=1729,
                attempt_count=1,
            )
            reconcile_quant_factory_run_status(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_state="Completed",
            )
            return PrefectFixtureResult(
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_flow_run_id="prefect-active-run",
                configuration_id=kwargs["configuration_id"],
                deterministic_value=1729,
                attempt_count=1,
            )
        finally:
            persistence.close()

    service = FixtureRunService(database=database, fixture_launcher=blocking_launcher)

    def launch() -> None:
        try:
            service.launch_fixture(configuration_id=configuration_id, run_id="qf-events-active")
        except BaseException as exc:  # pragma: no cover - assertion follows below
            errors.append(exc)

    launcher_thread = threading.Thread(target=launch)
    launcher_thread.start()
    try:
        assert started.wait(timeout=5)
        assert launcher_thread.is_alive()
        assert service.get_run("qf-events-active").status == "running"
        assert [event.event_type for event in service.events_for_run("qf-events-active")] == [
            "run_created",
            "run_started",
        ]
    finally:
        release.set()
        launcher_thread.join(timeout=5)

    assert not launcher_thread.is_alive()
    assert errors == []
    assert [event.event_type for event in service.events_for_run("qf-events-active")] == [
        "run_created",
        "run_started",
        "run_succeeded",
    ]


def test_failed_run_records_failure_without_copying_prefect_logs(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)

    with pytest.raises(ResearchLaunchInvocationError):
        service.launch_fixture(
            configuration_id=configuration_id,
            run_id="qf-events-failed",
            fail_after_run_start=True,
        )

    events = service.events_for_run("qf-events-failed")
    assert [event.event_type for event in events] == [
        "run_created",
        "run_started",
        "run_failed",
    ]
    assert events[-1].severity == "error"
    assert events[-1].message == "Run failed; see the Prefect reference for technical details."
    assert "controlled Prefect fixture failure" not in events[-1].message


def test_events_are_append_only_and_chronologically_ordered(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-events-append-only")

    events = service.events_for_run("qf-events-append-only")
    assert [event.event_id for event in events] == sorted(event.event_id for event in events)
    assert [event.timestamp for event in events] == sorted(event.timestamp for event in events)

    persistence = PersistenceService(database)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            persistence.connection.execute(
                "UPDATE run_operator_events SET message='changed' WHERE event_id=?",
                (events[0].event_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            persistence.connection.execute(
                "DELETE FROM run_operator_events WHERE event_id=?", (events[0].event_id,)
            )
    finally:
        persistence.close()


def test_event_query_methods_filter_one_run_and_recent_events(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-events-one")
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-events-two")

    one = service.events_for_run("qf-events-one")
    assert len(one) == 3
    assert {event.run_id for event in one} == {"qf-events-one"}

    recent = service.recent_events(limit=2)
    assert len(recent) == 2
    assert all(event.run_id in {"qf-events-one", "qf-events-two"} for event in recent)
    with pytest.raises(ValueError, match="positive"):
        service.recent_events(limit=0)


def test_mismatched_launcher_records_service_integrity_error(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)

    def mismatched_launcher(**kwargs):
        _launcher(**kwargs)
        return PrefectFixtureResult(
            quant_factory_run_id="wrong-qf-run",
            prefect_flow_run_id="prefect-wrong-qf-run",
            configuration_id=kwargs["configuration_id"],
            deterministic_value=1729,
            attempt_count=1,
            prefect_api_url="http://127.0.0.1:4200/api",
        )

    service = FixtureRunService(database=database, fixture_launcher=mismatched_launcher)
    with pytest.raises(ResearchLaunchInvocationError):
        service.launch_fixture(configuration_id=configuration_id, run_id="qf-events-integrity")

    events = service.events_for_run("qf-events-integrity")
    assert [event.event_type for event in events] == [
        "run_created",
        "run_started",
        "run_succeeded",
        "service_integrity_error",
    ]
    assert events[-1].severity == "error"
    assert events[-1].message == "Fixture launcher returned a mismatched Quant Factory run ID."
