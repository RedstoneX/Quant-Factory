"""Production Compare Selected survivor workspace."""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, dcc, html
import plotly.graph_objects as go

from dashboard.compare_projection import comparison_series, load_compare_records


GLYPHS={"dashboard":"▦","file":"+","flow":"⌁","list":"☷","chart":"⌁","external":"↗","back":"←"}
COLORS=["#4aa8ff","#a98cf8","#38d39f","#ffbd59"]
COMPARE_COLUMNS=[
    {"field":"title","headerName":"Survivor","minWidth":220,"flex":1.4,"pinned":"left"},
    {"field":"symbol","headerName":"Market","width":82},
    {"field":"trade_count","headerName":"Trades","type":"numericColumn","width":82},
    {"field":"sharpe","headerName":"OOS Sharpe","type":"numericColumn","width":110,"valueFormatter":{"function":"params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field":"max_drawdown","headerName":"Max DD","type":"numericColumn","width":92,"valueFormatter":{"function":"params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field":"paper","headerName":"Paper package","minWidth":150,"flex":1},
]


def _icon(name): return html.Span(GLYPHS[name],className="icon",**{"aria-hidden":"true"})
def _rail(name,label,item_id,*,active=False,disabled=False): return dmc.ActionIcon(_icon(name),id=item_id,className=f"rail-item{' active' if active else ''}",variant="subtle",disabled=disabled,**{"aria-label":label})


def _figure(records: list[dict[str,Any]],view: str) -> go.Figure:
    figure=go.Figure()
    for index,record in enumerate(records):
        x_values,values=comparison_series(record,view)
        if values: figure.add_trace(go.Scatter(x=x_values,y=values,mode="lines",name=record.get("title"),line={"color":COLORS[index % len(COLORS)],"width":2}))
    if not figure.data: figure.add_annotation(text="No common persisted evidence series is available.",x=.5,y=.5,xref="paper",yref="paper",showarrow=False,font={"color":"#8a97a8","size":11})
    figure.update_layout(height=650,paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",margin={"l":46,"r":18,"t":18,"b":36},font={"family":"Inter, sans-serif","size":9,"color":"#8a97a8"},legend={"orientation":"h","y":1.1},hovermode="x unified")
    figure.update_xaxes(gridcolor="#202936",linecolor="#344050",visible=bool(figure.data));figure.update_yaxes(gridcolor="#202936",linecolor="#344050",title="Drawdown" if view=="drawdown" else "Normalized equity",visible=bool(figure.data))
    return figure


def compare_layout(search: str | None) -> dmc.MantineProvider:
    data=load_compare_records(search);records=data.get("records") or []
    nav=dmc.Stack([dmc.Paper("Q",className="logo",radius="md"),_rail("dashboard","Dashboard","compare-nav-dashboard"),_rail("file","Submit strategies","compare-nav-submit"),_rail("flow","Factory runs","compare-nav-factory"),_rail("list","Candidates","compare-nav-candidates",active=True),_rail("chart","Results","compare-nav-results"),html.Div(className="rail-spacer"),_rail("external","Paper Trading","compare-nav-paper"),dmc.Avatar("TO",className="avatar",radius="xl")],gap=7,align="center",className="rail")
    header=dmc.Group([html.Div([dmc.Title("Compare selected",order=1),dmc.Text(f"Secondary Candidates workspace · {len(records)} qualified survivors",className="eyebrow")]),html.Div(className="top-spacer"),dmc.Button("Back to Candidates",id="compare-back",leftSection=_icon("back"),className="ghost",variant="default"),dmc.Button("Clear selection",id="compare-clear",className="ghost",variant="default")],gap=9,className="topbar")
    chips=dmc.Group([*[dmc.Badge(f"{record.get('title')} · {record.get('symbol')}",className="filter-chip") for record in records],html.Div(className="top-spacer"),dmc.Text(f"{data.get('shared_period','Shared period unavailable')} · net of configured costs",className="candidate-context")],gap=8,className="compare-toolbar")
    chart=dmc.Paper([html.Div([html.Div([html.H3("Normalized equity and drawdown"),html.P("Same starting basis and shared persisted dates")]),dmc.Select(id="compare-view",value="equity",data=[{"value":"equity","label":"Equity"},{"value":"drawdown","label":"Drawdown"}],allowDeselect=False,className="results-control")],className="panel-head"),dcc.Graph(id="compare-chart",figure=_figure(records,"equity"),config={"displayModeBar":False,"responsive":True})],className="panel compare-chart",radius="md")
    differences=dmc.Paper([html.Div([html.Div([html.H3("Material differences"),html.P("Ranking aid, not a promotion gate")])],className="panel-head"),html.Div(id="compare-differences",children=_differences(records,data.get("message")),className="side-body")],className="panel compare-differences",radius="md")
    rows=[{**{key:value for key,value in record.items() if key!="evidence"},"trade_count":int(((record.get("evidence") or {}).get("trade_count") or 0))} for record in records]
    table=dmc.Paper([html.Div([html.Div([html.H3("Selected survivors"),html.P("Open either exact record for full charts, trades, sensitivity, and lineage")])],className="panel-head"),dag.AgGrid(id="compare-grid",columnDefs=COMPARE_COLUMNS,rowData=rows,defaultColDef={"sortable":True,"resizable":True},dashGridOptions={"rowSelection":{"mode":"singleRow","enableClickSelection":True}},getRowId="params.data.run_id",className="ag-theme-quartz-dark compare-grid")],className="panel compare-table",radius="md")
    body=html.Div([chips,html.Div([chart,differences],className="compare-primary"),table],className="body compare-body")
    return dmc.MantineProvider(html.Div([dcc.Store(id="compare-records",data=records),html.Div([nav,html.Main([header,body],className="main")],className="app compare-app")]),forceColorScheme="dark",theme={"fontFamily":"Inter, ui-sans-serif, sans-serif","primaryColor":"blue"})


def _differences(records,message):
    if len(records)<2: return [html.Div(message or "Select two qualified survivors in Candidates.",className="submit-empty")]
    def values(key,percent=False): return " / ".join("—" if row.get(key) is None else f"{float(row[key]):.1f}{'%' if percent else ''}" for row in records)
    return [html.Div([html.Span(label),html.Strong(value)],className="compare-line") for label,value in [("OOS Sharpe",values("sharpe")),("Maximum drawdown",values("max_drawdown",True)),("Net return",values("net_return",True)),("OOS retention",values("retained",True)),("Robustness plateau"," / ".join(str(row.get("robustness") or "—") for row in records))]]+[html.Div("Compare behavior only; rank does not authorize paper promotion.",className="submit-mandate")]


def register_compare_callbacks(application: Any) -> None:
    @application.callback(Output("compare-chart","figure"),Input("compare-view","value"),Input("compare-records","data"))
    def view(value,records): return _figure(records or [],value or "equity")


__all__=["compare_layout","register_compare_callbacks"]
