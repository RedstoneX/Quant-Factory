"""Contextual link from Research Dashboard to isolated Paper operations."""

from __future__ import annotations

from dash import dcc, html


def paper_trading_destination() -> html.Section:
    """Render no paper metrics; link only to the dormant Paper surface."""

    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("PAPER TRADING", className="page-eyebrow"),
                            html.H2("Forward operation stays separate"),
                            html.P(
                                "Open the Quant Factory paper workspace for future Alpaca Paper "
                                "deployments. Forward paper performance stays out of research results.",
                            ),
                        ],
                        className="atlas-panel-heading",
                    ),
                    html.Span("Not active", className="pending-state-badge"),
                ],
                className="paper-destination-copy",
            ),
            dcc.Link(
                "Open paper trading",
                id="home-paper-trading-link",
                href="/paper/fleet",
                className="atlas-header-action",
            ),
        ],
        id="home-paper-trading-destination",
        className="atlas-panel paper-destination-panel",
    )


__all__ = ["paper_trading_destination"]
