from __future__ import annotations

import datetime as dt
import subprocess
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.check_documentation import check_repository


HISTORY = """# M23\n\n<!-- incident-history:start -->\n\n### 2026-09-02 — Incident\n\nImpact: startup failed; repair is undergoing validation.\n<!-- incident-history:end -->\n"""


def make_repo(queue: str, history: str = HISTORY, cleanup=None) -> Path:
    directory = Path(tempfile.mkdtemp())
    if cleanup:
        cleanup(directory)
    (directory / "docs/milestones").mkdir(parents=True)
    (directory / "docs/MILESTONES.md").write_text(
        "# Milestones\n\n" + queue + "\n\n" +
        "[incident history](milestones/milestone-23-acceptance.md#incident-history)\n", encoding="utf-8"
    )
    (directory / "docs/milestones/milestone-23-acceptance.md").write_text(history, encoding="utf-8")
    return directory


VALID_QUEUE = """<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R01 | 1 | in_progress | none | CI run evidence |
| R02 | 2 | pending | R01 | repair evidence |
<!-- active-work:end -->"""


class DocumentationGovernanceTests(unittest.TestCase):
    def repo(self, queue: str, history: str = HISTORY) -> Path:
        root = make_repo(queue, history)
        self.addCleanup(shutil.rmtree, root)
        return root

    def test_valid_repository(self):
        self.assertEqual(check_repository(self.repo(VALID_QUEUE), today=dt.date(2026, 9, 2)), [])

    def test_utf8_cap_and_agents_exempt(self):
        root = self.repo(VALID_QUEUE)
        milestones = root / "docs/MILESTONES.md"
        milestones.write_text("é" * 50001, encoding="utf-8")
        self.assertTrue(any("100000" in e for e in check_repository(root)))
        (root / "AGENTS.md").write_text("x" * 200000, encoding="utf-8")
        milestones.write_text("# Milestones\n\n" + VALID_QUEUE + "\n\n[incident history](milestones/milestone-23-acceptance.md#incident-history)", encoding="utf-8")
        self.assertEqual(check_repository(root), [])

    def test_queue_missing_invalid_status_dependencies_and_cycle(self):
        root = self.repo("no queue")
        self.assertTrue(any("markers" in e for e in check_repository(root)))
        bad = VALID_QUEUE.replace("in_progress", "done").replace("R01 | 1", "R01 | 0")
        bad = bad.replace("R01 | repair evidence", "R03 | repair evidence")
        root = self.repo(bad)
        errors = check_repository(root)
        self.assertTrue(any("status" in e for e in errors))
        self.assertTrue(any("priority" in e for e in errors))
        self.assertTrue(any("dependency" in e for e in errors))
        cycle = VALID_QUEUE.replace("none | CI", "R02 | CI").replace("R01 | repair", "R01 | repair")
        self.assertTrue(any("cycle" in e for e in check_repository(self.repo(cycle))))
        malformed = VALID_QUEUE.replace("| R02 | 2 | pending | R01 | repair evidence |", "R02 malformed")
        self.assertTrue(any("invalid active-work row" in e for e in check_repository(self.repo(malformed))))
        duplicate = VALID_QUEUE.replace("R02 | 2", "R01 | 2")
        errors = check_repository(self.repo(duplicate))
        self.assertTrue(any("duplicate active-work ID" in e for e in errors))
        distinct_priority = VALID_QUEUE.replace("R02 | 2", "R03 | 1")
        self.assertTrue(any("priorities" in e for e in check_repository(self.repo(distinct_priority))))
        bad_delimiter = VALID_QUEUE.replace("|---:|---|---|---|", "|--|x|x|x|x|")
        self.assertTrue(any("delimiter" in e for e in check_repository(self.repo(bad_delimiter))))
        bad_id = VALID_QUEUE.replace("R01 | 1", "X1 | 1")
        self.assertTrue(any("ID must match" in e for e in check_repository(self.repo(bad_id))))

    def test_deadline_validation(self):
        root = self.repo(VALID_QUEUE + "\n\n<!-- pending-decisions:start -->\n- [ ] DECIDE BY 2026-09-01 — overdue\n<!-- pending-decisions:end -->")
        self.assertTrue(any("overdue" in e for e in check_repository(root, today=dt.date(2026, 9, 2))))
        malformed = VALID_QUEUE + "\n\n<!-- pending-decisions:start -->\n- [ ] DECIDE BY nope\n<!-- pending-decisions:end -->"
        self.assertTrue(any("malformed" in e for e in check_repository(self.repo(malformed))))
        invalid_date = VALID_QUEUE + "\n\n<!-- pending-decisions:start -->\n- [ ] DECIDE BY 2026-02-31 — impossible\n<!-- pending-decisions:end -->"
        self.assertTrue(any("invalid DECIDE BY" in e for e in check_repository(self.repo(invalid_date))))
        unbalanced = VALID_QUEUE + "\n\n<!-- pending-decisions:end -->"
        self.assertTrue(any("stray" in e for e in check_repository(self.repo(unbalanced))))

    def test_history_missing_unlinked_empty_and_base_loss(self):
        root = self.repo(VALID_QUEUE, "no history")
        self.assertTrue(any("markers" in e for e in check_repository(root)))
        root = self.repo(VALID_QUEUE, "# M23\n\n<!-- incident-history:start --><!-- incident-history:end -->")
        self.assertTrue(any("nonempty" in e for e in check_repository(root)))
        root = self.repo(VALID_QUEUE)
        milestones = root / "docs/MILESTONES.md"
        milestones.write_text(milestones.read_text(encoding="utf-8").replace(
            "milestones/milestone-23-acceptance.md", "missing"
        ), encoding="utf-8")
        self.assertTrue(any("link" in e for e in check_repository(root)))

    def test_history_must_be_append_only_from_base(self):
        root = self.repo(VALID_QUEUE)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        subprocess.run(["git", "add", "docs/MILESTONES.md", "docs/milestones/milestone-23-acceptance.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        path = root / "docs/milestones/milestone-23-acceptance.md"
        path.write_text(HISTORY.replace("Impact:", "Impact: altered;"), encoding="utf-8")
        self.assertTrue(any("truncated or altered" in e for e in check_repository(root, base_ref=base)))
        self.assertTrue(any("cannot be resolved" in e for e in check_repository(root, base_ref="missing")))

    def test_legacy_base_without_history_markers_is_allowed(self):
        root = self.repo(VALID_QUEUE)
        path = root / "docs/milestones/milestone-23-acceptance.md"
        path.write_text("# Legacy M23\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        subprocess.run(["git", "add", "docs/MILESTONES.md", "docs/milestones/milestone-23-acceptance.md"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "legacy"], cwd=root, check=True)
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        path.write_text(HISTORY, encoding="utf-8")
        self.assertEqual(check_repository(root, base_ref=base), [])

    def test_cli_accepts_current_repository(self):
        result = subprocess.run(
            [sys.executable, "tools/check_documentation.py", "--root", str(Path(__file__).parents[1])],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
