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
    resolved_observed_at = observed_at or datetime.now(timezone.utc)
    credential_reading = supplied.get(
        "credential",
        HomeHealthReading(
            "credential",
            "Not checked",
            "Credential values are never displayed.",
        ),
    )
    snapshot = tuple(
        _truthful_reading(reading, resolved_observed_at, stale_after)
        for reading in (
            database_reading,
            artifact_reading,
            HomeHealthReading(
                "catalog",
                "Available" if datasets and configuration_error is None else "Not checked",
                (
                    f"{len(datasets)} committed manifests were inspected."
                    if datasets and configuration_error is None
                    else configuration_error or "No committed manifests were inspected."
                ),
                database_reading.checked_at,
            ),
            worker_reading,
            cache_reading,
            redact_credential_health_reading(credential_reading),
        )
    )
    available_count = sum(reading.status == "Available" for reading in snapshot)
    not_checked_count = sum(reading.status == "Not checked" for reading in snapshot)

    return html.Div(
        [
            page_heading(
                "SYSTEM / INFRASTRUCTURE",
                "Know whether research can operate",
                "Read the latest available health evidence without mistaking unmeasured services for healthy ones.",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Strong(
                                "Research state is readable; launch readiness is not established"
                                if not_checked_count
                                else "The recorded research components are available"
                            ),
                            html.P(
                                "Every status below is tied to the evidence and observation time shown on this page.",
                                className="section-description",
                            ),
                        ]
                    ),
                    html.Span(
                        f"{available_count} available · {not_checked_count} not checked",
                        className="support-summary-count",
                    ),
                ],
                className="support-summary-banner",
            ),
            html.Section(
                [_health_pulse(reading) for reading in snapshot],
                id="system-health-summary",
                className="health-pulse-strip",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2("Component health"),
                                            html.P("Status, evidence, and observation time stay together.", className="section-description"),
                                        ]
                                    ),
                                    html.Span("No inferred health", className="surface-badge"),
                                ],
                                className="surface-heading",
                            ),
                            html.Div(
                                [_health_component(reading) for reading in snapshot],
                                className="health-component-list",
                            ),
                        ],
                        className="support-surface",
                    ),
                    html.Aside(
                        [
                            html.Div(
                                [
                                    html.H2("Operational meaning"),
                                    html.P("What this snapshot permits you to conclude.", className="section-description"),
                                ],
                                className="surface-heading",
                            ),
                            html.Div(
                                [
                                    html.Strong(
                                        f"Milestone {PROJECT_STATUS.current_milestone_number} · {PROJECT_STATUS.current_milestone_title}"
                                    ),
                                    html.P(PROJECT_STATUS.current_milestone_status, className="field-help"),
                                    html.P(PROJECT_STATUS.workspace_status, className="field-help"),
                                    html.P(PROJECT_STATUS.strategy_status, className="field-help"),
                                ],
                                className="operational-meaning-block",
                            ),
                            html.Div(
                                [
                                    html.H3("Safe now"),
                                    html.Ul(
                                        [
                                            html.Li("Inspect persisted runs and artifacts."),
                                            html.Li("Review committed market-data manifests."),
                                            html.Li("Complete the owner workflow walkthrough."),
                                        ]
                                    ),
                                ],
                                className="operational-meaning-block",
                            ),
                            html.Div(
                                [
                                    html.H3("Requires a fresh check"),
                                    html.Ul(
                                        [
                                            html.Li("Worker availability before launching research."),
                                            html.Li("Cache identity and integrity before reuse."),
                                            html.Li("Named credential authority before any authorized external operation."),
                                        ]
                                    ),
                                ],
                                className="operational-meaning-block",
                            ),
                        ],
                        className="support-surface operational-meaning-panel",
                    ),
                ],
                className="support-primary-grid",
            ),
        ],
        className="page-container support-page system-status-page",
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
    validated_datasets = tuple(
        item for item in datasets if item.manifest.status == "validated"
    )
    providers = sorted({item.manifest.provider for item in validated_datasets})
    selected_provider = providers[0] if providers else None
    selected_records = tuple(
        item for item in validated_datasets if item.manifest.provider == selected_provider
    )
    return html.Div(
        [
            page_heading(
                "SYSTEM / DATA SOURCES",
                "Know where research data came from",
                "Trace committed datasets back to their recorded provider without confusing provenance with live access.",
            ),
            html.Section(
                [
                    _provider_metric("Provider families", str(len(providers)), "Recorded in validated manifests"),
                    _provider_metric("Validated provenance links", str(len(validated_datasets)), "One per validated dataset"),
                    _provider_metric("Live connections checked", "0", "Not tested by this view"),
                    _provider_metric("Credential grants checked", "0", "No secret values displayed"),
                ],
                className="support-metric-strip",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [html.H2("Recorded lineage"), html.P("Saved provider identity and local evidence remain separate.", className="section-description")]
                                    ),
                                    html.Span("Connectivity not checked", className="surface-badge surface-badge-warning"),
                                ],
                                className="surface-heading",
                            ),
                            html.Div(
                                [
                                    html.Div([html.Span("Recorded provider"), html.Strong(selected_provider or "None")], className="lineage-step"),
                                    html.Span("→", className="lineage-arrow", **{"aria-hidden": "true"}),
                                    html.Div([html.Span("Validated manifests"), html.Strong(str(len(selected_records)))], className="lineage-step"),
                                    html.Span("→", className="lineage-arrow", **{"aria-hidden": "true"}),
                                    html.Div([html.Span("Local catalog"), html.Strong("Committed · read only")], className="lineage-step"),
                                ],
                                className="lineage-flow",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [html.Strong(provider), html.Small(f"{sum(item.manifest.provider == provider for item in validated_datasets)} validated datasets"), html.Span("Not checked live")],
                                        className=("provider-choice provider-choice-selected" if provider == selected_provider else "provider-choice"),
                                    )
                                    for provider in providers
                                ]
                                or [html.P("No committed provider records were found.", className="support-empty-state")],
                                className="provider-choice-grid",
                            ),
                        ],
                        className="support-surface",
                    ),
                    html.Aside(
                        [
                            html.Div([html.H2("Selected source"), html.P("What the recorded evidence actually establishes.", className="section-description")], className="surface-heading"),
                            html.Div([html.Strong(selected_provider or "No source"), html.Small("Historical market-data provider")], className="selected-record-title"),
                            html.Dl(
                                [
                                    html.Div([html.Dt("Provenance status"), html.Dd("Present in committed manifests" if selected_provider else "Unavailable")]),
                                    html.Div([html.Dt("Validated datasets"), html.Dd(str(len(selected_records)))]),
                                    html.Div([html.Dt("Live connectivity"), html.Dd("Not checked")]),
                                    html.Div([html.Dt("Credential grant"), html.Dd("Not checked")]),
                                ],
                                className="selected-record-facts",
                            ),
                            html.Div(
                                [html.Strong("Recorded does not mean connected"), html.P("This page proves the saved data's recorded origin. It does not prove current entitlement, uptime, credential availability, or freshness.", className="field-help")],
                                className="operator-message operator-message-warning selected-record-warning",
                            ),
                        ],
                        className="support-surface selected-support-record",
                    ),
                ],
                className="support-primary-grid",
            ),
            html.Section(
                [
                    html.Div([html.H2("Validated provenance records"), html.P("Open Market data for coverage, restrictions, and local verification.", className="section-description")], className="surface-heading"),
                    html.Div(_provenance_table(validated_datasets), className="support-table-scroll"),
                    html.P(configuration_error, className="error-state") if configuration_error else None,
                ],
                className="support-surface",
            ),
        ],
        className="page-container support-page data-sources-page",
    )


