"""Owner-facing idea queue, readable review, and decision surface."""

from __future__ import annotations

from typing import Any

from dash import dcc, html


def idea_review_workspace(
    *,
    draft_count: int,
    draft_options: list[dict[str, object]],
    selected: Any,
    candidate_brief: Any,
    candidate_valid: bool,
    can_continue: bool,
) -> tuple[Any, Any]:
    """Build the approved three-column review hierarchy from live state."""

    attention = html.Section(
        [
            html.Div(
                [
                    html.Strong(f"{draft_count} ideas saved"),
                    html.Span("Choose an idea, read the proposal, then decide what happens next."),
                ],
                className="idea-review-attention-copy",
            ),
            html.Span("Nothing starts from Ideas", className="idea-review-boundary"),
        ],
        className="idea-review-attention",
    )
    workspace = html.Main(
        [
            html.Aside(
                [
                    html.Div(
                        [
                            html.Div([html.H2("Idea queue"), html.P("Agent and owner ideas share one history.")]),
                            html.Span(str(draft_count), id="idea-history-count", className="idea-count-badge"),
                        ],
                        className="idea-panel-heading idea-panel-heading-split",
                    ),
                    dcc.RadioItems(
                        id="idea-draft-selector",
                        options=draft_options,
                        value=selected.draft_id if selected else None,
                        className="idea-history-selector idea-review-queue",
                    ),
                    html.Div(
                        [html.Strong("No saved ideas yet"), html.P("Use Add / import to create the first idea.")],
                        id="idea-history-empty",
                        className="idea-history-empty",
                        style={} if not draft_count else {"display": "none"},
                    ),
                ],
                className="idea-workbench-panel idea-review-queue-panel",
            ),
            html.Article(
                [
                    html.Header(
                        [
                            html.P("Selected idea", className="page-eyebrow"),
                            html.H2(selected.title if selected else "Choose an idea", id="selected-idea-title"),
                            html.P(
                                _value(selected.description if selected else "", "Select or add an idea to review its meaning."),
                                id="idea-brief-hypothesis",
                                className="idea-review-summary",
                            ),
                        ],
                        className="idea-review-header",
                    ),
                    html.Dl(
                        [
                            _fact("Source basis", _value(selected.attribution if selected else "", "No source or owner observation recorded yet."), "idea-brief-source"),
                            _fact("Open questions", _value(selected.notes if selected else "", "No open questions recorded."), "idea-brief-questions"),
                            _fact("Setup", "Bounded setup saved" if selected and selected.configuration_id else "Not prepared", "idea-brief-setup"),
                        ],
                        className="idea-review-facts",
                    ),
                    html.Section(
                        [html.Div(candidate_brief, id="candidate-brief-content")],
                        id="candidate-brief-panel-v1",
                        className=(
                            "candidate-brief-panel-v1 idea-review-candidate"
                            if candidate_valid
                            else "candidate-brief-panel-v1 idea-review-candidate idea-path-hidden"
                        ),
                    ),
                    html.Div(
                        [
                            html.Button("Export YAML", id="export-candidate-yaml", n_clicks=0, disabled=not candidate_valid, className="secondary-action"),
                            html.Button("Export JSON", id="export-candidate-json", n_clicks=0, disabled=not candidate_valid, className="secondary-action"),
                        ],
                        className="idea-review-tools",
                    ),
                ],
                className="idea-workbench-panel idea-review-main",
            ),
            html.Aside(
                [
                    html.Div(
                        [
                            html.Span(
                                "Ready to review" if selected else "Choose an idea",
                                id="idea-brief-state",
                                className="idea-brief-badge idea-brief-badge-ready" if selected else "idea-brief-badge",
                            ),
                            html.H2("Choose what happens next"),
                            html.P("Save the exact version for Set up, revise it, or remove an unlinked draft."),
                        ],
                        className="idea-decision-heading",
                    ),
                    html.Strong(
                        "Save this draft, then continue to Set up." if selected else "Add or import an idea first.",
                        id="idea-next-action-copy",
                        className="idea-decision-next",
                    ),
                    dcc.Link(
                        "Accept",
                        id="continue-idea-to-setup",
                        href="/research/setup" if can_continue else None,
                        className="primary-action" if can_continue else "primary-action action-disabled",
                    ),
                    html.A("Revise", href="#idea-intake", className="secondary-action idea-decision-button"),
                    html.Button("Reject", id="discard-idea-draft", n_clicks=0, className="secondary-action idea-reject-button"),
                ],
                className="idea-workbench-panel idea-decision-panel",
            ),
        ],
        className="idea-review-workspace",
    )
    return attention, workspace


def _fact(label: str, value: str, component_id: str) -> html.Div:
    return html.Div([html.Dt(label), html.Dd(value, id=component_id)], className="idea-review-fact")


def _value(value: str | None, empty: str) -> str:
    return value.strip() if value and value.strip() else empty
