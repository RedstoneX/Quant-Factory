"""Durable stop-or-advance coordination for the research filter chain.

Stage adapters perform strategy-specific computation and persist one run. This
service owns the fixed order, reopens the persisted evidence, and stops before
another stage is invoked when that evidence does not qualify.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Literal

from persistence import (
    EventSeverity,
    PersistenceService,
    RunEventType,
    RunStage,
    RunStatus,
)
from persistence.evidence_service import ValidationEvidenceArtifactService


ChainStatus = Literal["screened_out", "stopped", "ready_for_protected_test"]

VALIDATION_STAGE_ORDER = (
    RunStage.OOS,
    RunStage.WALK_FORWARD,
    RunStage.ROBUSTNESS,
    RunStage.MONTE_CARLO,
)
FILTER_HANDOFF_ENVIRONMENT_KEY = "filter_handoff"


@dataclass(frozen=True)
class PersistedStageReference:
    """The only claim a stage adapter may make: which run it persisted."""

    stage: RunStage
    run_id: str


@dataclass(frozen=True)
class FilterStageContext:
    """Immutable identity handed from one stage adapter to the next."""

    screening_run_id: str
    stage: RunStage
    run_id: str
    previous: tuple[PersistedStageReference, ...] = ()

    @property
    def previous_run_id(self) -> str:
        return self.previous[-1].run_id if self.previous else self.screening_run_id


@dataclass(frozen=True)
class FilterStageHandoff:
    """Outcome derived by reopening one persisted stage's evidence."""

    stage: RunStage
    run_id: str
    status: str
    eligible_to_progress: bool
    evidence_identity: str | None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FilterChainOutcome:
    """Operator-readable result of one connected handoff attempt."""

    status: ChainStatus
    screening_run_id: str
    completed: tuple[FilterStageHandoff, ...]
    stopped_at: str | None
    reasons: tuple[str, ...]
    protected_test_gate: Any | None = None


StageAdapter = Callable[[FilterStageContext], PersistedStageReference]


class FilterStageInvocationUnknownError(RuntimeError):
    """Raised when a reserved filter stage may have started but did not finish."""


