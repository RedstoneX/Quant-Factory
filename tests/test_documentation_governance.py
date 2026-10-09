from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from tools.check_documentation import (
    REQUIRED_FRONTEND_FILES,
    VISUAL_CONTRACT,
    check_repository,
)


ROOT = Path(__file__).parents[1]
VALID_QUEUE = """<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R12 | 1 | in_progress | none | Current evidence. |
| R15 | 2 | blocked | R12 | Later evidence. |
<!-- active-work:end -->"""


def _repository(tmp_path: Path) -> Path:
    for relative in REQUIRED_FRONTEND_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative == VISUAL_CONTRACT:
            shutil.copyfile(ROOT / relative, target)
        else:
            target.write_text("Current authority.\n", encoding="utf-8")
    (tmp_path / "docs/MILESTONES.md").write_text(
        "# Milestones\n\n" + VALID_QUEUE + "\n", encoding="utf-8"
    )
    return tmp_path


def test_current_repository_satisfies_documentation_authority() -> None:
    assert check_repository(ROOT) == []


def test_queue_contract_rejects_unknown_dependency(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    path = root / "docs/MILESTONES.md"
    path.write_text(path.read_text(encoding="utf-8").replace("R12 | Later", "R99 | Later"), encoding="utf-8")
    assert any("unknown active-work dependency" in error for error in check_repository(root))


def test_overdue_decision_is_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    path = root / "docs/MILESTONES.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n<!-- pending-decisions:start -->\n"
        + "- [ ] DECIDE BY 2026-10-01 — expired\n"
        + "<!-- pending-decisions:end -->\n",
        encoding="utf-8",
    )
    assert any(
        "overdue" in error
        for error in check_repository(root, today=dt.date(2026, 10, 9))
    )


def test_visual_contract_checksum_is_locked(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / VISUAL_CONTRACT).write_text("replacement", encoding="utf-8")
    assert any("checksum changed" in error for error in check_repository(root))


def test_rejected_frontend_path_is_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    path = root / "dashboard/app.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# legacy composition root\n", encoding="utf-8")
    assert any("was restored" in error for error in check_repository(root))


def test_competing_visual_asset_is_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    path = root / "docs/assets/dashboard/alternate.png"
    path.write_bytes(b"not an authority")
    assert any("competing dashboard visual asset" in error for error in check_repository(root))


def test_stale_authority_reference_is_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "AGENTS.md").write_text(
        "Use results-page-flow-preview as the target.\n", encoding="utf-8"
    )
    assert any("stale frontend authority reference" in error for error in check_repository(root))
