"""Read operations listing an agent's ideas: candidate.list and candidate.status."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_gateway.contracts import GatewayIdentity, GatewayRequest
from agent_gateway.store import GatewayStore
from persistence import PersistenceService


def candidate_list(database: Path) -> dict[str, Any]:
    from agent_gateway.service import _candidate_summary

    service = PersistenceService(database)
    try:
        return {"candidates": [_candidate_summary(row) for row in service.idea_drafts.list()]}
    finally:
        service.close()


def candidate_status(
    store: GatewayStore, database: Path, request: GatewayRequest, identity: GatewayIdentity
) -> dict[str, Any]:
    """Every idea this agent submitted, its status and latest run, so it need not poll each run."""
    from agent_gateway.service import _bounded_text, _candidate_summary, _redact_value, _run_summary

    finished_since = request.arguments.get("finished_since")
    if finished_since is not None:
        finished_since = _bounded_text(finished_since, "finished_since", 40)
    candidate_ids = store.candidate_ids_created_by(identity.agent_id)
    service = PersistenceService(database)
    try:
        runs = service.runs.list()
        candidates = []
        for candidate_id in candidate_ids:
            draft = service.idea_drafts.get(candidate_id)
            if draft is None:
                continue
            own = [row for row in runs if draft.configuration_id and row.configuration_id == draft.configuration_id]
            latest = max(own, key=lambda row: (row.created_at, row.run_id), default=None)
            if finished_since is not None and (latest is None or not latest.completed_at or latest.completed_at <= finished_since):
                continue
            summary = _candidate_summary(draft)
            summary["latest_run"] = _run_summary(latest) if latest is not None else None
            candidates.append(summary)
        return _redact_value({"candidates": candidates, "finished_since": finished_since})
    finally:
        service.close()
