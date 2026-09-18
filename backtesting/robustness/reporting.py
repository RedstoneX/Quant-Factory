"""Strict schema-versioned JSON reporting for robustness results."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

REQUIRED_KEYS = {
    "schema_version",
    "status",
    "strategy_id",
    "strategy_version",
    "experiment_id",
    "source_artifact_id",
    "locked_parameters",
    "component_statuses",
    "reasons",
    "warnings",
    "timestamp",
}
VALID_STATUSES = {"passed", "failed", "insufficient_evidence", "invalid_input"}


def _validate_json_value(value: Any, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite number at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string key at {path}")
            _validate_json_value(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"unsupported JSON value at {path}: {type(value).__name__}")


def validate_robustness_report(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("robustness report must be a JSON object")
    missing = REQUIRED_KEYS - set(payload)
    if missing:
        raise ValueError(f"robustness report missing keys: {sorted(missing)}")
    if payload["schema_version"] != 1:
        raise ValueError("unsupported robustness report schema version")
    if payload["status"] not in VALID_STATUSES:
        raise ValueError("invalid robustness report status")
    component_statuses = payload["component_statuses"]
    if not isinstance(component_statuses, dict) or any(
        status not in VALID_STATUSES for status in component_statuses.values()
    ):
        raise ValueError("invalid component statuses")
    _validate_json_value(payload)
    return payload


def write_robustness_report(path: Path, payload: dict[str, Any]) -> None:
    validate_robustness_report(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_robustness_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid robustness report: {exc}") from exc
    return validate_robustness_report(payload)
