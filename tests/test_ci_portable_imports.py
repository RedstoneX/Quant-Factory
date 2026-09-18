"""Dependency-boundary checks for the public CI environment."""

from __future__ import annotations

import subprocess
import sys

import pytest

from tools import assert_junit_report


def test_market_data_import_does_not_require_vectorbtpro() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import market_data, sys; assert 'vectorbtpro' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_junit_report_accepts_matching_nested_testcase_counts(tmp_path, monkeypatch) -> None:
    report = tmp_path / "portable.xml"
    report.write_text(
        "<testsuites><testsuite name=\"portable\" tests=\"2\" skipped=\"0\" "
        "failures=\"0\" errors=\"0\"><testcase/><testcase/></testsuite></testsuites>"
    )
    monkeypatch.setattr(sys, "argv", ["assert_junit_report.py", str(report)])

    assert assert_junit_report.main() == 0


@pytest.mark.parametrize(
    "xml",
    [
        '<testsuite tests="0" skipped="0" failures="0" errors="0"/>',
        '<testsuite tests="1" skipped="0" failures="0" errors="0"/>',
        '<testsuite tests="1" skipped="0" failures="0" errors="0"><testcase><skipped/></testcase></testsuite>',
        '<testsuite tests="many" skipped="0" failures="0" errors="0"><testcase/></testsuite>',
        '<testsuites><testsuite tests="1" skipped="0" failures="0" errors="0"><testcase/><testcase/></testsuite></testsuites>',
        '<testsuites tests="2" skipped="0" failures="0" errors="0"><testsuite tests="1" skipped="0" failures="0" errors="0"><testcase/></testsuite></testsuites>',
    ],
)
def test_junit_report_rejects_invalid_or_non_passing_counts(tmp_path, monkeypatch, xml) -> None:
    report = tmp_path / "portable.xml"
    monkeypatch.setattr(sys, "argv", ["assert_junit_report.py", str(report)])
    report.write_text(xml)

    assert assert_junit_report.main() == 1
