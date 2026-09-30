"""Focused evidence-integrity proof for dashboard parameter variants."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.models import normalized_configuration_document


METRICS = (
    "total_return",
    "annualized_return",
    "sharpe_ratio",
    "max_drawdown",
    "number_of_trades",
    "win_rate",
)


def _variant_rows() -> list[dict[str, Any]]:
    return [
        {
            "parameter_row_id": "row-fast",
            "lookback": 5,
            "threshold": 0.25,
            "total_return": 0.12,
            "annualized_return": 0.10,
            "sharpe_ratio": 1.2,
            "max_drawdown": -0.05,
            "number_of_trades": 22,
            "win_rate": 0.60,
            "ranking_position": 1,
            "screening_status": "passed",
            "screening_rejection_reasons": "",
        },
        {
            "parameter_row_id": "row-slow",
            "lookback": 20,
            "threshold": 0.75,
            "total_return": -0.02,
            "annualized_return": -0.03,
            "sharpe_ratio": -0.1,
            "max_drawdown": -0.20,
            "number_of_trades": 5,
            "win_rate": 0.40,
            "ranking_position": 2,
            "screening_status": "screened_out",
            "screening_rejection_reasons": "too few trades",
        },
    ]


def _persist_run(
    tmp_path: Path,
    *,
    artifact_rows: list[dict[str, Any]] | None,
    corrupt_artifact: bool = False,
    extra_artifact: bool = False,
) -> tuple[Path, Path, str]:
    database = tmp_path / "state" / "variants.sqlite3"
    artifact_root = tmp_path / "evidence"
    run_id = "variant-run"
    service = PersistenceService(database)
    try:
        service.register_strategy(
            strategy_id="fixture_variants",
            strategy_version="1.0.0",
            display_name="Fixture variants",
            description="Deterministic dashboard evidence fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
            active=True,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="fixture_variants",
                strategy_id="fixture_variants",
                strategy_version="1.0.0",
                market_data={"provider": "fixture", "symbol": "TEST", "interval": "1m"},
                parameters={
                    "lookback": {"allowed_values": [5, 20]},
                    "threshold": {"allowed_values": [0.25, 0.75]},
                },
                execution={"mode": "deterministic_fixture"},
                ranking={"metric": "total_return"},
                screening={"minimum_trades": 10},
            )
        )
        service.create_run(
            configuration_id=configuration.configuration_id,
            strategy_id="fixture_variants",
            strategy_version="1.0.0",
            stage=RunStage.SCREENING,
            run_id=run_id,
            status=RunStatus.SUCCEEDED,
        )
        with transaction(service.connection):
            for row in _variant_rows():
                service.results.add_parameter_result(
                    run_id=run_id,
                    row_id=row["parameter_row_id"],
                    normalized_parameters={
                        "lookback": row["lookback"],
                        "threshold": row["threshold"],
                    },
                    metrics={key: row[key] for key in METRICS},
                    ranking_position=row["ranking_position"],
                    screening_status=row["screening_status"],
                    rejection_reasons=row["screening_rejection_reasons"],
                )
            service.results.set_data_provenance(
                DataProvenanceRecord(
                    run_id=run_id,
                    provider="fixture",
                    provider_implementation="deterministic",
                    symbol="TEST",
                    interval="1m",
                    timezone="UTC",
                    requested_coverage="2026-01-02/2026-01-02",
                    actual_coverage="2026-01-02/2026-01-02",
                    adjusted=False,
                    row_count=1,
                    cache_action="fixture",
                    validation_summary_json=canonical_json({"status": "valid"}),
                    manifest_reference="fixture",
                    checksum="fixture-checksum",
                )
            )
            service.results.set_execution_assumptions(
                ExecutionAssumptionsRecord(
                    run_id=run_id,
                    assumptions_json=canonical_json(
                        {"mode": "deterministic_fixture"}
                    ),
                )
            )

        if artifact_rows is not None:
            document = {"ranked_results": artifact_rows}
            content = (canonical_json(document) + "\n").encode("utf-8")
            location = f"artifacts/{run_id}/parameter_results.json"
            target = artifact_root / location
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            service.register_artifact(
                run_id=run_id,
                artifact_type=ArtifactType.PARAMETER_RESULTS,
                logical_name="parameter_results",
                media_type="application/json",
                format="json",
                location=location,
                content=content,
            )
            if extra_artifact:
                second_location = f"artifacts/{run_id}/parameter_results-v2.json"
                second_target = artifact_root / second_location
                second_target.write_bytes(content)
                service.register_artifact(
                    run_id=run_id,
                    artifact_type=ArtifactType.PARAMETER_RESULTS,
                    logical_name="parameter_results",
                    media_type="application/json",
                    format="json",
                    location=second_location,
                    content=content,
                    schema_version=2,
                )
            service.persist_run_manifest(service.build_run_manifest(run_id))
            if corrupt_artifact:
                target.write_text('{"ranked_results": []}\n', encoding="utf-8")
        else:
            service.persist_run_manifest(service.build_run_manifest(run_id))
    finally:
        service.close()
    return database, artifact_root, run_id


def _detail(tmp_path: Path, **kwargs: Any):
    database, artifact_root, run_id = _persist_run(tmp_path, **kwargs)
    return RunDetailDashboardAdapter(
        database,
        artifact_root=artifact_root,
    ).selected_run_detail(run_id)


def test_database_variants_have_stable_composite_identity_and_source_payloads(
    tmp_path: Path,
) -> None:
    detail = _detail(tmp_path, artifact_rows=None)

    summary = detail.result_summary
    assert summary.status == "available"
    assert summary.evidence_state == "database-persisted"
    assert len(summary.table_rows) == 2
    first = summary.table_rows[0]
    assert first["parameter_row_id"] == "row-fast"
    assert first["variant_key"] == "variant-run:row-fast"
    assert first["__parameters"] == {"lookback": 5, "threshold": 0.25}
    assert first["__metrics"] == {key: _variant_rows()[0][key] for key in METRICS}
    assert first["lookback"] == 5
    assert first["total_return"] == pytest.approx(0.12)
    assert first["ranking_position"] == 1
    assert first["screening_status"] == "passed"
    assert first["screening_reason"] == ""


def test_valid_registered_artifact_reconciles_every_variant(tmp_path: Path) -> None:
    detail = _detail(tmp_path, artifact_rows=_variant_rows())

    summary = detail.result_summary
    assert summary.status == "available"
    assert summary.evidence_state == "artifact-validated"
    assert "row-for-row" in summary.evidence_message
    assert len(summary.table_rows) == 2
    assert detail.warnings == ()


def test_artifact_optional_identity_and_screening_fields_are_not_invented(
    tmp_path: Path,
) -> None:
    rows = deepcopy(_variant_rows())
    for row in rows:
        row.pop("parameter_row_id")
        row.pop("screening_status")
        row.pop("screening_rejection_reasons")

    detail = _detail(tmp_path, artifact_rows=rows)

    assert detail.result_summary.evidence_state == "artifact-validated"
    assert [row["parameter_row_id"] for row in detail.result_summary.table_rows] == [
        "row-fast",
        "row-slow",
    ]


@pytest.mark.parametrize(
    "mismatch",
    (
        "count",
        "order",
        "parameter_row_id",
        "ranking_position",
        "parameter",
        *METRICS,
        "screening_status",
        "screening_rejection_reasons",
    ),
)
def test_artifact_database_mismatch_fails_closed(
    tmp_path: Path,
    mismatch: str,
) -> None:
    rows = deepcopy(_variant_rows())
    if mismatch == "count":
        rows.pop()
    elif mismatch == "order":
        rows.reverse()
    elif mismatch == "parameter_row_id":
        rows[0][mismatch] = "wrong-row"
    elif mismatch == "ranking_position":
        rows[0][mismatch] = 2
    elif mismatch == "parameter":
        rows[0]["lookback"] = 99
    elif mismatch == "screening_status":
        rows[0][mismatch] = "screened_out"
    elif mismatch == "screening_rejection_reasons":
        rows[0][mismatch] = "wrong reason"
    else:
        rows[0][mismatch] = 999

    detail = _detail(tmp_path, artifact_rows=rows)

    summary = detail.result_summary
    assert summary.status == "invalid"
    assert summary.evidence_state == "evidence-invalid"
    assert summary.rows == ()
    assert summary.table_rows == ()
    assert "Results are hidden" in summary.message
    assert any("Parameter-result evidence is invalid" in item for item in detail.warnings)


def test_corrupt_registered_artifact_fails_closed(tmp_path: Path) -> None:
    detail = _detail(
        tmp_path,
        artifact_rows=_variant_rows(),
        corrupt_artifact=True,
    )

    summary = detail.result_summary
    assert summary.status == "invalid"
    assert summary.evidence_state == "evidence-invalid"
    assert summary.table_rows == ()
    assert "not valid" in summary.evidence_message


def test_multiple_registered_parameter_artifacts_fail_closed(tmp_path: Path) -> None:
    detail = _detail(
        tmp_path,
        artifact_rows=_variant_rows(),
        extra_artifact=True,
    )

    summary = detail.result_summary
    assert summary.status == "invalid"
    assert summary.evidence_state == "evidence-invalid"
    assert summary.table_rows == ()
    assert "exactly one" in summary.evidence_message
