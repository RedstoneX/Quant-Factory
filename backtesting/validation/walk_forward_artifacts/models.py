"""Models for persisted generic walk-forward evidence artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

WALK_FORWARD_EVIDENCE_LOGICAL_NAME = "walk_forward_evidence"
WALK_FORWARD_EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PersistedWalkForwardEvidence:
    """Validated persisted generic walk-forward evidence."""

    artifact: Any
    document: dict[str, Any]
    evidence_identity: str
