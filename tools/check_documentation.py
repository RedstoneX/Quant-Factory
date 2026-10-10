#!/usr/bin/env python3
"""Enforce Quant Factory's current documentation and frontend authority."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import sys
from pathlib import Path

MAX_MILESTONES_BYTES = 100_000
QUEUE_START = "<!-- active-work:start -->"
QUEUE_END = "<!-- active-work:end -->"
DECISIONS_START = "<!-- pending-decisions:start -->"
DECISIONS_END = "<!-- pending-decisions:end -->"
QUEUE_COLUMNS = ("ID", "Priority", "Status", "Depends", "Evidence")
VALID_STATUSES = {"pending", "in_progress", "blocked"}
DEADLINE_RE = re.compile(r"^- \[ \] DECIDE BY (\d{4}-\d{2}-\d{2}) — (\S.*)$")
ID_RE = re.compile(r"^R[0-9]{2,}$")

VISUAL_CONTRACT = Path(
    "docs/assets/dashboard/current-visual-contract/dashboard.html"
)
VISUAL_CONTRACT_SHA256 = "266336fb5d62caa844cae6c67d4ed36df63a14bc4de7ad72919375d9318e74c1"
WORKSPACE_CONTRACT = Path(
    "docs/assets/workspaces/current-workflow-contract/workspaces.html"
)
WORKSPACE_CONTRACT_SHA256 = "313b098fa43ca0e25e6c92dad55b2d508faca94765c3cd8fe9c7005837f71b31"
REQUIRED_VISUAL_MARKERS = (
    'id="qf-toolset-preview"',
    "Candidate universe",
    "Factory now",
    "Top survivors",
    'class="drawer"',
)
FORBIDDEN_VISUAL_MARKERS = (
    "qfr-dashboard-overview",
    "quant-factory-reconciled-mockups",
)
REQUIRED_WORKSPACE_MARKERS = (
    'data-variant="Candidates"',
    'data-variant="Results"',
    'data-variant="Factory"',
    'data-variant="Submit Strategies"',
    'data-variant="Compare Selected"',
    'data-variant="Paper Trading"',
)
FORBIDDEN_WORKSPACE_MARKERS = (
    'data-variant="Dashboard"',
    "qfr-dashboard",
    "dashboardPresets",
    "dashFindings",
    "seven-screen mockups",
)
REQUIRED_FRONTEND_FILES = (
    VISUAL_CONTRACT,
    WORKSPACE_CONTRACT,
    WORKSPACE_CONTRACT.parent / "README.md",
    Path("docs/factory-operating-contract.md"),
    Path("docs/architecture/0016-dashboard-runtime.md"),
    Path(".agents/skills/quant-factory-frontend/SKILL.md"),
    Path(".agents/skills/web-interface-audit/SKILL.md"),
    Path("deployment/dashboard/quant-factory-dashboard.service"),
    Path("deployment/dashboard/README.md"),
)

ALLOWED_DASHBOARD_ROOT_FILES = {
    "__init__.py",
    "adapter.py",
    "candidate_launch_context.py",
    "candidate_workflow.py",
    "candidates_projection.py",
    "compare_query.py",
    "evidence_chart_window.py",
    "factory_projection.py",
    "submit_projection.py",
    "compare_projection.py",
    "formatting.py",
    "health.py",
    "mes_candidate_setup.py",
    "overview_projection.py",
    "results_model.py",
    "results_projection.py",
    "run_adapter.py",
    "run_detail_adapter.py",
}

ALLOWED_EXECUTION_ROOT_FILES = {
    "__init__.py",
    "paper_handoff.py",
}

ALLOWED_DEPLOYMENT_ROOT_FILES = {
    "agent_gateway_server.py",
    "entrypoint.sh",
}

ALLOWED_DEPLOYMENT_ROOT_DIRECTORIES = {
    "agent-gateway",
    "config",
    "dashboard",
}

def _marked(text: str, start: str, end: str, label: str) -> tuple[str | None, list[str]]:
    if text.count(start) != 1 or text.count(end) != 1:
        return None, [f"{label} markers must each occur exactly once"]
    begin = text.index(start) + len(start)
    finish = text.index(end)
    if finish < begin:
        return None, [f"{label} markers are out of order"]
    return text[begin:finish], []


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
    delimiter_cells = [cell.strip() for cell in lines[1].strip("|").split("|")]
    if len(delimiter_cells) != len(QUEUE_COLUMNS) or any(
        not re.fullmatch(r":?-{3,}:?", cell) for cell in delimiter_cells
    ):
        errors.append("active-work table delimiter is malformed")

    rows: dict[str, tuple[int, list[str]]] = {}
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")] if line.startswith("|") else []
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
        rows[ident] = (number, deps)

    priorities = [row[0] for row in rows.values() if row[0]]
    if not rows:
        errors.append("active-work queue must contain at least one row")
    if len(priorities) != len(set(priorities)):
        errors.append("active-work priorities must be unique")
    for ident, (_, deps) in rows.items():
        for dependency in deps:
            if dependency not in rows:
                errors.append(f"unknown active-work dependency {dependency} for {ident}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(ident: str) -> None:
        if ident in visiting:
            errors.append(f"active-work dependency cycle includes {ident}")
            return
        if ident in visited or ident not in rows:
            return
        visiting.add(ident)
        for dependency in rows[ident][1]:
            visit(dependency)
        visiting.remove(ident)
        visited.add(ident)

    for ident in rows:
        visit(ident)
    return errors


def _validate_decisions(text: str, today: dt.date) -> list[str]:
    errors: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == DECISIONS_START:
            if in_section:
                errors.append("nested pending-decisions section")
            in_section = True
            continue
        if stripped == DECISIONS_END:
            if not in_section:
                errors.append("stray pending-decisions end marker")
            in_section = False
            continue
        if "DECIDE BY" not in line:
            continue
        if not in_section:
            errors.append("DECIDE BY line must be inside pending-decisions markers")
            continue
        match = DEADLINE_RE.match(stripped)
        if not match:
            errors.append(f"malformed DECIDE BY line: {stripped}")
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


def _validate_frontend_authority(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_FRONTEND_FILES:
        if not (root / relative).is_file():
            errors.append(f"required frontend authority is missing: {relative}")
    visual = root / VISUAL_CONTRACT
    if visual.is_file():
        content = visual.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != VISUAL_CONTRACT_SHA256:
            errors.append(f"visual contract checksum changed: {digest} != {VISUAL_CONTRACT_SHA256}")
        text = content.decode("utf-8", errors="replace")
        for marker in REQUIRED_VISUAL_MARKERS:
            if marker not in text:
                errors.append(f"visual contract marker is missing: {marker}")
        for marker in FORBIDDEN_VISUAL_MARKERS:
            if marker in text:
                errors.append(f"superseded visual contract marker remains: {marker}")
    workspaces = root / WORKSPACE_CONTRACT
    if workspaces.is_file():
        content = workspaces.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != WORKSPACE_CONTRACT_SHA256:
            errors.append(
                "workspace contract checksum changed: "
                f"{digest} != {WORKSPACE_CONTRACT_SHA256}"
            )
        text = content.decode("utf-8", errors="replace")
        for marker in REQUIRED_WORKSPACE_MARKERS:
            if marker not in text:
                errors.append(f"workspace contract marker is missing: {marker}")
        for marker in FORBIDDEN_WORKSPACE_MARKERS:
            if marker in text:
                errors.append(f"prohibited Dashboard marker remains in workspace contract: {marker}")
    dashboard = root / "dashboard"
    if dashboard.is_dir():
        for path in dashboard.iterdir():
            if path.name == "__pycache__":
                continue
            if path.is_dir() and path.name == "ui":
                continue
            if path.is_file() and path.name in ALLOWED_DASHBOARD_ROOT_FILES:
                continue
            errors.append(f"unauthorized dashboard source path exists: {path.relative_to(root)}")
    presentation = dashboard / "ui"
    if presentation.is_dir():
        for path in presentation.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "import sqlite3" in text or "from sqlite3" in text or ".execute(" in text:
                errors.append(
                    f"dashboard presentation owns persistence logic: {path.relative_to(root)}"
                )
    assets = root / "docs/assets/dashboard"
    allowed_assets = {VISUAL_CONTRACT, VISUAL_CONTRACT.parent / "README.md"}
    if assets.is_dir():
        for path in assets.rglob("*"):
            if path.is_file() and path.relative_to(root) not in allowed_assets:
                errors.append(f"competing dashboard visual asset exists: {path.relative_to(root)}")
    return errors


def _validate_runtime_authority(root: Path) -> list[str]:
    errors: list[str] = []
    execution = root / "execution"
    if execution.is_dir():
        for path in execution.iterdir():
            if path.name == "__pycache__":
                continue
            if path.is_file() and path.name in ALLOWED_EXECUTION_ROOT_FILES:
                continue
            errors.append(f"unauthorized execution source path exists: {path.relative_to(root)}")

    deployment = root / "deployment"
    if deployment.is_dir():
        for path in deployment.iterdir():
            if path.name == "__pycache__":
                continue
            if path.is_file() and path.name in ALLOWED_DEPLOYMENT_ROOT_FILES:
                continue
            if path.is_dir() and path.name in ALLOWED_DEPLOYMENT_ROOT_DIRECTORIES:
                continue
            errors.append(f"unauthorized deployment source path exists: {path.relative_to(root)}")
    service = root / "deployment/dashboard/quant-factory-dashboard.service"
    if service.is_file():
        text = service.read_text(encoding="utf-8")
        for marker in (
            "EnvironmentFile=/etc/quant-factory/dashboard.env",
            "dashboard.ui.app:server",
            "Restart=on-failure",
        ):
            if marker not in text:
                errors.append(f"Dashboard service marker is missing: {marker}")
    return errors


def check_repository(root: Path, base_ref: str | None = None, today: dt.date | None = None) -> list[str]:
    del base_ref  # Historical documents are in Git; active governance is not append-only.
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
    errors.extend(_validate_frontend_authority(root))
    errors.extend(_validate_runtime_authority(root))
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
    print("Documentation and frontend authority checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
