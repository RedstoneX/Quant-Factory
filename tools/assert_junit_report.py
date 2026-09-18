"""Fail CI unless its portable pytest selection executed without skips."""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: assert_junit_report.py PATH", file=sys.stderr)
        return 2

    report_path = Path(sys.argv[1])
    if not report_path.is_file():
        print(f"Portable test report is missing: {report_path}", file=sys.stderr)
        return 1

    try:
        root = ElementTree.parse(report_path).getroot()
    except ElementTree.ParseError as exc:
        print(f"Portable test report is invalid XML: {exc}", file=sys.stderr)
        return 1

    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    cases = list(root.iter("testcase"))
    try:
        for suite in suites:
            suite_cases = list(suite.iter("testcase"))
            actual = {
                "tests": len(suite_cases),
                "failures": sum(bool(case.findall("failure")) for case in suite_cases),
                "errors": sum(bool(case.findall("error")) for case in suite_cases),
                "skipped": sum(bool(case.findall("skipped")) for case in suite_cases),
            }
            declared = {name: int(suite.get(name, "0")) for name in actual}
            if declared != actual:
                print(
                    f"Portable test report counter mismatch in suite {suite.get('name', '<unnamed>')}: "
                    f"declared {declared}, actual {actual}.",
                    file=sys.stderr,
                )
                return 1
    except ValueError as exc:
        print(f"Portable test report has invalid counters: {exc}", file=sys.stderr)
        return 1

    totals = {
        "tests": len(cases),
        "failures": sum(bool(case.findall("failure")) for case in cases),
        "errors": sum(bool(case.findall("error")) for case in cases),
        "skipped": sum(bool(case.findall("skipped")) for case in cases),
    }
    if root.tag == "testsuites" and any(name in root.attrib for name in totals):
        try:
            declared_root = {name: int(root.get(name, "0")) for name in totals}
        except ValueError as exc:
            print(f"Portable test report has invalid root counters: {exc}", file=sys.stderr)
            return 1
        if declared_root != totals:
            print(
                "Portable test report counter mismatch in root suite: "
                f"declared {declared_root}, actual {totals}.",
                file=sys.stderr,
            )
            return 1
    print(
        "Portable test selection: "
        f"{totals['tests']} collected; {totals['skipped']} skipped; "
        f"{totals['failures']} failed; {totals['errors']} errors."
    )
    if totals["tests"] == 0:
        print("Portable test selection collected zero tests.", file=sys.stderr)
        return 1
    if totals["skipped"]:
        print("Portable test selection must not contain skipped tests.", file=sys.stderr)
        return 1
    if totals["failures"] or totals["errors"]:
        print("Portable test selection contains failed tests.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