def _provider_metric(label: str, value: str, detail: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value), html.Small(detail)], className="support-metric")


def _provenance_table(datasets: tuple) -> html.Table:
    return html.Table(
        [
            html.Thead(html.Tr([html.Th(label) for label in ("Dataset", "Recorded source", "Bars", "Recorded coverage", "Rows", "Provenance")])),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(item.manifest.symbol),
                            html.Td(item.manifest.provider),
                            html.Td(item.manifest.timeframe),
                            html.Td(_provider_coverage(item)),
                            html.Td(f"{item.manifest.row_count:,}"),
                            html.Td("Recorded"),
                        ]
                    )
                    for item in datasets
                ]
                or [html.Tr(html.Td("No validated provenance records were found.", colSpan=6))]
            ),
        ],
        className="catalog-table support-table",
    )


def _provider_coverage(item) -> str:
    metadata = item.manifest.metadata
    start = metadata.get("earliest_timestamp") or metadata.get("coverage_start") or "Unknown"
    end = metadata.get("latest_timestamp") or metadata.get("latest_completed_session") or "Unknown"
    return f"{start} to {end}"


def _health_pulse(
    reading: HomeHealthReading,
    *,
    label: str | None = None,
) -> html.Div:
    state = reading.status.lower().replace(" ", "-")
    resolved_label = label or {
        "database": "Research database",
        "artifact": "Artifact storage",
        "catalog": "Data catalog",
        "cache": "Local data",
        "worker": "Orchestrator",
        "credential": "Credentials",
    }.get(reading.area, reading.area.replace("_", " ").title())
    return html.Div(
        [
            html.Span(resolved_label),
            html.Strong(reading.status, className=f"health-state health-state-{state}"),
        ],
        className="health-pulse",
    )


