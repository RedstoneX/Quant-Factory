"""Focused tests for the immutable persisted-run Compare read model."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from dashboard.compare_adapter import CompareDashboardAdapter, CompareViewModel
from persistence import (
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
from persistence.evidence_service import ValidationEvidenceArtifactService
from persistence.models import normalized_configuration_document
from tests.test_review_context_artifacts import (
    _persist_context,
    _persist_review_prerequisites,
    _review_service,
    _target_run,
)


def _comparison_stack(tmp_path: Path) -> tuple[Path, Path]:
    database = tmp_path / "state" / "compare-model.sqlite3"
    artifact_root = tmp_path / "artifacts"
    service = PersistenceService(database)
    try:
        service.register_strategy(
            strategy_id="compare_strategy",
            strategy_version="1.0.0",
            display_name="Compare Strategy",
            description="Portable Compare adapter fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
    finally:
        service.close()
    return database, artifact_root


def _persist_run(
    database: Path,
    artifact_root: Path,
    *,
    run_id: str,
    equity_values: tuple[float, ...],
    parameter_window: int = 10,
    fee: float = 0.001,
    metrics: dict[str, float | int] | None = None,
    provider: str = "fixture",
    requested_coverage: str = "2024-01-01/2024-01-03",
    actual_coverage: str = "2024-01-01/2024-01-03",
    timezone: str = "UTC",
    adjusted: bool = True,
    checksum: str = "shared-dataset-checksum",
    stage: RunStage = RunStage.FIXTURE,
) -> Path:
    service = PersistenceService(database)
    try:
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id=f"compare_{run_id}",
                strategy_id="compare_strategy",
                strategy_version="1.0.0",
                market_data={
                    "provider": provider,
                    "symbol": "SPY",
                    "interval": "1d",
                },
                parameters={"window": parameter_window, "threshold": 25},
                execution={
                    "fill_model": "next_open",
                    "fees": fee,
                    "slippage": 0.0005,
                },
                ranking={"metric": "sharpe_ratio"},
                screening={"minimum_trades": 1},
            )
        )
        service.create_run(
            configuration_id=configuration.configuration_id,
            strategy_id="compare_strategy",
            strategy_version="1.0.0",
            stage=stage,
            run_id=run_id,
            status=RunStatus.SUCCEEDED,
        )
        with transaction(service.connection):
            service.results.set_data_provenance(
                DataProvenanceRecord(
                    run_id=run_id,
                    provider=provider,
                    provider_implementation=f"{provider}-implementation",
                    symbol="SPY",
                    interval="1d",
                    timezone=timezone,
                    requested_coverage=requested_coverage,
                    actual_coverage=actual_coverage,
                    adjusted=adjusted,
                    row_count=len(equity_values),
                    cache_action="fixture",
                    validation_summary_json=canonical_json({"status": "valid"}),
                    manifest_reference="data/manifests/compare-fixture.json",
                    checksum=checksum,
                )
            )
            service.results.set_execution_assumptions(
                ExecutionAssumptionsRecord(
                    run_id=run_id,
                    assumptions_json=canonical_json(
                        {
                            "fill_model": "next_open",
                            "fees": fee,
                            "slippage": 0.0005,
                        }
                    ),
                )
            )
            if metrics is not None:
                service.results.add_parameter_result(
                    run_id=run_id,
                    row_id=f"{run_id}-rank-1",
                    normalized_parameters={
                        "window": parameter_window,
                        "threshold": 25,
                    },
                    metrics=metrics,
                    ranking_position=1,
                    screening_status="passed",
                )

        payload = {
            "equity_curve": [
                {
                    "timestamp": f"2024-01-0{index + 1}T00:00:00Z",
                    "value": value,
                }
                for index, value in enumerate(equity_values)
            ]
        }
        content = canonical_json(payload).encode("utf-8")
        location = f"artifacts/{run_id}/equity_curve.json"
        target = artifact_root / location
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        service.register_artifact(
            run_id=run_id,
            artifact_type=ArtifactType.EQUITY_CURVE,
            logical_name="equity_curve",
            media_type="application/json",
            format="json",
            location=location,
            content=content,
        )
        service.persist_run_manifest(service.build_run_manifest(run_id))
        return target
    finally:
        service.close()


def _seed_two_runs(tmp_path: Path) -> tuple[Path, Path]:
    database, artifact_root = _comparison_stack(tmp_path)
    _persist_run(
        database,
        artifact_root,
        run_id="run-a",
        equity_values=(100.0, 110.0, 105.0),
        parameter_window=10,
        fee=0.001,
        metrics={
            "total_return": 0.05,
            "sharpe_ratio": 1.1,
            "number_of_trades": 4,
        },
    )
    _persist_run(
        database,
        artifact_root,
        run_id="run-b",
        equity_values=(200.0, 220.0, 180.0),
        parameter_window=20,
        fee=0.002,
        metrics={
            "total_return": -0.1,
            "sharpe_ratio": 0.8,
            "number_of_trades": 6,
        },
    )
    return database, artifact_root


def _model(tmp_path: Path) -> tuple[Path, Path, CompareViewModel]:
    database, artifact_root = _seed_two_runs(tmp_path)
    model = CompareDashboardAdapter(
        database,
        artifact_root=artifact_root,
    ).compare(("run-a", "run-b"))
    return database, artifact_root, model


def _group(model: CompareViewModel, key: str):
    return next(group for group in model.difference_groups if group.key == key)


def _field(model: CompareViewModel, group: str, key: str):
    return next(field for field in _group(model, group).fields if field.key == key)


def test_comparable_runs_build_aligned_metrics_normalized_curves_and_differences(
    tmp_path: Path,
) -> None:
    _, _, model = _model(tmp_path)

    assert model.requested_run_ids == ("run-a", "run-b")
    assert tuple(run.run_id for run in model.runs) == model.requested_run_ids
    assert all(run.available for run in model.runs)
    assert all(run.instrument == "SPY" for run in model.runs)
    assert all(run.timeframe == "1d" for run in model.runs)
    assert model.runs[0].results_href == (
        "/research/backtest-results?run_id=run-a"
    )

    total_return = next(row for row in model.metric_rows if row.key == "total_return")
    assert total_return.state == "changed"
    assert [value.raw_value for value in total_return.values] == [0.05, -0.1]
    assert [value.display_value for value in total_return.values] == ["5.00%", "-10.00%"]
    assert total_return.basis_warning is None
    annualized = next(
        row for row in model.metric_rows if row.key == "annualized_return"
    )
    assert annualized.state == "missing"
    assert all(value.display_value == "Unavailable" for value in annualized.values)

    assert [point.value for point in model.equity_series[0].points] == pytest.approx([
        100.0,
        110.0,
        105.0,
    ])
    assert [point.value for point in model.equity_series[1].points] == pytest.approx([
        100.0,
        110.0,
        90.0,
    ])
    assert [point.value for point in model.drawdown_series[0].points] == pytest.approx([
        0.0,
        0.0,
        105.0 / 110.0 - 1.0,
    ])
    assert [point.value for point in model.drawdown_series[1].points] == pytest.approx([
        0.0,
        0.0,
        180.0 / 220.0 - 1.0,
    ])

    assert _field(model, "parameters", "window").state == "changed"
    assert _field(model, "data", "provider").state == "equal"
    assert _field(model, "data", "dataset_identity").state == "equal"
    assert _field(model, "data", "manifest_reference").state == "equal"
    assert _field(model, "data", "row_count").state == "equal"
    assert _field(model, "execution", "persisted.fees").state == "changed"
    assert {group.key for group in model.difference_groups} == {
        "parameters",
        "data",
        "execution",
        "evidence",
        "review",
    }
    assert model.directly_comparable is True
    assert any(finding.code == "execution_differences" for finding in model.findings)


def test_incompatible_metric_basis_and_data_windows_are_explicit(
    tmp_path: Path,
) -> None:
    database, artifact_root = _comparison_stack(tmp_path)
    _persist_run(
        database,
        artifact_root,
        run_id="basis-a",
        equity_values=(100.0, 101.0),
        metrics={"total_return": 0.01},
    )
    _persist_run(
        database,
        artifact_root,
        run_id="basis-b",
        equity_values=(100.0, 102.0),
        metrics=None,
        provider="alternate-fixture",
        checksum="different-dataset-checksum",
        requested_coverage="2024-02-01/2024-02-02",
        actual_coverage="2024-02-01/2024-02-02",
    )

    model = CompareDashboardAdapter(
        database,
        artifact_root=artifact_root,
    ).compare(("basis-a", "basis-b"))
    codes = {finding.code: finding.severity for finding in model.findings}

    assert model.directly_comparable is False
    assert codes["dataset_identity"] == "blocking"
    assert codes["actual_period"] == "blocking"
    assert codes["metric_basis"] == "blocking"
    assert codes["provider"] == "warning"
    total_return = next(row for row in model.metric_rows if row.key == "total_return")
    assert total_return.state == "missing"
    assert total_return.basis_warning is not None
    assert _field(model, "data", "requested_period").state == "changed"
    assert _field(model, "data", "actual_period").state == "changed"


def test_missing_and_corrupt_evidence_retain_every_requested_identity(
    tmp_path: Path,
) -> None:
    database, artifact_root = _comparison_stack(tmp_path)
    _persist_run(
        database,
        artifact_root,
        run_id="healthy",
        equity_values=(100.0, 101.0),
        metrics={"total_return": 0.01},
    )
    corrupt_path = _persist_run(
        database,
        artifact_root,
        run_id="corrupt",
        equity_values=(100.0, 99.0),
        metrics={"total_return": -0.01},
    )
    corrupt_path.write_text(
        '{"equity_curve":[{"timestamp":"2024-01-01T00:00:00Z","value":999}]}',
        encoding="utf-8",
    )

    model = CompareDashboardAdapter(
        database,
        artifact_root=artifact_root,
    ).compare(("corrupt", "missing run/with space", "healthy"))

    assert model.requested_run_ids == (
        "corrupt",
        "missing run/with space",
        "healthy",
    )
    assert tuple(run.run_id for run in model.runs) == model.requested_run_ids
    assert model.runs[1].available is False
    assert model.runs[1].results_href.endswith(
        "run_id=missing+run%2Fwith+space"
    )
    assert model.equity_series[0].points == ()
    assert "validated persisted equity curve" in (
        model.equity_series[0].omission or ""
    ).lower()
    assert model.equity_series[1].points == ()
    assert model.equity_series[2].points
    assert any(
        "artifact_size_mismatch" in error or "artifact_checksum_mismatch" in error
        for error in model.runs[0].errors
    )
    assert any("unavailable" in error.lower() for error in model.runs[1].errors)
    assert model.directly_comparable is False
    assert any(finding.code == "run_unavailable" for finding in model.findings)
    assert any(
        finding.code == "persisted_evidence_error" for finding in model.findings
    )
    assert any(finding.code == "equity_unavailable" for finding in model.findings)


def test_durable_human_review_differences_are_read_from_persisted_evidence(
    tmp_path: Path,
) -> None:
    service = _review_service(tmp_path)
    artifact_root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, artifact_root)
    reviewed_run = _target_run(service, "reviewed-run")
    _persist_context(
        service,
        artifact_root,
        target_run_id=reviewed_run,
        source_lock_run_id=reviewed_run,
    )
    evidence = ValidationEvidenceArtifactService(service)
    gate = evidence.evaluate_persisted_review_context(
        reviewed_run,
        artifact_root=artifact_root,
    )
    evidence.persist_evidence_decision(
        run_id=reviewed_run,
        gate_result=gate,
        review_state=ReviewState.WATCHLIST,
        review_reason="Retain for additional evidence.",
        reviewer="dashboard-operator",
        artifact_root=artifact_root,
        created_at="2026-01-02T00:00:00+00:00",
    )
    database = tmp_path / "state.sqlite3"
    service.close()

    model = CompareDashboardAdapter(
        database,
        artifact_root=artifact_root,
    ).compare((reviewed_run, "wf-run"))
    review_state = _field(model, "review", "state")

    assert [run.human_review for run in model.runs] == ["Watchlist", "Unreviewed"]
    assert review_state.state == "changed"
    assert [value.value for value in review_state.values] == [
        "Watchlist",
        "Unreviewed",
    ]
    assert _field(model, "review", "note").values[0].value == (
        "Retain for additional evidence."
    )
    assert any(finding.code == "review_differences" for finding in model.findings)


def test_zero_equity_baseline_fails_closed_without_invented_points(
    tmp_path: Path,
) -> None:
    database, artifact_root = _comparison_stack(tmp_path)
    _persist_run(
        database,
        artifact_root,
        run_id="zero-baseline",
        equity_values=(0.0, 1.0, 2.0),
        metrics={"total_return": 0.0},
    )
    _persist_run(
        database,
        artifact_root,
        run_id="valid-baseline",
        equity_values=(100.0, 101.0, 102.0),
        metrics={"total_return": 0.02},
    )

    model = CompareDashboardAdapter(
        database,
        artifact_root=artifact_root,
    ).compare(("zero-baseline", "valid-baseline"))

    assert model.equity_series[0].points == ()
    assert model.drawdown_series[0].points == ()
    assert "zero starting value" in (model.equity_series[0].omission or "")
    assert model.equity_series[1].points
    assert model.directly_comparable is False


def _database_snapshot(database: Path) -> tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]:
    connection = sqlite3.connect(database)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return tuple(
            (
                table,
                tuple(
                    tuple(row)
                    for row in connection.execute(f'SELECT * FROM "{table}"')
                ),
            )
            for table in tables
        )
    finally:
        connection.close()


def test_repeated_compare_reads_are_identical_and_do_not_mutate_persistence(
    tmp_path: Path,
) -> None:
    database, artifact_root = _seed_two_runs(tmp_path)
    adapter = CompareDashboardAdapter(database, artifact_root=artifact_root)
    before = _database_snapshot(database)

    first = adapter.compare(("run-b", "run-a"))
    second = adapter.compare(("run-b", "run-a"))
    after = _database_snapshot(database)

    assert first == second
    assert before == after
    assert tuple(run.run_id for run in first.runs) == ("run-b", "run-a")
