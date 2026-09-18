"""Focused tests for Milestone 18A's minimum fixture run service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestration import FixtureRunService, RunServiceError
from persistence import PersistenceService, RunStage, RunStatus, StrategyLifecycle
from persistence.models import normalized_configuration_document
from prefect_spike.fixture_flow import PrefectFixtureResult, deterministic_fixture_body


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "slice_18a.sqlite3"


def _configuration(tmp_path: Path) -> tuple[Path, str]:
    database = _db_path(tmp_path)
    service = PersistenceService(database)
    try:
        service.register_strategy(
            strategy_id="prefect_fixture_strategy",
            strategy_version="1.0.0",
            display_name="Prefect Fixture Strategy",
            description="Synthetic fixture for Slice 18A",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="slice_18a_fixture",
                strategy_id="prefect_fixture_strategy",
                strategy_version="1.0.0",
                market_data={"kind": "none"},
                parameters={"fixture": True},
                execution={"kind": "prefect_fixture"},
                ranking={"columns": ("deterministic_value",), "ascending": (False,)},
                screening={"kind": "none"},
            )
        )
        return database, configuration.configuration_id
    finally:
        service.close()


def _launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def test_successful_launch_records_separate_prefect_identity(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)

    result = service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-success")

    assert result.run.run_id == "qf-run-success"
    assert result.run.status == RunStatus.SUCCEEDED.value
    assert result.prefect_result is not None
    assert result.prefect_result.prefect_flow_run_id == "prefect-qf-run-success"
    assert result.run.prefect_flow_run_id == "prefect-qf-run-success"
    assert result.run.prefect_flow_run_id != result.run.run_id

    persisted = service.get_run("qf-run-success")
    assert persisted == result.run


def test_failed_launch_reconciles_to_failed_run(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)

    result = service.launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-run-failed",
        fail_after_run_start=True,
    )

    assert result.prefect_result is None
    assert result.run.status == RunStatus.FAILED.value
    assert result.run.error_summary == "controlled Prefect fixture failure"
    assert result.run.prefect_flow_run_id == "prefect-qf-run-failed"


def test_duplicate_run_launch_is_rejected_without_relaunch(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    launches: list[str] = []

    def launcher(**kwargs):
        launches.append(kwargs["quant_factory_run_id"])
        return _launcher(**kwargs)

    service = FixtureRunService(database=database, fixture_launcher=launcher)
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-once")

    with pytest.raises(ValueError, match="Quant Factory run already exists"):
        service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-once")

    assert launches == ["qf-run-once"]


def test_missing_configuration_fails_before_launch(tmp_path: Path) -> None:
    database = _db_path(tmp_path)
    called = False

    def launcher(**kwargs):
        nonlocal called
        called = True
        return _launcher(**kwargs)

    service = FixtureRunService(database=database, fixture_launcher=launcher)

    with pytest.raises(KeyError, match="unknown Quant Factory configuration"):
        service.launch_fixture(configuration_id="missing", run_id="qf-run-missing-config")

    assert not called


def test_configuration_reuse_does_not_duplicate_configuration(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)

    service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-a")
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-b")

    persistence = PersistenceService(database)
    try:
        configurations = persistence.configurations.list(strategy_id="prefect_fixture_strategy")
        assert len(configurations) == 1
        assert configurations[0].configuration_id == configuration_id
    finally:
        persistence.close()


def test_query_methods_return_one_run_and_recent_runs(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-one")
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-two")

    one = service.get_run("qf-run-one")
    assert one is not None
    assert one.run_id == "qf-run-one"
    assert one.status == RunStatus.SUCCEEDED.value

    recent = service.recent_runs(limit=1)
    assert len(recent) == 1
    assert recent[0].run_id in {"qf-run-one", "qf-run-two"}

    all_recent = service.recent_runs(limit=10)
    assert {run.run_id for run in all_recent} == {"qf-run-one", "qf-run-two"}

    with pytest.raises(ValueError, match="positive"):
        service.recent_runs(limit=0)


def test_prefect_reference_is_only_technical_metadata_not_artifact(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-metadata")

    persistence = PersistenceService(database)
    try:
        run = persistence.runs.get("qf-run-metadata")
        assert run is not None
        environment = json.loads(run.environment_json)
        assert environment["prefect_identity_storage"] == "technical_run_environment"
        assert environment["prefect_flow_run_id"] == "prefect-qf-run-metadata"
        assert persistence.results.list_artifacts("qf-run-metadata") == ()
    finally:
        persistence.close()


def test_launcher_failure_before_persistence_is_reported(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)

    def broken_launcher(**kwargs):
        raise RuntimeError("fixture did not start")

    service = FixtureRunService(database=database, fixture_launcher=broken_launcher)

    with pytest.raises(RunServiceError, match="failed without terminal run"):
        service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-no-record")


def test_launcher_failure_with_nonterminal_run_is_rejected(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)

    def broken_after_created(**kwargs):
        persistence = PersistenceService(database)
        try:
            configuration = persistence.configurations.get(kwargs["configuration_id"])
            assert configuration is not None
            persistence.create_run(
                configuration_id=configuration.configuration_id,
                strategy_id=configuration.strategy_id,
                strategy_version=configuration.strategy_version,
                stage=RunStage.FIXTURE,
                run_id=kwargs["quant_factory_run_id"],
                status=RunStatus.CREATED,
                environment={"prefect_flow_run_id": "prefect-started"},
            )
        finally:
            persistence.close()
        raise RuntimeError("fixture stopped before terminal state")

    service = FixtureRunService(database=database, fixture_launcher=broken_after_created)

    with pytest.raises(RunServiceError, match="failed without terminal run"):
        service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-created")

    persisted = service.get_run("qf-run-created")
    assert persisted is not None
    assert persisted.status == RunStatus.CREATED.value


def test_successful_launcher_must_return_requested_quant_factory_run_id(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)

    def mismatched_launcher(**kwargs):
        _launcher(**kwargs)
        return PrefectFixtureResult(
            quant_factory_run_id="different-run-id",
            prefect_flow_run_id="prefect-different-run-id",
            configuration_id=kwargs["configuration_id"],
            deterministic_value=1729,
            attempt_count=1,
            prefect_api_url="http://127.0.0.1:4200/api",
        )

    service = FixtureRunService(database=database, fixture_launcher=mismatched_launcher)

    with pytest.raises(RunServiceError, match="mismatched Quant Factory run ID"):
        service.launch_fixture(configuration_id=configuration_id, run_id="qf-run-requested")
