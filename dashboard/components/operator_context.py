"""Persistent, read-only operator context for a selected research run."""

from __future__ import annotations

from dataclasses import dataclass

from dash import html


__all__ = ["OperatorContextViewModel", "operator_context"]


@dataclass(frozen=True, slots=True)
class OperatorContextViewModel:
    """Trader-facing values sourced from persisted run and review records."""

    selected_run: bool = False
    run_status: str | None = None
    evidence_outcome: str | None = None
    human_decision: str | None = None
    next_safe_action: str | None = None


def operator_context(
    view_model: OperatorContextViewModel | None = None,
    *,
    component_id: str = "selected-run-context",
) -> html.Section:
    """Render the four distinct operator meanings without inferring evidence."""

    context = view_model or OperatorContextViewModel()
    if not context.selected_run:
        return _empty_context(component_id)

    items = (
        ("Run status", _value_or(context.run_status, "Unavailable")),
        ("Evidence outcome", _value_or(context.evidence_outcome, "Not run")),
        ("Human decision", _value_or(context.human_decision, "Unavailable")),
        ("Next safe action", _value_or(context.next_safe_action, "No action available")),
    )

    return html.Section(
        html.Dl(
            [
                html.Div(
                    [
                        html.Dt(label, className="operator-context-label"),
                        html.Dd(value, className="operator-context-value"),
                    ],
                    className="operator-context-item",
                )
                for label, value in items
            ],
            className="operator-context-grid",
        ),
        id=component_id,
        className="operator-context",
        **{
            "aria-label": "Selected run context",
            "aria-live": "polite",
            "aria-atomic": "true",
        },
    )


def _empty_context(component_id: str) -> html.Section:
    return html.Section(
        [
            html.Strong("No run selected"),
            html.P(
                (
                    "Select a persisted run to inspect its status, evidence, "
                    "human decision, and next safe action."
                ),
                className="operator-context-empty-message",
            ),
        ],
        id=component_id,
        className="operator-context operator-context-empty",
        **{
            "aria-label": "Selected run context",
            "aria-live": "polite",
            "aria-atomic": "true",
        },
    )


def _value_or(value: str | None, fallback: str) -> str:
    if value is None:
        return fallback
    normalized = value.strip()
    return normalized or fallback