def health_pulse_cards(
    readings: Iterable[HomeHealthReading],
    *,
    observed_at: datetime,
    stale_after: timedelta,
) -> list[html.Div]:
    """Refresh the compact System status strip from its captured snapshot."""

    supplied = {reading.area: reading for reading in readings}
    specifications = (
        ("Research database", "database"),
        ("Artifact storage", "artifact"),
        ("Data catalog", "catalog"),
        ("Local data", "cache"),
        ("Orchestrator", "worker"),
        ("Credentials", "credential"),
    )
    cards: list[html.Div] = []
    for label, area in specifications:
        reading = supplied.get(
            area,
            HomeHealthReading(
                area,
                "Not checked",
                f"No timestamped {label.lower()} snapshot was supplied.",
            ),
        )
        if area == "credential":
            reading = redact_credential_health_reading(reading)
        cards.append(
            _health_pulse(
                _truthful_reading(reading, observed_at, stale_after),
                label=label,
            )
        )
    return cards


def _health_component(reading: HomeHealthReading) -> html.Div:
    label = {
        "database": "Research database",
        "artifact": "Artifact storage",
        "catalog": "Data catalog",
        "cache": "Local data",
        "worker": "Orchestrator",
        "credential": "Credentials",
    }.get(reading.area, reading.area.replace("_", " ").title())
    return html.Div(
        [
            html.Div([html.Strong(label), html.Small("Recorded component")]),
            html.Strong(reading.status, className="health-component-state"),
            html.P(reading.detail),
            html.Time(f"Last checked: {reading.checked_at or 'Not checked'}"),
        ],
        className="health-component-row",
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


def health_metric_cards(
    readings: Iterable[HomeHealthReading],
    *,
    observed_at: datetime,
    stale_after: timedelta,
) -> list[html.Div]:
    """Render current System cards from a previously captured snapshot."""

    supplied = {reading.area: reading for reading in readings}
    specifications = (
        (
            "Research database",
            "database",
            "No timestamped research-database health snapshot was supplied.",
        ),
        (
            "Artifact storage",
            "artifact",
            "No timestamped artifact-storage health snapshot was supplied.",
        ),
        (
            "Local data",
            "cache",
            "No timestamped active-setup cache snapshot was supplied.",
        ),
        (
            "Orchestrator",
            "worker",
            "No timestamped worker or orchestrator health snapshot was supplied.",
        ),
        ("Credentials", "credential", "Credential values are never displayed."),
    )
    cards: list[html.Div] = []
    for label, area, missing_detail in specifications:
        reading = supplied.get(
            area,
            HomeHealthReading(area, "Not checked", missing_detail),
        )
        if area == "credential":
            reading = redact_credential_health_reading(reading)
        cards.append(
            _metric(
                label,
                _truthful_reading(reading, observed_at, stale_after),
            )
        )
    return cards
