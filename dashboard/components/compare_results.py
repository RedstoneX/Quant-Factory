"""Accessible rendering for the immutable persisted-run Compare read model."""

from __future__ import annotations

from collections.abc import Sequence

import plotly.graph_objects as go
from dash import dcc, html

from dashboard.compare_adapter import (
    CompareDifferenceGroup,
    CompareRunIdentity,
    CompareSeries,
    CompareViewModel,
)
from dashboard.components.operator_context import (
    OperatorContextViewModel,
    operator_context,
)


def compare_results(model: CompareViewModel) -> html.Div:
    """Render every requested run and only its validated persisted evidence."""

    return html.Div(
        [
            _run_cards(model.runs),
            _findings(model),
            _chart_section(model),
            _metric_section(model),
            _difference_sections(model.difference_groups, model.runs),
        ],
        id="comparison-read-model",
        className=(
            "compare-read-model compare-read-model-comparable"
            if model.directly_comparable
            else "compare-read-model compare-read-model-blocked"
        ),
        **{"data-directly-comparable": str(model.directly_comparable).lower()},
    )


def compare_loading(run_ids: Sequence[str]) -> html.Section:
    """Keep requested identities explicit before the first persisted read completes."""

    selected = tuple(str(run_id) for run_id in run_ids)
    return html.Section(
        [
            html.H2("Loading comparison"),
            html.P(
                "Reading persisted evidence only. No test will run or change.",
                className="section-description",
            ),
            _requested_identity_list(selected),
        ],
        className="comparison-state-panel comparison-loading-state",
        **{"aria-live": "polite", "aria-busy": "true"},
    )


def compare_empty() -> html.Section:
    """Explain the safe next action when no persisted run is selected."""

    return html.Section(
        [
            html.H2("Choose persisted tests to compare"),
            html.P(
                "Select at least two saved tests. Adding a test reads its recorded "
                "evidence; it does not run or reproduce anything.",
            ),
        ],
        className="comparison-state-panel comparison-empty-state",
        **{"aria-live": "polite"},
    )


def compare_failure(run_ids: Sequence[str], diagnostic: str) -> html.Section:
    """Retain requested identities and provide a read-only retry path."""

    selected = tuple(str(run_id) for run_id in run_ids)
    return html.Section(
        [
            html.H2("Comparison could not be read"),
            html.P(
                "The selected tests are unchanged. Choose Refresh to retry reading "
                "their persisted evidence; nothing will be run or changed.",
            ),
            _requested_identity_list(selected),
            html.Details(
                [
                    html.Summary("Problem details"),
                    html.P(diagnostic, className="comparison-diagnostic"),
                ]
            ),
        ],
        className="comparison-state-panel comparison-failure-state",
        role="alert",
    )


def _requested_identity_list(run_ids: tuple[str, ...]) -> html.Ul | html.P:
    if not run_ids:
        return html.P("No tests are selected.")
    return html.Ul(
        [html.Li(run_id, className="comparison-trace-id") for run_id in run_ids],
        className="comparison-requested-identities",
        **{"aria-label": "Requested tests"},
    )


def _run_cards(runs: tuple[CompareRunIdentity, ...]) -> html.Section:
    return html.Section(
        [
            html.Div(
                [
                    html.Span("Selected tests", className="section-kicker"),
                    html.H2("Persisted run context"),
                    html.P(
                        "Each test keeps its own status, evidence outcome, human "
                        "decision, and next safe action.",
                        className="section-description",
                    ),
                ],
                className="section-heading-row",
            ),
            html.Div(
                [_run_card(run) for run in runs],
                className="compare-run-grid",
            ),
        ],
        className="compare-section compare-run-contexts",
        **{"aria-label": "Selected test contexts"},
    )


def _run_card(run: CompareRunIdentity) -> html.Article:
    period = _period(run)
    primary_problem = None
    if not run.available:
        primary_problem = "This persisted test is unavailable."
    elif run.errors:
        primary_problem = "Some persisted evidence is invalid or unreadable."
    elif run.omissions:
        primary_problem = "Some persisted evidence is unavailable."

    return html.Article(
        [
            html.Header(
                [
                    html.Span(f"Test {run.position}", className="metric-label"),
                    html.H3(run.strategy),
                    html.Code(run.run_id, className="comparison-trace-id"),
                ]
            ),
            html.Dl(
                [
                    _identity_item("Instrument", run.instrument),
                    _identity_item("Timeframe", run.timeframe),
                    _identity_item("Data period", period),
                ],
                className="compare-identity-grid",
            ),
            operator_context(
                OperatorContextViewModel(
                    selected_run=True,
                    run_status=run.run_status,
                    evidence_outcome=run.evidence_outcome,
                    human_decision=run.human_review,
                    next_safe_action=_next_safe_action(run),
                ),
                component_id=f"compare-operator-context-{run.position}",
            ),
            (
                html.P(primary_problem, className="compare-run-impact")
                if primary_problem
                else None
            ),
            _omission_details(run),
            dcc.Link(
                "Open full Results",
                href=run.results_href,
                className="secondary-action compare-results-link",
                title=f"Open the full persisted Results page for {run.run_id}",
            ),
        ],
        className=(
            "compare-run-card"
            if run.available and not run.errors
            else "compare-run-card compare-run-card-problem"
        ),
        **{"data-run-id": run.run_id},
    )


