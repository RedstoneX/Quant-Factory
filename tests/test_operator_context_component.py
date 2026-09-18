"""Focused rendering contract for the persistent operator context."""

from __future__ import annotations

from typing import Any

from dash import html

from dashboard.components.operator_context import (
    OperatorContextViewModel,
    operator_context,
)


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None:
        yield from _walk(children)


def _text(component: Any) -> list[str]:
    return [item for item in _walk(component) if isinstance(item, str)]


def test_operator_context_renders_exact_labels_and_supplied_values() -> None:
    component = operator_context(
        OperatorContextViewModel(
            selected_run=True,
            run_status="Succeeded",
            evidence_outcome="Insufficient evidence",
            human_decision="Infrastructure fixture",
            next_safe_action="Inspect evidence",
        )
    )

    assert _text(component) == [
        "Run status",
        "Succeeded",
        "Evidence outcome",
        "Insufficient evidence",
        "Human decision",
        "Infrastructure fixture",
        "Next safe action",
        "Inspect evidence",
    ]


def test_operator_context_replaces_quartet_with_plain_language_empty_state() -> None:
    component = operator_context()

    assert _text(component) == [
        "No run selected",
        (
            "Select a persisted run to inspect its status, evidence, "
            "human decision, and next safe action."
        ),
    ]
    assert isinstance(component.children, list)
    assert not any(isinstance(item, html.Dl) for item in _walk(component))


def test_selected_run_with_missing_records_does_not_imply_an_outcome() -> None:
    component = operator_context(
        OperatorContextViewModel(
            selected_run=True,
            run_status=" ",
            evidence_outcome="",
            human_decision=None,
            next_safe_action="\t",
        )
    )

    assert _text(component) == [
        "Run status",
        "Unavailable",
        "Evidence outcome",
        "Not run",
        "Human decision",
        "Unavailable",
        "Next safe action",
        "No action available",
    ]


def test_operator_context_has_definition_list_and_live_region_semantics() -> None:
    component = operator_context(
        OperatorContextViewModel(selected_run=True),
        component_id="results-run-context",
    )
    descendants = list(_walk(component))

    assert component.id == "results-run-context"
    assert getattr(component, "aria-label") == "Selected run context"
    assert getattr(component, "aria-live") == "polite"
    assert getattr(component, "aria-atomic") == "true"
    assert isinstance(component.children, html.Dl)
    assert sum(isinstance(item, html.Dt) for item in descendants) == 4
    assert sum(isinstance(item, html.Dd) for item in descendants) == 4
