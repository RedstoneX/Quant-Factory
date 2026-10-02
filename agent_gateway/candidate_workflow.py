"""Candidate persistence and exact execution binding for the agent gateway."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from agent_gateway.contracts import GatewayError, GatewayIdentity
from agent_gateway.store import GatewayStore
from persistence import PersistenceService, StrategyLifecycle
from research_intake import import_candidate_as_idea


def persist_submitted_candidate(
    *,
    validation: Any,
    validation_document: dict[str, Any],
    candidate_id: str,
    content_hash: str,
    lineage: Mapping[str, Any] | None,
    identity: GatewayIdentity,
    store: GatewayStore,
    database: str | Path,
) -> dict[str, Any]:
    imported = import_candidate_as_idea(validation.document, database=database, draft_id=candidate_id)
    origin = f"Agent {identity.agent_id} ({identity.provider})"
    if lineage is not None:
        origin += f" · revision of {lineage['parent_candidate_id']}"
    if imported.draft.attribution:
        origin += f" · source: {imported.draft.attribution}"
    service = PersistenceService(database)
    try:
        service.save_idea_draft(
            draft_id=imported.draft.draft_id,
            title=imported.draft.title,
            description=imported.draft.description,
            source_url=imported.draft.source_url,
            attribution=origin[:240],
            notes=imported.draft.notes,
        )
    finally:
        service.close()
    created = store.record_candidate(
        candidate_id=candidate_id,
        content_hash=content_hash,
        canonical_json=validation.canonical_json,
        created_by=identity.agent_id,
        lineage=lineage,
    )
    return {
        "candidate_id": imported.draft.draft_id,
        "duplicate": not created,
        "validation": validation_document,
    }


def executable_candidate_configuration(candidate_id: str, database: str | Path) -> str:
    service = PersistenceService(database)
    try:
        draft = service.idea_drafts.get(candidate_id)
        if draft is None:
            raise GatewayError("not_found", "Candidate was not found")
        try:
            candidate = json.loads(draft.candidate_json)
        except json.JSONDecodeError as exc:
            raise GatewayError("candidate_invalid", "Candidate content is invalid") from exc
        status = str((candidate.get("candidate") or {}).get("status") or "") if isinstance(candidate, dict) else ""
        if status != "owner_approved":
            raise GatewayError("owner_approval_required", "Candidate is not owner approved")
        if not draft.configuration_id:
            raise GatewayError("configuration_required", "Candidate has no linked immutable configuration")
        linked = tuple(row.draft_id for row in service.idea_drafts.list() if row.configuration_id == draft.configuration_id)
        if linked != (candidate_id,):
            raise GatewayError("candidate_not_executable", "linked configuration does not identify exactly one Candidate")
        configuration = service.configurations.get(draft.configuration_id)
        if configuration is None:
            raise GatewayError("configuration_required", "linked configuration was not found")
        strategy = service.strategies.get(configuration.strategy_id, configuration.strategy_version)
        if strategy is None or not strategy.active or strategy.lifecycle != StrategyLifecycle.CANDIDATE:
            raise GatewayError("candidate_not_executable", "linked strategy is not an active Candidate")
        return configuration.configuration_id
    finally:
        service.close()
