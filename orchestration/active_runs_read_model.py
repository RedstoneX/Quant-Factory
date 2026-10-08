"""Bounded read model for every currently active Factory operation."""

from __future__ import annotations

from itertools import chain
from pathlib import Path

from orchestration.run_service import RunSummary, _summary
from persistence import PersistenceService, RunStatus


ACTIVE_RUN_STATUSES = (
    RunStatus.CREATED,
    RunStatus.RUNNING,
)


def active_run_summaries(database: str | Path) -> tuple[RunSummary, ...]:
    """Read active records only, without hydrating terminal run history."""

    service = PersistenceService(database)
    try:
        records = chain.from_iterable(
            service.runs.list(status=status) for status in ACTIVE_RUN_STATUSES
        )
        return tuple(
            sorted(
                (_summary(record) for record in records),
                key=lambda run: (run.created_at, run.run_id),
                reverse=True,
            )
        )
    finally:
        service.close()


__all__ = ["ACTIVE_RUN_STATUSES", "active_run_summaries"]
