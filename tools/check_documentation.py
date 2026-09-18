#!/usr/bin/env python3
"""Validate the small set of machine-readable documentation contracts."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

MAX_MILESTONES_BYTES = 100_000
QUEUE_START = "<!-- active-work:start -->"
QUEUE_END = "<!-- active-work:end -->"
HISTORY_START = "<!-- incident-history:start -->"
HISTORY_END = "<!-- incident-history:end -->"
DECISIONS_START = "<!-- pending-decisions:start -->"
DECISIONS_END = "<!-- pending-decisions:end -->"
QUEUE_COLUMNS = ("ID", "Priority", "Status", "Depends", "Evidence")
VALID_STATUSES = {"pending", "in_progress", "blocked"}
DEADLINE_RE = re.compile(r"^- \[ \] DECIDE BY (\d{4}-\d{2}-\d{2}) — (\S.*)$")
ID_RE = re.compile(r"^R[0-9]{2,}$")
LINK_RE = re.compile(r"\]\(milestones/milestone-23-acceptance\.md#incident-history\)")


def _marked(text: str, start: str, end: str, label: str) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    if text.count(start) != 1 or text.count(end) != 1:
        return None, [f"{label} markers must each occur exactly once"]
    begin = text.index(start) + len(start)
    finish = text.index(end)
    if finish < begin:
        return None, [f"{label} markers are out of order"]
    return text[begin:finish], errors


def _validate_queue(text: str) -> list[str]:
    block, errors = _marked(text, QUEUE_START, QUEUE_END, "active-work")
    if block is None:
        return errors
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 3 or not lines[0].startswith("|") or not lines[1].startswith("|"):
        return ["active-work queue must contain a Markdown table with header and rows"]
    header = tuple(cell.strip() for cell in lines[0].strip("|").split("|"))
    if header != QUEUE_COLUMNS:
        errors.append(f"active-work columns must be {QUEUE_COLUMNS}")
    rows: dict[str, tuple[int, str, list[str], str]] = {}
    delimiter = lines[1]
    delimiter_cells = [cell.strip() for cell in delimiter.strip("|").split("|")]
    if len(delimiter_cells) != len(QUEUE_COLUMNS) or any(
        not re.fullmatch(r":?-{3,}:?", cell) for cell in delimiter_cells
    ):
        errors.append("active-work table delimiter is malformed")
    for line in lines[2:]:
        if not line.startswith("|"):
            errors.append(f"invalid active-work row: {line}")
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 5 and cells[0] == "---":
            continue
        if len(cells) != len(QUEUE_COLUMNS):
            errors.append(f"invalid active-work row: {line}")
            continue
        ident, priority, status, depends, evidence = cells
        if not ID_RE.fullmatch(ident):
            errors.append(f"active-work ID must match R[0-9]{{2,}}: {ident}")
        if ident in rows:
            errors.append(f"duplicate active-work ID: {ident}")
        try:
            number = int(priority)
            if number <= 0:
                raise ValueError
        except ValueError:
            errors.append(f"active-work priority must be positive: {ident}")
            number = 0
        if status not in VALID_STATUSES:
            errors.append(f"invalid active-work status for {ident}: {status}")
        if not evidence:
            errors.append(f"active-work evidence is required: {ident}")
        deps = [] if depends.lower() == "none" else [item.strip() for item in depends.split(",")]
        rows[ident] = (number, status, deps, evidence)
    if not rows:
        errors.append("active-work queue must contain at least one row")
    priorities = [row[0] for row in rows.values() if row[0]]
    if len(priorities) != len(set(priorities)):
        errors.append("active-work priorities must be unique")
    for ident, (_, _, deps, _) in rows.items():
        for dep in deps:
            if dep not in rows:
                errors.append(f"unknown active-work dependency {dep} for {ident}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(ident: str) -> None:
        if ident in visiting:
            errors.append(f"active-work dependency cycle includes {ident}")
            return
        if ident in visited or ident not in rows:
            return
        visiting.add(ident)
        for dep in rows[ident][2]:
            visit(dep)
        visiting.remove(ident)
        visited.add(ident)

    for ident in rows:
        visit(ident)
    return errors


def _validate_decisions(text: str, today: dt.date) -> list[str]:
    errors: list[str] = []
    lines = text.splitlines()
    if text.count(DECISIONS_START) > 1 or text.count(DECISIONS_END) > 1:
        errors.append("pending-decisions markers must each occur at most once")
    in_section = False
    for line in lines:
        if line.strip() == DECISIONS_START:
            if in_section:
                errors.append("nested pending-decisions section")
            in_section = True
            continue
        if line.strip() == DECISIONS_END:
            if not in_section:
                errors.append("stray pending-decisions end marker")
            in_section = False
            continue
        if "DECIDE BY" not in line:
            continue
        if not in_section:
            errors.append("DECIDE BY line must be inside pending-decisions markers")
            continue
        match = DEADLINE_RE.match(line.strip())
        if not match:
            errors.append(f"malformed DECIDE BY line: {line.strip()}")
            continue
        try:
            deadline = dt.date.fromisoformat(match.group(1))
        except ValueError:
            errors.append(f"invalid DECIDE BY date: {match.group(1)}")
            continue
        if deadline < today:
            errors.append(f"overdue DECIDE BY date: {match.group(1)}")
    if in_section:
        errors.append("pending-decisions markers are unbalanced")
    return errors


def _history(text: str) -> tuple[str | None, list[str]]:
    return _marked(text, HISTORY_START, HISTORY_END, "incident-history")


def _validate_history(root: Path, milestones: str, base_ref: str | None) -> list[str]:
    errors: list[str] = []
    history_path = root / "docs/milestones/milestone-23-acceptance.md"
    if not history_path.is_file():
        return ["Milestone 23 acceptance document is missing"]
    history, history_errors = _history(history_path.read_text(encoding="utf-8"))
    errors.extend(history_errors)
    if history is not None and not history.strip():
        errors.append("incident-history section must be nonempty")
    if not LINK_RE.search(milestones):
        errors.append("MILESTONES must link the Milestone 23 incident history")
    if base_ref is not None and history is not None:
        try:
            old = subprocess.run(
                ["git", "show", f"{base_ref}:docs/milestones/milestone-23-acceptance.md"],
                cwd=root, check=True, capture_output=True, text=True,
            ).stdout
        except (subprocess.CalledProcessError, OSError):
            return errors + [f"base ref cannot be resolved: {base_ref}"]
        old_has_start = HISTORY_START in old
        old_has_end = HISTORY_END in old
        if not old_has_start and not old_has_end:
            old_history = None
        else:
            old_history, old_errors = _history(old)
            errors.extend(old_errors)
        if old_history is not None and not history.startswith(old_history):
            errors.append("incident-history was truncated or altered relative to base ref")
    return errors


def check_repository(root: Path, base_ref: str | None = None, today: dt.date | None = None) -> list[str]:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    milestones_path = root / "docs/MILESTONES.md"
    if not milestones_path.is_file():
        return ["docs/MILESTONES.md is missing"]
    milestones = milestones_path.read_text(encoding="utf-8")
    errors: list[str] = []
    if len(milestones.encode("utf-8")) > MAX_MILESTONES_BYTES:
        errors.append("docs/MILESTONES.md exceeds 100000 UTF-8 bytes")
    errors.extend(_validate_queue(milestones))
    errors.extend(_validate_decisions(milestones, today))
    errors.extend(_validate_history(root, milestones, base_ref))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref")
    args = parser.parse_args()
    errors = check_repository(args.root.resolve(), args.base_ref)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Documentation governance checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
