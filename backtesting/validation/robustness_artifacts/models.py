"""Constants and persisted records for robustness evidence artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from persistence import ArtifactContractRecord

ROBUSTNESS_EVIDENCE_LOGICAL_NAME = "robustness_evidence"
ROBUSTNESS_EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PersistedRobustnessEvidence:
    """Validated robustness evidence artifact and canonical document."""

    artifact: ArtifactContractRecord
    document: dict
    evidence_identity: str
