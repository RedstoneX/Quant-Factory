"""Full persisted run-history metadata and normalized validation outcomes."""

from __future__ import annotations

from pathlib import Path

from orchestration import FixtureRunService
from persistence import (
    ArtifactAvailability,
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    ReviewState,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.models import normalized_configuration_document
from tests.test_run_service import _configuration, _launcher


def test_all_runs_exposes_history_beyond_recent_limit(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)
    for index in range(21):
        service.launch_fixture(
            configuration_id=configuration_id,
            run_id=f"history-run-{index:02d}",
        )

    assert len(service.recent_runs(limit=20)) == 20
    history = service.all_runs()

    assert len(history) == 21
    assert {run.run_id for run in history} == {
        f"history-run-{index:02d}" for index in range(21)
    }
    assert history[0].created_at >= history[-1].created_at


def test_all_history_reports_ranked_metrics_and_metadata_without_artifact_payloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "state" / "history.sqlite3"
    service = PersistenceService(database)
    try:
        strategy = service.register_strategy(
            strategy_id="ranked_history_strategy",
            strategy_version="1.0.0",
            display_name="Ranked History Strategy",
            description="History-grid metadata fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="history_grid",
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                market_data={"provider": "fixture", "symbol": "SPY", "interval": "1d"},
                parameters={"window": 14},
                execution={"kind": "fixture"},
                ranking={"columns": ("total_return",), "ascending": (False,)},
                screening={"kind": "none"},
            )
        )
        for index in range(21):
            run_id = f"history-grid-{index:02d}"
            service.create_run(
                configuration_id=configuration.configuration_id,
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                stage=RunStage.FIXTURE,
                run_id=run_id,
                status=RunStatus.SUCCEEDED,
            )
            with transaction(service.connection):
                service.results.set_data_provenance(
                    DataProvenanceRecord(
                        run_id=run_id,
                        provider="fixture",
                        provider_implementation="history-test",
                        symbol="SPY",
                        interval="1d",
                        timezone="America/New_York",
                        requested_coverage="2024-01-01/2024-01-31",
                        actual_coverage="2024-01-01/2024-01-31",
                        adjusted=True,
                        row_count=21,
                        cache_action="fixture",
                        validation_summary_json=canonical_json({"status": "valid"}),
                        manifest_reference=f"manifest-{run_id}",
                        checksum=f"checksum-{run_id}",
                    )
                )
                service.results.set_execution_assumptions(
                    ExecutionAssumptionsRecord(
                        run_id=run_id,
                        assumptions_json=canonical_json({"kind": "fixture"}),
                    )
                )
                service.results.add_parameter_result(
                    run_id=run_id,
                    row_id=f"{run_id}-rank-1",
                    normalized_parameters={"window": 10},
                    metrics={
                        "total_return": 0.10 + index,
                        "annualized_return": 0.20 + index,
                        "sharpe_ratio": 1.5 + index,
                        "max_drawdown": -0.05,
                        "win_rate": 0.6,
                        "number_of_trades": 5 + index,
                    },
                    ranking_position=1,
                    screening_status="passed",
                )
                service.results.add_parameter_result(
                    run_id=run_id,
                    row_id=f"{run_id}-rank-2",
                    normalized_parameters={"window": 20},
                    metrics={
                        "total_return": 99.0,
                        "annualized_return": 99.0,
                        "sharpe_ratio": 99.0,
                        "number_of_trades": 99,
                    },
                    ranking_position=2,
                    screening_status="passed",
                )
            if index == 0:
                with transaction(service.connection):
                    service.reviews.update(
                        target_type="run",
                        target_id=run_id,
                        state=ReviewState.WATCHLIST,
                        note="Keep watching.",
                        operator="local-user",
                    )
                service.register_artifact(
                    run_id=run_id,
                    artifact_type=ArtifactType.VALIDATION_EVIDENCE,
                    logical_name="validation_evidence",
                    media_type="application/json",
                    format="json",
                    location=f"state/artifacts/{run_id}/validation_evidence.json",
                    content=canonical_json({"status": "passed"}).encode("utf-8"),
                    availability_state=ArtifactAvailability.AVAILABLE,
                )
                service.persist_run_manifest(service.build_run_manifest(run_id))
        with transaction(service.connection):
            service.connection.execute(
                """
                INSERT INTO run_manifests
                (run_id, schema_version, manifest_json, content_checksum, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "history-grid-20",
                    3,
                    "{not-json",
                    "invalid",
                    "2026-09-03T00:00:00Z",
                ),
            )
    finally:
        service.close()

    def reject_payload_reads(*args, **kwargs):
        raise AssertionError("history metadata must not load artifact payloads")

    monkeypatch.setattr(PersistenceService, "retrieve_run_artifacts", reject_payload_reads)

    rows = FixtureRunService(database=database).all_history()
    first = rows[0]
    last = rows[-1]

    assert len(rows) == 21
    assert first["run_id"] == "history-grid-20"
    assert first["total_return"] == 20.1
    assert first["annualized_return"] == 20.2
    assert first["sharpe_ratio"] == 21.5
    assert first["max_drawdown"] == -0.05
    assert first["win_rate"] == 0.6
    assert first["number_of_trades"] == 25
    assert first["metric_basis"] == "Top-ranked variation · Rank 1 · Screening Passed"
    assert first["instrument"] == "SPY"
    assert first["interval"] == "1d"
    assert first["strategy"] == "Ranked History Strategy"
    assert first["stage"] == "Fixture backtest"
    assert first["status"] == "Succeeded"
    assert first["review"] == "Not reviewed"
    assert first["evidence"] == "No validation evidence"
    assert first["artifact_status"] == "No registered artifacts"
    assert first["reproducibility"].startswith("Manifest invalid:")
    assert last["run_id"] == "history-grid-00"
    assert last["total_return"] == 0.10
    assert last["metric_basis"] == "Top-ranked variation · Rank 1 · Screening Passed"
    assert last["review"] == "Watchlist"
    assert last["evidence"] == "Evidence registered; outcome not applicable"
    assert last["artifact_status"] == "1 registered artifacts"
    assert last["reproducibility"] == "Manifest persisted"


def test_all_history_uses_normalized_validation_stage_outcome(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "validation-history.sqlite3"
    service = PersistenceService(database)
    try:
        strategy = service.register_strategy(
            strategy_id="validation_history_strategy",
            strategy_version="1.0.0",
            display_name="Validation History Strategy",
            description="History-grid validation outcome fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="validation_history",
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                market_data={"provider": "fixture", "symbol": "SPY", "interval": "1d"},
                parameters={"window": 14},
                execution={"kind": "fixture"},
                ranking={"columns": ("total_return",), "ascending": (False,)},
                screening={"kind": "none"},
            )
        )
        service.create_run(
            configuration_id=configuration.configuration_id,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            stage=RunStage.WALK_FORWARD,
            run_id="validation-history-run",
            status=RunStatus.SUCCEEDED,
        )
    finally:
        service.close()

    rows = FixtureRunService(database=database).all_history(artifact_root=tmp_path)

    assert rows[0]["run_id"] == "validation-history-run"
    assert rows[0]["stage"] == "Walk-forward validation"
    assert rows[0]["evidence"] == "Invalid"
