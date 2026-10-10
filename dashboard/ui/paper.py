"""External Paper Trading destination boundary."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import dash_mantine_components as dmc
from dash import html


GLYPHS={"dashboard":"▦","file":"+","flow":"⌁","list":"☷","chart":"⌁","external":"↗"}
PAPER_URL_ENVIRONMENT_VARIABLE="QUANT_FACTORY_PAPER_URL"


def _icon(name): return html.Span(GLYPHS[name],className="icon",**{"aria-hidden":"true"})
def _rail(name,label,item_id,*,active=False): return dmc.ActionIcon(_icon(name),id=item_id,className=f"rail-item{' active' if active else ''}",variant="subtle",**{"aria-label":label})


def _configured_url() -> str | None:
    value=os.environ.get(PAPER_URL_ENVIRONMENT_VARIABLE,"").strip()
    try:
        parsed=urlsplit(value)
    except ValueError:
        return None
    return value if parsed.scheme=="https" and parsed.netloc and not parsed.username and not parsed.password else None


def paper_layout() -> dmc.MantineProvider:
    destination=_configured_url()
    nav=dmc.Stack([dmc.Paper("Q",className="logo",radius="md"),_rail("dashboard","Dashboard","paper-nav-dashboard"),_rail("file","Submit strategies","paper-nav-submit"),_rail("flow","Factory runs","paper-nav-factory"),_rail("list","Candidates","paper-nav-candidates"),_rail("chart","Results","paper-nav-results"),html.Div(className="rail-spacer"),_rail("external","Paper Trading","paper-nav-paper",active=True),dmc.Avatar("TO",className="avatar",radius="xl")],gap=7,align="center",className="rail")
    header=dmc.Group([html.Div([dmc.Title("Paper trading",order=1),dmc.Text("External system boundary",className="eyebrow")])],className="topbar")
    action=dmc.Anchor(dmc.Button("Open paper-trading dashboard",leftSection=_icon("external"),className="primary"),href=destination,target="_blank",rel="noopener noreferrer") if destination else dmc.Button("Paper destination not configured",leftSection=_icon("external"),disabled=True,className="primary")
    card=dmc.Paper([html.Div([html.Div([html.H3("Alpaca paper-trading dashboard"),html.P("Separate project · separate runtime · separate operational authority")]),dmc.Badge("External",color="blue",variant="light")],className="panel-head"),html.Div([html.Div(_icon("external"),className="paper-symbol"),dmc.Title("Survivor packages continue in the paper-trading system",order=2),dmc.Text("Quant Factory prepares a sealed paper package and records the handoff. Orders, positions, broker state, and paper P&L remain outside Quant Factory so research and trading state do not cross-contaminate.",className="paper-copy"),html.Div([html.Span("Destination"),html.Strong("Configured private paper dashboard" if destination else "No private URL configured"),html.Span("Separate")],className="candidate-evidence-item"),html.Div([html.Span("Quant Factory authority"),html.Strong("Package and handoff status only"),html.Span()],className="candidate-evidence-item"),html.Div([html.Span("Trading controls"),html.Strong("Owned by the paper-trading project"),html.Span()],className="candidate-evidence-item"),action,dmc.Text("No broker access, paper activation, orders, or capital authority is exposed here." if not destination else "Opens the separately operated private paper-trading system.",className="paper-note")],className="paper-card-body")],className="panel paper-card",radius="md")
    body=html.Div(card,className="body paper-body")
    return dmc.MantineProvider(html.Div([nav,html.Main([header,body],className="main")],className="app paper-app"),forceColorScheme="dark",theme={"fontFamily":"Inter, ui-sans-serif, sans-serif","primaryColor":"blue"})


__all__=["PAPER_URL_ENVIRONMENT_VARIABLE","paper_layout"]
