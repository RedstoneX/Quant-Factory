"""Models for persisted Monte Carlo evidence artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MONTE_CARLO_EVIDENCE_LOGICAL_NAME = "monte_carlo_evidence"
MONTE_CARLO_EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PersistedMonteCarloEvidence:
    """Validated persisted Monte Carlo evidence."""

    artifact: Any
    document: dict[str, Any]
    evidence_identity: str
