"""Typed lockbox prerequisite-gate records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backtesting.validation.evidence_models import EvidenceStatus, ProtectedDataState

PrerequisiteStage = Literal[
    "out_of_sample", "walk_forward", "monte_carlo", "robustness"
]


@dataclass(frozen=True)
class LockboxArtifactReference:
    """Compact identity of prerequisite evidence used by the gate."""

    stage: PrerequisiteStage
    artifact_id: str
    evidence_identity: str | None


@dataclass(frozen=True)
class LockboxGateResult:
    """Fail-closed lockbox access evaluation without executing lockbox data."""

    status: EvidenceStatus
    reasons: tuple[str, ...]
    referenced_artifacts: tuple[LockboxArtifactReference, ...]
    parameter_lock_identity: str | None
    protected_data_state: ProtectedDataState
    lineage_identity: str | None
    gate_identity: str
    eligible_to_execute_lockbox: bool
    eligible_to_progress: bool = False
