"""Candidate and run summary documents plus secret redaction, shared by gateway read operations."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from agent_gateway.contracts import GatewayError

_SECRET_KEY = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|auth(?:orization)?|credential|password|private[_-]?key|secret|token)"
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|password|secret|token|signature|sig)\s*[:=]\s*[^\s&]+"
)


def _candidate_summary(draft: Any) -> dict[str, Any]:
    status = "idea"
    if draft.candidate_json:
        try:
            document = json.loads(draft.candidate_json)
            status = _text((document.get("candidate") or {}).get("status")) or "draft"
        except (AttributeError, json.JSONDecodeError):
            status = "invalid"
    return {
        "candidate_id": draft.draft_id,
        "title": draft.title,
        "status": status,
        "configuration_id": draft.configuration_id,
        "updated_at": draft.updated_at,
    }


def _candidate_document(draft: Any) -> dict[str, Any]:
    summary = _candidate_summary(draft)
    summary["candidate"] = json.loads(draft.candidate_json) if draft.candidate_json else None
    return summary


def _run_summary(run: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "configuration_id": run.configuration_id,
        "strategy_id": run.strategy_id,
        "strategy_version": run.strategy_version,
        "stage": run.stage.value,
        "status": run.status.value,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "error_summary": _redact_text(run.error_summary) if run.error_summary else None,
        "attempt_count": run.attempt_count,
    }


def _bounded_text(value: Any, label: str, maximum: int) -> str:
    text = _text(value)
    if not text or len(text) > maximum:
        raise GatewayError("invalid_text", f"{label} must contain 1 to {maximum} characters")
    return text


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _redact_text(value: str) -> str:
    return _SECRET_VALUE.sub("[REDACTED]", value)[:1_000]


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]" if _SECRET_KEY.search(str(key)) else _redact_value(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(child) for child in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value
