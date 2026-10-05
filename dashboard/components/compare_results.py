"""Approved compact rendering for the immutable persisted-run Compare read model."""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlencode

import numpy as np
import plotly.graph_objects as go
from tsdownsample import MinMaxLTTBDownsampler
from dash import dcc, html

from dashboard.compare_adapter import (
    CompareDifferenceField,
    CompareDifferenceGroup,
    CompareRunIdentity,
    CompareSeries,
    CompareSeriesPoint,
    CompareViewModel,
)


def compare_results(model: CompareViewModel) -> html.Div:
    """Render the approved Compare workspace from persisted evidence only."""

    return html.Div(
        [
            _selected_runs(model.runs),
            _comparability(model),
            _run_contexts(model.runs),
            html.Div(
                [
                    html.Section(
                        [_equity_panel(model), _metric_table(model)],
                        className="compare-performance-panel",
                    ),
                    _material_differences(model.difference_groups, model.runs),
                ],
                className="compare-workspace",
            ),
        ],
        id="comparison-read-model",
        className="compare-read-model",
        **{"data-directly-comparable": str(model.directly_comparable).lower()},
    )


def compare_loading(run_ids: Sequence[str]) -> html.Section:
    """Keep requested identities explicit while persisted evidence is read."""

    selected = tuple(str(run_id) for run_id in run_ids)
    return html.Section(
        [
            html.H2("Loading comparison"),
            html.P("Reading persisted evidence only. No test will run or change."),
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
                "Select at least two saved tests, up to four. Comparison reads recorded evidence; "
                "it never runs or changes a test."
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
                "persisted evidence; nothing will run or change."
            ),
            _requested_identity_list(selected),
            html.Details(
                [html.Summary("Problem details"), html.P(diagnostic)],
                className="compare-run-details",
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
        **{"aria-label": "Requested tests"},
    )


def _selected_runs(runs: tuple[CompareRunIdentity, ...]) -> html.Section:
    chips: list[object] = []
    for index, run in enumerate(runs):
        remaining = [item.run_id for item in runs if item.run_id != run.run_id]
        href = "/research/compare-backtests"
        if len(remaining) >= 2:
            href += "?" + urlencode([("run_id", run_id) for run_id in remaining])
        chips.append(
            html.Article(
                [
                    html.Div(
                        [
                            html.Strong(run.strategy),
                            html.Span(
                                " · ".join(
                                    value
                                    for value in (run.instrument, run.timeframe, _period(run))
                                    if value and value != "Unavailable"
                                )
                                or run.run_id
                            ),
                        ]
                    ),
                    dcc.Link(
                        "×",
                        href=href,
                        className="compare-remove-run",
                        title=f"Remove {run.strategy} from the comparison",
                    ),
                ],
                className=f"compare-run-chip compare-run-chip-{(index % 4) + 1}",
                **{"data-run-id": run.run_id},
            )
        )
    chips.append(
        dcc.Link(
            "Find runs",
            href="/research/compare-backtests#compare-run-finder",
            className="secondary-action compare-find-runs",
        )
    )
    return html.Section(chips, className="compare-selected-runs", **{"aria-label": "Selected runs"})


def _comparability(model: CompareViewModel) -> html.Section:
    details = (
        " ".join(finding.message for finding in model.findings)
        if model.findings
        else "No persisted-basis incompatibilities were found."
    )
    heading = (
        "Comparable on the recorded basis"
        if model.directly_comparable
        else "Comparison requires caution"
    )
    return html.Section(
        [html.Strong(heading), html.P(details)],
        id="comparison-findings",
        className=(
            "compare-comparability compare-comparability-supported"
            if model.directly_comparable
            else "compare-comparability compare-comparability-blocked"
        ),
        **{"aria-live": "polite"},
    )


def _run_contexts(runs: tuple[CompareRunIdentity, ...]) -> html.Section:
    return html.Section(
        [_run_context(run, index) for index, run in enumerate(runs)],
        className="compare-run-contexts",
        **{"aria-label": "Selected run contexts"},
    )


def _run_context(run: CompareRunIdentity, index: int) -> html.Article:
    return html.Article(
        [
            html.Header(
                [
                    html.Span(
                        run.strategy,
                        className=(
                            f"compare-series-label compare-series-{(index % 4) + 1}"
                        ),
                    ),
                    dcc.Link("Open Results", href=run.results_href),
                ]
            ),
            html.Dl(
                [
                    _context_item("Run status", run.run_status),
                    _context_item("Evidence outcome", run.evidence_outcome),
                    _context_item("Human decision", run.human_review),
                    _context_item("Next safe action", _next_safe_action(run)),
                ],
                className="compare-context-quartet",
            ),
            _evidence_gaps(run),
        ],
        className=(
            "compare-run-context"
            if run.available and not run.errors
            else "compare-run-context compare-run-context-problem"
        ),
        **{"data-run-id": run.run_id},
    )


def _context_item(label: str, value: str) -> html.Div:
    return html.Div([html.Dt(label), html.Dd(value)])


def _period(run: CompareRunIdentity) -> str:
    return run.actual_period if run.actual_period != "Unavailable" else run.requested_period


def _next_safe_action(run: CompareRunIdentity) -> str:
    status = run.run_status.lower().replace(" ", "_")
    if status in {"created", "queued", "running", "retrying"}:
        return "Wait for completion"
    if status in {"failed", "cancelled", "timed_out"}:
        return "Review failure"
    if status == "succeeded" and run.human_review == "Unreviewed":
        return "Record decision"
    if status == "succeeded" and run.human_review not in {"", "Unavailable"}:
        return "None"
    return "Inspect evidence"


def _evidence_gaps(run: CompareRunIdentity) -> html.Details | None:
    messages = (*run.omissions, *run.errors)
    if not messages:
        return None
    return html.Details(
        [html.Summary("Unavailable evidence"), html.Ul([html.Li(message) for message in messages])],
        className="compare-run-details",
    )


def _equity_panel(model: CompareViewModel) -> html.Div:
    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.H2("Normalized equity comparison"),
                            html.P(
                                "Each persisted curve is rebased to 100 at its own start; "
                                "missing points are never inferred."
                            ),
                        ]
                    ),
                    _legend(model.equity_series),
                ],
                className="compare-panel-heading",
            ),
            _equity_chart(model.equity_series),
        ],
        className="compare-equity-block",
    )


