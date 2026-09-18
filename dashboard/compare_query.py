"""Strict, presentation-safe Compare query handling."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import parse_qsl, urlencode


_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_MAX_QUERY_LENGTH = 2_048
_MAX_RUN_ID_LENGTH = 256
_MAX_VISIBLE_TOKEN_LENGTH = 96
_MIN_COMPARE_RUNS = 2
_MAX_COMPARE_RUNS = 4


@dataclass(frozen=True, slots=True)
class CompareQueryRequest:
    """One parsed Compare request without any persistence lookup."""

    requested: bool
    run_ids: tuple[str, ...] = ()
    visible_tokens: tuple[str, ...] = ()
    error: str | None = None

    @property
    def valid(self) -> bool:
        return self.requested and self.error is None


def parse_compare_search(search: str | None) -> CompareQueryRequest:
    """Parse an ordered two-to-four-run query and fail closed on ambiguity."""

    if not search:
        return CompareQueryRequest(requested=False)
    query = search[1:] if search.startswith("?") else search
    if not query:
        return CompareQueryRequest(requested=False)
    if len(query) > _MAX_QUERY_LENGTH:
        return _invalid((query,), "The comparison query is too long.")
    if _INVALID_PERCENT_ESCAPE.search(query):
        return _invalid((query,), "The comparison query has invalid URL encoding.")
    try:
        pairs = parse_qsl(
            query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=20,
        )
    except (UnicodeDecodeError, ValueError):
        return _invalid((query,), "The comparison query could not be parsed safely.")

    values = tuple(value for key, value in pairs if key == "run_id")
    visible = values or tuple(f"{key}={value}" for key, value in pairs)
    if any(key != "run_id" for key, _ in pairs):
        return _invalid(visible, "Only repeated run_id fields are allowed.")
    if not _MIN_COMPARE_RUNS <= len(values) <= _MAX_COMPARE_RUNS:
        return _invalid(
            visible,
            "An exact comparison requires two to four persisted run identities.",
        )
    if any(not value.strip() for value in values):
        return _invalid(values, "Every requested run identity must be non-empty.")
    if any(len(value) > _MAX_RUN_ID_LENGTH for value in values):
        return _invalid(values, "A requested run identity is too long.")
    if any(_has_control_characters(value) for value in values):
        return _invalid(values, "A requested run identity contains control characters.")
    if len(set(values)) != len(values):
        return _invalid(values, "Requested run identities must be distinct.")
    return CompareQueryRequest(
        requested=True,
        run_ids=values,
        visible_tokens=tuple(_visible_token(value) for value in values),
    )


def compare_query_href(run_ids: tuple[str, ...] | list[str]) -> str | None:
    """Build an ordinary exact-comparison link for a safe distinct selection."""

    values = tuple(str(run_id) for run_id in run_ids)
    query = urlencode(tuple(("run_id", value) for value in values))
    parsed = parse_compare_search(f"?{query}")
    if not parsed.valid or parsed.run_ids != values:
        return None
    return f"/research/compare-backtests?{query}"


def _invalid(tokens: tuple[str, ...], error: str) -> CompareQueryRequest:
    return CompareQueryRequest(
        requested=True,
        visible_tokens=tuple(_visible_token(token) for token in tokens),
        error=error,
    )


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _visible_token(value: str) -> str:
    safe = "".join(
        f"\\x{ord(character):02x}"
        if ord(character) < 32 or ord(character) == 127
        else character
        for character in value
    )
    if len(safe) <= _MAX_VISIBLE_TOKEN_LENGTH:
        return safe
    return f"{safe[:_MAX_VISIBLE_TOKEN_LENGTH]}…"


__all__ = ["CompareQueryRequest", "compare_query_href", "parse_compare_search"]
