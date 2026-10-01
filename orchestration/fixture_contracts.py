"""Executor-neutral fixture launch contracts owned by orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FixtureExecutionResult:
    """Durable run identity returned by a technical fixture executor."""

    quant_factory_run_id: str
    prefect_flow_run_id: str
    configuration_id: str
    deterministic_value: int
    attempt_count: int
    prefect_api_url: str | None = None


class FixtureLauncher(Protocol):
    """Injected technical fixture executor."""

    def __call__(self, **kwargs: object) -> FixtureExecutionResult: ...
