"""Data for the New idea page: what a checked batch looks like, and where it will go in the factory's line.

Checking is submit_projection's job (the same parser and validator as before); the line and the typical test time come from
factory_overview (the same numbers the Factory page shows). This module only shapes them for the page. No invented numbers.
"""

from __future__ import annotations

import json
from typing import Any

from dashboard.factory_history import STEPS
from rule_language.validation import MAX_VARIABLE_GRID

SHOWN_WAITING = 3  # waiting tests listed by name; the rest are counted
STEP_WORDS = {
    "screening": "every combination, with trading costs",
    "oos": "the best setting on years it never saw",
    "walk_forward": "rolling windows",
    "robustness": "worse fills and delays",
    "monte_carlo": "against shuffled histories",
}
NEXT_STEPS = [{"n": index, "name": name, "what": STEP_WORDS[key]} for index, (key, name) in enumerate(STEPS, 1)]
FIXED_SHOWN = 3  # fixed settings named in a card's sentence
FIXED_MAX_CHARS = 14  # longer values (ids, date spans) stay out of the sentence
SOURCES = (("grok", "Grok"), ("codex", "Codex"))


def plural(count: int, word: str = "idea") -> str:
    return f"{count:,} {word}" + ("" if count == 1 else "s")


def minutes_label(minutes: float | None) -> str:
    """'now', '~7 min' or '~1 h 5 min'; '—' when nothing is known."""
    if minutes is None:
        return "—"
    if minutes < 0.5:
        return "now"
    whole = int(round(minutes))
    return f"~{whole} min" if whole < 60 else f"~{whole // 60} h {whole % 60:02d} min"


def card_has_grid(row: dict[str, Any]) -> bool:
    """An idea that was read well enough to count its settings (including one rejected for being over the limit)."""
    return bool(row.get("variations")) or bool(row.get("review_ready") and row.get("canonical_json"))


def combos(row: dict[str, Any]) -> int:
    """Settings combinations an idea tests; the validator reports 0 for an idea with nothing varied, which is one test."""
    return int(row.get("variations") or 0) or 1


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value).strip() else ""


