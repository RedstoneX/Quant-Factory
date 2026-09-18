"""Typed evidence-decision artifact records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from persistence.models import ArtifactContractRecord

EVIDENCE_DECISION_LOGICAL_NAME = "evidence_decision_record"
EVIDENCE_DECISION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PersistedEvidenceDecisionRecord:
    """Validated durable evidence decision record."""

    artifact: ArtifactContractRecord
    document: Mapping[str, Any]
    decision_identity: str
