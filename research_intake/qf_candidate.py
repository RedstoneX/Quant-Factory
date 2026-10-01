"""QF Candidate v1: provider-neutral research-intake contract.

This module validates and persists research proposals only. It never registers a
strategy, creates a runnable configuration, launches VectorBT, fetches sources,
or calls an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import yaml

from persistence import IdeaDraftRecord, PersistenceService, canonical_json

QF_CANDIDATE_SCHEMA = "qf_candidate_v1"
MAX_PACKET_CHARS = 100_000
MAX_VARIABLE_VALUES = 64
MAX_PARAMETER_COMBINATIONS = 10_000

_ALLOWED_STATUSES = {
    "draft",
    "needs_clarification",
    "ready_for_review",
    "owner_approved",
    "implemented",
    "rejected",
    "retired",
}
_ALLOWED_IMPORTANCE = {"high", "medium", "low"}
_FORBIDDEN_CONTROL_KEYS = {
    "auto_launch",
    "execute_now",
    "submit_order",
    "place_order",
    "paper_trade",
    "live_trade",
    "capital_allocation",
    "python_code",
    "vectorbt_code",
}


class CandidatePacketError(ValueError):
    """Raised when a Candidate packet cannot be parsed or safely imported."""


@dataclass(frozen=True)
class CandidateIssue:
    severity: str
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class CandidateValidation:
    document: dict[str, Any]
    canonical_json: str
    issues: tuple[CandidateIssue, ...]
    parameter_combinations: int

    @property
    def errors(self) -> tuple[CandidateIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[CandidateIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def review_ready(self) -> bool:
        if not self.valid:
            return False
        questions = self.document.get("open_questions") or []
        return not any(
            isinstance(question, Mapping)
            and str(question.get("importance", "")).strip().lower() == "high"
            for question in questions
        )


@dataclass(frozen=True)
class CandidateImportResult:
    draft: IdeaDraftRecord
    validation: CandidateValidation


def parse_candidate_packet(
    payload: str | Mapping[str, Any],
    *,
    format_hint: str | None = None,
) -> dict[str, Any]:
    """Parse YAML/JSON into a plain mapping without executing source content."""

    if isinstance(payload, Mapping):
        document = dict(payload)
    else:
        text = str(payload)
        if len(text) > MAX_PACKET_CHARS:
            raise CandidatePacketError(
                f"candidate packet exceeds {MAX_PACKET_CHARS:,} characters"
            )
        hint = (format_hint or "").strip().lower()
        try:
            if hint == "json" or (not hint and text.lstrip().startswith(("{", "["))):
                document = json.loads(text)
            elif hint in {"yaml", "yml", ""}:
                document = yaml.safe_load(text)
            else:
                raise CandidatePacketError(f"unsupported candidate format {format_hint!r}")
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise CandidatePacketError("candidate packet is not valid JSON/YAML") from exc
    if not isinstance(document, dict):
        raise CandidatePacketError("candidate packet must contain one top-level object")
    return document


def validate_candidate_packet(document: Mapping[str, Any]) -> CandidateValidation:
    """Validate research structure and active intraday safety boundaries."""

    doc = _plain(document)
    issues: list[CandidateIssue] = []

    def error(code: str, path: str, message: str) -> None:
        issues.append(CandidateIssue("error", code, path, message))

    def warning(code: str, path: str, message: str) -> None:
        issues.append(CandidateIssue("warning", code, path, message))

    if doc.get("schema") != QF_CANDIDATE_SCHEMA:
        error("schema", "schema", f"schema must be {QF_CANDIDATE_SCHEMA!r}")

    candidate = _mapping(doc.get("candidate"))
    title = _text(candidate.get("title"))
    if not title:
        error("candidate_title", "candidate.title", "candidate title is required")
    elif len(title) > 160:
        error("candidate_title_length", "candidate.title", "candidate title is too long")
    status = _text(candidate.get("status")) or "draft"
    if status not in _ALLOWED_STATUSES:
        error("candidate_status", "candidate.status", "candidate status is not recognized")

    hypothesis = _mapping(doc.get("hypothesis"))
    if not _text(hypothesis.get("behavior")):
        error("hypothesis", "hypothesis.behavior", "a falsifiable behavior hypothesis is required")
    if not hypothesis.get("failure_theory"):
        warning(
            "failure_theory_missing",
            "hypothesis.failure_theory",
            "record why the proposed edge might fail before approval",
        )

    market = _mapping(doc.get("market"))
    holding_style = _text(market.get("holding_style")).lower()
    if holding_style != "intraday":
        error(
            "holding_style",
            "market.holding_style",
            "current Quant Factory mandate requires holding_style: intraday",
        )
    if market.get("overnight_positions") is not False:
        error(
            "overnight_positions",
            "market.overnight_positions",
            "current Quant Factory mandate requires overnight_positions: false",
        )

    rules = _mapping(doc.get("rules"))
    if not rules:
        error("rules", "rules", "testable strategy rules are required")

    sources = doc.get("sources", [])
    if sources is None:
        sources = []
    if not isinstance(sources, list):
        error("sources_type", "sources", "sources must be a list")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, Mapping):
                error("source_type", f"sources[{index}]", "each source must be an object")
                continue
            source_type = _text(source.get("type")).lower()
            if not source_type:
                error("source_kind", f"sources[{index}].type", "source type is required")
            url = _text(source.get("url"))
            if url and not _valid_public_url(url):
                error("source_url", f"sources[{index}].url", "source URL must be http/https without embedded credentials")
            if not url and source_type != "owner_observation":
                warning(
                    "source_reference_missing",
                    f"sources[{index}]",
                    "non-owner sources should retain a URL or equivalent reference",
                )

    variables = _mapping(doc.get("variables"))
    combination_count = 1
    for name, specification in variables.items():
        path = f"variables.{name}"
        if not isinstance(specification, Mapping):
            error("variable_spec", path, "variable definition must be an object")
            continue
        values = specification.get("values")
        if not isinstance(values, list) or not values:
            error("variable_values", f"{path}.values", "variable must define a non-empty bounded values list")
            continue
        if len(values) > MAX_VARIABLE_VALUES:
            error(
                "variable_too_wide",
                f"{path}.values",
                f"variable may contain at most {MAX_VARIABLE_VALUES} values",
            )
            continue
        if any(not _scalar(value) for value in values):
            error("variable_scalar", f"{path}.values", "variable values must be scalar JSON values")
            continue
        if len({canonical_json(value) for value in values}) != len(values):
            error("variable_duplicate", f"{path}.values", "variable values must be unique")
            continue
        combination_count *= len(values)

    if combination_count > MAX_PARAMETER_COMBINATIONS:
        warning(
            "large_parameter_space",
            "variables",
            f"bounded grid expands to {combination_count:,} combinations; review before execution",
        )

    variants = doc.get("variants", []) or []
    if not isinstance(variants, list):
        error("variants_type", "variants", "variants must be a list")
    else:
        seen_variants: set[str] = set()
        for index, variant in enumerate(variants):
            if not isinstance(variant, Mapping):
                error("variant_type", f"variants[{index}]", "each structural variant must be an object")
                continue
            variant_id = _text(variant.get("id"))
            if not variant_id:
                error("variant_id", f"variants[{index}].id", "structural variant id is required")
            elif variant_id in seen_variants:
                error("variant_duplicate", f"variants[{index}].id", "structural variant ids must be unique")
            else:
                seen_variants.add(variant_id)
            if not _text(variant.get("difference")):
                warning(
                    "variant_difference",
                    f"variants[{index}].difference",
                    "state how this structural variant differs from the base hypothesis",
                )

    questions = doc.get("open_questions", []) or []
    if not isinstance(questions, list):
        error("questions_type", "open_questions", "open_questions must be a list")
    else:
        for index, question in enumerate(questions):
            if not isinstance(question, Mapping):
                error("question_type", f"open_questions[{index}]", "each question must be an object")
                continue
            if not _text(question.get("question")):
                error("question_text", f"open_questions[{index}].question", "question text is required")
            importance = _text(question.get("importance")).lower() or "medium"
            if importance not in _ALLOWED_IMPORTANCE:
                error("question_importance", f"open_questions[{index}].importance", "importance must be high, medium, or low")

    execution = doc.get("execution")
    if execution is not None:
        if not isinstance(execution, Mapping):
            error("execution_type", "execution", "execution must be an object")
        elif "use_qf_defaults" in execution and not isinstance(execution["use_qf_defaults"], bool):
            error("execution_defaults", "execution.use_qf_defaults", "use_qf_defaults must be true or false")

    for path, key, value in _walk_items(doc):
        if key in _FORBIDDEN_CONTROL_KEYS and value not in (None, False, "", [], {}):
            error(
                "forbidden_control",
                path,
                f"{key} is not allowed in a QF Candidate packet; intake cannot execute or authorize trading",
            )
        if isinstance(value, float) and not math.isfinite(value):
            error("non_finite", path, "candidate packet cannot contain NaN or infinite values")

    canonical = canonical_json(doc)
    if len(canonical) > MAX_PACKET_CHARS:
        error("packet_size", "$", f"canonical candidate packet exceeds {MAX_PACKET_CHARS:,} characters")

    return CandidateValidation(
        document=doc,
        canonical_json=canonical,
        issues=tuple(issues),
        parameter_combinations=combination_count if variables else 0,
    )


def import_candidate_as_idea(
    payload: str | Mapping[str, Any],
    *,
    database: str | Path | None = None,
    format_hint: str | None = None,
) -> CandidateImportResult:
    """Persist one valid Candidate packet as a durable, non-executable idea draft."""

    document = parse_candidate_packet(payload, format_hint=format_hint)
    validation = validate_candidate_packet(document)
    if not validation.valid:
        detail = "; ".join(f"{issue.path}: {issue.message}" for issue in validation.errors)
        raise CandidatePacketError(f"candidate packet failed validation: {detail}")

    candidate = _mapping(document.get("candidate"))
    hypothesis = _mapping(document.get("hypothesis"))
    sources = document.get("sources") if isinstance(document.get("sources"), list) else []
    first_source = next((source for source in sources if isinstance(source, Mapping)), {})
    source_url = _text(first_source.get("url"))
    attribution = _source_attribution(first_source)
    questions = document.get("open_questions") if isinstance(document.get("open_questions"), list) else []
    notes = "\n".join(
        f"- {_text(question.get('question'))}"
        for question in questions
        if isinstance(question, Mapping) and _text(question.get("question"))
    )

    service = PersistenceService(database)
    try:
        draft = service.save_idea_draft(
            title=_text(candidate.get("title")),
            description=_text(hypothesis.get("behavior")),
            source_url=source_url,
            attribution=attribution,
            notes=notes[:2000],
        )
        draft = service.set_idea_candidate_packet(
            draft_id=draft.draft_id,
            candidate_json=validation.canonical_json,
        )
        return CandidateImportResult(draft=draft, validation=validation)
    finally:
        service.close()


def export_candidate_packet(
    document: Mapping[str, Any],
    *,
    format: str = "yaml",
) -> str:
    """Serialize a validated packet for exchange with an external LLM/tool."""

    validation = validate_candidate_packet(document)
    if not validation.valid:
        detail = "; ".join(f"{issue.path}: {issue.message}" for issue in validation.errors)
        raise CandidatePacketError(f"candidate packet failed validation: {detail}")
    if format == "json":
        return json.dumps(validation.document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if format in {"yaml", "yml"}:
        return yaml.safe_dump(validation.document, sort_keys=False, allow_unicode=True)
    raise CandidatePacketError(f"unsupported export format {format!r}")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise CandidatePacketError(f"candidate packet contains unsupported value type {type(value).__name__}")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _valid_public_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and parsed.username is None and parsed.password is None


def _source_attribution(source: Mapping[str, Any]) -> str:
    parts = [
        _text(source.get("creator")),
        _text(source.get("community")),
        _text(source.get("title")),
    ]
    return " · ".join(part for part in parts if part)[:240]


def _walk_items(value: Any, path: str = "$"):
    if isinstance(value, Mapping):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), item
            yield from _walk_items(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_items(item, f"{path}[{index}]")