def _identity_item(label: str, value: str) -> html.Div:
    return html.Div([html.Dt(label), html.Dd(value)])


def _period(run: CompareRunIdentity) -> str:
    if run.actual_period != "Unavailable":
        return run.actual_period
    return run.requested_period


def _next_safe_action(run: CompareRunIdentity) -> str:
    status = run.run_status.lower().replace(" ", "_")
    if status in {"created", "queued", "running", "retrying"}:
        return "Wait for completion"
    if status in {"failed", "cancelled", "timed_out"}:
        return "Review failure"
    if status == "succeeded":
        if run.human_review == "Unreviewed":
            return "Record decision"
        if run.human_review in {"", "Unavailable"}:
            return "Inspect evidence"
        return "No action available"
    return "No action available"


def _omission_details(run: CompareRunIdentity) -> html.Details | None:
    if not run.errors and not run.omissions:
        return None
    children: list[object] = [html.Summary("Unavailable evidence and problem details")]
    if run.omissions:
        children.extend(
            [
                html.Strong("Unavailable"),
                html.Ul([html.Li(message) for message in run.omissions]),
            ]
        )
    if run.errors:
        children.extend(
            [
                html.Strong("Problem details"),
                html.Ul([html.Li(message) for message in run.errors]),
            ]
        )
    return html.Details(children, className="compare-run-details")


def _findings(model: CompareViewModel) -> html.Section:
    status = (
        "Direct comparison is supported"
        if model.directly_comparable
        else "Direct comparison is blocked"
    )
    findings = (
        html.Ul(
            [
                html.Li(
                    [
                        html.Strong(f"{finding.severity.title()}: "),
                        finding.message,
                    ],
                    className=f"compare-finding compare-finding-{finding.severity}",
                    **{"data-finding-code": finding.code},
                )
                for finding in model.findings
            ],
            className="compare-finding-list",
        )
        if model.findings
        else html.P("No persisted-basis incompatibilities were found.")
    )
    return html.Section(
        [
            html.Span("Comparability", className="section-kicker"),
            html.H2("Can these tests be compared?"),
            html.P(status, className="compare-comparability-status"),
            findings,
        ],
        id="comparison-findings",
        className=(
            "compare-section compare-findings-supported"
            if model.directly_comparable
            else "compare-section compare-findings-blocked"
        ),
        **{"aria-live": "polite"},
    )


def _chart_section(model: CompareViewModel) -> html.Section:
    copy = (
        "Aligned normalized series use only validated persisted observations."
        if model.directly_comparable
        else "Comparison is blocked. Supported series remain visible for separate "
        "inspection and must not be interpreted as directly comparable."
    )
    return html.Section(
        [
            html.Span("Charts", className="section-kicker"),
            html.H2("Normalized performance and drawdown"),
            html.P(copy, className="section-description"),
            html.Div(
                [
                    _series_panel(
                        "Normalized equity",
                        "Indexed value (start = 100)",
                        model.equity_series,
                        "comparison-equity-chart",
                        percent=False,
                    ),
                    _series_panel(
                        "Drawdown",
                        "Drawdown from running peak",
                        model.drawdown_series,
                        "comparison-drawdown-chart",
                        percent=True,
                    ),
                ],
                className="compare-chart-grid",
            ),
        ],
        className="compare-section compare-chart-section",
    )


