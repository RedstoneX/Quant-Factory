"""Passive freshness updates for permanently mounted health pages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Mapping

from dash import Dash, Input, Output, State

from dashboard.health import HomeHealthReading
from dashboard.pages.home import health_cards_for_readings
from dashboard.pages.system_health import health_metric_cards


DEFAULT_STALE_AFTER = timedelta(minutes=15)


def health_presentations(
    snapshot: object,
    *,
    observed_at: datetime | None = None,
) -> tuple[list[Any], list[Any]]:
    """Re-evaluate snapshot age without probing services or replacing routes."""

    readings, stale_after = _snapshot_values(snapshot)
    resolved_observed_at = observed_at or datetime.now(timezone.utc)
    return (
        health_cards_for_readings(
            readings,
            observed_at=resolved_observed_at,
            stale_after=stale_after,
        ),
        health_metric_cards(
            readings,
            observed_at=resolved_observed_at,
            stale_after=stale_after,
        ),
    )


def register_health_callbacks(app: Dash) -> None:
    """Refresh only passive health presentation in the mounted page tree."""

    @app.callback(
        Output("home-health-cards", "children"),
        Output("system-health-summary", "children"),
        Input("health-freshness-interval", "n_intervals"),
        State("health-observation-snapshot", "data"),
    )
    def refresh_health_freshness(
        _n_intervals: int,
        snapshot: object,
    ) -> tuple[list[Any], list[Any]]:
        return health_presentations(snapshot)


def _snapshot_values(
    snapshot: object,
) -> tuple[tuple[HomeHealthReading, ...], timedelta]:
    if not isinstance(snapshot, Mapping):
        return (), DEFAULT_STALE_AFTER
    raw_seconds = snapshot.get("stale_after_seconds")
    if not isinstance(raw_seconds, (int, float)):
        return (), DEFAULT_STALE_AFTER
    seconds = float(raw_seconds)
    if not isfinite(seconds) or seconds <= 0:
        return (), DEFAULT_STALE_AFTER
    raw_readings = snapshot.get("readings")
    if not isinstance(raw_readings, list):
        return (), DEFAULT_STALE_AFTER

    readings: list[HomeHealthReading] = []
    for value in raw_readings:
        if not isinstance(value, Mapping):
            return (), DEFAULT_STALE_AFTER
        area = value.get("area")
        status = value.get("status")
        detail = value.get("detail")
        checked_at = value.get("checked_at")
        if (
            not isinstance(area, str)
            or not isinstance(status, str)
            or not isinstance(detail, str)
            or (checked_at is not None and not isinstance(checked_at, str))
        ):
            return (), DEFAULT_STALE_AFTER
        readings.append(HomeHealthReading(area, status, detail, checked_at))
    return tuple(readings), timedelta(seconds=seconds)
