"""The page shell: one Mantine AppShell with a scrolling main area and a navbar that collapses on phones."""

from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import Input, Output, State, clientside_callback, html
from dash_iconify import DashIconify

from dashboard.ui.theme import MANTINE_THEME

NAV_ITEMS = (
    ("/", "Dashboard", "tabler:layout-dashboard"),
    ("/submit", "Submit strategies", "tabler:upload"),
    ("/factory", "Factory runs", "tabler:building-factory-2"),
    ("/candidates", "Candidates", "tabler:list-details"),
    ("/results", "Results", "tabler:chart-candle"),
    ("/paper-trading", "Paper trading", "tabler:currency-dollar"),
)


def _brand() -> dmc.Group:
    return dmc.Group([
        dmc.ThemeIcon("Q", variant="light", size="md", radius="sm", fw=600),
        dmc.Text("Quant Factory", size="sm", fw=600),
    ], gap="sm", wrap="nowrap")


def _nav_link(href: str, label: str, icon: str) -> dmc.NavLink:
    return dmc.NavLink(label=label, href=href, active="exact", leftSection=DashIconify(icon=icon, width=16), variant="light", py=6)


def app_shell(*children: Any) -> dmc.MantineProvider:
    """Wrap the routed page in the shared theme and navigation."""
    shell = dmc.AppShell([
        dmc.AppShellHeader(dmc.Group([dmc.Burger(id="qf-burger", size="sm", opened=False, hiddenFrom="sm"), _brand()], h="100%", px="md", gap="md")),
        dmc.AppShellNavbar([
            dmc.Stack([_nav_link(*item) for item in NAV_ITEMS], gap=2, px="xs", pt="xs"),
        ]),
        dmc.AppShellMain(html.Div(list(children))),
    ], id="qf-shell", header={"height": 48}, navbar={"width": 200, "breakpoint": "sm", "collapsed": {"mobile": True}}, padding=0)
    return dmc.MantineProvider(shell, theme=MANTINE_THEME, forceColorScheme="dark")


def page_content(layout: Any) -> Any:
    """Pages still return their own MantineProvider; the shell's provider is the only one that should apply."""
    return layout.children if isinstance(layout, dmc.MantineProvider) else layout


clientside_callback(
    "(opened, navbar) => ({...navbar, collapsed: {mobile: !opened}})",
    Output("qf-shell", "navbar"), Input("qf-burger", "opened"), State("qf-shell", "navbar"),
)
clientside_callback("() => false", Output("qf-burger", "opened"), Input("router-location", "pathname"), prevent_initial_call=True)
