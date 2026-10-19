"""The page shell: one Mantine AppShell with a scrolling main area and a navbar that collapses on phones."""

from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import Input, Output, State, clientside_callback, dcc, html
from dash_iconify import DashIconify

from dashboard.ui.theme import BORDER, MANTINE_THEME

NAV_ITEMS = (
    ("/", "Today", "tabler:layout-dashboard"),
    ("/workbench", "Results", "tabler:chart-candle"),
    ("/factory", "Factory", "tabler:building-factory-2"),
    ("/new", "New idea", "tabler:upload"),
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
        # Pinned to the window bottom so its border runs the full height whatever the viewport unit reports.
        dmc.AppShellNavbar([
            dmc.Stack([_nav_link(*item) for item in NAV_ITEMS], gap=2, px="xs", pt="xs"),
        ], h="auto", bottom=0),
        dmc.AppShellMain(html.Div(list(children))),
    ], id="qf-shell", header={"height": 48}, navbar={"width": 200, "breakpoint": "sm", "collapsed": {"mobile": True}}, padding=0)
    return dmc.MantineProvider(shell, theme=MANTINE_THEME, forceColorScheme="dark")


def page_header(title: str, subtitle: str, *actions: Any) -> dmc.Group:
    """Title, one plain line under it, and actions that wrap below on phones."""
    return dmc.Group([
        dmc.Stack([dmc.Title(title, order=1), dmc.Text(subtitle, size="xs", c="dimmed")], gap=2),
        dmc.Group(list(actions), gap="xs"),
    ], justify="space-between", gap="sm", px="lg", py="md", style={"borderBottom": f"1px solid {BORDER}"})


TILE_NOTES = {
    "Net return": "Profit after trading costs, as a share of starting money.",
    "Best net return": "Profit after trading costs for the best setting.",
    "Sharpe": "Return per unit of risk. Above 0.5 is decent, above 1 is strong.",
    "Sharpe on first check": "Return per unit of risk on the first-check data.",
    "Sharpe on unseen data": "Return per unit of risk on data it never saw while being built.",
    "Max drawdown": "Biggest fall from a peak to a low along the way. Smaller is better.",
    "Trades": "How many trades it took. More trades make the numbers more trustworthy.",
    "Win rate": "Share of trades that made money. Low is fine if wins are bigger than losses.",
    "Profit factor": "Money won per dollar lost. Above 1 means it made money.",
}


def stat_card(label: str, value: Any, note: Any = "", *, color: str | None = None, value_id: str | None = None, note_id: str | None = None) -> dmc.Paper:
    """A flat figure card: small label, one colour-coded number, a plain note."""
    note = note or TILE_NOTES.get(label, "")
    value_props = {"id": value_id} if value_id else {}
    note_props = {"id": note_id} if note_id else {}
    return dmc.Paper(dmc.Stack([
        dmc.Text(label, size="xs", c="dimmed"), dmc.Text(value, fz=18, fw=600, **({"c": color} if color else {}), **value_props), dmc.Text(note, size="xs", c="dimmed", **note_props),
    ], gap=2), p="md")


def copy_id(value: Any) -> Any:
    """Keep an identifier out of the text: a copy icon whose hover title shows it."""
    text = str(value or "")
    return dcc.Clipboard(content=text, title=f"Copy {text}", style={"display": "inline-block", "cursor": "pointer"}) if text else "—"


def page_content(layout: Any) -> Any:
    """Pages still return their own MantineProvider; the shell's provider is the only one that should apply."""
    return layout.children if isinstance(layout, dmc.MantineProvider) else layout


clientside_callback(
    "(opened, navbar) => ({...navbar, collapsed: {mobile: !opened}})",
    Output("qf-shell", "navbar"), Input("qf-burger", "opened"), State("qf-shell", "navbar"),
)
clientside_callback("() => false", Output("qf-burger", "opened"), Input("router-location", "pathname"), prevent_initial_call=True)
