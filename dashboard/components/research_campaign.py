"""Compact current-research summary for the owner dashboard."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from dash import dcc, html


def research_campaign_overview(
    *,
    model: Any,
    rows: tuple[dict[str, object], ...],
    outcome_for: Callable[[Mapping[str, object]], str],
) -> html.Section:
    """Render live campaign context and one useful owner action."""

    latest = rows[0] if rows else None
    latest_finding = (
        f"{_text(latest, 'strategy')} · {outcome_for(latest)}"
        if latest is not None
        else "No persisted research result yet"
    )
    assessment = (
        _text(latest, "rejection_reasons", _text(latest, "evidence"))
        if latest is not None
        else "The research record is ready for the first bounded idea."
    )
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span("Research program", className="atlas-campaign-kicker"),
                                            html.H2("Quant Factory research workflow"),
                                        ]
                                    ),
                                    html.Span(
                                        "Active test" if model.run is not None else "Ready for review",
                                        className="atlas-campaign-state",
                                    ),
                                ],
                                className="atlas-campaign-heading",
                            ),
                            html.Div(
                                [
                                    _answer("Current scope", model.subtitle),
                                    _answer("Latest finding", latest_finding),
                                    _answer("Assessment", assessment),
                                ],
                                className="atlas-campaign-answers",
                            ),
                            html.Div(
                                [
                                    html.Strong(f"{len(rows)} persisted research run{'s' if len(rows) != 1 else ''}"),
                                    html.Span("Every saved result remains visible in the evidence maps below."),
                                ],
                                className="atlas-campaign-foot",
                            ),
                        ],
                        className="atlas-campaign-summary",
                    ),
                    html.Aside(
                        [
                            html.Span("NEXT ACTION", className="atlas-decision-label"),
                            html.H2(model.action.label),
                            html.P(model.action.description),
                            dcc.Link("Open", href=model.action.href, className="primary-action"),
                        ],
                        className="atlas-decision-card",
                    ),
                ],
                className="atlas-overview-grid",
            )
        ],
        className="atlas-overview",
    )


def _answer(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value)], className="atlas-campaign-answer")


def _text(row: Mapping[str, object], name: str, fallback: str = "Unavailable") -> str:
    value = row.get(name)
    return str(value).strip() if value is not None and str(value).strip() else fallback
