"""Production Compare Selected survivor workspace."""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, dcc, html
import plotly.graph_objects as go

from dash_iconify import DashIconify

from dashboard.compare_projection import comparison_series, load_compare_records
from dashboard.ui.layout import page_header
from dashboard.ui.theme import COLUMN_DEFAULTS, grid_options, hide_when_narrow


COMPARE_COLUMNS=[
    {"field":"title","headerName":"Idea","minWidth":140,"flex":1.4,"tooltipField":"run_id"},
    {"field":"symbol","headerName":"Market","flex":.6},
    {"field":"trade_count","headerName":"Trades","type":"numericColumn","flex":.6},
    {"field":"sharpe","headerName":"Out-of-sample Sharpe","type":"numericColumn","minWidth":100,"flex":.9,"valueFormatter":{"function":"params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field":"max_drawdown","headerName":"Max drawdown","type":"numericColumn","flex":.8,"valueFormatter":{"function":"params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field":"paper","headerName":"Paper trading","minWidth":110,"flex":1},
]


def _figure(records: list[dict[str,Any]],view: str) -> go.Figure:
    figure=go.Figure()
    for record in records:
        x_values,values=comparison_series(record,view)
        if values: figure.add_trace(go.Scatter(x=x_values,y=values,mode="lines",name=record.get("title"),line={"width":2}))
    if not figure.data:
        figure.add_annotation(text="Pick two to four passed ideas in Ideas to compare them here.",x=.5,y=.5,xref="paper",yref="paper",showarrow=False,font={"size":12})
    figure.update_layout(height=360)
    figure.update_xaxes(visible=bool(figure.data));figure.update_yaxes(visible=bool(figure.data))
    return figure


def _head(title: str, subtitle: str, *extra: Any) -> html.Div:
    return html.Div([html.Div([html.H3(title),html.P(subtitle)]),*extra],className="panel-head")


def compare_layout(search: str | None) -> html.Div:
    data=load_compare_records(search);records=data.get("records") or []
    header=page_header("Compare ideas",f"{len(records)} passed ideas side by side, after trading costs",dmc.Button("Back to Ideas",id="compare-back",leftSection=DashIconify(icon="tabler:arrow-left",width=14),variant="default"),dmc.Button("Clear selection",id="compare-clear",variant="default"))
    chips=dmc.Group([*[dmc.Badge(f"{record.get('title')} · {record.get('symbol')}",color="gray") for record in records],dmc.Text(data.get("shared_period") or "",size="xs",c="dimmed",ml="auto")],gap="xs",mb="sm")
    chart=dmc.Paper([_head("Growth and drops","Each line starts from the same amount on the same dates",dmc.SegmentedControl(id="compare-view",value="equity",size="xs",data=[{"value":"equity","label":"Equity"},{"value":"drawdown","label":"Drawdown"}])),dcc.Graph(id="compare-chart",figure=_figure(records,"equity"),config={"displayModeBar":False,"responsive":True})],className="panel compare-chart")
    differences=dmc.Paper([_head("Key differences","To help rank them, not to approve them"),html.Div(id="compare-differences",children=_differences(records,data.get("message")),className="side-body")],className="panel compare-differences")
    rows=[{**{key:value for key,value in record.items() if key!="evidence"},"trade_count":int(((record.get("evidence") or {}).get("trade_count") or 0))} for record in records]
    table=dmc.Paper([_head("Selected ideas","Open one for its full charts, trades and history"),dag.AgGrid(id="compare-grid",columnDefs=COMPARE_COLUMNS,rowData=rows,defaultColDef=COLUMN_DEFAULTS,eventListeners=hide_when_narrow("symbol","trade_count","max_drawdown","paper"),dashGridOptions=grid_options("No ideas selected.",rowSelection={"mode":"singleRow","enableClickSelection":True,"checkboxes":False},domLayout="autoHeight"),getRowId="params.data.run_id",className="compare-grid", columnSize="responsiveSizeToFit",style={"height":None})],className="panel compare-table")
    body=html.Div([chips,html.Div([chart,differences],className="compare-primary"),*([table] if rows else [])],className="body compare-body")
    return html.Div([dcc.Store(id="compare-records",data=records),header,body],className="compare-app")


def _differences(records,message):
    if len(records)<2: return [dmc.Text(message or "Pick two passed ideas in Ideas.",size="xs",c="dimmed")]
    def values(key,percent=False): return " / ".join("—" if row.get(key) is None else f"{float(row[key]):.1f}{'%' if percent else ''}" for row in records)
    return [html.Div([html.Span(label),html.Strong(value)],className="compare-line") for label,value in [("Out-of-sample Sharpe",values("sharpe")),("Maximum drawdown",values("max_drawdown",True)),("Net return",values("net_return",True)),("Kept out-of-sample",values("retained",True)),("Robustness"," / ".join(str(row.get("robustness") or "—") for row in records))]]+[dmc.Text("For comparison only; ranking does not start paper trading.",size="xs",c="dimmed",mt="sm")]


def register_compare_callbacks(application: Any) -> None:
    @application.callback(Output("compare-chart","figure"),Input("compare-view","value"),Input("compare-records","data"))
    def view(value,records): return _figure(records or [],value or "equity")


__all__=["compare_layout","register_compare_callbacks"]
