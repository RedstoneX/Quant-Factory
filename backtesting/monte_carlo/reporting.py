"""Strict JSON serialization and schema validation."""
import json, math
from pathlib import Path
from typing import Any

REQUIRED_KEYS = {"schema_version", "status", "source", "config", "observation_count", "distributions", "reasons", "warnings", "timestamp"}

def _validate_finite(value: Any, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value): raise ValueError(f"non-finite number at {path}")
    if isinstance(value, dict):
        for key, item in value.items(): _validate_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value): _validate_finite(item, f"{path}[{index}]")

def validate_report(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict): raise ValueError("report must be a JSON object")
    missing = REQUIRED_KEYS - payload.keys()
    if missing: raise ValueError(f"report missing required keys: {sorted(missing)}")
    if payload["schema_version"] != 1: raise ValueError("unsupported report schema version")
    _validate_finite(payload)
    return payload

def write_report(path: Path, payload: dict[str, Any]) -> None:
    validate_report(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")

def read_report(path: Path) -> dict[str, Any]:
    try: payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"invalid report: {exc}") from exc
    return validate_report(payload)
