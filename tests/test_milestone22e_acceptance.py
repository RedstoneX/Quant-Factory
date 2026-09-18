"""Milestone 22E acceptance coverage for normalized evidence outcomes."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.app import _run_detail_panel
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import RunSummary
from persistence import StrategyLifecycle
from persistence.evidence_service import ValidationEvidenceArtifactService
from tests.test_lockbox_gate import (
    _persist_prerequisites,
    _service,
)


def _database_path(base: Path) -> Path:
    return base / "state.sqlite3"


def _mc_artifact_path(root: Path) -> Path:
    return root / "artifacts" / "mc-run" / "monte_carlo_evidence.json"


def _run_summary(service) -> RunSummary:
    run = service.runs.get("mc-run")
    assert run is not None
    return RunSummary(
        run_id=run.run_id,
        configuration_id=run.configuration_id,
        strategy_id=run.strategy_id,
        strategy_version=run.strategy_version,
        stage=run.stage.value,
        status=run.status.value,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_summary=run.error_summary,
        prefect_flow_run_id=None,
        prefect_api_url=None,
        attempt_count=run.attempt_count,
    )


def _dashboard_fields(detail) -> dict[str, str]:
    return {field.label: field.value for field in detail.evidence.validation_outcome}


def _persist_missing_monte_carlo_file_case(service, root: Path) -> None:
    _persist_prerequisites(service, root)
    _mc_artifact_path(root).unlink()


def _persist_corrupt_monte_carlo_file_case(service, root: Path) -> None:
    _persist_prerequisites(service, root)
    _mc_artifact_path(root).write_text("{}", encoding="utf-8")


def _persist_failed_monte_carlo_case(service, root: Path) -> None:
    _persist_prerequisites(service, root, mc_status="failed")


def _persist_passed_monte_carlo_case(service, root: Path) -> None:
    _persist_prerequisites(service, root)


@pytest.mark.parametrize(
    ("expected_status", "arrange"),
    (
        ("passed", _persist_passed_monte_carlo_case),
        ("failed", _persist_failed_monte_carlo_case),
        ("invalid", _persist_corrupt_monte_carlo_file_case),
        ("insufficient_evidence", _persist_missing_monte_carlo_file_case),
    ),
)
def test_milestone22e_outcomes_flow_through_service_and_run_detail_dashboard(
    tmp_path: Path,
    expected_status: str,
    arrange,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        arrange(service, root)
        before_runs = tuple(
            (run.run_id, run.stage, run.status) for run in service.runs.list()
        )
        before_lifecycle = service.strategies.get(
            "fixture_strategy",
            "1.0.0",
        ).lifecycle

        outcome = ValidationEvidenceArtifactService(service).stage_outcome(
            "mc-run",
            artifact_root=root,
        )
        detail = RunDetailDashboardAdapter(
            database=_database_path(tmp_path),
            artifact_root=root,
        ).selected_run_detail("mc-run")
        fields = _dashboard_fields(detail)
        rendered = str(_run_detail_panel(_run_summary(service), detail=detail))

        assert outcome.status == expected_status
        assert fields["Normalized status"] == outcome.status
        assert fields["Reasons"] == (
            ", ".join(outcome.reasons) if outcome.reasons else "Not recorded"
        )
        assert fields["Stage"] == "Monte Carlo"
        assert fields["Protected-data state"] == (
            outcome.protected_data_state or "Not recorded"
        )
        assert fields["Evidence identity"] == (
            outcome.evidence_identity or "Not recorded"
        )
        assert fields["Artifact identity"] == (
            str(outcome.artifact_id)
            if outcome.artifact_id is not None
            else "Not recorded"
        )
        assert fields["Lockbox eligibility"] == "Not recorded"
        assert fields["Strategy progression"] == "No strategy progression occurred."

        assert "Validation outcome" in rendered
        assert "Normalized status" in rendered
        assert expected_status in rendered
        assert "Protected-data state" in rendered
        assert "Evidence identity" in rendered
        assert "Artifact identity" in rendered
        assert "Lockbox eligibility" in rendered
        assert "No strategy progression occurred." in rendered

        assert (
            tuple((run.run_id, run.stage, run.status) for run in service.runs.list())
            == before_runs
        )
        assert (
            service.strategies.get("fixture_strategy", "1.0.0").lifecycle
            == before_lifecycle
            == StrategyLifecycle.INFRASTRUCTURE_FIXTURE
        )
    finally:
        service.close()
