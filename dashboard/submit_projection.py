"""Non-mutating validation projection for the Submit Strategies workspace."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

import yaml

from research_intake.qf_candidate import (
    CandidatePacketError,
    parse_candidate_packet,
    validate_candidate_packet,
)


MAX_UPLOAD_BYTES = 5_000_000
MAX_DEFINITIONS = 250
ACCEPTED_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml"}


def candidate_example() -> str:
    """Return the repository-owned QF Candidate v1 example."""

    path = Path(__file__).resolve().parents[1] / "research_intake" / "mes_sma_10_30_candidate.json"
    return path.read_text(encoding="utf-8")


def validate_candidate_text(text: str, *, filename: str = "candidate.yaml") -> dict[str, Any]:
    """Validate one candidate packet without persisting it."""

    suffix = Path(filename).suffix.lower()
    hint = "json" if suffix in {".json", ".jsonl"} else "yaml"
    try:
        document = parse_candidate_packet(text, format_hint=hint)
        result = validate_candidate_packet(document)
    except (CandidatePacketError, ValueError) as exc:
        return {"filename": filename, "title": Path(filename).name, "market": "—", "valid": False, "review_ready": False, "variations": None, "issues": [{"severity": "error", "path": "$", "message": str(exc)}]}
    candidate = document.get("candidate") if isinstance(document.get("candidate"), dict) else {}
    market = document.get("market") if isinstance(document.get("market"), dict) else {}
    instruments = market.get("instruments") if isinstance(market.get("instruments"), dict) else {}
    preferred = instruments.get("preferred") if isinstance(instruments.get("preferred"), list) else []
    return {
        "filename": filename,
        "title": str(candidate.get("title") or Path(filename).name),
        "market": " · ".join(str(value) for value in preferred) or "Unspecified",
        "valid": result.valid,
        "review_ready": result.review_ready,
        "variations": result.parameter_combinations,
        "issues": [{"severity": issue.severity, "path": issue.path, "message": issue.message} for issue in result.issues],
        "canonical_json": result.canonical_json if result.valid else None,
    }


def validate_upload(contents: str | None, filename: str | None) -> dict[str, Any]:
    """Decode and validate a bounded JSON/YAML/JSONL/ZIP upload in memory."""

    if not contents or not filename:
        return _summary([], "No package loaded")
    try:
        encoded = contents.split(",", 1)[1]
        payload = base64.b64decode(encoded, validate=True)
    except (IndexError, ValueError) as exc:
        return _summary([_upload_error(filename, f"Upload could not be decoded: {exc}")], filename)
    if len(payload) > MAX_UPLOAD_BYTES:
        return _summary([_upload_error(filename, f"Package exceeds the {MAX_UPLOAD_BYTES // 1_000_000} MB review limit")], filename)
    rows: list[dict[str, Any]] = []
    try:
        if Path(filename).suffix.lower() == ".zip":
            with ZipFile(BytesIO(payload)) as archive:
                members = [item for item in archive.infolist() if not item.is_dir() and Path(item.filename).suffix.lower() in ACCEPTED_SUFFIXES]
                if len(members) > MAX_DEFINITIONS:
                    raise CandidatePacketError(f"package contains more than {MAX_DEFINITIONS} definitions")
                for item in members:
                    if item.file_size > MAX_UPLOAD_BYTES or ".." in Path(item.filename).parts:
                        raise CandidatePacketError(f"unsafe archive member {item.filename!r}")
                    rows.extend(_validate_document_file(archive.read(item).decode("utf-8"), item.filename))
        else:
            rows = _validate_document_file(payload.decode("utf-8"), filename)
    except (BadZipFile, CandidatePacketError, UnicodeDecodeError, OSError, yaml.YAMLError) as exc:
        rows = [_upload_error(filename, str(exc))]
    return _summary(rows[:MAX_DEFINITIONS], filename)


def _validate_document_file(text: str, filename: str) -> list[dict[str, Any]]:
    if Path(filename).suffix.lower() == ".jsonl":
        return [validate_candidate_text(line, filename=f"{filename}:{index}") for index, line in enumerate(text.splitlines(), 1) if line.strip()]
    if Path(filename).suffix.lower() in {".yaml", ".yml"}:
        documents = list(yaml.safe_load_all(text))
        return [validate_candidate_text(yaml.safe_dump(document), filename=f"{filename}:{index}") for index, document in enumerate(documents, 1) if document is not None]
    return [validate_candidate_text(text, filename=filename)]


def _upload_error(filename: str, message: str) -> dict[str, Any]:
    return {"filename": filename, "title": Path(filename).name, "market": "—", "valid": False, "review_ready": False, "variations": None, "issues": [{"severity": "error", "path": "$", "message": message}]}


def _summary(rows: list[dict[str, Any]], package: str) -> dict[str, Any]:
    valid = sum(1 for row in rows if row.get("valid"))
    ready = sum(1 for row in rows if row.get("review_ready"))
    variations = sum(int(row.get("variations") or 0) for row in rows if row.get("valid"))
    return {"package": package, "rows": rows, "definitions": len(rows), "valid": valid, "needs_attention": len(rows) - ready, "ready": ready, "variations": variations}


__all__ = ["candidate_example", "validate_candidate_text", "validate_upload"]
