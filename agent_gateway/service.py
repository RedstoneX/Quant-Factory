"""Provider-neutral application service over existing Quant Factory contracts."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from agent_gateway.contracts import (
    GatewayError,
    GatewayIdentity,
    GatewayRequest,
    GatewayResponse,
    failure,
    success,
)
from agent_gateway.store import GatewayStore
from persistence import PersistenceService, RunStage, StrategyLifecycle
from research_intake import (
    build_research_context,
    import_candidate_as_idea,
    parse_candidate_packet,
    validate_candidate_packet,
)


RunLauncher = Callable[[str, str, str], str]
_STATE_CHANGING = {"candidate.submit", "research.note.add", "run.request"}
_LEVELS = {
    "context.get": 0,
    "prior.search": 0,
    "candidate.list": 0,
    "candidate.get": 0,
    "run.status": 0,
    "run.results": 0,
    "run.evidence": 0,
    "lineage.get": 0,
    "candidate.validate": 1,
    "candidate.submit": 1,
    "research.note.add": 1,
    "run.request": 2,
}
_SAFE_EVIDENCE_STATES = {"gated", "not_applicable", None}
_WORD = re.compile(r"[a-z0-9]+")
_SECRET_KEY = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|auth(?:orization)?|credential|password|private[_-]?key|secret|token)"
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|password|secret|token|signature|sig)\s*[:=]\s*[^\s&]+"
)


class AgentResearchGateway:
    def __init__(
        self,
        *,
        database: str | Path,
        gateway_database: str | Path,
        artifact_root: str | Path,
        run_launcher: RunLauncher | None = None,
    ) -> None:
        self.database = Path(database)
        self.gateway_database = Path(gateway_database)
        self.artifact_root = Path(artifact_root)
        self.run_launcher = run_launcher

    def handle(
        self,
        request: GatewayRequest,
        identity: GatewayIdentity,
    ) -> GatewayResponse:
        store = GatewayStore(self.gateway_database)
        try:
            if request.operation in _STATE_CHANGING:
                replay = store.audited_request(request.request_id)
                if replay is not None:
                    if (
                        replay["agent_id"] != identity.agent_id
                        or replay["transport"] != identity.transport
                        or replay["operation"] != request.operation
                    ):
                        return failure(
                            request.request_id,
                            "request_conflict",
                            "request identity is already bound to another caller or operation",
                        )
                    replay = replay["response"]
                    return GatewayResponse(
                        request_id=str(replay["request_id"]),
                        ok=bool(replay["ok"]),
                        result=replay.get("result"),
                        error=replay.get("error"),
                    )
            candidate_id = _text(request.arguments.get("candidate_id")) or None
            run_id = _text(request.arguments.get("run_id")) or None
            try:
                lineage = _lineage_argument(request.arguments)
                result = self._dispatch(request, identity, store)
                response = success(request.request_id, result)
                accepted, reason = True, "accepted"
                if isinstance(result, Mapping):
                    candidate_id = _text(result.get("candidate_id")) or candidate_id
                    run_id = _text(result.get("run_id")) or run_id
            except GatewayError as exc:
                lineage = None
                response = failure(request.request_id, exc.code, exc.safe_message)
                accepted, reason = False, exc.code
            except (KeyError, ValueError) as exc:
                lineage = None
                response = failure(request.request_id, "invalid_request", _safe_validation_message(exc))
                accepted, reason = False, "invalid_request"
            except Exception:
                lineage = None
                response = failure(
                    request.request_id,
                    "internal_error",
                    "gateway operation failed without exposing internal details",
                )
                accepted, reason = False, "internal_error"
            if request.operation in _STATE_CHANGING:
                store.audit(
                    request_id=request.request_id,
                    agent_id=identity.agent_id,
                    transport=identity.transport,
                    peer_uid=identity.peer_uid,
                    operation=request.operation,
                    candidate_id=candidate_id,
                    run_id=run_id,
                    authority_level=identity.authority_level,
                    accepted=accepted,
                    reason_code=reason,
                    parent_lineage=lineage,
                    response=response.document(),
                )
            return response
        finally:
            store.close()

    def _dispatch(
        self,
        request: GatewayRequest,
        identity: GatewayIdentity,
        store: GatewayStore,
    ) -> Any:
        required = _LEVELS.get(request.operation)
        if required is None:
            raise GatewayError("operation_not_allowed", "gateway operation is not allowed")
        if identity.authority_level < required:
            raise GatewayError("authority_denied", "agent authority does not permit this operation")
        handlers = {
            "context.get": self._context_get,
            "prior.search": self._prior_search,
            "candidate.validate": self._candidate_validate,
            "candidate.submit": self._candidate_submit,
            "candidate.get": self._candidate_get,
            "candidate.list": self._candidate_list,
            "research.note.add": self._note_add,
            "lineage.get": self._lineage_get,
            "run.request": self._run_request,
            "run.status": self._run_status,
            "run.results": self._run_results,
            "run.evidence": self._run_evidence,
        }
        return handlers[request.operation](request, identity, store)

    def _context_get(self, *_: Any) -> dict[str, Any]:
        return build_research_context()

    def _prior_search(
        self, request: GatewayRequest, _identity: GatewayIdentity, _store: GatewayStore
    ) -> dict[str, Any]:
        query = _bounded_text(request.arguments.get("query"), "query", 200)
        _reject_secret_material(query)
        terms = set(_WORD.findall(query.lower()))
        if not terms:
            raise GatewayError("invalid_query", "prior-work query must contain searchable terms")
        rows: list[dict[str, Any]] = []
        for item in build_research_context()["prior_work"]:
            score = _overlap_score(terms, json.dumps(item, sort_keys=True))
            if score:
                rows.append({"kind": "prior_work", "score": score, "record": item})
        service = PersistenceService(self.database)
        try:
            for draft in service.idea_drafts.list():
                searchable = " ".join(
                    (draft.title, draft.description, draft.attribution, draft.candidate_json)
                )
                score = _overlap_score(terms, searchable)
                if score:
                    rows.append(
                        {
                            "kind": "candidate",
                            "score": score,
                            "record": _candidate_summary(draft),
                        }
                    )
        finally:
            service.close()
        rows.sort(key=lambda row: (-row["score"], row["kind"], json.dumps(row["record"], sort_keys=True)))
        return {"query": query, "matches": rows[:50]}

    def _candidate_validate(
        self, request: GatewayRequest, _identity: GatewayIdentity, _store: GatewayStore
    ) -> dict[str, Any]:
        document = parse_candidate_packet(_required_payload(request))
        _reject_secret_material(document)
        validation = validate_candidate_packet(document)
        return _validation_document(validation)

    def _candidate_submit(
        self, request: GatewayRequest, identity: GatewayIdentity, store: GatewayStore
    ) -> dict[str, Any]:
        payload = _required_payload(request)
        document = parse_candidate_packet(payload)
        _reject_secret_material(document)
        validation = validate_candidate_packet(document)
        if not validation.valid:
            raise GatewayError("candidate_invalid", "Candidate failed QF Candidate v1 validation")
        content_hash = hashlib.sha256(validation.canonical_json.encode("utf-8")).hexdigest()
        candidate_id = f"qfc_{content_hash[:32]}"
        existing = store.candidate_for_hash(content_hash)
        if existing is not None:
            return {
                "candidate_id": existing["candidate_id"],
                "duplicate": True,
                "validation": _validation_document(validation),
            }
        lineage = _validated_lineage(request.arguments, self.database)
        imported = import_candidate_as_idea(
            validation.document,
            database=self.database,
            draft_id=candidate_id,
        )
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
            "validation": _validation_document(imported.validation),
        }

    def _candidate_get(
        self, request: GatewayRequest, _identity: GatewayIdentity, _store: GatewayStore
    ) -> dict[str, Any]:
        candidate_id = _identifier(request.arguments.get("candidate_id"), "candidate")
        service = PersistenceService(self.database)
        try:
            draft = service.idea_drafts.get(candidate_id)
            if draft is None:
                raise GatewayError("not_found", "Candidate was not found")
            return _redact_value(_candidate_document(draft))
        finally:
            service.close()

    def _candidate_list(self, *_: Any) -> dict[str, Any]:
        service = PersistenceService(self.database)
        try:
            return {"candidates": [_candidate_summary(row) for row in service.idea_drafts.list()]}
        finally:
            service.close()

    def _note_add(
        self, request: GatewayRequest, identity: GatewayIdentity, store: GatewayStore
    ) -> dict[str, Any]:
        candidate_id = _identifier(request.arguments.get("candidate_id"), "candidate")
        note = _required_payload(request)
        _reject_secret_material(note)
        if len(note) > 4_000:
            raise GatewayError("note_too_large", "research note exceeds 4,000 characters")
        service = PersistenceService(self.database)
        try:
            if service.idea_drafts.get(candidate_id) is None:
                raise GatewayError("not_found", "Candidate was not found")
        finally:
            service.close()
        note_id = store.add_note(candidate_id=candidate_id, agent_id=identity.agent_id, note=note)
        return {"candidate_id": candidate_id, "note_id": note_id}

    def _lineage_get(
        self, request: GatewayRequest, _identity: GatewayIdentity, store: GatewayStore
    ) -> dict[str, Any]:
        candidate_id = _identifier(request.arguments.get("candidate_id"), "candidate")
        gateway_lineage = store.lineage(candidate_id)
        service = PersistenceService(self.database)
        try:
            draft = service.idea_drafts.get(candidate_id)
            if draft is None:
                raise GatewayError("not_found", "Candidate was not found")
            run_ids = []
            if draft.configuration_id:
                run_ids = [
                    row.run_id
                    for row in service.runs.list()
                    if row.configuration_id == draft.configuration_id
                ]
        finally:
            service.close()
        return {
            "candidate_id": candidate_id,
            "configuration_id": draft.configuration_id,
            "runs": run_ids,
            "gateway": gateway_lineage,
        }

    def _run_request(
        self, request: GatewayRequest, _identity: GatewayIdentity, _store: GatewayStore
    ) -> dict[str, Any]:
        if self.run_launcher is None:
            raise GatewayError("run_unavailable", "development-run requests are disabled")
        candidate_id = _identifier(request.arguments.get("candidate_id"), "candidate")
        service = PersistenceService(self.database)
        try:
            draft = service.idea_drafts.get(candidate_id)
            if draft is None:
                raise GatewayError("not_found", "Candidate was not found")
            try:
                candidate = json.loads(draft.candidate_json)
            except json.JSONDecodeError as exc:
                raise GatewayError("candidate_invalid", "Candidate content is invalid") from exc
            status = _text((candidate.get("candidate") or {}).get("status")) if isinstance(candidate, dict) else ""
            if status != "owner_approved":
                raise GatewayError("owner_approval_required", "Candidate is not owner approved")
            if not draft.configuration_id:
                raise GatewayError("configuration_required", "Candidate has no linked immutable configuration")
            configuration = service.configurations.get(draft.configuration_id)
            if configuration is None:
                raise GatewayError("configuration_required", "linked configuration was not found")
            strategy = service.strategies.get(configuration.strategy_id, configuration.strategy_version)
            if (
                strategy is None
                or not strategy.active
                or strategy.lifecycle != StrategyLifecycle.CANDIDATE
            ):
                raise GatewayError("candidate_not_executable", "linked strategy is not an active Candidate")
            configuration_id = configuration.configuration_id
        finally:
            service.close()
        idempotency_key = f"agent_{hashlib.sha256(candidate_id.encode()).hexdigest()[:48]}"
        run_id = self.run_launcher(candidate_id, configuration_id, idempotency_key)
        return {"candidate_id": candidate_id, "run_id": run_id, "idempotency_key": idempotency_key}

    def _run_status(
        self, request: GatewayRequest, _identity: GatewayIdentity, _store: GatewayStore
    ) -> dict[str, Any]:
        run_id = _identifier(request.arguments.get("run_id"), "run")
        service = PersistenceService(self.database)
        try:
            run = _permitted_run(service, run_id)
            return {"run": _run_summary(run)}
        finally:
            service.close()

    def _run_results(
        self, request: GatewayRequest, _identity: GatewayIdentity, _store: GatewayStore
    ) -> dict[str, Any]:
        run_id = _identifier(request.arguments.get("run_id"), "run")
        service = PersistenceService(self.database)
        try:
            run = _permitted_run(service, run_id)
            if run.stage not in {RunStage.FIXTURE, RunStage.SCREENING}:
                raise GatewayError("protected_result_denied", "full results are unavailable for this run stage")
            rows = service.results.list_parameter_results(run_id)
            return {
                "run": _run_summary(run),
                "parameters": [
                    {
                        "row_id": row.row_id,
                        "parameters": json.loads(row.normalized_parameters_json),
                        "metrics": json.loads(row.metrics_json),
                        "ranking_position": row.ranking_position,
                        "screening_status": row.screening_status,
                        "rejection_reasons": row.rejection_reasons,
                    }
                    for row in rows
                ],
            }
        finally:
            service.close()

    def _run_evidence(
        self, request: GatewayRequest, _identity: GatewayIdentity, _store: GatewayStore
    ) -> dict[str, Any]:
        run_id = _identifier(request.arguments.get("run_id"), "run")
        service = PersistenceService(self.database)
        try:
            run = _permitted_run(service, run_id)
            retrieval = service.retrieve_run_artifacts(run_id, artifact_root=self.artifact_root)
            invalid = [item.reason for item in retrieval.validations if not item.valid]
            if invalid:
                raise GatewayError("evidence_invalid", "run evidence failed persisted artifact validation")
            summaries = []
            for artifact, checked in zip(retrieval.artifacts, retrieval.validations, strict=True):
                if artifact.artifact_type.value != "validation_evidence":
                    continue
                path = Path(checked.resolved_path or "")
                document = json.loads(path.read_text())
                protected_states = set(_values_for_key(document, "protected_data_state"))
                if not protected_states.issubset(_SAFE_EVIDENCE_STATES):
                    raise GatewayError("protected_result_denied", "protected evidence is not available through this gateway")
                normalized = (document.get("evidence") or {}).get("normalized_evidence")
                summaries.append(
                    {
                        "logical_name": artifact.logical_name,
                        "checksum": artifact.checksum,
                        "evidence_identity": (document.get("artifact") or {}).get("evidence_identity"),
                        "normalized_evidence": normalized,
                    }
                )
            return {
                "run": _run_summary(run),
                "manifest_checksum": retrieval.manifest_checksum,
                "evidence": summaries,
            }
        finally:
            service.close()


def _validation_document(validation: Any) -> dict[str, Any]:
    return {
        "valid": validation.valid,
        "review_ready": validation.review_ready,
        "parameter_combinations": validation.parameter_combinations,
        "issues": [_json_value(item) for item in validation.issues],
    }


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


def _permitted_run(service: PersistenceService, run_id: str) -> Any:
    run = service.runs.get(run_id)
    if run is None:
        raise GatewayError("not_found", "run was not found")
    if run.stage == RunStage.OOS:
        raise GatewayError("protected_result_denied", "protected-stage records are unavailable through this gateway")
    return run


def _validated_lineage(arguments: Mapping[str, Any], database: Path) -> dict[str, str] | None:
    lineage = _lineage_argument(arguments)
    if not lineage:
        return None
    required = (
        "change_reason",
        "evidence_cited",
        "rule_changed",
        "material_difference",
        "falsification",
        "bounded_search_space",
    )
    if not lineage.get("parent_candidate_id") and not lineage.get("parent_run_id"):
        raise GatewayError("lineage_invalid", "child Candidate requires a parent Candidate or run")
    for key in required:
        lineage[key] = _bounded_text(lineage.get(key), key, 1_000)
    service = PersistenceService(database)
    try:
        if lineage.get("parent_candidate_id") and service.idea_drafts.get(lineage["parent_candidate_id"]) is None:
            raise GatewayError("lineage_invalid", "parent Candidate was not found")
        if lineage.get("parent_run_id") and service.runs.get(lineage["parent_run_id"]) is None:
            raise GatewayError("lineage_invalid", "parent run was not found")
    finally:
        service.close()
    return lineage


def _lineage_argument(arguments: Mapping[str, Any]) -> dict[str, str] | None:
    value = arguments.get("lineage")
    if value in (None, {}):
        return None
    if not isinstance(value, Mapping):
        raise GatewayError("lineage_invalid", "Candidate lineage must be an object")
    allowed = {
        "parent_candidate_id",
        "parent_run_id",
        "change_reason",
        "evidence_cited",
        "rule_changed",
        "material_difference",
        "falsification",
        "bounded_search_space",
    }
    if set(value) - allowed:
        raise GatewayError("lineage_invalid", "Candidate lineage contains unsupported fields")
    return {key: _text(value.get(key)) for key in allowed}


def _values_for_key(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, Mapping):
        for name, child in value.items():
            if name == key:
                found.append(child)
            found.extend(_values_for_key(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_values_for_key(child, key))
    return found


def _required_payload(request: GatewayRequest) -> str:
    if request.payload is None or not request.payload.strip():
        raise GatewayError("payload_required", "operation requires a non-empty text payload")
    return request.payload


def _identifier(value: Any, label: str) -> str:
    text = _bounded_text(value, f"{label}_id", 128)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise GatewayError("invalid_identifier", f"{label} identity is invalid")
    return text


def _bounded_text(value: Any, label: str, maximum: int) -> str:
    text = _text(value)
    if not text or len(text) > maximum:
        raise GatewayError("invalid_text", f"{label} must contain 1 to {maximum} characters")
    return text


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _overlap_score(terms: set[str], text: str) -> int:
    haystack = set(_WORD.findall(text.lower()))
    return len(terms & haystack)


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    return value


def _safe_validation_message(exc: Exception) -> str:
    message = str(exc)
    if len(message) > 300:
        message = message[:297] + "..."
    lowered = message.lower()
    if any(token in lowered for token in ("token=", "api_key", "password", "secret=")):
        return "request failed validation; sensitive detail was redacted"
    return message or "request failed validation"


def _reject_secret_material(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _SECRET_KEY.search(str(key)):
                raise GatewayError("secret_material_denied", "secret-like material is not accepted")
            _reject_secret_material(child)
    elif isinstance(value, list):
        for child in value:
            _reject_secret_material(child)
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        raise GatewayError("secret_material_denied", "secret-like material is not accepted")


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