def _series_panel(
    title: str,
    yaxis_title: str,
    series_items: tuple[CompareSeries, ...],
    component_id: str,
    *,
    percent: bool,
) -> html.Article:
    supported = tuple(series for series in series_items if series.points)
    missing = tuple(series for series in series_items if not series.points)
    body: list[object] = [html.H3(title)]
    if supported:
        figure = go.Figure()
        for series in supported:
            figure.add_trace(
                go.Scatter(
                    x=[point.timestamp for point in series.points],
                    y=[point.value for point in series.points],
                    mode="lines",
                    name=f"{series.label} · {series.run_id}",
                    connectgaps=False,
                    hovertemplate=(
                        "%{x}<br>%{y:.2%}<extra>%{fullData.name}</extra>"
                        if percent
                        else "%{x}<br>%{y:.2f}<extra>%{fullData.name}</extra>"
                    ),
                )
            )
        figure.update_layout(
            template="plotly_white",
            margin={"l": 58, "r": 24, "t": 28, "b": 54},
            hovermode="x unified",
            legend={"orientation": "h", "y": -0.22},
            xaxis_title="Persisted observation time",
            yaxis_title=yaxis_title,
            yaxis={"tickformat": ".1%"} if percent else {},
            autosize=True,
        )
        body.append(
            dcc.Graph(
                id=component_id,
                figure=figure,
                responsive=True,
                config={"displayModeBar": False, "responsive": True},
                className="compare-chart",
            )
        )
    else:
        body.append(
            html.P(
                "No validated persisted series is available. No points were reconstructed.",
                className="compare-chart-empty",
            )
        )
    if missing:
        body.append(
            html.Ul(
                [
                    html.Li(
                        f"{series.run_id}: {series.omission or 'Series unavailable.'}"
                    )
                    for series in missing
                ],
                className="compare-series-omissions",
                **{"aria-label": f"{title} omissions"},
            )
        )
    return html.Article(body, className="compare-chart-card")


def _metric_section(model: CompareViewModel) -> html.Section:
    headers = [html.Th("Metric", scope="col"), html.Th("State", scope="col")]
    headers.extend(
        html.Th(
            [html.Span(f"Test {run.position}"), html.Code(run.run_id)],
            scope="col",
        )
        for run in model.runs
    )
    rows = []
    for metric in model.metric_rows:
        values = []
        for value in metric.values:
            values.append(
                html.Td(
                    [
                        html.Strong(value.display_value),
                        html.Small(f"Basis: {value.basis}"),
                        (
                            html.Small(value.omission, className="comparison-omission")
                            if value.omission
                            else None
                        ),
                    ]
                )
            )
        rows.append(
            html.Tr(
                [
                    html.Th(metric.label, scope="row"),
                    html.Td(metric.state.title()),
                    *values,
                ],
                className=f"comparison-row comparison-row-{metric.state}",
                title=metric.basis_warning,
            )
        )
    return html.Section(
        [
            html.Span("Metrics", className="section-kicker"),
            html.H2("Aligned headline metrics"),
            html.P(
                "Every value keeps its persisted metric basis. Missing values remain unavailable.",
                className="section-description",
            ),
            html.Div(
                html.Table(
                    [
                        html.Caption("Persisted headline metric comparison"),
                        html.Thead(html.Tr(headers)),
                        html.Tbody(rows),
                    ],
                    className="compare-table compare-metric-table",
                ),
                className="compare-table-scroll",
            ),
        ],
        className="compare-section compare-metric-section",
    )


def _difference_sections(
    groups: tuple[CompareDifferenceGroup, ...],
    runs: tuple[CompareRunIdentity, ...],
) -> html.Section:
    return html.Section(
        [
            html.Span("Differences", className="section-kicker"),
            html.H2("What changed between tests?"),
            html.P(
                "Equal, changed, and missing values are labelled in text.",
                className="section-description",
            ),
            *[_difference_group(group, runs) for group in groups],
        ],
        className="compare-section compare-difference-section",
    )


def _difference_group(
    group: CompareDifferenceGroup,
    runs: tuple[CompareRunIdentity, ...],
) -> html.Article:
    if not group.fields:
        body: object = html.P("No persisted values are available for this group.")
    else:
        headers = [html.Th("Field", scope="col"), html.Th("State", scope="col")]
        headers.extend(
            html.Th(
                [html.Span(f"Test {run.position}"), html.Code(run.run_id)],
                scope="col",
            )
            for run in runs
        )
        rows = []
        for field in group.fields:
            values = [
                html.Td(
                    [
                        html.Span(value.value),
                        (
                            html.Small(
                                value.omission,
                                className="comparison-omission",
                            )
                            if value.omission
                            else None
                        ),
                    ]
                )
                for value in field.values
            ]
            rows.append(
                html.Tr(
                    [
                        html.Th(field.label, scope="row"),
                        html.Td(field.state.title()),
                        *values,
                    ],
                    className=f"comparison-row comparison-row-{field.state}",
                )
            )
        body = html.Div(
            html.Table(
                [
                    html.Caption(f"{group.label} comparison"),
                    html.Thead(html.Tr(headers)),
                    html.Tbody(rows),
                ],
                className="compare-table",
            ),
            className="compare-table-scroll",
        )
    return html.Article(
        [html.H3(group.label), body],
        className="compare-difference-group",
        **{"data-difference-group": group.key},
    )


__all__ = [
    "compare_empty",
    "compare_failure",
    "compare_loading",
    "compare_results",
]
