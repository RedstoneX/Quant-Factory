"""Dormant Quant Factory paper-operations destination.

This page is presentation-only.  It reads no research or broker state and has
no credential, order, or activation capability.
"""

from __future__ import annotations

from dash import html

from dashboard.pages.common import page_heading


def layout() -> html.Div:
    return html.Div(
        [
            page_heading(
                "QUANT FACTORY / PAPER",
                "Paper trading",
                "The future operating view for qualified strategies running in Alpaca Paper.",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Not active", className="pending-state-badge"),
                            html.H2("No paper lane is connected"),
                            html.P(
                                "This destination is reserved for Quant Factory's own paper system. "
                                "It is not QAMC, and it does not read QAMC state or credentials.",
                                className="summary-detail",
                            ),
                        ]
                    ),
                    html.Span(
                        "No orders",
                        className="surface-badge surface-badge-safe",
                    ),
                ],
                className="support-summary-banner pending-page-banner",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.H2("What will live here"),
                            html.Div(
                                [
                                    _fact(
                                        "Qualified deployments",
                                        "Strategies admitted through the immutable paper handoff.",
                                    ),
                                    _fact(
                                        "Forward performance",
                                        "Broker-observed P&L, positions, orders, fills and reconciliation.",
                                    ),
                                    _fact(
                                        "Operating health",
                                        "Freshness, risk state, pauses, mismatches and recovery status.",
                                    ),
                                ],
                                className="pending-fact-grid",
                            ),
                        ],
                        className="support-surface",
                    ),
                    html.Aside(
                        [
                            html.Span("BOUNDARY", className="page-eyebrow"),
                            html.H2("Separate from research"),
                            html.P(
                                "Research results do not become paper P&L. Paper performance appears "
                                "only after the isolated Alpaca paper system supplies broker-backed observations.",
                                className="section-description",
                            ),
                        ],
                        className="support-surface pending-boundary-panel",
                    ),
                ],
                className="pending-page-grid",
            ),
        ],
        className="page-container support-page pending-page paper-trading-page",
    )


def _fact(label: str, detail: str) -> html.Div:
    return html.Div(
        [html.Strong(label), html.Small(detail)],
        className="pending-fact",
    )


__all__ = ["layout"]
