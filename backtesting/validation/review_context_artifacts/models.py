"""Typed review-context artifact records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from persistence.artifact_contracts import REVIEW_CONTEXT_LOGICAL_NAME
from persistence.models import ArtifactContractRecord

REVIEW_CONTEXT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PersistedReviewContextRecord:
    """Validated review context linking one target run to prerequisite evidence."""

    artifact: ArtifactContractRecord
    document: Mapping[str, Any]
    context_identity: str
