"""Focused operator-operation completion proofs."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.callbacks.review_state import (
    load_durable_review,
    persist_screening_rejection_review,
    screening_rejection_available,
)
from persistence import ReviewState, RunStatus
from tests.test_run_lineage import _service_with_lineage_run


def _terminal_screening(tmp_path: Path):
    run_id = "terminal-screening"
    service, _ = _service_with_lineage_run(tmp_path, run_id=run_id)
    service.connection.execute(
        "UPDATE experiment_runs SET stage='screening' WHERE run_id=?", (run_id,)
    )
    service.results.add_parameter_result(
        run_id=run_id,
        row_id="fixed",
        normalized_parameters={"fixed": True},
        metrics={"total_return": -0.01, "number_of_trades": 4},
        ranking_position=1,
        screening_status="screened_out",
        rejection_reasons="minimum return not met",
    )
    service.connection.commit()
    service.transition_run(run_id, RunStatus.RUNNING)
    service.transition_run(run_id, RunStatus.SUCCEEDED)
    metrics = tmp_path / "artifacts" / run_id / "metrics.json"
    metrics.parent.mkdir(parents=True, exist_ok=True)
    metrics.write_bytes(b'{"total_return":0.1}')
    service.persist_run_manifest(service.build_run_manifest(run_id))
    return service, run_id


def test_terminal_screening_reject_is_integrity_backed_and_cannot_advance(
    tmp_path: Path,
) -> None:
    service, run_id = _terminal_screening(tmp_path)
    database = tmp_path / "state" / f"{run_id}.sqlite3"
    try:
        assert screening_rejection_available(service, run_id, artifact_root=tmp_path)
        decision = persist_screening_rejection_review(
            service,
            run_id=run_id,
            review_reason="Fixed candidate failed its predeclared screen.",
            reviewer="local-user",
            artifact_root=tmp_path,
        )
        assert decision.document["decision"]["eligible_to_progress"] is False
        assert decision.document["decision"]["review"]["state"] == "reject"
    finally:
        service.close()

    snapshot = load_durable_review(database, tmp_path, run_id)
    assert snapshot.state == ReviewState.REJECT
    assert snapshot.decision_identity == decision.decision_identity


def test_screening_rejection_requires_every_result_to_be_screened_out(
    tmp_path: Path,
) -> None:
    service, run_id = _terminal_screening(tmp_path)
    try:
        service.connection.execute(
            "UPDATE parameter_results SET screening_status='passed' WHERE run_id=?",
            (run_id,),
        )
        service.connection.commit()
        with pytest.raises(ValueError, match="not a terminal rejected outcome"):
            screening_rejection_available(service, run_id, artifact_root=tmp_path)
    finally:
        service.close()
