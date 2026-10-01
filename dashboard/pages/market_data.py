"""Read-only operator view of committed market-data manifests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dash import dcc, html
import plotly.graph_objects as go

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
    validated_datasets = tuple(
        item for item in datasets if item.manifest.status == "validated"
    )
    quarantined_datasets = tuple(
        item for item in datasets if item.manifest.status == "quarantined"
    )
    selected = next(
        (
            item
            for item in validated_datasets
            if item.manifest.symbol.upper() == "SPYM"
            and item.availability == "Available locally"
        ),
        next(
            (
                item
                for item in validated_datasets
                if item.availability == "Available locally"
            ),
            validated_datasets[0] if validated_datasets else None,
        ),
    )
    return html.Div(
        [
            page_heading(
                "RESEARCH / MARKET DATA",
                "Know what data is usable",
                "Inspect coverage, provenance, restrictions, and local verification before choosing a research dataset.",
            ),
            html.Section(
                [
                    _metric("Catalogued datasets", str(len(datasets)), "Committed manifests"),
                    _metric("Validated", str(validated), "Approved for stated uses"),
                    _metric("Available locally", str(available), "File presence verified"),
                    _metric("Quarantined", str(quarantined), "Retained, not experiment-ready"),
                ],
                className="support-metric-strip",
            ),
            _configuration_notice(configuration_error),
            html.Div(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2("Validated coverage landscape"),
                                            html.P(
                                                "Recorded start and end dates from committed manifests; missing dates remain absent.",
                                                className="section-description",
                                            ),
                                        ]
                                    ),
                                    html.Span("Manifest evidence", className="surface-badge"),
                                ],
                                className="surface-heading",
                            ),
                            _coverage_chart(datasets),
                        ],
                        className="support-surface market-coverage-surface",
                    ),
                    _selected_dataset(selected),
                ],
                className="support-primary-grid",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("Committed dataset catalog"),
                                    html.P(
                                        "Use a row's manifest details to inspect assumptions and restrictions.",
                                        className="section-description",
                                    ),
                                ]
                            ),
                            html.Span(f"{len(datasets)} records", className="surface-badge"),
                        ],
                        className="surface-heading",
                    ),
                    html.Div(_catalog_table(validated_datasets), className="support-table-scroll"),
                    html.Details(
                        [
                            html.Summary(
                                f"Inspect all {len(datasets)} manifest assumptions and restrictions"
                            ),
                            html.Div(
                                [_dataset_assumptions(item) for item in datasets],
                                className="dataset-assumption-list",
                            ),
                        ],
                        className="all-manifest-details",
                    ),
                ],
                className="support-surface",
            ),
            html.Footer(
                [
                    html.Span(f"{len(quarantined_datasets)} quarantined datasets remain provenance records and are not approved for experiments."),
                    html.Span("Fixture evidence does not authorize research conclusions or promotion."),
                    html.Span("Provider connectivity, credentials, and freshness are not checked here."),
                ],
                className="support-footer-note",
            ),
        ],
        className="page-container support-page market-data-page",
    )


def _metric(label: str, value: str, detail: str) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="metric-label"),
            html.Strong(value),
            html.Small(detail),
        ],
        className="support-metric",
    )


def _manifest_date(item: DatasetHealth, *keys: str) -> str | None:
    for key in keys:
        value = item.manifest.metadata.get(key)
        if value:
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
            except ValueError:
                continue
    return None


def _coverage_chart(datasets: tuple[DatasetHealth, ...]) -> dcc.Graph | html.Div:
    figure = go.Figure()
    plotted = 0
    for item in reversed(datasets):
        start = _manifest_date(item, "earliest_timestamp", "coverage_start")
        end = _manifest_date(item, "latest_timestamp", "latest_completed_session")
        if not start or not end:
            continue
        status = item.manifest.status
        color = "#20a37a" if status == "validated" else "#c78315"
        label = f"{item.manifest.symbol} · {item.manifest.timeframe}"
        figure.add_trace(
            go.Scatter(
                x=[start, end],
                y=[label, label],
                mode="lines+markers",
                line={"color": color, "width": 9},
                marker={"color": color, "size": 8},
                customdata=[[item.manifest.provider, status], [item.manifest.provider, status]],
                hovertemplate=(
                    "%{y}<br>%{x}<br>Provider: %{customdata[0]}"
                    "<br>Status: %{customdata[1]}<extra></extra>"
                ),
                showlegend=False,
            )
        )
        plotted += 1
    if not plotted:
        return html.Div(
            [html.Strong("Coverage dates unavailable"), html.P("No committed manifest records a parseable start and end date.")],
            className="support-empty-state",
        )
    figure.update_layout(
        height=max(260, plotted * 38 + 80),
        margin={"l": 105, "r": 24, "t": 22, "b": 42},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": "Inter, ui-sans-serif, system-ui, sans-serif", "color": "#475569", "size": 11},
        xaxis={"showgrid": True, "gridcolor": "#e7ecf2", "zeroline": False},
        yaxis={"showgrid": False, "title": None},
        hovermode="closest",
    )
    return dcc.Graph(
        figure=figure,
        config={"displayModeBar": False, "responsive": True},
        className="market-coverage-chart",
    )


def _selected_dataset(item: DatasetHealth | None) -> html.Aside:
    if item is None:
        return html.Aside(
            [html.H2("Selected dataset"), html.P("No committed dataset is available.")],
            className="support-surface selected-support-record",
        )
    return html.Aside(
        [
            html.Div(
                [html.H2("Selected dataset"), html.P("Operator-readable manifest summary.", className="section-description")],
                className="surface-heading",
            ),
            html.Div(
                [
                    html.Strong(f"{item.manifest.symbol} · {item.manifest.timeframe}"),
                    html.Small(item.manifest.dataset_id),
                ],
                className="selected-record-title",
            ),
            html.Dl(
                [
                    html.Div([html.Dt("Provider"), html.Dd(item.manifest.provider)]),
                    html.Div([html.Dt("Coverage"), html.Dd(_coverage(item))]),
                    html.Div([html.Dt("Rows"), html.Dd(f"{item.manifest.row_count:,}")]),
                    html.Div([html.Dt("Local file"), html.Dd(item.availability)]),
                    html.Div([html.Dt("Approval"), html.Dd(_approval(item))]),
                ],
                className="selected-record-facts",
            ),
            html.Div(
                [
                    html.Strong("Use restrictions"),
                    html.P(
                        str(item.manifest.metadata.get("restrictions", "No restrictions were recorded in the manifest.")),
                        className="field-help",
                    ),
                ],
                className="operator-message operator-message-warning selected-record-warning",
            ),
        ],
        className="support-surface selected-support-record",
    )


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
