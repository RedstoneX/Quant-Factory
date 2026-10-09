from __future__ import annotations

import datetime as dt
import shutil
import tempfile
import unittest
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


class DocumentationGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in REQUIRED_FRONTEND_FILES:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == VISUAL_CONTRACT:
                shutil.copyfile(ROOT / relative, target)
            else:
                target.write_text("Current authority.\n", encoding="utf-8")
        (self.root / "docs/MILESTONES.md").write_text(
            "# Milestones\n\n" + VALID_QUEUE + "\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_current_repository_satisfies_documentation_authority(self) -> None:
        self.assertEqual(check_repository(ROOT), [])

    def test_queue_contract_rejects_unknown_dependency(self) -> None:
        path = self.root / "docs/MILESTONES.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("R12 | Later", "R99 | Later"),
            encoding="utf-8",
        )
        self.assertTrue(
            any("unknown active-work dependency" in error for error in check_repository(self.root))
        )

    def test_overdue_decision_is_rejected(self) -> None:
        path = self.root / "docs/MILESTONES.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n<!-- pending-decisions:start -->\n"
            + "- [ ] DECIDE BY 2026-10-01 — expired\n"
            + "<!-- pending-decisions:end -->\n",
            encoding="utf-8",
        )
        self.assertTrue(
            any(
                "overdue" in error
                for error in check_repository(self.root, today=dt.date(2026, 10, 9))
            )
        )

    def test_visual_contract_checksum_is_locked(self) -> None:
        (self.root / VISUAL_CONTRACT).write_text("replacement", encoding="utf-8")
        self.assertTrue(any("checksum changed" in error for error in check_repository(self.root)))

    def test_unauthorized_presentation_path_is_rejected(self) -> None:
        path = self.root / "dashboard/extra.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# unauthorized composition root\n", encoding="utf-8")
        self.assertTrue(any("unauthorized" in error for error in check_repository(self.root)))

    def test_competing_visual_asset_is_rejected(self) -> None:
        path = self.root / "docs/assets/dashboard/alternate.png"
        path.write_bytes(b"not an authority")
        self.assertTrue(
            any("competing dashboard visual asset" in error for error in check_repository(self.root))
        )

    def test_unauthorized_execution_source_is_rejected(self) -> None:
        path = self.root / "execution/extra.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# unauthorized execution source\n", encoding="utf-8")
        self.assertTrue(
            any("unauthorized execution source path" in error for error in check_repository(self.root))
        )

    def test_unauthorized_deployment_source_is_rejected(self) -> None:
        path = self.root / "deployment/extra/service.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# unauthorized deployment source\n", encoding="utf-8")
        self.assertTrue(
            any("unauthorized deployment source path" in error for error in check_repository(self.root))
        )

if __name__ == "__main__":
    unittest.main()
