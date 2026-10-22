"""Durable, read-cheap projection of fully verified Factory survivors."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from persistence import EventSeverity, PersistenceService, RunEventType


SURVIVOR_EVENT_SOURCE = "candidate_pipeline_runtime"
SURVIVOR_EVENT_MESSAGE = (
    "Factory filter chain completed and is ready for the protected-test gate."
)


def record_factory_outcome(
    *, database: str | Path, screening_run_id: str, outcome: object
) -> None:
    """Persist one idempotent survivor marker from an authoritative chain outcome."""

    if getattr(outcome, "status", None) != "ready_for_protected_test":
        return
    service = PersistenceService(database)
    try:
        service.connection.execute("BEGIN IMMEDIATE")
        try:
            already_recorded = any(
                event.source == SURVIVOR_EVENT_SOURCE
                and event.message == SURVIVOR_EVENT_MESSAGE
                for event in service.events.list_for_run(screening_run_id)
            )
            if not already_recorded:
                service.events.append(
                    run_id=screening_run_id,
                    event_type=RunEventType.RUN_SUCCEEDED,
                    severity=EventSeverity.INFO,
                    source=SURVIVOR_EVENT_SOURCE,
                    message=SURVIVOR_EVENT_MESSAGE,
                )
            service.connection.commit()
        except Exception:
            service.connection.rollback()
            raise
    finally:
        service.close()


def verified_survivor_run_ids(*, database: str | Path) -> frozenset[str]:
    """Read screening-run IDs bearing the exact authoritative survivor marker."""

    service = PersistenceService(database)
    try:
        records = service.connection.execute(
            """
            SELECT DISTINCT run_id FROM run_operator_events
            WHERE source=? AND message=?
            """,
            (SURVIVOR_EVENT_SOURCE, SURVIVOR_EVENT_MESSAGE),
        )
        return frozenset(str(record["run_id"]) for record in records)
    finally:
        service.close()


def annotate_factory_outcomes(
    rows: Iterable[Mapping[str, object]],
    *,
    database: str | Path,
) -> tuple[dict[str, object], ...]:
    """Attach the persisted chain outcome without replaying evidence artifacts."""

    survivors = verified_survivor_run_ids(database=database)
    return tuple(
        {
            **row,
            "factory_outcome": (
                "ready_for_protected_test" if str(row.get("run_id")) in survivors else None
            ),
        }
        for row in rows
    )


__all__ = [
    "SURVIVOR_EVENT_MESSAGE",
    "annotate_factory_outcomes",
    "record_factory_outcome",
    "verified_survivor_run_ids",
]
