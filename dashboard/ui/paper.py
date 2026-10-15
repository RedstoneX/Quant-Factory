"""External Paper Trading destination boundary."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from dashboard.ui.layout import page_header


PAPER_URL_ENVIRONMENT_VARIABLE="QUANT_FACTORY_PAPER_URL"


def _configured_url() -> str | None:
    value=os.environ.get(PAPER_URL_ENVIRONMENT_VARIABLE,"").strip()
    try:
        parsed=urlsplit(value)
    except ValueError:
        return None
    return value if parsed.scheme=="https" and parsed.netloc and not parsed.username and not parsed.password else None


def paper_layout() -> html.Div:
    destination=_configured_url()
    header=page_header("Paper trading","Practice trading with pretend money runs in a separate system")
    if destination:
        notice=dmc.Alert(dmc.Group([dmc.Text("Passed ideas are handed to the paper-trading system.",size="sm"),dmc.Anchor(dmc.Button("Open paper trading",leftSection=DashIconify(icon="tabler:external-link",width=14)),href=destination,target="_blank",rel="noopener noreferrer")],justify="space-between"),variant="light",color="blue")
    else:
        notice=dmc.Alert("Paper trading isn't connected yet, so there is nothing to open here. Passed ideas will be handed to it once its address is set.",title="Not connected",variant="light",color="gray")
    return html.Div([header,html.Div(notice,className="body")],className="paper-app")


__all__=["PAPER_URL_ENVIRONMENT_VARIABLE","paper_layout"]
