"""Read-only Milestone 23 system-status page."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from dash import html

from dashboard.health import (
    HomeHealthReading,
    inspect_artifact_storage,
    inspect_catalog,
    inspect_database,
    normalize_health_reading,
    redact_credential_health_reading,
)
from dashboard.pages.common import page_heading
from dashboard.project_status import PROJECT_STATUS
from market_data.catalog import DEFAULT_CONFIG_PATH, DEFAULT_MANIFEST_DIR


def layout(
    database: Path,
    artifact_root: Path,
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    manifest_dir: Path = DEFAULT_MANIFEST_DIR,
    catalog_snapshot: tuple | None = None,
    health_readings: Iterable[HomeHealthReading] | None = None,
    observed_at: datetime | None = None,
    stale_after: timedelta = timedelta(minutes=15),
) -> html.Div:
    locations, datasets, configuration_error = (
        catalog_snapshot
        if catalog_snapshot is not None
        else inspect_catalog(config_path=config_path, manifest_dir=manifest_dir)
    )
    supplied = (
        {reading.area: reading for reading in health_readings}
        if health_readings is not None
        else {}
    )
    if not supplied:
        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        database_health = inspect_database(database)
        artifact_health = inspect_artifact_storage(artifact_root)
        database_reading = HomeHealthReading(
            "database", database_health.status, database_health.detail, checked_at
        )
        artifact_reading = HomeHealthReading(
            "artifact", artifact_health.status, artifact_health.detail, checked_at
        )
        cache_reading = HomeHealthReading(
            "cache",
            "Not checked",
            (
                "No active saved-setup dataset identities were supplied for "
                "research-cache health."
            ),
        )
    else:
        database_reading = supplied.get(
            "database",
            HomeHealthReading(
                "database",
                "Not checked",
                "No timestamped research-database health snapshot was supplied.",
            ),
        )
        artifact_reading = supplied.get(
            "artifact",
            HomeHealthReading(
                "artifact",
                "Not checked",
                "No timestamped artifact-storage health snapshot was supplied.",
            ),
        )
        cache_reading = supplied.get(
            "cache",
            HomeHealthReading(
                "cache",
                "Not checked",
                "No timestamped active-setup cache snapshot was supplied.",
            ),
        )
    worker_reading = supplied.get(
        "worker",
        HomeHealthReading(
            "worker",
            "Not checked",
            "No timestamped worker or orchestrator health snapshot was supplied.",
        ),
    )
    credential_reading = supplied.get(
        "credential",
        HomeHealthReading(
            "credential",
            "Not checked",
            "Credential values are never displayed.",
        ),
    )
    credential_reading = redact_credential_health_reading(credential_reading)
    resolved_observed_at = observed_at or datetime.now(timezone.utc)
    return html.Div(
        [
            page_heading(
                "SYSTEM / INFRASTRUCTURE",
                "System Status",
                (
                    "Read-only health for the current research milestone. "
                    f"{PROJECT_STATUS.strategy_status} "
                    f"{PROJECT_STATUS.workspace_status} Strategy discovery, "
                    "paper execution, and live trading are blocked."
                ),
            ),
            html.Section(
                [
                    _metric(
                        "Research database",
                        _truthful_reading(
                            database_reading, resolved_observed_at, stale_after
                        ),
                    ),
                    _metric(
                        "Artifact storage",
                        _truthful_reading(
                            artifact_reading, resolved_observed_at, stale_after
                        ),
                    ),
                    _metric(
                        "Local data",
                        _truthful_reading(
                            cache_reading, resolved_observed_at, stale_after
                        ),
                    ),
                    _metric(
                        "Orchestrator",
                        _truthful_reading(
                            worker_reading, resolved_observed_at, stale_after
                        ),
                    ),
                    _metric(
                        "Credentials",
                        _truthful_reading(
                            credential_reading, resolved_observed_at, stale_after
                        ),
                    ),
                ],
                className="summary-grid",
            ),
            html.Section(
                [
                    html.H2("Milestone gate"),
                    html.P(
                        f"Milestone {PROJECT_STATUS.current_milestone_number}: "
                        f"{PROJECT_STATUS.current_milestone_status}",
                        className="summary-detail",
                    ),
                    html.P(
                        "Provider health is not implied by historical dataset files. "
                        "See Data Sources for recorded provenance only.",
                        className="summary-detail",
                    ),
                ],
                className="panel",
            ),
            html.Section(
                [
                    html.H2("Data verification"),
                    html.P(
                        configuration_error
                        or (
                            f"{len(datasets)} committed manifests inspected against "
                            "the configured local data root."
                        )
                    ),
                    html.P(
                        (
                            "The configured data root is available for technical review."
                            if locations
                            else "No configured local data root was read."
                        ),
                        className="summary-detail",
                    ),
                ],
                className="panel",
            ),
        ],
        className="page-container",
    )


def provider_layout(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    manifest_dir: Path = DEFAULT_MANIFEST_DIR,
    catalog_snapshot: tuple | None = None,
) -> html.Div:
    _, datasets, configuration_error = (
        catalog_snapshot
        if catalog_snapshot is not None
        else inspect_catalog(config_path=config_path, manifest_dir=manifest_dir)
    )
    providers = sorted({item.manifest.provider for item in datasets})
    return html.Div(
        [
            page_heading(
                "SYSTEM / PROVIDERS",
                "Data Sources",
                (
                    "Recorded historical-data provenance. This page does not "
                    "test live provider connectivity."
                ),
            ),
            html.Section(
                [
                    html.H2("Recorded providers"),
                    html.Ul(
                        [html.Li(provider) for provider in providers]
                        or [html.Li("No committed provider records were found.")]
                    ),
                    html.P(
                        "Connectivity and credential availability: Not checked. "
                        "No credential values are displayed.",
                        className="summary-detail",
                    ),
                    (
                        html.P(configuration_error, className="error-state")
                        if configuration_error
                        else None
                    ),
                ],
                className="panel",
            ),
        ],
        className="page-container",
    )


def _metric(label: str, reading: HomeHealthReading) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="metric-label"),
            html.Strong(reading.status),
            html.Small(reading.detail),
            html.Small(f"Last checked: {reading.checked_at or 'Not checked'}"),
        ],
        className="metric-card",
    )


def _truthful_reading(
    reading: HomeHealthReading,
    observed_at: datetime,
    stale_after: timedelta,
) -> HomeHealthReading:
    return normalize_health_reading(
        reading,
        observed_at=observed_at,
        stale_after=stale_after,
    )[0]