def _legend(series_items: tuple[CompareSeries, ...]) -> html.Div:
    return html.Div(
        [
            html.Span(
                [
                    html.I(
                        className=f"compare-swatch compare-swatch-{(index % 4) + 1}"
                    ),
                    series.label,
                ],
                className="compare-legend-item",
            )
            for index, series in enumerate(series_items)
        ],
        className="compare-legend",
    )


def _equity_chart(series_items: tuple[CompareSeries, ...]) -> html.Div:
    supported = tuple(series for series in series_items if series.points)
    missing = tuple(series for series in series_items if not series.points)
    children: list[object] = []
    if supported:
        figure = go.Figure()
        colors = ("#316ff4", "#7a55d9", "#0b9f76", "#b66b00")
        for index, series in enumerate(supported):
            displayed_points = _display_points(series.points)
            figure.add_trace(
                go.Scatter(
                    x=[point.timestamp for point in displayed_points],
                    y=[point.value for point in displayed_points],
                    mode="lines",
                    name=f"{series.label} · {series.run_id}",
                    line={"color": colors[index % len(colors)], "width": 2.5},
                    connectgaps=False,
                    hovertemplate="%{x}<br>%{y:.2f}<extra>%{fullData.name}</extra>",
                )
            )
        figure.update_layout(
            template="plotly_white",
            height=300,
            margin={"l": 52, "r": 20, "t": 20, "b": 45},
            hovermode="x unified",
            showlegend=False,
            xaxis_title="Persisted observation time",
            yaxis_title="Indexed value (start = 100)",
            autosize=True,
        )
        children.append(
            dcc.Graph(
                id="comparison-equity-chart",
                figure=figure,
                responsive=True,
                config={"displayModeBar": False, "responsive": True},
                className="compare-equity-chart",
            )
        )
    else:
        children.append(
            html.P(
                "No validated persisted equity series is available.",
                className="compare-chart-empty",
            )
        )
    if missing:
        children.append(
            html.Ul(
                [
                    html.Li(
                        f"{series.run_id}: {series.omission or 'Series unavailable.'}"
                    )
                    for series in missing
                ],
                className="compare-series-omissions",
                **{"aria-label": "Normalized equity omissions"},
            )
        )
    return html.Div(children, className="compare-chart-wrap")


