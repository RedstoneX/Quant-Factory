"""Reusable page-level Dash components."""

from __future__ import annotations

from dash import dcc, html


def page_heading(
    eyebrow: str,
    title: str,
    description: str,
) -> html.Header:
    return html.Header(
        [
            html.P(eyebrow, className="page-eyebrow"),
            html.H1(title, className="page-title"),
            html.P(description, className="page-description"),
        ],
        className="page-heading",
    )


def pending_page(
    eyebrow: str,
    title: str,
    description: str,
    *,
    scope_note: str | None = None,
) -> html.Div:
    note = (
        scope_note
        or "This destination is registered in the approved dashboard shell. Its full workflow will be implemented in a later bounded pass."
    )
    return html.Div(
        [
            page_heading(eyebrow, title, description),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Unavailable by design", className="pending-state-badge"),
                            html.H2("Paper trading is not active"),
                            html.P(note, className="summary-detail"),
                        ]
                    ),
                    html.Span("Research only", className="surface-badge surface-badge-safe"),
                ],
                className="support-summary-banner pending-page-banner",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.H2("Current boundaries"),
                                    html.P(
                                        "The page is present so its status is unmistakable.",
                                        className="section-description",
                                    ),
                                ],
                                className="surface-heading",
                            ),
                            html.Div(
                                [
                                    _pending_fact(
                                        "Research workspace",
                                        "Available",
                                        "Existing research and evidence remain readable.",
                                    ),
                                    _pending_fact(
                                        "Paper execution",
                                        "Not active",
                                        "No paper account or execution worker is connected.",
                                    ),
                                    _pending_fact(
                                        "Orders & capital",
                                        "Not authorized",
                                        "Nothing on this page can place an order or move money.",
                                    ),
                                ],
                                className="pending-fact-grid",
                            ),
                        ],
                        className="support-surface",
                    ),
                    html.Aside(
                        [
                            html.Span("OWNER GATE", className="page-eyebrow"),
                            html.H2("Activation comes later"),
                            html.P(
                                "This destination becomes operational only after a qualified edge, the required paper safeguards, and explicit owner approval.",
                                className="section-description",
                            ),
                        ],
                        className="support-surface pending-boundary-panel",
                    ),
                ],
                className="pending-page-grid",
            ),
        ],
        className="page-container support-page pending-page",
    )


def _pending_fact(label: str, value: str, detail: str) -> html.Div:
    return html.Div(
        [html.Span(label), html.Strong(value), html.Small(detail)],
        className="pending-fact",
    )


def not_found_page(pathname: str) -> html.Div:
    return html.Div(
        [
            page_heading(
                "NAVIGATION ERROR",
                "Page not found",
                f"No dashboard page is registered for {pathname!r}.",
            ),
            dcc.Link("Return Home", href="/", className="primary-link"),
        ],
        className="page-container",
    )
