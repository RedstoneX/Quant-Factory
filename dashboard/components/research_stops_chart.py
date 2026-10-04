"""Compact Plotly renderer for the Research Atlas stop-reason panel."""

from __future__ import annotations

import math
from collections.abc import Mapping

import plotly.graph_objects as go


def research_stops_figure(counts: Mapping[str, int]) -> go.Figure:
    """Render persisted stop reasons with legible bounded integer ticks."""

    figure = go.Figure()
    figure.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, ui-sans-serif, system-ui, sans-serif", "color": "#526173", "size": 11},
        margin={"l": 112, "r": 20, "t": 10, "b": 30},
        hoverlabel={"bgcolor": "#172237", "font": {"color": "#f8fafc"}},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    if not counts:
        figure.add_annotation(
            text="No failed evidence gates are recorded yet.", x=0.5, y=0.5,
            xref="paper", yref="paper", showarrow=False,
            font={"size": 13, "color": "#7a8798"}, align="center",
        )
        figure.update_xaxes(visible=False)
        figure.update_yaxes(visible=False)
        return figure
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    largest = max(counts.values())
    step = max(1, math.ceil(largest / 5))
    figure.add_trace(
        go.Bar(
            x=[count for _, count in ordered][::-1],
            y=[label for label, _ in ordered][::-1],
            orientation="h",
            marker={"color": "#ff8787", "line": {"color": "#fa5252", "width": 1}},
            text=[str(count) for _, count in ordered][::-1],
            textposition="outside",
            hovertemplate="%{y}: %{x} failed gate(s)<extra></extra>",
        )
    )
    figure.update_xaxes(
        gridcolor="#e9eef5", zeroline=False, linecolor="#cfd8e6",
        tickmode="array", tickvals=list(range(0, largest + step, step)),
        range=[0, largest + max(1, step * 0.45)], title="Failed gates",
    )
    figure.update_yaxes(gridcolor="#e9eef5", zeroline=False, linecolor="#cfd8e6", title=None)
    return figure