def _document(row: dict[str, Any]) -> dict[str, Any]:
    try:
        document = json.loads(row.get("canonical_json") or "null")
    except (TypeError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def source_label(document: dict[str, Any]) -> str:
    """'From Grok' / 'From Codex' only when the file records it (a source's creator or collected_by); otherwise nothing."""
    for source in document.get("sources") or []:
        if not isinstance(source, dict):
            continue
        written = " ".join(_text(source.get(key)) for key in ("collected_by", "creator", "submitted_by")).lower()
        for needle, label in SOURCES:
            if needle in written:
                return f"From {label}"
    return ""


def _range_text(values: list[Any]) -> str:
    numbers = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if numbers and len(numbers) == len(values):
        low, high = min(numbers), max(numbers)
        return f"{low:g}–{high:g}" if low != high else f"{low:g}"
    return " / ".join(str(value) for value in values[:4]) + (" …" if len(values) > 4 else "")


def rule_tokens(document: dict[str, Any]) -> list[dict[str, str]]:
    """The idea read back as words and tokens: fixed values are 'fixed' tokens, ranges are 'range' tokens.

    No library or existing page turns a packet into a sentence, and the structured rule_spec has no plain-words renderer, so the
    sentence is the idea's own one-line wording framed by what the file fixes (market, bar size, fixed settings) and what it varies.
    """
    tokens: list[dict[str, str]] = []

    def add(kind: str, text: str) -> None:
        if text:
            tokens.append({"kind": kind, "text": text})

    market = document.get("market") if isinstance(document.get("market"), dict) else {}
    instruments = (market.get("instruments") or {}).get("preferred") if isinstance(market.get("instruments"), dict) else None
    names = " · ".join(str(item) for item in instruments or [])
    timeframe = _text(market.get("timeframe"))
    if names:
        add("word", "Trade")
        add("fixed", names)
        if timeframe:
            add("word", "on")
            add("fixed", f"{timeframe} bars")
        add("word", ".")
    candidate = document.get("candidate") if isinstance(document.get("candidate"), dict) else {}
    add("word", _text(candidate.get("one_line")))
    variables = document.get("variables") if isinstance(document.get("variables"), dict) else {}
    varied = [(name.replace("_", " "), spec.get("values")) for name, spec in variables.items() if isinstance(spec, dict) and isinstance(spec.get("values"), list) and spec["values"]]
    if varied:
        add("word", "Tries")
        for name, values in varied:
            add("word", name)
            add("range", _range_text(values))
    fixed = document.get("fixed") if isinstance(document.get("fixed"), dict) else {}
    shown = [(key, value) for key, value in fixed.items() if _text(value) and len(_text(value)) <= FIXED_MAX_CHARS and _text(value) != timeframe and key not in variables][:FIXED_SHOWN]
    if shown:
        add("word", "Fixed:")
        for position, (key, value) in enumerate(shown):
            if position:
                add("word", "·")
            add("word", key.replace("_", " ").removeprefix("fixed "))
            add("fixed", _text(value))
    return tokens


def data_label(document: dict[str, Any]) -> str:
    needs = document.get("data_needs") if isinstance(document.get("data_needs"), dict) else {}
    market = document.get("market") if isinstance(document.get("market"), dict) else {}
    instruments = (market.get("instruments") or {}).get("preferred") if isinstance(market.get("instruments"), dict) else None
    head = " · ".join(str(item) for item in instruments or []) or _text(needs.get("dataset_id"))
    resolution = _text(needs.get("minimum_resolution")) or _text(market.get("timeframe"))
    start = _text(needs.get("requested_start"))
    when = f"from {start}" if start else _text(needs.get("coverage"))
    return " ".join(part for part in (head, resolution, when) if part) or "—"


def _problem(row: dict[str, Any]) -> str:
    """This idea's own problem in the validator's words (errors first, then warnings); never a sentence about the whole file."""
    issues = [i for i in row.get("issues") or [] if i.get("severity") == "error"] or [i for i in row.get("issues") or [] if i.get("severity") == "warning"]
    if not issues:
        return "This idea is not ready to submit yet."
    return "; ".join(_named(issue) for issue in issues[:2])


def _named(issue: dict[str, Any]) -> str:
    """The validator's message verbatim, prefixed with the failing variable's name when its path names one (variables.<name>...)."""
    parts = str(issue.get("path") or "").split(".")
    message = str(issue.get("message"))
    return f"{parts[1].replace('_', ' ')}: {message}" if len(parts) > 1 and parts[0] == "variables" and parts[1] else message


def review_batch(batch: dict[str, Any] | None) -> dict[str, Any]:
    """Cards, counts and the combinations bar for a checked batch (the dict submit_projection.validate_upload returns)."""
    rows = list((batch or {}).get("rows") or [])
    cards: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        ready = bool(row.get("review_ready") and row.get("canonical_json"))
        document = _document(row)
        candidate = document.get("candidate") if isinstance(document.get("candidate"), dict) else {}
        family = _text(candidate.get("family")).replace("_", " ")
        meta = " · ".join(part for part in (source_label(document), family) if part)
        cards.append({
            "index": index, "name": row.get("title") or row.get("filename") or "Untitled idea", "meta": meta, "ready": ready,
            "tokens": rule_tokens(document) if ready else [],
            "combinations": f"{combos(row):,}" if ready else "—",
            "over_limit": combos(row) > MAX_VARIABLE_GRID,
            "data": data_label(document) if document else "—",
            "problem": "" if ready else _problem(row),
        })
    ready_rows = [card for card, row in zip(cards, rows) if card["ready"]]
    combinations = sum(combos(row) for card, row in zip(cards, rows) if card["ready"])
    largest = max((combos(row) for row in rows if card_has_grid(row)), default=0)
    return {"cards": cards, "total": len(cards), "ready": len(ready_rows), "left_out": len(cards) - len(ready_rows), "combinations": combinations,
            "largest": largest, "budget": MAX_VARIABLE_GRID, "budget_text": f"Largest idea: {largest:,} of {MAX_VARIABLE_GRID:,} settings allowed",
            "total_text": f"{combinations:,} settings to test in total", "budget_percent": min(100.0, 100 * largest / MAX_VARIABLE_GRID),
            "over_budget": largest > MAX_VARIABLE_GRID,
            "submit_rows": [row for row in rows if row.get("review_ready") and row.get("canonical_json")]}


def typical_text(typical: float | None) -> str:
    return f"~{typical:.0f} min" if typical else "not yet known"


def line_ahead(overview: dict[str, Any]) -> int:
    """Tests in front of a new submission: the one running plus everything waiting."""
    return len(overview.get("running") or []) + int((overview.get("queue") or {}).get("total") or 0)


def where_they_go(overview: dict[str, Any], ready: int) -> list[dict[str, str]]:
    """The live line: running test first, then those waiting, then this batch. Start times are typical test time x place in line."""
    typical = overview.get("typical_minutes")
    rows: list[dict[str, str]] = []
    place = 0
    for run in overview.get("running") or []:
        place += 1
        rows.append({"n": str(place), "name": f"{run['name']} (running)", "when": "now", "kind": "running"})
    queue = overview.get("queue") or {}
    waiting = list(queue.get("next") or [])
    for item in waiting[:SHOWN_WAITING]:
        place += 1
        rows.append({"n": str(place), "name": str(item["name"]), "when": minutes_label((place - 1) * typical) if typical else "—", "kind": "waiting"})
    hidden = int(queue.get("total") or 0) - len(waiting[:SHOWN_WAITING])
    if hidden > 0:
        rows.append({"n": "…", "name": f"and {hidden} more waiting", "when": "", "kind": "more"})
    if ready:
        ahead = line_ahead(overview)
        rows.append({"n": str(ahead + 1), "name": f"Your {plural(ready)}", "when": minutes_label(ahead * typical) if typical is not None else "—", "kind": "yours"})
    return rows


def start_minutes(overview: dict[str, Any]) -> float | None:
    """When the first idea of a new batch starts: typical test time x tests ahead (0 when nothing is ahead)."""
    typical = overview.get("typical_minutes")
    ahead = line_ahead(overview)
    if not ahead:
        return 0.0
    return ahead * typical if typical else None


def bar_text(review: dict[str, Any], overview: dict[str, Any]) -> str:
    if not review["total"]:
        return "Choose a file or paste an idea to check it. Nothing is saved until you submit."
    start = start_minutes(overview)
    when = "right away" if start == 0 else f"in about {start:.0f} min" if start is not None else "after the tests in line"
    return f"{review['ready']} ready · {review['left_out']} left out · first starts {when}"


def button(review: dict[str, Any], gateway_ready: bool) -> tuple[str, bool]:
    """Primary button text and whether it is disabled (nothing ready, or the submission service is not available)."""
    ready = review["ready"]
    return (f"Submit and test {plural(ready)}" if ready else "Submit and test ideas"), (not ready or not gateway_ready)


def submitted_state(responses: list[dict[str, Any]], overview_before: dict[str, Any], names: list[str] | None = None) -> dict[str, Any]:
    """After submit: the bar text (place in line, start estimate) and one line per idea: queued, already tested, or failed."""
    names = names or [f"Idea {index}" for index in range(1, len(responses) + 1)]
    notes: list[dict[str, str]] = []
    new: list[str] = []
    for name, item in zip(names, responses):
        result = item.get("result") or {}
        if not item.get("ok"):
            notes.append({"tone": "bad", "text": f"{name} — failed to submit: {(item.get('error') or {}).get('message') or 'Submission failed'}"})
        elif result.get("duplicate"):
            notes.append({"tone": "warn", "text": f"{name} — already tested — not queued again"})
        else:
            new.append(str(result.get("candidate_id")))
            notes.append({"tone": "ok", "text": f"{name} — queued"})
    ahead = line_ahead(overview_before)
    typical = overview_before.get("typical_minutes")
    if new:
        start = "right away" if not ahead else f"in ~{ahead * typical:.0f} min" if typical else "after the tests in line"
        text = f"Queued · #{ahead + 1} in line · starts {start}"
    else:
        text = "Nothing new was queued"
    return {"text": text, "queued": len(new), "notes": notes, "candidate_ids": new}


__all__ = ["NEXT_STEPS", "bar_text", "button", "line_ahead", "minutes_label", "review_batch", "rule_tokens", "source_label", "start_minutes", "submitted_state", "typical_text", "where_they_go"]
