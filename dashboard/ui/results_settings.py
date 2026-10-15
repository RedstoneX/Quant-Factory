"""Results page settings table columns and settings heatmap, built from each run's own recorded parameters."""

from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
import pandas as pd
import plotly.express as px
from dash import Input, Output, State, dcc

from dashboard.time_display import eastern_label

METRICS = {
    "sharpe_ratio": "Sharpe",
    "total_return": "Net return %",
    "annualized_return": "Annualised return %",
    "max_drawdown": "Biggest drop %",
    "win_rate": "Win rate %",
    "number_of_trades": "Trades",
}
_CENTRED = {"headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}}


def _label(name: str) -> str:
    return name.replace("_", " ").capitalize()


def parameter_names(rows: list[dict[str, Any]]) -> list[str]:
    """Parameter names in first-seen order across every recorded row."""
    return list(dict.fromkeys(name for row in rows for name in (row.get("parameters") or {})))


def settings_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Grid columns, one per recorded parameter name."""
    return [{"field": f"parameters.{n}", "headerName": _label(n), "minWidth": 50, "flex": 1, **_CENTRED} for n in parameter_names(rows)]


def _value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return eastern_label(value) if "T" in value else value.replace("_", " ").capitalize()
        except ValueError:
            return value.replace("_", " ").capitalize()
    return value


def display_settings_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy rows with parameter values formatted for people (times in Eastern, words capitalised)."""
    return [{**row, "parameters": {k: _value(v) for k, v in (row.get("parameters") or {}).items()}} for row in rows]


def settings_identity(parameters: dict[str, Any]) -> str:
    """One-line description of a setting from its own recorded parameters."""
    shown = [f"{_label(k)} {_value(v)}" for k, v in (parameters or {}).items()]
    return " · ".join(shown) or "Exact saved settings"


def varying_parameters(rows: list[dict[str, Any]]) -> list[str]:
    """Parameter names with more than one distinct value, most distinct values first."""
    counts = {n: len({str((r.get("parameters") or {}).get(n)) for r in rows}) for n in parameter_names(rows)}
    return sorted((n for n, c in counts.items() if c > 1), key=lambda n: -counts[n])


def heatmap_figure(rows: list[dict[str, Any]], x: str, y: str, metric: str):
    """Plotly heatmap of the metric over two parameters, averaging over any others."""
    data = pd.DataFrame({
        x: [(r.get("parameters") or {}).get(x) for r in rows],
        y: [(r.get("parameters") or {}).get(y) for r in rows],
        "value": [r.get(metric) for r in rows],
    }).dropna()
    series = data.groupby([x, y])["value"].mean()
    figure = px.imshow(series.unstack(x), origin="lower", aspect="auto", template="qf")
    figure.update_traces(texttemplate="%{z:.2f}", colorbar={"thickness": 10, "len": 0.9, "x": 1.02, "xpad": 0})
    figure.update_xaxes(type="category", title_text=_label(x), side="bottom")
    figure.update_yaxes(type="category", title_text=_label(y), side="left")
    figure.update_layout(autosize=True, width=None, height=340, margin={"l": 60, "r": 16, "t": 18, "b": 48})
    return figure


def settings_heatmap_layout() -> dmc.Paper:
    size = {"size": "xs", "allowDeselect": False}
    controls = dmc.Group([
        dmc.Select(id="results-heat-metric", data=[{"value": k, "label": v} for k, v in METRICS.items()], value="sharpe_ratio", w=170, **size),
        dmc.Select(id="results-heat-x", data=[], w=170, **size),
        dmc.Select(id="results-heat-y", data=[], w=170, **size),
    ], gap="xs", wrap="wrap")
    return dmc.Paper(dmc.Stack([
        dmc.Title("Settings heatmap", order=5), controls,
        dcc.Graph(id="results-heat-graph", config={"displayModeBar": False, "responsive": True}),
    ], gap="sm"), id="results-heat-panel", p="md", style={"display": "none"})


def register_settings_callbacks(application: Any) -> None:
    @application.callback(
        Output("results-heat-x", "data"), Output("results-heat-y", "data"),
        Output("results-heat-x", "value"), Output("results-heat-y", "value"),
        Output("results-heat-panel", "style"),
        Input("results-record", "data"),
    )
    def choose_parameters(record: dict[str, Any] | None):
        rows = (record or {}).get("screening_rows") or []
        names = varying_parameters(rows)
        if len(names) < 2:
            return [], [], None, None, {"display": "none"}
        data = [{"value": n, "label": _label(n)} for n in names]
        return data, data, names[0], names[1], {}

    @application.callback(
        Output("results-heat-graph", "figure"),
        Input("results-heat-metric", "value"), Input("results-heat-x", "value"), Input("results-heat-y", "value"),
        State("results-record", "data"),
    )
    def render_heatmap(metric: str | None, x: str | None, y: str | None, record: dict[str, Any] | None):
        rows = (record or {}).get("screening_rows") or []
        if not x or not y or x == y or metric not in METRICS:
            return {}
        return heatmap_figure(rows, x, y, metric)
