"""Deterministic JSON serialization and stable identity helpers."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import math
from pathlib import Path
from typing import Any


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON cannot serialize non-finite floats")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if hasattr(value, "item"):
        return _normalize(value.item())
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return compact deterministic UTF-8 JSON text for supported values."""
    import json

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def configuration_hash(value: Any) -> str:
    """Return the SHA-256 hash of a normalized experiment configuration."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
