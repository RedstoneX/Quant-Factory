"""Fault-injection proofs for atomic review and decision-artifact persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import persistence.database as persistence_database
from backtesting.validation.evidence_decision_artifacts import (
    EVIDENCE_DECISION_LOGICAL_NAME,
)
from backtesting.validation.evidence_service import ValidationEvidenceArtifactService
from dashboard.callbacks.review_state import persist_screening_rejection_review
from persistence import PersistenceService, ReviewState
from tests.test_evidence_decision_artifacts import _gate, _references, _service_with_run
from tests.test_operator_run_operations import _terminal_screening


def _inject_fault(
    monkeypatch: pytest.MonkeyPatch,
    service: PersistenceService,
    fault: str,
) -> type[Exception]:
    if fault == "write":
        original_write_bytes = Path.write_bytes

        def fail_staged_write(path: Path, content: bytes) -> int:
            if path.name.endswith(".staged"):
                raise OSError("injected artifact write failure")
            return original_write_bytes(path, content)

        monkeypatch.setattr(Path, "write_bytes", fail_staged_write)
        return OSError
    if fault == "register":

        def fail_registration(**kwargs: Any) -> Any:
            raise RuntimeError("injected artifact registration failure")

        monkeypatch.setattr(service, "register_artifact", fail_registration)
        return RuntimeError

    def fail_commit(connection: Any) -> None:
        raise RuntimeError("injected database commit failure")

    monkeypatch.setattr(persistence_database, "_commit", fail_commit)
    return RuntimeError


def _assert_no_decision(
    database: Path,
    *,
    run_id: str,
    target: Path,
) -> None:
    reopened = PersistenceService(database)
    try:
        assert reopened.reviews.get_current("run", run_id) is None
        assert reopened.reviews.history("run", run_id) == ()
        assert not any(
            artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
            for artifact in reopened.list_run_artifacts(run_id)
        )
        assert not target.exists()
    finally:
        reopened.close()


@pytest.mark.parametrize("fault", ["write", "register", "commit"])
def test_decision_fault_cannot_leave_durable_review_without_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    database = tmp_path / "state.sqlite3"
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    gate = _gate(_references(service, root=root))
    target = root / "artifacts" / "decision-run" / "evidence_decision.json"
    expected = _inject_fault(monkeypatch, service, fault)

    with pytest.raises(expected):
        ValidationEvidenceArtifactService(service).persist_evidence_decision(
            run_id="decision-run",
            gate_result=gate,
            review_state=ReviewState.REVISE,
            review_reason="human review note",
            reviewer="reviewer-1",
            artifact_root=root,
        )

    monkeypatch.undo()
    service.close()
    _assert_no_decision(database, run_id="decision-run", target=target)


@pytest.mark.parametrize("fault", ["write", "register", "commit"])
def test_screening_rejection_fault_cannot_leave_durable_review_without_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    service, run_id = _terminal_screening(tmp_path)
    database = tmp_path / "state" / f"{run_id}.sqlite3"
    target = tmp_path / "artifacts" / run_id / "evidence_decision.json"
    expected = _inject_fault(monkeypatch, service, fault)

    with pytest.raises(expected):
        persist_screening_rejection_review(
            service,
            run_id=run_id,
            review_reason="Fixed candidate failed its predeclared screen.",
            reviewer="local-user",
            artifact_root=tmp_path,
        )

    monkeypatch.undo()
    service.close()
    _assert_no_decision(database, run_id=run_id, target=target)
