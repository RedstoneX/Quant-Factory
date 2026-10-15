"""Owner ruling 15 Oct 2026: walk-forward and stress results are scores, not gates.

Paper trading is the real filter. A merit result at walk-forward, robustness or
Monte Carlo is recorded and the idea continues to the shortlist. Invalid
evidence and crashes still stop the idea. The costs screen and the
out-of-sample test remain hard gates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestration.filter_chain import (
    FactoryFilterChainService,
    FilterStageInvocationUnknownError,
    VALIDATION_STAGE_ORDER,
)
from persistence import RunStage, RunStatus
from tests.test_filter_chain_service import _adapters, _create_stage, _service


def _run(tmp_path: Path, overrides=None, *, screening_status: str = "passed", crash=None):
    service = _service(tmp_path, screening_status=screening_status)
    root = tmp_path / "artifacts"
    calls: list[tuple[str, str]] = []
    adapters = _adapters(service, root, calls, overrides)
    if crash is not None:

        def explode(context):
            calls.append((crash.value, context.previous_run_id))
            _create_stage(service, crash, context.run_id)
            raise RuntimeError("fixture adapter crash")

        adapters[crash] = explode
    return service, calls, FactoryFilterChainService(service, artifact_root=root), adapters


def _handoff(outcome, stage: RunStage):
    return next(item for item in outcome.completed if item.stage == stage)


@pytest.mark.parametrize(
    ("stage", "override", "reason"),
    (
        (RunStage.WALK_FORWARD, "failed_walk_forward", "fixture stage failed"),
        (RunStage.ROBUSTNESS, "failed_robustness", "fixture robustness merit failure"),
        (RunStage.MONTE_CARLO, "failed_monte_carlo", "fixture Monte Carlo merit failure"),
    ),
)
def test_merit_failure_is_recorded_as_score_and_idea_continues(
    tmp_path: Path, stage: RunStage, override: str, reason: str
) -> None:
    service, calls, chain, adapters = _run(tmp_path, {stage: {override: True}})
    try:
        outcome = chain.run(screening_run_id="screening-run", stage_adapters=adapters)

        assert tuple(name for name, _ in calls) == tuple(s.value for s in VALIDATION_STAGE_ORDER)
        assert outcome.status == "ready_for_protected_test"
        assert outcome.stopped_at is None
        scored = _handoff(outcome, stage)
        assert scored.status == "failed"
        assert scored.eligible_to_progress is True
        assert scored.evidence_identity is not None
        assert any(reason in item for item in scored.reasons)
        assert service.runs.get(scored.run_id).status == RunStatus.SUCCEEDED
        assert service.list_run_artifacts(scored.run_id)
        assert outcome.protected_test_gate.eligible_to_execute_lockbox is True
        assert any(
            item.startswith(f"{stage.value} (score):") and reason in item
            for item in outcome.protected_test_gate.reasons
        )
    finally:
        service.close()


@pytest.mark.parametrize("stage", (RunStage.WALK_FORWARD, RunStage.ROBUSTNESS))
def test_invalid_evidence_still_stops_the_idea(tmp_path: Path, stage: RunStage) -> None:
    service, calls, chain, adapters = _run(tmp_path, {stage: {"corrupt": True}})
    try:
        outcome = chain.run(screening_run_id="screening-run", stage_adapters=adapters)

        assert outcome.status == "stopped"
        assert outcome.stopped_at == stage.value
        assert outcome.completed[-1].status == "invalid"
        assert outcome.completed[-1].eligible_to_progress is False
        assert calls[-1][0] == stage.value
    finally:
        service.close()


@pytest.mark.parametrize("stage", (RunStage.WALK_FORWARD, RunStage.ROBUSTNESS))
def test_adapter_crash_still_fails_the_stage(tmp_path: Path, stage: RunStage) -> None:
    service, calls, chain, adapters = _run(tmp_path, crash=stage)
    try:
        with pytest.raises(FilterStageInvocationUnknownError):
            chain.run(screening_run_id="screening-run", stage_adapters=adapters)

        assert calls[-1][0] == stage.value
        failed = [run for run in service.runs.list() if run.stage == stage]
        assert [run.status for run in failed] == [RunStatus.FAILED]
    finally:
        service.close()


def test_costs_screen_failure_still_stops_the_idea(tmp_path: Path) -> None:
    service, calls, chain, adapters = _run(tmp_path, screening_status="screened_out")
    try:
        outcome = chain.run(screening_run_id="screening-run", stage_adapters=adapters)

        assert outcome.status == "screened_out"
        assert calls == []
    finally:
        service.close()


def test_out_of_sample_failure_still_stops_the_idea(tmp_path: Path) -> None:
    service, calls, chain, adapters = _run(tmp_path, {RunStage.OOS: {"failed_oos": True}})
    try:
        outcome = chain.run(screening_run_id="screening-run", stage_adapters=adapters)

        assert outcome.status == "stopped"
        assert outcome.stopped_at == RunStage.OOS.value
        assert outcome.completed[-1].status != "passed"
        assert outcome.completed[-1].eligible_to_progress is False
        assert tuple(name for name, _ in calls) == (RunStage.OOS.value,)
    finally:
        service.close()
