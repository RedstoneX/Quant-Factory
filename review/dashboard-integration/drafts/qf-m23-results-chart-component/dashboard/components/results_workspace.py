"""Chart-first components for one persisted research run.

This module renders only data already validated by :mod:`dashboard.results_model`.
It does not read persistence, select runs, register callbacks, or mutate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

import plotly.graph_objects as go
from dash import dcc, html

from dashboard.components.operator_context import (
    OperatorContextViewModel,
    operator_context,
)
from dashboard.results_model import (
    IntervalBars,
    TradeEvent,
    TradeGrouping,
    map_event_to_bar,
)


INTERVALS: Final[tuple[str, ...]] = ("1m", "5m", "15m", "1D")
VIEWS: Final[tuple[tuple[str, str], ...]] = (
    ("Full run", "full"),
    ("1D", "1D"),
    ("1W", "1W"),
    ("1M", "1M"),
)


@dataclass(frozen=True, slots=True)
class ResultsWorkspaceViewModel:
    """Persisted identity and validated presentation data for one selected run."""

    run_id: str
    strategy: str
    instrument: str
    source_interval: str
    evidence_timezone: str
    backtest_period: str
    run_status: str
    evidence_outcome: str
    human_decision: str
    next_safe_action: str
    intervals: tuple[IntervalBars, ...]
    trades: TradeGrouping
    active_interval: str = "1m"
    active_view: str = "full"
    fixture_warning: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class PriceChart:
    """Plotly figure plus its plain-language evidence counts."""

    figure: go.Figure
    bar_count: int
    entry_marker_count: int
    exit_marker_count: int
    omitted_marker_count: int
    omission_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _MarkerPoint:
    event: TradeEvent
    bar_timestamp: datetime


def build_price_chart(
    interval_bars: IntervalBars,
    trades: TradeGrouping,
    *,
    instrument: str,
    view: str = "full",
) -> PriceChart:
    """Build a truthful candlestick figure from validated bars and trade events."""

    if not interval_bars.available:
        raise ValueError(interval_bars.reason or "The selected bars are unavailable.")
    if not interval_bars.bars:
        raise ValueError("The selected interval has no validated persisted bars.")
    if view not in {value for _, value in VIEWS}:
        raise ValueError(f"View {view!r} is not supported.")

    entries, entry_reasons = _marker_points(
        tuple(group.entry for group in trades.groups if group.entry is not None),
        interval_bars,
    )
    exits, exit_reasons = _marker_points(
        tuple(group.exit for group in trades.groups if group.exit is not None),
        interval_bars,
    )
    bars = interval_bars.bars
    figure = go.Figure(
        go.Candlestick(
            x=[bar.timestamp for bar in bars],
            open=[bar.open for bar in bars],
            high=[bar.high for bar in bars],
            low=[bar.low for bar in bars],
            close=[bar.close for bar in bars],
            name=f"{instrument} price",
            increasing_line_color="#15803d",
            decreasing_line_color="#b91c1c",
            hovertext=[
                f"{bar.source_count:,} persisted source bar"
                + ("" if bar.source_count == 1 else "s")
                for bar in bars
            ],
            hoverinfo="x+open+high+low+close+text",
        )
    )
    _add_marker_trace(figure, entries, leg="entry")
    _add_marker_trace(figure, exits, leg="exit")

    xaxis: dict[str, object] = {
        "rangeslider": {"visible": False},
        "title": f"Evidence time ({interval_bars.interval} bars)",
        "type": "date",
    }
    visible_range = _view_range(bars[0].timestamp, bars[-1].timestamp, view)
    if visible_range is not None:
        xaxis["range"] = visible_range
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 58, "r": 24, "t": 28, "b": 54},
        dragmode="pan",
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.2},
        xaxis=xaxis,
        yaxis={"title": f"{instrument} price", "tickformat": "$,.2f"},
    )
    reasons = tuple(dict.fromkeys((*entry_reasons, *exit_reasons)))
    return PriceChart(
        figure=figure,
        bar_count=len(bars),
        entry_marker_count=len(entries),
        exit_marker_count=len(exits),
        omitted_marker_count=len(entry_reasons) + len(exit_reasons),
        omission_reasons=reasons,
    )


def results_workspace(
    model: ResultsWorkspaceViewModel | None = None,
    *,
    id_prefix: str = "results-workspace",
) -> html.Section:
    """Render a compact selected-run strip and its primary chart workspace."""

    if model is None:
        return _state_panel(
            "No persisted run selected",
            "Choose a saved test to inspect its recorded price and trade evidence.",
            id_prefix=id_prefix,
            state="empty",
        )

    context = _selected_run_context(model, id_prefix=id_prefix)
    if model.error_message:
        return html.Section(
            [
                context,
                _state_panel(
                    "Price chart unavailable",
                    model.error_message,
                    id_prefix=id_prefix,
                    state="error",
                ),
            ],
            id=id_prefix,
            className="results-workspace results-workspace-error",
        )

    interval_map = {item.interval: item for item in model.intervals}
    if len(interval_map) != len(model.intervals):
        return _workspace_error(
            context,
            "Duplicate interval evidence was supplied; no chart was rendered.",
            id_prefix=id_prefix,
        )
    active = interval_map.get(model.active_interval)
    if active is None:
        return _workspace_error(
            context,
            f"No validated {model.active_interval} interval evidence was supplied.",
            id_prefix=id_prefix,
            controls=_chart_controls(model, interval_map, id_prefix=id_prefix),
        )
    if not active.available:
        return html.Section(
            [
                context,
                _chart_header(model),
                _chart_controls(model, interval_map, id_prefix=id_prefix),
                _state_panel(
                    f"{model.active_interval} bars unavailable",
                    active.reason or "The selected bars cannot be rendered truthfully.",
                    id_prefix=f"{id_prefix}-chart",
                    state="unavailable",
                ),
            ],
            id=id_prefix,
            className="results-workspace results-workspace-unavailable",
        )

    try:
        chart = build_price_chart(
            active,
            model.trades,
            instrument=model.instrument,
            view=model.active_view,
        )
    except ValueError as exc:
        return _workspace_error(
            context,
            str(exc),
            id_prefix=id_prefix,
            controls=_chart_controls(model, interval_map, id_prefix=id_prefix),
        )

    return html.Section(
        [
            context,
            _chart_header(model),
            _chart_controls(model, interval_map, id_prefix=id_prefix),
            dcc.Graph(
                id=f"{id_prefix}-price-chart",
                figure=chart.figure,
                responsive=True,
                config={"responsive": True, "scrollZoom": True},
                className="results-price-chart",
            ),
            _chart_status(chart, model, id_prefix=id_prefix),
        ],
        id=id_prefix,
        className="results-workspace",
    )


def _selected_run_context(
    model: ResultsWorkspaceViewModel, *, id_prefix: str
) -> html.Section:
    identity = " · ".join(
        value
        for value in (model.strategy, model.instrument, model.source_interval)
        if value.strip()
    )
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Selected backtest", className="section-kicker"),
                            html.H2(identity or "Persisted test"),
                            html.P(
                                f"{model.backtest_period} · {model.evidence_timezone}",
                                className="section-description",
                            ),
                        ]
                    ),
                    html.Button(
                        "Change run",
                        id=f"{id_prefix}-change-run",
                        type="button",
                        className="secondary-action",
                    ),
                ],
                className="results-selected-run-heading",
            ),
            (
                html.P(model.fixture_warning, className="fixture-warning")
                if model.fixture_warning
                else None
            ),
            operator_context(
                OperatorContextViewModel(
                    selected_run=True,
                    run_status=model.run_status,
                    evidence_outcome=model.evidence_outcome,
                    human_decision=model.human_decision,
                    next_safe_action=model.next_safe_action,
                ),
                component_id=f"{id_prefix}-operator-context",
            ),
            html.Details(
                [html.Summary("Technical run identity"), html.Code(model.run_id)],
                className="results-technical-run-identity",
            ),
        ],
        className="results-selected-run-context",
        **{"aria-label": "Selected backtest"},
    )


def _chart_header(model: ResultsWorkspaceViewModel) -> html.Header:
    return html.Header(
        [
            html.Span("Price and trades", className="section-kicker"),
            html.H2(f"{model.instrument} persisted price"),
            html.P(
                (
                    f"Evidence timezone {model.evidence_timezone}; source interval "
                    f"{model.source_interval}; immutable backtest period "
                    f"{model.backtest_period}."
                ),
                className="section-description",
            ),
        ],
        className="results-chart-heading",
    )


def _chart_controls(
    model: ResultsWorkspaceViewModel,
    interval_map: dict[str, IntervalBars],
    *,
    id_prefix: str,
) -> html.Div:
    interval_options = []
    reasons = []
    for interval in INTERVALS:
        evidence = interval_map.get(interval)
        reason = (
            "No validated interval evidence was supplied."
            if evidence is None
            else evidence.reason
        )
        available = evidence is not None and evidence.available and bool(evidence.bars)
        interval_options.append(
            {"label": interval, "value": interval, "disabled": not available}
        )
        if not available:
            reasons.append(
                html.Li(
                    f"{interval}: {reason or 'No validated persisted bars are available.'}"
                )
            )

    return html.Div(
        [
            html.Div(
                [
                    html.Strong("Bars:", id=f"{id_prefix}-bars-label"),
                    dcc.RadioItems(
                        id=f"{id_prefix}-bars",
                        options=interval_options,
                        value=model.active_interval,
                        inline=True,
                        **{"aria-labelledby": f"{id_prefix}-bars-label"},
                    ),
                ],
                className="results-chart-control",
            ),
            html.Div(
                [
                    html.Strong("View:", id=f"{id_prefix}-view-label"),
                    dcc.RadioItems(
                        id=f"{id_prefix}-view",
                        options=[
                            {"label": label, "value": value}
                            for label, value in VIEWS
                        ],
                        value=model.active_view,
                        inline=True,
                        **{"aria-labelledby": f"{id_prefix}-view-label"},
                    ),
                ],
                className="results-chart-control",
            ),
            (
                html.Ul(
                    reasons,
                    className="results-interval-reasons",
                    **{"aria-label": "Unavailable bar intervals"},
                )
                if reasons
                else None
            ),
        ],
        className="results-chart-controls",
    )


def _marker_points(
    events: tuple[TradeEvent, ...], interval_bars: IntervalBars
) -> tuple[tuple[_MarkerPoint, ...], tuple[str, ...]]:
    points: list[_MarkerPoint] = []
    reasons: list[str] = []
    for event in events:
        mapping = map_event_to_bar(event, interval_bars)
        if mapping.available and mapping.bar_timestamp is not None:
            points.append(_MarkerPoint(event=event, bar_timestamp=mapping.bar_timestamp))
        else:
            reasons.append(
                f"Trade {event.trade_id} {event.leg}: "
                f"{mapping.reason or 'Marker unavailable.'}"
            )
    return tuple(points), tuple(reasons)


def _add_marker_trace(
    figure: go.Figure, points: tuple[_MarkerPoint, ...], *, leg: str
) -> None:
    if not points:
        return
    is_entry = leg == "entry"
    figure.add_trace(
        go.Scattergl(
            x=[point.bar_timestamp for point in points],
            y=[point.event.price for point in points],
            mode="markers",
            marker={
                "symbol": "triangle-up" if is_entry else "triangle-down",
                "size": 11,
                "color": "#15803d" if is_entry else "#b91c1c",
                "line": {
                    "color": "#052e16" if is_entry else "#450a0a",
                    "width": 1,
                },
            },
            customdata=[
                [
                    point.event.trade_id,
                    point.event.timestamp.isoformat(),
                    point.bar_timestamp.isoformat(),
                    point.event.leg,
                ]
                for point in points
            ],
            name="Trade entries" if is_entry else "Trade exits",
            hovertemplate=(
                "Trade %{customdata[0]} "
                + leg
                + "<br>Exact event %{customdata[1]}"
                "<br>Containing bar %{customdata[2]}"
                "<br>Persisted price %{y:$,.2f}<extra></extra>"
            ),
        )
    )


def _view_range(
    first_timestamp: datetime, last_timestamp: datetime, view: str
) -> tuple[datetime, datetime] | None:
    if view == "full":
        return None
    duration = {
        "1D": timedelta(days=1),
        "1W": timedelta(days=7),
        "1M": timedelta(days=30),
    }[view]
    return max(first_timestamp, last_timestamp - duration), last_timestamp


def _chart_status(
    chart: PriceChart, model: ResultsWorkspaceViewModel, *, id_prefix: str
) -> html.Div:
    marker_count = chart.entry_marker_count + chart.exit_marker_count
    summary = (
        f"Showing {chart.bar_count:,} {model.active_interval} bars for "
        f"{_view_label(model.active_view)}, with {chart.entry_marker_count:,} entry "
        f"and {chart.exit_marker_count:,} exit markers."
    )
    children: list[object] = [html.P(summary)]
    if chart.omitted_marker_count:
        children.extend(
            [
                html.P(
                    f"{chart.omitted_marker_count:,} persisted trade event"
                    + (" was" if chart.omitted_marker_count == 1 else "s were")
                    + " not shown because no truthful containing bar was available."
                ),
                html.Details(
                    [
                        html.Summary("Unavailable marker details"),
                        html.Ul([html.Li(reason) for reason in chart.omission_reasons]),
                    ]
                ),
            ]
        )
    if marker_count == 0 and not chart.omitted_marker_count:
        children.append(html.P("No persisted entry or exit events are recorded."))
    children.append(
        html.P(
            "Bars and View affect presentation only; the selected run and its "
            "immutable backtest period do not change.",
            className="empty-state-note",
        )
    )
    return html.Div(
        children,
        id=f"{id_prefix}-chart-status",
        className="results-chart-status",
        role="status",
        **{"aria-live": "polite", "aria-atomic": "true"},
    )


def _view_label(value: str) -> str:
    return next(label for label, option_value in VIEWS if option_value == value)


def _state_panel(
    title: str,
    message: str,
    *,
    id_prefix: str,
    state: str,
) -> html.Section:
    attributes = {"aria-live": "polite"}
    if state == "error":
        attributes["role"] = "alert"
    return html.Section(
        [html.H2(title), html.P(message)],
        id=f"{id_prefix}-{state}-state",
        className=f"results-workspace-state results-workspace-{state}-state",
        **attributes,
    )


def _workspace_error(
    context: html.Section,
    message: str,
    *,
    id_prefix: str,
    controls: html.Div | None = None,
) -> html.Section:
    return html.Section(
        [
            context,
            controls,
            _state_panel(
                "Price chart unavailable",
                message,
                id_prefix=f"{id_prefix}-chart",
                state="error",
            ),
        ],
        id=id_prefix,
        className="results-workspace results-workspace-error",
    )


__all__ = [
    "INTERVALS",
    "VIEWS",
    "PriceChart",
    "ResultsWorkspaceViewModel",
    "build_price_chart",
    "results_workspace",
]
