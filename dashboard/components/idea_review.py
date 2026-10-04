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
    candidate_status: str,
    can_continue: bool,
    queue_counts: tuple[int, int, int] = (0, 0, 0),
    selected_kicker: str = "Selected idea",
) -> tuple[Any, Any]:
    """Build the approved three-column review hierarchy from live state."""

    attention = html.Section(
        [
            html.Div(
                [
                    html.Span(
                        "",
                        className="idea-review-attention-icon",
                        **{"aria-hidden": "true"},
                    ),
                    html.Div(
                        [
                            html.Strong(
                                f"{queue_counts[0]} idea{'s' if queue_counts[0] != 1 else ''} need your decision"
                                if queue_counts[0]
                                else "Your idea queue is up to date"
                            ),
                            html.Span("Read the selected proposal, then choose what should happen next."),
                        ],
                        className="idea-review-attention-copy",
                    ),
                ],
                className="idea-review-attention-message",
            ),
            html.Span(
                f"Selected: {1 if selected else 0} of {draft_count}",
                className="idea-review-selection",
            ),
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
                    html.Div(
                        [
                            _queue_stat(queue_counts[0], "Need you"),
                            _queue_stat(queue_counts[1], "Accepted"),
                            _queue_stat(queue_counts[2], "Closed"),
                        ],
                        className="idea-queue-summary",
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
                    html.Div(
                        [
                            html.Details([html.Summary("View all idea history")]),
                            html.P(
                                f"All {draft_count} saved idea{'s are' if draft_count != 1 else ' is'} shown above. Rejected and superseded versions remain visible here.",
                            ),
                        ],
                        className="idea-history-footer",
                    ),
                ],
                className="idea-workbench-panel idea-review-queue-panel",
            ),
            html.Article(
                [
                    html.Header(
                        [
                            html.P(selected_kicker, className="page-eyebrow"),
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
                        className="idea-review-facts idea-review-callback-state",
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
                ],
                className="idea-workbench-panel idea-review-main",
            ),
            _decision_panel(selected, candidate_valid, candidate_status, can_continue),
        ],
        className="idea-review-workspace",
    )
    return attention, workspace


def _decision_panel(
    selected: Any,
    candidate_valid: bool,
    candidate_status: str,
    can_continue: bool,
) -> html.Aside:
    approved = candidate_status == "owner_approved"
    rejected = candidate_status == "rejected"
    state = "Accepted" if approved else "Rejected" if rejected else "Decision needed" if selected else "Choose an idea"
    next_action = (
        "Accepted version is locked and ready for Set up."
        if approved else "This Candidate remains in history and cannot continue."
        if rejected else "Review the exact Candidate, then choose one action."
        if selected else "Add or import an idea first."
    )
    actionable = bool(selected and candidate_valid and not rejected)
    return html.Aside(
        [
            html.Div(
                [
                    html.Span(
                        state,
                        id="idea-brief-state",
                        className=(
                            "idea-brief-badge idea-brief-badge-approved"
                            if approved
                            else "idea-brief-badge idea-brief-badge-rejected"
                            if rejected
                            else "idea-brief-badge idea-brief-badge-ready"
                            if selected
                            else "idea-brief-badge"
                        ),
                    ),
                    html.H2("Choose what happens next"),
                    html.P(
                        "Continue with this accepted version, revise it, or reject it."
                        if approved
                        else "Revise this rejected version to create a new decision."
                        if rejected
                        else "Accept this exact version, revise it, or reject it."
                    ),
                ],
                className="idea-decision-heading",
            ),
            html.Div(
                [
                    html.Span("✓", className="idea-decision-ready-icon", **{"aria-hidden": "true"}),
                    html.Strong(next_action, id="idea-next-action-copy", className="idea-decision-next"),
                ],
                className="idea-decision-readiness",
            ),
            html.Div(
                [
                    html.Button(
                        "Accept",
                        id="accept-candidate-for-setup",
                        n_clicks=0,
                        disabled=not actionable,
                        className="primary-action" if actionable else "primary-action action-disabled",
                    ),
                    dcc.Link(
                        ["Continue to Set up", html.Span("→", **{"aria-hidden": "true"})],
                        id="continue-idea-to-setup",
                        href="/research/setup" if can_continue else None,
                        className=(
                            "primary-action idea-decision-button"
                            if can_continue else "secondary-action idea-decision-button action-disabled"
                        ),
                    ),
                    html.A([html.Span("✎", **{"aria-hidden": "true"}), "Revise"], href="#idea-intake", className="secondary-action idea-decision-button"),
                    html.Button(
                        [html.Span("×", **{"aria-hidden": "true"}), "Reject"],
                        id="reject-candidate",
                        n_clicks=0,
                        disabled=not selected or not candidate_valid or rejected,
                        className="secondary-action idea-reject-button",
                    ),
                ],
                className="idea-decision-actions",
            ),
        ],
        className=(
            "idea-workbench-panel idea-decision-panel idea-decision-approved"
            if approved
            else "idea-workbench-panel idea-decision-panel idea-decision-rejected"
            if rejected
            else "idea-workbench-panel idea-decision-panel"
        ),
    )


def _fact(label: str, value: str, component_id: str) -> html.Div:
    return html.Div([html.Dt(label), html.Dd(value, id=component_id)], className="idea-review-fact")


def _value(value: str | None, empty: str) -> str:
    return value.strip() if value and value.strip() else empty


def _queue_stat(value: int, label: str) -> html.Div:
    return html.Div([html.Strong(str(value)), html.Span(label)], className="idea-queue-stat")
