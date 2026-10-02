"""Tests for exact portable/licensed/external CI lane accounting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.assert_test_lane_report import verify_report


def _inventory(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "total": 4,
                "counts": {
                    "portable": 2,
                    "licensed_vectorbt": 1,
                    "external_prefect": 1,
                },
                "lanes": {
                    "portable": [
                        "tests/test_unit.py::test_unit",
                        "tests/browser/test_page.py::test_page",
                    ],
                    "licensed_vectorbt": [
                        "tests/test_engine.py::test_real_engine"
                    ],
                    "external_prefect": [
                        "tests/test_prefect.py::test_external_server"
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _report(path: Path, *, count: int, skipped: bool = False) -> Path:
    skip = "<skipped/>" if skipped else ""
    cases = "".join(f'<testcase name="case-{index}">{skip}</testcase>' for index in range(count))
    path.write_text(f"<testsuite>{cases}</testsuite>", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "lane",
    (
        "portable-nonbrowser",
        "portable-browser",
        "licensed-vectorbt",
        "external-prefect",
    ),
)
def test_lane_report_accepts_exact_green_coverage(tmp_path: Path, lane: str) -> None:
    summary = verify_report(
        _inventory(tmp_path / "inventory.json"),
        _report(tmp_path / "report.xml", count=1),
        lane,
    )

    assert "expected 1; reported 1" in summary


def test_lane_report_rejects_missing_or_skipped_cases(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path / "inventory.json")
    with pytest.raises(ValueError, match="expected 1; reported 0"):
        verify_report(
            inventory,
            _report(tmp_path / "missing.xml", count=0),
            "portable-nonbrowser",
        )
    with pytest.raises(ValueError, match="skipped 1"):
        verify_report(
            inventory,
            _report(tmp_path / "skipped.xml", count=1, skipped=True),
            "portable-browser",
        )
