"""Read-only Milestone 23 system-status page."""

from __future__ import annotations

import os
from pathlib import Path

from dash import html

from dashboard.health import inspect_catalog, inspect_database
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
) -> html.Div:
    database_health = inspect_database(database)
    locations, datasets, configuration_error = catalog_snapshot if catalog_snapshot is not None else inspect_catalog(
        config_path=config_path, manifest_dir=manifest_dir
    )
    local_verified = sum(item.checksum == "Verified" for item in datasets)
    artifact_status, artifact_detail = _artifact_health(artifact_root)
    data_status = (
        f"{local_verified} local checksum(s) verified"
        if configuration_error is None
        else "Not checked"
    )
    return html.Div(
        [
            page_heading(
                "SYSTEM / INFRASTRUCTURE",
                "System Status",
                f"Read-only health for the current research milestone. {PROJECT_STATUS.strategy_status} {PROJECT_STATUS.workspace_status} Strategy discovery, paper execution, and live trading are blocked.",
            ),
            html.Section(
                [
                    _metric("Research database", database_health.status, database_health.detail),
                    _metric("Artifact storage", artifact_status, artifact_detail),
                    _metric("Local data", data_status, "Committed manifests and local file checks only."),
                    _metric("Orchestrator", "Not checked", "No local or remote orchestrator probe was requested."),
                    _metric("Credentials", "Not checked", "Credential values are never displayed."),
                ],
                className="summary-grid",
            ),
            html.Section(
                [
                    html.H2("Milestone gate"),
                    html.P(f"Milestone {PROJECT_STATUS.current_milestone_number}: {PROJECT_STATUS.current_milestone_status}", className="summary-detail"),
                    html.P("Provider health is not implied by historical dataset files. See Data Sources for recorded provenance only.", className="summary-detail"),
                ],
                className="panel",
            ),
            html.Section(
                [
                    html.H2("Data verification"),
                    html.P(configuration_error or f"{len(datasets)} committed manifests inspected against the configured local data root."),
                    html.P("The configured data root is available for technical review." if locations else "No configured local data root was read.", className="summary-detail"),
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
    _, datasets, configuration_error = catalog_snapshot if catalog_snapshot is not None else inspect_catalog(
        config_path=config_path, manifest_dir=manifest_dir
    )
    providers = sorted({item.manifest.provider for item in datasets})
    return html.Div(
        [
            page_heading("SYSTEM / PROVIDERS", "Data Sources", "Recorded historical-data provenance. This page does not test live provider connectivity."),
            html.Section(
                [
                    html.H2("Recorded providers"),
                    html.Ul([html.Li(provider) for provider in providers] or [html.Li("No committed provider records were found.")]),
                    html.P("Connectivity and credential availability: Not checked. No credential values are displayed.", className="summary-detail"),
                    html.P(configuration_error, className="error-state") if configuration_error else None,
                ],
                className="panel",
            ),
        ],
        className="page-container",
    )


def _metric(label: str, status: str, detail: str) -> html.Div:
    return html.Div([html.Span(label, className="metric-label"), html.Strong(status), html.Small(detail)], className="metric-card")


def _artifact_health(root: Path) -> tuple[str, str]:
    if not root.exists():
        return "Unavailable", "The configured artifact location does not exist."
    if not root.is_dir():
        return "Unavailable", "The configured artifact location is not a directory."
    if not os.access(root, os.R_OK | os.X_OK):
        return "Unavailable", "The configured artifact location is not readable."
    return "Available", "The configured artifact location is readable."
