"""Focused Slice 18D tests for immutable saved-configuration fixture launches."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestration import FixtureRunService, RunServiceError
from persistence import PersistenceService, StrategyLifecycle
from persistence.models import normalized_configuration_document
from prefect_spike.fixture_flow import deterministic_fixture_body
from tests.test_run_service import _configuration


def _capturing_launcher(captured: dict[str, object]):
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


def test_active_infrastructure_saved_configuration_launches_unchanged(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    captured: dict[str, object] = {}
    service = FixtureRunService(database=database, fixture_launcher=_capturing_launcher(captured))
    persistence = PersistenceService(database)
    try:
        configuration = persistence.configurations.get(configuration_id)
        assert configuration is not None
        original = configuration.canonical_config_json
        document = json.loads(original)
    finally:
        persistence.close()

    result = service.launch_fixture(configuration_id=configuration_id, run_id="qf-saved-config")

    assert result.run.configuration_id == configuration_id
    assert result.run.strategy_id == document["strategy_id"]
    assert result.run.strategy_version == document["strategy_version"]
    assert result.run.prefect_flow_run_id == "prefect-qf-saved-config"
    assert result.run.prefect_flow_run_id != result.run.run_id
    assert captured == {
        "parameters": document["parameters"],
        "execution": document["execution"],
    }
    persistence = PersistenceService(database)
    try:
        unchanged = persistence.configurations.get(configuration_id)
        assert unchanged is not None
        assert unchanged.canonical_config_json == original
    finally:
        persistence.close()


@pytest.mark.parametrize(
    ("active", "lifecycle"),
    [
        (False, StrategyLifecycle.INFRASTRUCTURE_FIXTURE),
        (True, StrategyLifecycle.CANDIDATE),
    ],
)
def test_non_launchable_saved_configuration_fails_before_run_creation(
    tmp_path: Path,
    active: bool,
    lifecycle: StrategyLifecycle,
) -> None:
    database = tmp_path / "state" / "saved.sqlite3"
    persistence = PersistenceService(database)
    try:
        persistence.register_strategy(
            strategy_id="not_launchable",
            strategy_version="1.0.0",
            display_name="Not launchable",
            description="fixture",
            lifecycle=lifecycle,
            active=active,
        )
        configuration = persistence.upsert_configuration(
            normalized_configuration_document(
                experiment_id="saved",
                strategy_id="not_launchable",
                strategy_version="1.0.0",
                market_data={"kind": "none"},
                parameters={"window": 9},
                execution={"mode": "fixture"},
                ranking={"columns": (), "ascending": ()},
                screening={"kind": "none"},
            )
        )
    finally:
        persistence.close()
    called = False

    def launcher(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not launch")

    service = FixtureRunService(database=database, fixture_launcher=launcher)
    with pytest.raises(RunServiceError, match="not launchable"):
        service.launch_fixture(configuration_id=configuration.configuration_id, run_id="qf-not-launchable")
    assert not called
    assert service.get_run("qf-not-launchable") is None


def test_unknown_mismatched_and_duplicate_saved_configuration_launches_fail_safely(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_capturing_launcher({}))

    with pytest.raises(KeyError, match="unknown Quant Factory configuration"):
        service.launch_fixture(configuration_id="missing", run_id="qf-missing-config")
    assert service.get_run("qf-missing-config") is None

    persistence = PersistenceService(database)
    try:
        persistence.connection.execute("PRAGMA foreign_keys = OFF")
        persistence.connection.execute(
            "UPDATE experiment_configurations SET strategy_version='9.9.9' WHERE configuration_id=?",
            (configuration_id,),
        )
        persistence.connection.commit()
    finally:
        persistence.close()
    with pytest.raises(RunServiceError, match="mismatched strategy identity"):
        service.launch_fixture(configuration_id=configuration_id, run_id="qf-mismatched-config")
    assert service.get_run("qf-mismatched-config") is None

    persistence = PersistenceService(database)
    try:
        record = persistence.configurations.get(configuration_id)
        assert record is not None
        document = json.loads(record.canonical_config_json)
        document["strategy_version"] = "9.9.9"
        persistence.connection.execute(
            "UPDATE experiment_configurations SET canonical_config_json=? WHERE configuration_id=?",
            (json.dumps(document, sort_keys=True, separators=(",", ":")), configuration_id),
        )
        persistence.connection.commit()
    finally:
        persistence.close()
    with pytest.raises(RunServiceError, match="unregistered strategy"):
        service.launch_fixture(configuration_id=configuration_id, run_id="qf-missing-strategy")
    assert service.get_run("qf-missing-strategy") is None

    database, configuration_id = _configuration(tmp_path / "duplicate")
    launches: list[str] = []

    def launcher(**kwargs):
        launches.append(kwargs["quant_factory_run_id"])
        return _capturing_launcher({})(**kwargs)

    service = FixtureRunService(database=database, fixture_launcher=launcher)
    first = service.launch_fixture(configuration_id=configuration_id, run_id="qf-duplicate-saved")
    before = service.get_run("qf-duplicate-saved")
    with pytest.raises(ValueError, match="already exists"):
        service.launch_fixture(configuration_id=configuration_id, run_id="qf-duplicate-saved")
    assert first.run == before
    assert launches == ["qf-duplicate-saved"]