_MAX_COMPARE_CHART_POINTS = 1_500


def _display_points(
    points: Sequence[CompareSeriesPoint],
    *,
    max_points: int = _MAX_COMPARE_CHART_POINTS,
) -> tuple[CompareSeriesPoint, ...]:
    """Bound browser chart geometry while preserving the immutable read model."""

    if len(points) <= max_points:
        return tuple(points)
    values = np.asarray([point.value for point in points], dtype=np.float64)
    selected = MinMaxLTTBDownsampler().downsample(values, n_out=max_points)
    return tuple(points[int(index)] for index in selected)


def _metric_table(model: CompareViewModel) -> html.Div:
    headers: list[object] = [html.Th("Metric", scope="col")]
    headers.extend(html.Th(f"Test {run.position}", scope="col") for run in model.runs)
    headers.append(html.Th("Basis", scope="col"))
    rows = []
    for metric in model.metric_rows:
        basis = metric.basis_warning or " · ".join(
            dict.fromkeys(value.basis for value in metric.values)
        )
        rows.append(
            html.Tr(
                [
                    html.Th(metric.label, scope="row"),
                    *[
                        html.Td(
                            [
                                html.Strong(value.display_value),
                                html.Small(
                                    value.omission,
                                    className="comparison-omission",
                                )
                                if value.omission
                                else None,
                            ]
                        )
                        for value in metric.values
                    ],
                    html.Td(basis, className="compare-metric-basis"),
                ],
                className=f"comparison-row comparison-row-{metric.state}",
            )
        )
    return html.Div(
        [
            html.Header(
                [
                    html.H3("Aligned persisted metrics"),
                    html.P("Values retain their recorded basis."),
                ],
                className="compare-panel-heading",
            ),
            html.Div(
                html.Table(
                    [html.Thead(html.Tr(headers)), html.Tbody(rows)],
                    className="compare-metric-table",
                    **{"aria-label": "Aligned persisted metrics"},
                ),
                className="compare-table-scroll",
            ),
        ],
        className="compare-metrics-block",
    )


def _material_differences(
    groups: tuple[CompareDifferenceGroup, ...],
    runs: tuple[CompareRunIdentity, ...],
) -> html.Aside:
    group_map = {group.key: group for group in groups}
    sections = (
        ("Market & sample", (group_map.get("data"),)),
        ("Signal & timing", (group_map.get("parameters"),)),
        ("Execution & costs", (group_map.get("execution"),)),
        ("Evidence & review", (group_map.get("evidence"), group_map.get("review"))),
    )
    return html.Aside(
        [
            html.Header(
                [
                    html.H2("Material differences"),
                    html.P("Only differences that change interpretation."),
                ],
                className="compare-panel-heading",
            ),
            *[_difference_section(label, source_groups, runs) for label, source_groups in sections],
        ],
        className="compare-differences-panel",
    )


def _difference_section(
    label: str,
    groups: tuple[CompareDifferenceGroup | None, ...],
    runs: tuple[CompareRunIdentity, ...],
) -> html.Section:
    fields: list[CompareDifferenceField] = []
    for group in groups:
        if group is not None:
            fields.extend(field for field in group.fields if field.state != "equal")
    bounded_fields = fields[:5]
    body: list[object]
    if not bounded_fields:
        body = [html.P("No material difference recorded.", className="compare-difference-empty")]
    else:
        body = [_difference_row(field, runs) for field in bounded_fields]
    return html.Section(
        [html.H3(label), *body],
        className="compare-difference-section",
        **{"data-difference-group": label.lower().replace(" & ", "-").replace(" ", "-")},
    )


def _difference_row(
    field: CompareDifferenceField,
    runs: tuple[CompareRunIdentity, ...],
) -> html.Div:
    values: list[object] = [html.Span(field.label)]
    for run, value in zip(runs, field.values, strict=False):
        values.append(
            html.Strong(
                [value.value, html.Small(value.omission) if value.omission else None],
                title=f"Test {run.position}",
            )
        )
    return html.Div(
        values,
        className=f"compare-difference-row comparison-row-{field.state}",
        style={"gridTemplateColumns": f"76px repeat({len(runs)}, minmax(0, 1fr))"},
    )


__all__ = ["compare_empty", "compare_failure", "compare_loading", "compare_results"]
