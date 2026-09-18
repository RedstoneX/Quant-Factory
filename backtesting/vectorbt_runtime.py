"""Explicit runtime boundary for the separately licensed research engine."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType


class VectorBTProUnavailableError(RuntimeError):
    """Raised when an operation requires VectorBT Pro but it is unavailable."""


def require_vectorbtpro() -> ModuleType:
    """Load VectorBT Pro when research execution reaches the engine boundary."""
    try:
        return import_module("vectorbtpro")
    except ModuleNotFoundError as exc:
        if exc.name != "vectorbtpro":
            raise
        raise VectorBTProUnavailableError(
            "VectorBT Pro is required for this research operation but is not "
            "installed in the active environment. Install the separately licensed "
            "engine before invoking VectorBT-backed research."
        ) from exc