class FactoryFilterChainService:
    """Invoke persisted filters in order and derive every decision from evidence."""

    def __init__(
        self,
        persistence: PersistenceService,
        *,
        artifact_root: str | Path,
    ) -> None:
        self._persistence = persistence
        self._artifact_root = Path(artifact_root)
        self._evidence = ValidationEvidenceArtifactService(persistence)

    def run(
        self,
        *,
        screening_run_id: str,
        stage_adapters: Mapping[RunStage, StageAdapter],
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

        self._require_complete_adapters(stage_adapters)
        references: list[PersistedStageReference] = []
        completed: list[FilterStageHandoff] = []
        source_lock: Any | None = None

        for expected_stage in VALIDATION_STAGE_ORDER:
            previous_run_id = (
                references[-1].run_id if references else screening_run_id
            )
            expected_run_id = self._handoff_run_id(
                screening_run_id=screening_run_id,
                source_run_id=previous_run_id,
                stage=expected_stage,
            )
            context = FilterStageContext(
                screening_run_id=screening_run_id,
                stage=expected_stage,
                run_id=expected_run_id,
                previous=tuple(references),
            )
            reserved = self._reserve_stage_run(
                screening_run_id=screening_run_id,
                stage=expected_stage,
                run_id=expected_run_id,
                source_run_id=previous_run_id,
            )
            if reserved:
                try:
                    reference = stage_adapters[expected_stage](context)
                except Exception as exc:
                    persisted = self._persistence.runs.get(expected_run_id)
                    if persisted is not None and persisted.status == RunStatus.SUCCEEDED:
                        reference = PersistedStageReference(
                            stage=expected_stage,
                            run_id=expected_run_id,
                        )
                    else:
                        if persisted is not None and persisted.status in {
                            RunStatus.CREATED,
                            RunStatus.RUNNING,
                        }:
                            failed = self._persistence.transition_run(
                                expected_run_id,
                                RunStatus.FAILED,
                                error_summary=(
                                    "Filter-stage adapter outcome is unknown; automatic "
                                    "rerun is blocked pending owner investigation."
                                ),
                            )
                            self._persistence.append_run_event(
                                run_id=expected_run_id,
                                event_type=RunEventType.RUN_FAILED,
                                severity=EventSeverity.ERROR,
                                message=(
                                    "Filter stage stopped with an unknown outcome; "
                                    "automatic rerun is blocked."
                                ),
                                occurred_at=failed.completed_at,
                            )
                        raise FilterStageInvocationUnknownError(
                            f"{expected_stage.value} adapter outcome is unknown; "
                            "automatic rerun is blocked pending owner investigation"
                        ) from exc
            else:
                reference = PersistedStageReference(
                    stage=expected_stage,
                    run_id=expected_run_id,
                )
            self._validate_persisted_reference(
                screening_run_id=screening_run_id,
                expected_stage=expected_stage,
                expected_source_run_id=context.previous_run_id,
                expected_run_id=expected_run_id,
                reference=reference,
            )
            references.append(reference)

            if expected_stage == RunStage.OOS:
                try:
                    source_lock = self._evidence.retrieve_out_of_sample_source_lock(
                        reference.run_id,
                        artifact_root=self._artifact_root,
                    )
                except (KeyError, RuntimeError, ValueError) as exc:
                    handoff = FilterStageHandoff(
                        stage=expected_stage,
                        run_id=reference.run_id,
                        status="invalid",
                        eligible_to_progress=False,
                        evidence_identity=None,
                        reasons=(str(exc),),
                    )
                else:
                    handoff = FilterStageHandoff(
                        stage=expected_stage,
                        run_id=reference.run_id,
                        status=source_lock.status,
                        eligible_to_progress=source_lock.status == "passed",
                        evidence_identity=source_lock.artifact_id,
                        reasons=tuple(source_lock.reasons),
                    )
            else:
                outcome = self._evidence.stage_outcome(
                    reference.run_id,
                    artifact_root=self._artifact_root,
                )
                walk_forward_complete = (
                    expected_stage == RunStage.WALK_FORWARD
                    and outcome.status == "insufficient_evidence"
                    and outcome.reasons
                    == (
                        "successful walk-forward folds do not define an overall "
                        "acceptance decision",
                    )
                )
                handoff = FilterStageHandoff(
                    stage=expected_stage,
                    run_id=reference.run_id,
                    status=outcome.status,
                    eligible_to_progress=(
                        outcome.status == "passed" or walk_forward_complete
                    ),
                    evidence_identity=outcome.evidence_identity,
                    reasons=outcome.reasons,
                )

            completed.append(handoff)
            if not handoff.eligible_to_progress:
                return FilterChainOutcome(
                    status="stopped",
                    screening_run_id=screening_run_id,
                    completed=tuple(completed),
                    stopped_at=expected_stage.value,
                    reasons=handoff.reasons
                    or (f"{expected_stage.value} did not qualify for the next filter.",),
                )

        assert source_lock is not None
        by_stage = {reference.stage: reference.run_id for reference in references}
        gate = self._evidence.evaluate_lockbox_prerequisites(
            walk_forward_run_id=by_stage[RunStage.WALK_FORWARD],
            monte_carlo_run_id=by_stage[RunStage.MONTE_CARLO],
            robustness_run_id=by_stage[RunStage.ROBUSTNESS],
            source_lock=source_lock,
            artifact_root=self._artifact_root,
            protected_data_state="gated",
        )
        if not gate.eligible_to_execute_lockbox:
            return FilterChainOutcome(
                status="stopped",
                screening_run_id=screening_run_id,
                completed=tuple(completed),
                stopped_at="protected_test_gate",
                reasons=gate.reasons or ("The protected test prerequisites did not pass.",),
                protected_test_gate=gate,
            )
        return FilterChainOutcome(
            status="ready_for_protected_test",
            screening_run_id=screening_run_id,
            completed=tuple(completed),
            stopped_at=None,
            reasons=("Protected test remains locked until separate authority is granted.",),
            protected_test_gate=gate,
        )

    @staticmethod
    def _handoff_run_id(
        *,
        screening_run_id: str,
        source_run_id: str,
        stage: RunStage,
    ) -> str:
        identity = "|".join(
            ("factory_filter_handoff_v1", screening_run_id, source_run_id, stage.value)
        )
        return "run_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]

    def _reserve_stage_run(
        self,
        *,
        screening_run_id: str,
        stage: RunStage,
        run_id: str,
        source_run_id: str,
    ) -> bool:
        """Atomically reserve one deterministic stage run before adapter work."""
        if self._persistence.runs.get(run_id) is not None:
            return False
        screening = self._persistence.runs.get(screening_run_id)
        assert screening is not None
        try:
            self._persistence.create_run(
                configuration_id=screening.configuration_id,
                strategy_id=screening.strategy_id,
                strategy_version=screening.strategy_version,
                stage=stage,
                run_id=run_id,
                environment={
                    FILTER_HANDOFF_ENVIRONMENT_KEY: {
                        "source_run_id": source_run_id,
                    }
                },
            )
        except sqlite3.IntegrityError:
            if self._persistence.runs.get(run_id) is None:
                raise
            return False
        return True

    @staticmethod
    def _require_complete_adapters(
        stage_adapters: Mapping[RunStage, StageAdapter],
    ) -> None:
        supplied = set(stage_adapters)
        required = set(VALIDATION_STAGE_ORDER)
        if supplied == required:
            return
        missing = sorted(stage.value for stage in required - supplied)
        extra = sorted(stage.value for stage in supplied - required)
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected: {', '.join(extra)}")
        raise ValueError("filter-stage adapters are incomplete (" + "; ".join(details) + ")")

    def _validate_persisted_reference(
        self,
        *,
        screening_run_id: str,
        expected_stage: RunStage,
        expected_source_run_id: str,
        expected_run_id: str,
        reference: PersistedStageReference,
    ) -> None:
        if reference.stage != expected_stage:
            raise ValueError(
                f"expected {expected_stage.value} handoff, got {reference.stage.value}"
            )
        if not reference.run_id.strip():
            raise ValueError(f"{expected_stage.value} handoff run identity is incomplete")
        if reference.run_id != expected_run_id:
            raise ValueError(
                f"{expected_stage.value} handoff did not use its durable run identity"
            )

        source = self._persistence.runs.get(screening_run_id)
        persisted = self._persistence.runs.get(reference.run_id)
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
        try:
            environment = json.loads(persisted.environment_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{expected_stage.value} handoff lineage is malformed"
            ) from exc
        handoff = environment.get(FILTER_HANDOFF_ENVIRONMENT_KEY)
        if (
            not isinstance(handoff, dict)
            or handoff.get("source_run_id") != expected_source_run_id
        ):
            raise ValueError(
                f"{expected_stage.value} handoff predecessor lineage is invalid"
            )
