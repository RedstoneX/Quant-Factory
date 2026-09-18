"""Read-only operator view of committed market-data manifests."""

from __future__ import annotations

from pathlib import Path

from dash import html

from dashboard.health import DatasetHealth, inspect_catalog
from dashboard.pages.common import page_heading
from market_data.catalog import DEFAULT_CONFIG_PATH, DEFAULT_MANIFEST_DIR


def layout(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    manifest_dir: Path = DEFAULT_MANIFEST_DIR,
    catalog_snapshot: tuple | None = None,
) -> html.Div:
    locations, datasets, configuration_error = catalog_snapshot if catalog_snapshot is not None else inspect_catalog(
        config_path=config_path, manifest_dir=manifest_dir
    )
    validated = sum(item.manifest.status == "validated" for item in datasets)
    quarantined = sum(item.manifest.status == "quarantined" for item in datasets)
    available = sum(item.availability == "Available locally" for item in datasets)
    return html.Div(
        [
            page_heading(
                "RESEARCH / DATA CATALOG",
                "Market Data",
                "View the price history used in strategy research. Inspect provenance and local verification before an approved fixture run.",
            ),
            html.Section(
                [
                    _metric("Catalogued datasets", str(len(datasets))),
                    _metric("Validated", str(validated)),
                    _metric("Available locally", str(available)),
                    _metric("Quarantined", str(quarantined)),
                ],
                className="summary-grid",
            ),
            _configuration_notice(configuration_error),
            html.Section(
                [
                    html.H2("Historical datasets"),
                    html.P(
                        "SPYM is the current Databento infrastructure fixture. Fixture evidence does not authorize a strategy, paper trading, or live use.",
                        className="summary-detail",
                    ),
                    _catalog_table(datasets),
                ],
                className="panel table-panel",
            ),
            html.Section(
                [html.H2("Dataset assumptions and restrictions"), *[_dataset_assumptions(item) for item in datasets]],
                className="panel",
            ),
            html.Section(
                [
                    html.H2("Use and verification notes"),
                    html.P("Quarantined datasets are retained for provenance and are not approved for experiments.", className="error-state"),
                    html.P("Provider connectivity, credential availability, and data freshness were not checked on this page.", className="summary-detail"),
                    html.Details(
                        [
                            html.Summary("Technical manifest references"),
                            html.Ul(
                                [
                                    html.Li(
                                        f"{item.manifest.dataset_id}: {item.manifest.canonical_relative_path} · SHA-256 {item.manifest.sha256}"
                                    )
                                    for item in datasets
                                ]
                            ),
                        ]
                    ),
                ],
                className="panel",
            ),
        ],
        className="page-container",
    )


def _metric(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label, className="metric-label"), html.Strong(value)], className="metric-card")


def _configuration_notice(error: str | None) -> html.Div | None:
    if error is None:
        return None
    return html.Div(
        [html.Strong("Local data verification is unavailable."), html.P(error)],
        className="operator-message operator-message-warning",
    )


def _catalog_table(datasets: tuple[DatasetHealth, ...]) -> html.Table:
    return html.Table(
        [
            html.Thead(html.Tr([html.Th(label) for label in ("Instrument", "Provider", "Timeframe", "Coverage", "Rows", "Approval", "Local file", "Checksum")])),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(f"{item.manifest.asset_class.title()} · {item.manifest.symbol}"),
                            html.Td(item.manifest.provider),
                            html.Td(item.manifest.timeframe),
                            html.Td(_coverage(item)),
                            html.Td(str(item.manifest.row_count)),
                            html.Td(_approval(item)),
                            html.Td(item.availability),
                            html.Td(item.checksum),
                        ]
                    )
                    for item in datasets
                ]
                or [html.Tr(html.Td("No committed dataset manifests were found.", colSpan=8))]
            ),
        ],
        className="catalog-table",
    )


def _coverage(item: DatasetHealth) -> str:
    metadata = item.manifest.metadata
    start = metadata.get("earliest_timestamp") or metadata.get("coverage_start") or "Unknown"
    end = metadata.get("latest_timestamp") or metadata.get("latest_completed_session") or "Unknown"
    return f"{start} to {end}"


def _approval(item: DatasetHealth) -> str:
    if item.manifest.status == "quarantined":
        return "Quarantined — not approved"
    return item.manifest.status.title()


def _dataset_assumptions(item: DatasetHealth) -> html.Details:
    metadata = item.manifest.metadata
    fields = (
        ("Timestamp timezone", metadata.get("timezone", "Not recorded")),
        ("Market timezone", metadata.get("market_timezone", "Not recorded")),
        ("Price adjustment", metadata.get("adjustment", "Not recorded")),
        ("Missing sessions", metadata.get("missing_session_count", "Not recorded")),
        ("Corporate-action policy", metadata.get("corporate_action_policy", "Not recorded")),
        ("Restrictions", metadata.get("restrictions", "Not recorded")),
        ("File verification", item.detail),
    )
    return html.Details([
        html.Summary(f"{item.manifest.symbol} · {item.manifest.provider} · {item.manifest.timeframe} · {_approval(item)}"),
        html.Dl([
            html.Div([html.Dt(label), html.Dd("; ".join(map(str, value)) if isinstance(value, list) else str(value))])
            for label, value in fields
        ], className="run-monitor-details"),
    ])
