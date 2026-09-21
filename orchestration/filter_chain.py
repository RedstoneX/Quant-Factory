"""Durable stop-or-advance coordination for the research filter chain.

The stage adapters remain responsible for strategy-specific computation and
evidence persistence.  This service owns only the fixed factory order and the
decision to stop before another stage is invoked.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from persistence import PersistenceService, RunStage, RunStatus


FilterStatus = Literal["passed", "failed", "insufficient_evidence", "invalid"]
ChainStatus = Literal[
    "screened_out",
    "stopped",
    "ready_for_protected_test",
]

VALIDATION_STAGE_ORDER = (
    RunStage.OOS,
    RunStage.WALK_FORWARD,
    RunStage.ROBUSTNESS,
    RunStage.MONTE_CARLO,
)


@dataclass(frozen=True)
class FilterStageContext:
    """Immutable identity handed from one persisted stage to the next."""

    screening_run_id: str
    previous: tuple["FilterStageHandoff", ...] = ()

    @property
    def previous_run_id(self) -> str:
        return (
            self.previous[-1].run_id
            if self.previous
            else self.screening_run_id
        )


@dataclass(frozen=True)
class FilterStageHandoff:
    """One adapter's persisted stage result and progression decision."""

    stage: RunStage
    run_id: str
    status: FilterStatus
    eligible_to_progress: bool
    evidence_identity: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProtectedTestGate:
    """Final prerequisite decision; this never executes protected data."""

    status: FilterStatus
    eligible_to_execute: bool
    evidence_identity: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FilterChainOutcome:
    """Complete, operator-readable result of one connected handoff attempt."""

    status: ChainStatus
    screening_run_id: str
    completed: tuple[FilterStageHandoff, ...]
    stopped_at: str | None
    reasons: tuple[str, ...]
    protected_test_gate: ProtectedTestGate | None = None


StageAdapter = Callable[[FilterStageContext], FilterStageHandoff]
GateAdapter = Callable[[FilterStageContext], ProtectedTestGate]


class FactoryFilterChainService:
    """Invoke persisted filter stages in order and stop on the first failure."""

    def __init__(self, persistence: PersistenceService) -> None:
        self._persistence = persistence

    def run(
        self,
        *,
        screening_run_id: str,
        stage_adapters: Mapping[RunStage, StageAdapter],
        protected_test_gate: GateAdapter,
    ) -> FilterChainOutcome:
        screening = self._persistence.runs.get(screening_run_id)
        if screening is None:
            raise KeyError(f"unknown screening run {screening_run_id}")
        if screening.stage != RunStage.SCREENING:
            raise ValueError("filter-chain source must be a screening run")
        if screening.status != RunStatus.SUCCEEDED:
            raise ValueError("filter-chain source screening run must have succeeded")

        rows = self._persistence.results.list_parameter_results(screening_run_id)
        if not rows:
            raise ValueError("screening run has no persisted ranked results")
        if not any(row.screening_status == "passed" for row in rows):
            reasons = tuple(
                reason
                for row in rows
                for reason in (row.rejection_reasons.strip(),)
                if reason
            )
            return FilterChainOutcome(
                status="screened_out",
                screening_run_id=screening_run_id,
                completed=(),
                stopped_at=RunStage.SCREENING.value,
                reasons=reasons or ("No screening result qualified for later filters.",),
            )

        supplied = set(stage_adapters)
        required = set(VALIDATION_STAGE_ORDER)
        if supplied != required:
            missing = sorted(stage.value for stage in required - supplied)
            extra = sorted(stage.value for stage in supplied - required)
            details = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if extra:
                details.append(f"unexpected: {', '.join(extra)}")
            raise ValueError("filter-stage adapters are incomplete (" + "; ".join(details) + ")")

        completed: list[FilterStageHandoff] = []
        for expected_stage in VALIDATION_STAGE_ORDER:
            context = FilterStageContext(screening_run_id, tuple(completed))
            handoff = stage_adapters[expected_stage](context)
            self._validate_handoff(
                screening_run_id=screening_run_id,
                expected_stage=expected_stage,
                handoff=handoff,
            )
            completed.append(handoff)
            if not handoff.eligible_to_progress:
                return FilterChainOutcome(
                    status="stopped",
                    screening_run_id=screening_run_id,
                    completed=tuple(completed),
                    stopped_at=expected_stage.value,
                    reasons=handoff.reasons or (
                        f"{expected_stage.value} did not qualify for the next filter.",
                    ),
                )

        context = FilterStageContext(screening_run_id, tuple(completed))
        gate = protected_test_gate(context)
        self._validate_gate(gate)
        if not gate.eligible_to_execute:
            return FilterChainOutcome(
                status="stopped",
                screening_run_id=screening_run_id,
                completed=tuple(completed),
                stopped_at="protected_test_gate",
                reasons=gate.reasons or (
                    "The protected test prerequisites did not pass.",
                ),
                protected_test_gate=gate,
            )
        return FilterChainOutcome(
            status="ready_for_protected_test",
            screening_run_id=screening_run_id,
            completed=tuple(completed),
            stopped_at=None,
            reasons=(
                "Protected test remains locked until its separate authority is granted.",
            ),
            protected_test_gate=gate,
        )

    def _validate_handoff(
        self,
        *,
        screening_run_id: str,
        expected_stage: RunStage,
        handoff: FilterStageHandoff,
    ) -> None:
        if handoff.stage != expected_stage:
            raise ValueError(
                f"expected {expected_stage.value} handoff, got {handoff.stage.value}"
            )
        if not handoff.run_id.strip() or not handoff.evidence_identity.strip():
            raise ValueError(f"{expected_stage.value} handoff identity is incomplete")
        if handoff.eligible_to_progress and handoff.status != "passed":
            raise ValueError(
                f"{expected_stage.value} cannot advance with status {handoff.status}"
            )

        source = self._persistence.runs.get(screening_run_id)
        persisted = self._persistence.runs.get(handoff.run_id)
        if source is None or persisted is None:
            raise ValueError(f"{expected_stage.value} handoff run is not persisted")
        if (
            persisted.stage != expected_stage
            or persisted.status != RunStatus.SUCCEEDED
            or persisted.configuration_id != source.configuration_id
            or persisted.strategy_id != source.strategy_id
            or persisted.strategy_version != source.strategy_version
        ):
            raise ValueError(
                f"{expected_stage.value} handoff disagrees with persisted run identity"
            )
        if not self._persistence.list_run_artifacts(handoff.run_id):
            raise ValueError(f"{expected_stage.value} handoff has no persisted evidence")
        if self._persistence.read_persisted_run_manifest(handoff.run_id) is None:
            raise ValueError(f"{expected_stage.value} handoff has no persisted manifest")

    @staticmethod
    def _validate_gate(gate: ProtectedTestGate) -> None:
        if not gate.evidence_identity.strip():
            raise ValueError("protected-test gate identity is incomplete")
        if gate.eligible_to_execute and gate.status != "passed":
            raise ValueError(
                f"protected-test gate cannot advance with status {gate.status}"
            )
