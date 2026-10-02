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
                "total": 5,
                "counts": {
                    "portable": 2,
                    "licensed_vectorbt": 1,
                    "external_prefect": 1,
                    "controlled_market_data": 1,
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
                    "controlled_market_data": [
                        "tests/test_data.py::test_controlled_dataset"
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _report(
    path: Path,
    *,
    cases: list[tuple[str, str]],
    skipped: bool = False,
) -> Path:
    skip = "<skipped/>" if skipped else ""
    payload = "".join(
        f'<testcase classname="{classname}" name="{name}">{skip}</testcase>'
        for classname, name in cases
    )
    path.write_text(f"<testsuite>{payload}</testsuite>", encoding="utf-8")
    return path


EXPECTED_CASES = {
    "portable-nonbrowser": ("tests.test_unit", "test_unit"),
    "portable-browser": ("tests.browser.test_page", "test_page"),
    "licensed-vectorbt": ("tests.test_engine", "test_real_engine"),
    "external-prefect": ("tests.test_prefect", "test_external_server"),
    "controlled-market-data": ("tests.test_data", "test_controlled_dataset"),
}


@pytest.mark.parametrize(
    "lane",
    (
        "portable-nonbrowser",
        "portable-browser",
        "licensed-vectorbt",
        "external-prefect",
        "controlled-market-data",
    ),
)
def test_lane_report_accepts_exact_green_coverage(tmp_path: Path, lane: str) -> None:
    summary = verify_report(
        _inventory(tmp_path / "inventory.json"),
        _report(tmp_path / "report.xml", cases=[EXPECTED_CASES[lane]]),
        lane,
    )

    assert "expected 1; reported 1" in summary


def test_lane_report_rejects_missing_or_skipped_cases(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path / "inventory.json")
    with pytest.raises(ValueError, match="expected 1; reported 0"):
        verify_report(
            inventory,
            _report(tmp_path / "missing.xml", cases=[]),
            "portable-nonbrowser",
        )
    with pytest.raises(ValueError, match="skipped 1"):
        verify_report(
            inventory,
            _report(
                tmp_path / "skipped.xml",
                cases=[EXPECTED_CASES["portable-browser"]],
                skipped=True,
            ),
            "portable-browser",
        )


def test_lane_report_rejects_same_count_wrong_test(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing.*unexpected"):
        verify_report(
            _inventory(tmp_path / "inventory.json"),
            _report(
                tmp_path / "wrong-test.xml",
                cases=[("tests.test_other", "test_other")],
            ),
            "portable-nonbrowser",
        )
