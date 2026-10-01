"""Reusable operator-message presentation."""

from __future__ import annotations

from typing import Any

from dash import html


def operator_message(
    summary: str,
    detail: str | None = None,
    *,
    tone: str,
) -> html.Div:
    children: list[Any] = [html.Strong(summary)]
    if detail:
        children.append(html.P(detail, className="operator-message-detail"))
    return html.Div(
        children,
        className=f"operator-message operator-message-{tone}",
    )
