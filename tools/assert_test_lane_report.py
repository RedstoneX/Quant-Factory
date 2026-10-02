"""Verify that a pytest JUnit report exactly covers one declared CI lane."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from xml.etree import ElementTree


LANES = (
    "portable-nonbrowser",
    "portable-browser",
    "licensed-vectorbt",
    "external-prefect",
    "controlled-market-data",
)


def _expected_node_ids(inventory: dict[str, object], lane: str) -> list[str]:
    lanes = inventory.get("lanes")
    if not isinstance(lanes, dict):
        raise ValueError("inventory lanes are missing")
    if lane == "portable-nonbrowser":
        node_ids = [
            node_id
            for node_id in lanes.get("portable", [])
            if not str(node_id).startswith("tests/browser/")
        ]
    elif lane == "portable-browser":
        node_ids = [
            node_id
            for node_id in lanes.get("portable", [])
            if str(node_id).startswith("tests/browser/")
        ]
    elif lane == "licensed-vectorbt":
        node_ids = list(lanes.get("licensed_vectorbt", []))
    elif lane == "external-prefect":
        node_ids = list(lanes.get("external_prefect", []))
    elif lane == "controlled-market-data":
        node_ids = list(lanes.get("controlled_market_data", []))
    else:
        raise ValueError(f"unsupported test lane: {lane}")
    return [str(node_id) for node_id in node_ids]


def _junit_identity(node_id: str) -> tuple[str, str]:
    parts = node_id.split("::")
    module = parts[0].removesuffix(".py").replace("/", ".")
    if len(parts) < 2:
        raise ValueError(f"unsupported pytest node id: {node_id}")
    return ".".join((module, *parts[1:-1])), parts[-1]


def verify_report(inventory_path: Path, report_path: Path, lane: str) -> str:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    expected_node_ids = _expected_node_ids(inventory, lane)
    expected_cases = Counter(_junit_identity(node_id) for node_id in expected_node_ids)
    root = ElementTree.parse(report_path).getroot()
    cases = list(root.iter("testcase"))
    reported_cases = Counter(
        (case.get("classname", ""), case.get("name", "")) for case in cases
    )
    failures = sum(bool(case.findall("failure")) for case in cases)
    errors = sum(bool(case.findall("error")) for case in cases)
    skipped = sum(bool(case.findall("skipped")) for case in cases)
    summary = (
        f"{lane}: expected {len(expected_node_ids)}; reported {len(cases)}; "
        f"skipped {skipped}; failed {failures}; errors {errors}"
    )
    if reported_cases != expected_cases or skipped or failures or errors:
        missing = list((expected_cases - reported_cases).elements())
        unexpected = list((reported_cases - expected_cases).elements())
        raise ValueError(f"{summary}; missing {missing}; unexpected {unexpected}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("lane", choices=LANES)
    arguments = parser.parse_args(argv)
    try:
        print(verify_report(arguments.inventory, arguments.report, arguments.lane))
    except (OSError, ValueError, ElementTree.ParseError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
