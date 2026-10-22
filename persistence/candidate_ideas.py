"""Atomic persistence operation for content-addressed Candidate ideas."""

from __future__ import annotations

from typing import Protocol

from persistence.database import transaction
from persistence.models import IdeaDraftRecord


class CandidateIdeaPersistence(Protocol):
    connection: object
    idea_drafts: object


def save_candidate_idea(
    service: CandidateIdeaPersistence,
    *,
    draft_id: str,
    title: str,
    candidate_json: str,
    description: str = "",
    source_url: str = "",
    attribution: str = "",
    notes: str = "",
) -> tuple[IdeaDraftRecord, bool]:
    """Atomically create one content-addressed Candidate idea or return it."""

    with transaction(service.connection):  # type: ignore[arg-type]
        existing = service.idea_drafts.get(draft_id)
        if existing is not None:
            if existing.candidate_json != candidate_json:
                raise ValueError("candidate identity already has different content")
            return existing, False
        draft = service.idea_drafts.save(
            draft_id=draft_id,
            title=title,
            description=description,
            source_url=source_url,
            attribution=attribution,
            notes=notes,
        )
        draft = service.idea_drafts.set_candidate_packet(draft_id, candidate_json)
        return draft, True
