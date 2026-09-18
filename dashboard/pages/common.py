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
                    html.Span("Implementation pending", className="pending-state-badge"),
                    html.H2("Shared shell ready"),
                    html.P(note, className="summary-detail"),
                ],
                className="panel pending-page-panel",
            ),
        ],
        className="page-container pending-page",
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
