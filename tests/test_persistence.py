"""Deterministic tests for the local experiment database."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sqlite3

import pandas as pd
import pytest

from backtesting.experiments.models import ExecutionConfig, ExperimentConfig
from backtesting.screening import ScreeningConfig
from market_data.models import DataAudit, MarketDataConfig
from persistence import (
    LATEST_SCHEMA_VERSION,
    ArtifactAvailability,
    ConfigurationRecord,
    PersistenceService,
    ReviewState,
    RunStage,
    RunStatus,
    SchemaVersionError,
    StrategyLifecycle,
    canonical_json,
    configuration_hash,
    initialize_database,
)
import persistence.database as database
from persistence.database import transaction
from persistence.models import (
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    normalized_configuration_document,
)
from persistence.service import configuration_document_from_experiment_config


def _db_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "quant_factory.sqlite3"


def _service(tmp_path: Path) -> PersistenceService:
    return PersistenceService(_db_path(tmp_path))


def _market_config(tmp_path: Path) -> MarketDataConfig:
    return MarketDataConfig(
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="fixture-provider",
        interval="1 day",
        requested_start="2020-01-01",
        end_date_policy="fixture",
        adjusted=True,
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        cache_path=tmp_path / "spy.csv",
    )


def _experiment_config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="fixture_experiment",
        strategy_id="fixture_strategy",
        parameter_combinations=({"window": 10}, {"window": 20}),
        market_data=_market_config(tmp_path),
        execution=ExecutionConfig.next_bar_open(
            initial_cash=10_000,
            fees=0.0005,
            slippage=0.0002,
            direction="longonly",
            leverage=1.0,
            accumulate=False,
            position_sizing="fixed_units",
            order_size=1.0,
        ),
        ranking_columns=("total_return", "sharpe_ratio"),
        ranking_ascending=(False, False),
        output_path=tmp_path / "result.csv",
        screening=ScreeningConfig.provisional_defaults(),
    )


def _document(tmp_path: Path, *, window: int = 10) -> dict:
    return normalized_configuration_document(
        experiment_id="fixture_experiment",
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        market_data={"symbol": "SPY", "provider": "fixture"},
        parameters=({"window": window},),
        execution={"mode": "next_bar_open"},
        ranking={"columns": ("total_return",), "ascending": (False,)},
        screening={"minimum_trades": 1},
    )


def _register_strategy(service: PersistenceService):
    return service.register_strategy(
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        display_name="Fixture Strategy",
        description="Synthetic persistence fixture",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )


def _audit() -> DataAudit:
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="fixture-provider",
        interval="1 day",
        requested_start="2020-01-01",
        requested_dynamic_end_policy="fixture",
        latest_completed_exchange_session="2020-01-10",
        prices_adjusted=True,
        adjustment_verification="fixture",
        download_time="2026-07-09T00:00:00Z",
        download_timezone="America/New_York",
        actual_first_row_date="2020-01-02",
        actual_last_row_date="2020-01-10",
        row_count=7,
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
        unexpected_session_gaps=[],
        provider_warnings=[],
        cache_path="fixture",
        cache_action="reused",
        cache_decision_reason="fixture",
    )


def _fixture_result():
    ranked = pd.DataFrame(
        [
            {
                "parameter_row_id": "row_a",
                "window": 10,
                "total_return": 0.12,
                "annualized_return": 0.10,
                "sharpe_ratio": 1.2,
                "max_drawdown": -0.05,
                "number_of_trades": 22,
                "win_rate": 0.6,
                "screening_status": "passed",
                "screening_rejection_reasons": "",
            },
            {
                "parameter_row_id": "row_b",
                "window": 20,
                "total_return": -0.02,
                "annualized_return": -0.03,
                "sharpe_ratio": -0.1,
                "max_drawdown": -0.20,
                "number_of_trades": 5,
                "win_rate": 0.4,
                "screening_status": "screened_out",
                "screening_rejection_reasons": "too few trades",
            },
        ]
    )
    screening = (
        SimpleNamespace(
            parameter_row_id="row_a",
            normalized_parameters={"window": 10},
            passed=True,
        ),
        SimpleNamespace(
            parameter_row_id="row_b",
            normalized_parameters={"window": 20},
            passed=False,
        ),
    )
    return SimpleNamespace(
        ranked_results=ranked,
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        strategy_name="Fixture Strategy",
        screening_results=screening,
        market_data_audit=_audit(),
        execution_assumptions={
            "mode": "next_bar_open",
            "fees": 0.0005,
            "direction": "longonly",
        },
    )


def test_fresh_database_initialization_schema_version_and_restart(tmp_path):
    path = _db_path(tmp_path)
    connection = initialize_database(path)
    version = connection.execute(
        "SELECT schema_version FROM schema_metadata"
    ).fetchone()["schema_version"]
    assert version == LATEST_SCHEMA_VERSION
    connection.close()

    restarted = initialize_database(path)
    assert restarted.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    restarted.close()


def test_default_database_path_is_anchored_to_repository_root(tmp_path, monkeypatch):
    monkeypatch.delenv(database.ENV_DATABASE_PATH, raising=False)
    monkeypatch.chdir(tmp_path)
    assert database.database_path() == (
        Path(database.__file__).resolve().parents[1]
        / "state"
        / "quant_factory.sqlite3"
    )

    explicit = tmp_path / "explicit.sqlite3"
    assert database.database_path(explicit) == explicit

    override = tmp_path / "override.sqlite3"
    monkeypatch.setenv(database.ENV_DATABASE_PATH, str(override))
    assert database.database_path() == override


def test_migration_failure_leaves_no_partial_schema(tmp_path, monkeypatch):
    path = _db_path(tmp_path)
    monkeypatch.setattr(
        database,
        "MIGRATION_001_STATEMENTS",
        database.MIGRATION_001_STATEMENTS[:2]
        + ("INSERT INTO missing_table VALUES (1)",)
        + database.MIGRATION_001_STATEMENTS[2:],
    )
    with pytest.raises(sqlite3.Error):
        database.initialize_database(path)

    connection = sqlite3.connect(path)
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    connection.close()
    assert tables == []


def test_initialize_database_closes_connection_on_schema_error(tmp_path, monkeypatch):
    class TrackingConnection(sqlite3.Connection):
        closed = False

        def close(self):
            type(self).closed = True
            super().close()

    path = tmp_path / "newer.sqlite3"
    setup = sqlite3.connect(path)
    setup.execute(
        "CREATE TABLE schema_metadata (schema_version INTEGER PRIMARY KEY, migration_id TEXT, applied_at TEXT)"
    )
    setup.execute(
        "INSERT INTO schema_metadata VALUES (?, ?, ?)",
        (LATEST_SCHEMA_VERSION + 1, "future", "2026-01-01T00:00:00Z"),
    )
    setup.commit()
    setup.close()

    def tracking_connect(path_arg=None):
        connection = sqlite3.connect(path, factory=TrackingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    monkeypatch.setattr(database, "connect", tracking_connect)
    with pytest.raises(SchemaVersionError):
        database.initialize_database(path)
    assert TrackingConnection.closed is True


def test_records_persist_across_restart(tmp_path):
    path = _db_path(tmp_path)
    service = PersistenceService(path)
    _register_strategy(service)
    service.close()

    restarted = PersistenceService(path)
    strategy = restarted.strategies.get("fixture_strategy", "1.0.0")
    assert strategy is not None
    assert strategy.display_name == "Fixture Strategy"
    restarted.close()


def test_foreign_key_enforcement_and_transaction_rollback(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        service.runs.create(
            run_id="bad",
            configuration_id="missing",
            strategy_id="fixture_strategy",
            strategy_version="1.0.0",
            stage=RunStage.FIXTURE,
        )
    service.connection.rollback()

    with pytest.raises(RuntimeError):
        with transaction(service.connection):
            service.strategies.upsert(
                strategy_id="fixture_strategy",
                strategy_version="1.0.0",
                display_name="Fixture Strategy",
                description="Synthetic persistence fixture",
                lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
            )
            raise RuntimeError("rollback")
    assert service.strategies.list() == ()


def test_canonical_json_and_configuration_hash_are_deterministic():
    left = {"b": (2, 3), "a": {"z": 1}}
    right = {"a": {"z": 1}, "b": [2, 3]}
    assert canonical_json(left) == canonical_json(right)
    assert configuration_hash(left) == configuration_hash(right)
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json({"bad": float("nan")})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_experiment_config_adapter_rejects_non_finite_values(value):
    config = SimpleNamespace(
        experiment_id="bad_config",
        strategy_id="fixture_strategy",
        market_data={"symbol": "SPY"},
        parameter_combinations=({"window": 10},),
        execution={"order_size": value},
        ranking_columns=("total_return",),
        ranking_ascending=(False,),
        parameter_output_names=(),
        screening={"minimum_trades": 1},
    )
    with pytest.raises(ValueError, match="non-finite"):
        configuration_document_from_experiment_config(
            config,
            strategy_version="1.0.0",
        )


def test_configuration_deduplication_and_collision_rejection(tmp_path):
    service = _service(tmp_path)
    _register_strategy(service)
    first = service.upsert_configuration(_document(tmp_path))
    second = service.upsert_configuration(_document(tmp_path))
    assert first.configuration_id == second.configuration_id

    conflicting = ConfigurationRecord(
        configuration_id=first.configuration_id,
        experiment_id=first.experiment_id,
        strategy_id=first.strategy_id,
        strategy_version=first.strategy_version,
        canonical_config_json=canonical_json(_document(tmp_path, window=99)),
        config_hash=configuration_hash(_document(tmp_path, window=99)),
        created_at=first.created_at,
    )
    with pytest.raises(ValueError, match="collision"):
        with transaction(service.connection):
            service.configurations.insert_record(conflicting)


def test_strategy_lifecycle_validation(tmp_path):
    service = _service(tmp_path)
    strategy = _register_strategy(service)
    assert strategy.lifecycle == StrategyLifecycle.INFRASTRUCTURE_FIXTURE
    updated = service.update_strategy_lifecycle(
        "fixture_strategy",
        "1.0.0",
        lifecycle=StrategyLifecycle.WATCHLIST,
        active=False,
    )
    assert updated.lifecycle == StrategyLifecycle.WATCHLIST
    assert updated.active is False
    with pytest.raises(ValueError):
        service.register_strategy(
            strategy_id="bad",
            strategy_version="1.0.0",
            display_name="Bad",
            description="Bad",
            lifecycle="not_a_state",
        )


def test_run_creation_and_status_transitions(tmp_path):
    service = _service(tmp_path)
    _register_strategy(service)
    config = service.upsert_configuration(_document(tmp_path))
    run = service.create_run(
        configuration_id=config.configuration_id,
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        stage=RunStage.FIXTURE,
        run_id="run_1",
    )
    assert run.status == RunStatus.CREATED
    assert service.transition_run("run_1", RunStatus.RUNNING).status == RunStatus.RUNNING
    assert service.transition_run("run_1", RunStatus.SUCCEEDED).status == RunStatus.SUCCEEDED
    with pytest.raises(ValueError, match="invalid run-status transition"):
        service.transition_run("run_1", RunStatus.RUNNING)


def test_invalid_direct_terminal_transition(tmp_path):
    service = _service(tmp_path)
    _register_strategy(service)
    config = service.upsert_configuration(_document(tmp_path))
    service.create_run(
        configuration_id=config.configuration_id,
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        stage=RunStage.FIXTURE,
        run_id="run_cancelled",
    )
    assert service.transition_run("run_cancelled", RunStatus.CANCELLED).status == RunStatus.CANCELLED
    with pytest.raises(ValueError):
        service.transition_run("run_cancelled", RunStatus.FAILED)


def test_parameter_rows_provenance_execution_artifacts_and_review(tmp_path):
    service = _service(tmp_path)
    _register_strategy(service)
    config = service.upsert_configuration(_document(tmp_path))
    run = service.create_run(
        configuration_id=config.configuration_id,
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        stage=RunStage.FIXTURE,
        run_id="run_rows",
    )
    service.results.add_parameter_result(
        run_id=run.run_id,
        row_id="row_1",
        normalized_parameters={"window": 10},
        metrics={"total_return": 0.1, "number_of_trades": 3},
        ranking_position=1,
        screening_status="passed",
    )
    service.connection.commit()
    assert service.results.list_parameter_results(run.run_id)[0].ranking_position == 1

    provenance = DataProvenanceRecord(
        run_id=run.run_id,
        provider="fixture",
        provider_implementation="fixture-provider",
        symbol="SPY",
        interval="1 day",
        timezone="America/New_York",
        requested_coverage="2020-01-01",
        actual_coverage="2020-01-02..2020-01-10",
        adjusted=True,
        row_count=7,
        cache_action="reused",
        validation_summary_json=canonical_json({"duplicates": 0}),
        manifest_reference="data/manifests/fixture.json",
        checksum="abc",
    )
    service.results.set_data_provenance(provenance)
    service.connection.commit()
    assert service.results.get_data_provenance(run.run_id).adjusted is True

    service.results.set_execution_assumptions(
        ExecutionAssumptionsRecord(
            run_id=run.run_id,
            assumptions_json=canonical_json({"fees": 0.1}),
        )
    )
    service.connection.commit()
    assert "fees" in service.results.get_execution_assumptions(run.run_id).assumptions_json

    artifact = service.results.add_artifact(
        run_id=run.run_id,
        artifact_type="fixture_json",
        schema_version=1,
        path="results/fixture.json",
        validation_status="validated",
        availability=ArtifactAvailability.AVAILABLE,
    )
    service.connection.commit()
    assert artifact.availability == ArtifactAvailability.AVAILABLE
    missing = service.results.add_artifact(
        run_id=run.run_id,
        artifact_type="fixture_json",
        schema_version=1,
        path="results/missing.json",
        validation_status="missing",
        availability=ArtifactAvailability.MISSING,
    )
    corrupt = service.results.add_artifact(
        run_id=run.run_id,
        artifact_type="fixture_json",
        schema_version=1,
        path="results/corrupt.json",
        validation_status="corrupt",
        availability=ArtifactAvailability.CORRUPT,
    )
    service.connection.commit()
    assert {missing.availability, corrupt.availability} == {
        ArtifactAvailability.MISSING,
        ArtifactAvailability.CORRUPT,
    }

    review = service.update_review(
        target_type="run",
        target_id=run.run_id,
        state=ReviewState.INFRASTRUCTURE_FIXTURE,
        note="fixture",
    )
    assert review.state == ReviewState.INFRASTRUCTURE_FIXTURE
    second = service.update_review(
        target_type="run",
        target_id=run.run_id,
        state=ReviewState.WATCHLIST,
        note="watch",
    )
    assert second.state == ReviewState.WATCHLIST
    history = service.reviews.history("run", run.run_id)
    assert [row["new_state"] for row in history] == [
        "infrastructure_fixture",
        "watchlist",
    ]


def test_complete_fixture_result_persistence_and_dashboard_queries(tmp_path):
    service = _service(tmp_path)
    run = service.persist_experiment_result(
        config=_experiment_config(tmp_path),
        result=_fixture_result(),
        stage=RunStage.FIXTURE,
        artifact_path="results/fixture.csv",
        run_id="run_fixture",
    )
    assert run.status == RunStatus.SUCCEEDED
    assert service.configurations.list(strategy_id="fixture_strategy")
    assert len(service.results.list_parameter_results(run.run_id)) == 2
    assert service.runs.list(strategy_id="fixture_strategy", status=RunStatus.SUCCEEDED)

    detail = service.run_detail(run.run_id)
    assert detail["run"]["run_id"] == "run_fixture"
    assert detail["provenance"]["provider"] == "Yahoo Finance"
    assert detail["artifacts"][0]["availability"] == "available"
    assert detail["review"]["state"] == "infrastructure_fixture"

    with pytest.raises(ValueError, match="at least two runs"):
        service.compare_runs(("run_fixture",))
    second = service.persist_experiment_result(
        config=_experiment_config(tmp_path),
        result=_fixture_result(),
        stage=RunStage.FIXTURE,
        artifact_path="results/fixture-copy.csv",
        run_id="run_fixture_copy",
    )
    comparison = service.compare_runs((run.run_id, second.run_id))
    assert comparison[0]["parameter_count"] == 2
    assert comparison[1]["parameter_count"] == 2
    assert any(field["state"] == "equal" for field in comparison[0]["fields"])


def test_run_detail_allows_absent_optional_records(tmp_path, monkeypatch):
    service = _service(tmp_path)
    strategy = _register_strategy(service)
    configuration = service.upsert_configuration(_document(tmp_path))
    run = service.create_run(
        configuration_id=configuration.configuration_id,
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.strategy_version,
        stage=RunStage.FIXTURE,
        run_id="run_without_optional_records",
    )
    monkeypatch.setattr(service.configurations, "get", lambda _: None)
    monkeypatch.setattr(service.strategies, "get", lambda *_: None)

    detail = service.run_detail(run.run_id)

    assert detail["configuration"] is None
    assert detail["strategy"] is None
    assert detail["provenance"] is None
    assert detail["execution_assumptions"] is None


def test_complete_fixture_result_transaction_rolls_back(tmp_path, monkeypatch):
    service = _service(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("artifact failed")

    monkeypatch.setattr(service.results, "add_artifact", fail)
    with pytest.raises(RuntimeError, match="artifact failed"):
        service.persist_experiment_result(
            config=_experiment_config(tmp_path),
            result=_fixture_result(),
            stage=RunStage.FIXTURE,
            artifact_path="results/fixture.csv",
            run_id="run_rollback",
        )
    assert service.runs.get("run_rollback") is None
    assert service.strategies.list() == ()


def test_corrupt_and_newer_schema_fail_clearly(tmp_path):
    corrupt = tmp_path / "corrupt.sqlite3"
    connection = sqlite3.connect(corrupt)
    connection.execute("CREATE TABLE orphan (id INTEGER)")
    connection.commit()
    connection.close()
    with pytest.raises(SchemaVersionError, match="no schema metadata"):
        initialize_database(corrupt)

    newer = tmp_path / "newer.sqlite3"
    connection = sqlite3.connect(newer)
    connection.execute(
        "CREATE TABLE schema_metadata (schema_version INTEGER PRIMARY KEY, migration_id TEXT, applied_at TEXT)"
    )
    connection.execute(
        "INSERT INTO schema_metadata VALUES (?, ?, ?)",
        (LATEST_SCHEMA_VERSION + 1, "future", "2026-01-01T00:00:00Z"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(SchemaVersionError, match="newer than supported"):
        initialize_database(newer)


def test_database_and_sidecar_files_are_git_ignored():
    import subprocess

    paths = [
        "state/quant_factory.sqlite3",
        "state/quant_factory.sqlite3-wal",
        "state/quant_factory.sqlite3-shm",
    ]
    completed = subprocess.run(
        ["git", "check-ignore", *paths],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.splitlines() == paths
