"""Server-independent tests for the bounded Prefect compatibility spike.

The normal suite exercises mapping and persistence behavior with controlled
inputs. The live test at the bottom requires an explicitly configured external
``PREFECT_API_URL`` and never starts an ephemeral Prefect server.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from persistence import PersistenceService, RunStatus, StrategyLifecycle
from persistence.models import normalized_configuration_document
from prefect_spike.fixture_flow import (
    PREFECT_AVAILABLE,
    deterministic_fixture_body,
    ensure_prefect_available,
    map_prefect_state_to_quant_factory,
)
from prefect_spike.live_verification import run_live_verification
from prefect_spike.live_verification import run_live_timeout_verification
import prefect_spike.fixture_flow as fixture_flow


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "prefect_spike.sqlite3"


def _registered_configuration(tmp_path: Path) -> tuple[Path, str]:
    database_path = _db_path(tmp_path)
    service = PersistenceService(database_path)
    try:
        service.register_strategy(
            strategy_id="prefect_fixture_strategy",
            strategy_version="1.0.0",
            display_name="Prefect Fixture Strategy",
            description="Synthetic Prefect compatibility fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        document = normalized_configuration_document(
            experiment_id="prefect_fixture_experiment",
            strategy_id="prefect_fixture_strategy",
            strategy_version="1.0.0",
            market_data={"kind": "none", "reason": "server-independent fixture"},
            parameters={"fixture": True},
            execution={"kind": "prefect_spike_fixture"},
            ranking={"columns": ("deterministic_value",), "ascending": (False,)},
            screening={"kind": "none"},
        )
        configuration = service.upsert_configuration(document)
        return database_path, configuration.configuration_id
    finally:
        service.close()


def _service(path: Path) -> PersistenceService:
    return PersistenceService(path)


def test_server_independent_state_mapping_from_names_and_objects() -> None:
    assert map_prefect_state_to_quant_factory("Pending") == RunStatus.CREATED
    assert map_prefect_state_to_quant_factory("Scheduled") == RunStatus.CREATED
    assert map_prefect_state_to_quant_factory("Running") == RunStatus.RUNNING
    assert map_prefect_state_to_quant_factory("Completed") == RunStatus.SUCCEEDED
    assert map_prefect_state_to_quant_factory("Failed") == RunStatus.FAILED
    assert map_prefect_state_to_quant_factory("Crashed") == RunStatus.FAILED
    assert map_prefect_state_to_quant_factory("Cancelled") == RunStatus.CANCELLED
    assert map_prefect_state_to_quant_factory(SimpleNamespace(name="Timed Out")) == RunStatus.FAILED
    assert map_prefect_state_to_quant_factory(SimpleNamespace(name="Cancelling")) == RunStatus.CANCELLED

    with pytest.raises(ValueError, match="unsupported Prefect state"):
        map_prefect_state_to_quant_factory(SimpleNamespace(name="Paused"))


def test_server_independent_prefect_and_quant_factory_ids_remain_distinct(tmp_path: Path) -> None:
    database_path, configuration_id = _registered_configuration(tmp_path)
    result = deterministic_fixture_body(
        database_path=database_path,
        configuration_id=configuration_id,
        quant_factory_run_id="qf-run-1",
        prefect_flow_run_id="prefect-flow-run-1",
        prefect_api_url="http://127.0.0.1:4200/api",
    )

    assert result.quant_factory_run_id == "qf-run-1"
    assert result.prefect_flow_run_id == "prefect-flow-run-1"
    assert result.quant_factory_run_id != result.prefect_flow_run_id

    service = _service(database_path)
    try:
        run = service.runs.get("qf-run-1")
        assert run is not None
        assert run.status == RunStatus.SUCCEEDED
        environment = json.loads(run.environment_json)
        assert environment["prefect_identity_storage"] == "technical_run_environment"
        assert environment["prefect_flow_run_id"] == "prefect-flow-run-1"
        assert service.results.list_artifacts("qf-run-1") == ()
    finally:
        service.close()


def test_server_independent_persistence_adapter_writes_deterministic_result(
    tmp_path: Path,
) -> None:
    database_path, configuration_id = _registered_configuration(tmp_path)
    deterministic_fixture_body(
        database_path=database_path,
        configuration_id=configuration_id,
        quant_factory_run_id="qf-run-result",
        prefect_flow_run_id="prefect-flow-run-result",
        deterministic_value=1729,
    )

    service = _service(database_path)
    try:
        rows = service.results.list_parameter_results("qf-run-result")
        assert len(rows) == 1
        assert rows[0].row_id == "prefect_fixture:qf-run-result"
        assert json.loads(rows[0].normalized_parameters_json) == {
            "configuration_id": configuration_id
        }
        assert json.loads(rows[0].metrics_json) == {
            "attempt_count": 1,
            "deterministic_value": 1729,
        }
    finally:
        service.close()


def test_server_independent_reconciliation_uses_state_mapping(tmp_path: Path, monkeypatch) -> None:
    database_path, configuration_id = _registered_configuration(tmp_path)
    deterministic_fixture_body(
        database_path=database_path,
        configuration_id=configuration_id,
        quant_factory_run_id="qf-run-reconcile",
        prefect_flow_run_id="prefect-flow-run-reconcile",
    )

    calls: list[object] = []

    def fake_map(state: object) -> RunStatus:
        calls.append(state)
        return RunStatus.SUCCEEDED

    monkeypatch.setattr(fixture_flow, "map_prefect_state_to_quant_factory", fake_map)
    service = _service(database_path)
    try:
        record = fixture_flow.reconcile_quant_factory_run_status(
            service,
            quant_factory_run_id="qf-run-reconcile",
            prefect_state=SimpleNamespace(name="Completed"),
        )
        assert record.status == RunStatus.SUCCEEDED
        assert calls == [SimpleNamespace(name="Completed")]
    finally:
        service.close()


def test_server_independent_failed_run_error_summary(tmp_path: Path) -> None:
    database_path, configuration_id = _registered_configuration(tmp_path)

    with pytest.raises(RuntimeError, match="controlled Prefect fixture failure"):
        deterministic_fixture_body(
            database_path=database_path,
            configuration_id=configuration_id,
            quant_factory_run_id="qf-run-failed",
            prefect_flow_run_id="prefect-flow-run-failed",
            fail_after_run_start=True,
        )

    service = _service(database_path)
    try:
        run = service.runs.get("qf-run-failed")
        assert run is not None
        assert run.status == RunStatus.FAILED
        assert run.error_summary == "controlled Prefect fixture failure"
        assert service.results.list_parameter_results("qf-run-failed") == ()
    finally:
        service.close()


def test_server_independent_duplicate_configuration_prevention(tmp_path: Path) -> None:
    database_path, configuration_id = _registered_configuration(tmp_path)
    service = _service(database_path)
    try:
        original_count = len(service.configurations.list(strategy_id="prefect_fixture_strategy"))
    finally:
        service.close()

    deterministic_fixture_body(
        database_path=database_path,
        configuration_id=configuration_id,
        quant_factory_run_id="qf-run-a",
        prefect_flow_run_id="prefect-run-a",
    )
    deterministic_fixture_body(
        database_path=database_path,
        configuration_id=configuration_id,
        quant_factory_run_id="qf-run-b",
        prefect_flow_run_id="prefect-run-b",
    )

    service = _service(database_path)
    try:
        configurations = service.configurations.list(strategy_id="prefect_fixture_strategy")
        assert len(configurations) == original_count
        assert configurations[0].configuration_id == configuration_id
    finally:
        service.close()


def test_server_independent_timeout_and_cancellation_mapping_from_controlled_states() -> None:
    assert map_prefect_state_to_quant_factory(SimpleNamespace(name="TimedOut")) == RunStatus.FAILED
    assert map_prefect_state_to_quant_factory(SimpleNamespace(name="Cancelled")) == RunStatus.CANCELLED


def test_server_independent_graceful_behavior_when_prefect_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(fixture_flow, "PREFECT_AVAILABLE", False)

    with pytest.raises(RuntimeError, match="Prefect is not available"):
        ensure_prefect_available()


def test_live_external_prefect_retry_success_path(tmp_path: Path) -> None:
    if not os.environ.get("PREFECT_API_URL"):
        pytest.skip(
            "PREFECT_API_URL is required for live external Prefect verification; "
            "the test intentionally never starts an ephemeral server."
        )
    if not PREFECT_AVAILABLE:
        pytest.fail("Prefect is not importable, so the live external verification cannot run.")

    database_path = _db_path(tmp_path)
    result = run_live_verification(
        database_path=database_path,
        run_id="qf-live-run",
        attempt_marker_path=tmp_path / "attempts" / "retry.txt",
    )

    assert result.quant_factory_run_id == "qf-live-run"
    assert result.prefect_flow_run_id != result.quant_factory_run_id
    assert result.attempt_count == 1
    assert result.prefect_logs_found
    assert result.prefect_state_name
    service = _service(database_path)
    try:
        run = service.runs.get("qf-live-run")
        assert run is not None
        assert run.status == RunStatus.SUCCEEDED
    finally:
        service.close()


def test_live_external_prefect_timeout_path(tmp_path: Path) -> None:
    if not os.environ.get("PREFECT_API_URL"):
        pytest.skip(
            "PREFECT_API_URL is required for live external Prefect verification; "
            "the test intentionally never starts an ephemeral server."
        )
    if not PREFECT_AVAILABLE:
        pytest.fail("Prefect is not importable, so the live external verification cannot run.")

    timeout = run_live_timeout_verification(
        database_path=_db_path(tmp_path),
        run_id="qf-live-timeout",
        timeout_seconds=1.0,
    )
    assert timeout.quant_factory_run_id == "qf-live-timeout"
    assert timeout.prefect_flow_run_id != timeout.quant_factory_run_id
    assert timeout.quant_factory_status == RunStatus.FAILED.value
    assert timeout.prefect_state_name

    service = _service(_db_path(tmp_path))
    try:
        timeout_run = service.runs.get("qf-live-timeout")
        assert timeout_run is not None
        assert timeout_run.status == RunStatus.FAILED
        assert timeout_run.status != RunStatus.RUNNING
        assert timeout_run.error_summary
    finally:
        service.close()
