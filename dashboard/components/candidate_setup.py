"""Small owner-facing surfaces for exact Candidate setup boundaries."""

from __future__ import annotations

from typing import Any

from dash import dcc, html

from dashboard.candidate_workflow import CandidateConfigurationBinding


def candidate_identity_summary(
    selected_draft: Any,
    binding: CandidateConfigurationBinding | None,
) -> html.Div:
    identity = binding.identity if binding is not None else None
    return html.Div(
        [
            html.Strong(
                selected_draft.title
                if selected_draft is not None
                else "Choose and accept a Candidate on Ideas first."
            ),
            html.Small(
                f"{identity.candidate_id} · version {identity.short_version}"
                if identity is not None
                else "No exact Candidate selected"
            ),
        ],
        id="setup-candidate-identity",
        className="candidate-workflow-identity",
    )


def candidate_implementation_boundary(*, open_boundary: bool) -> html.Section:
    """Show implementation readiness without disguising status as an action."""

    title = "Review decision"
    state = "Blocked" if open_boundary else "Ready"
    state_class = "setup-rail-state setup-rail-state-blocked" if open_boundary else "setup-rail-state setup-rail-state-ready"
    summary = (
        "Implementation required. The exact test cannot be saved until its implementation is bound."
        if open_boundary
        else "The exact accepted Candidate has a saved immutable implementation."
    )
    checks = (
        (
            ("complete", "Candidate accepted"),
            ("missing", "Exact rules implemented"),
            ("missing", "Immutable version bound"),
            ("waiting", "Local price history verified"),
            ("waiting", "Final review available"),
        )
        if open_boundary
        else (
            ("complete", "Candidate accepted"),
            ("complete", "Exact rules implemented"),
            ("complete", "Immutable version bound"),
            ("complete", "Local price history verified"),
            ("complete", "Final review available"),
        )
    )

    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("IMPLEMENTATION", className="setup-state-label"),
                            html.H2(title),
                            html.P(summary, className="section-description"),
                        ]
                    ),
                    html.Span(state, className=state_class),
                ],
                className="setup-rail-heading",
            ),
            html.Div(
                [
                    dcc.Link(
                        "Save",
                        id="review-test-action",
                        href=None if open_boundary else "/research/run-test",
                        className="primary-action" if not open_boundary else "primary-action setup-action-disabled",
                        title=(
                            "Resolve every implementation blocker before final review."
                            if open_boundary
                            else "Review this immutable saved setup before running it."
                        ),
                    ),
                    html.Button("Revise", type="button", disabled=open_boundary, className="secondary-action"),
                    html.Button("Reject", type="button", disabled=open_boundary, className="danger-action"),
                ],
                className="setup-decision-actions",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("1 / 5" if open_boundary else "5 / 5", className="setup-readiness-ring"),
                            html.Div(
                                [
                                    html.Strong("1 of 5 ready" if open_boundary else "5 of 5 ready"),
                                    html.Span("Implementation is the next missing requirement." if open_boundary else "The test can move to final review."),
                                ]
                            ),
                        ],
                        className="setup-readiness-overview",
                    ),
                    html.Div(
                        [_readiness_check(tone, label) for tone, label in checks],
                        className="setup-readiness-checks",
                    ),
                    html.Div(
                        [
                            html.Strong(
                                "No owner action right now"
                                if open_boundary
                                else "Ready for your final review"
                            ),
                            html.P(
                                (
                                    "Quant Factory is waiting for the exact implementation. It will not substitute a fixture or unrelated strategy."
                                    if open_boundary
                                    else "The saved test can now move to the separate Run test review page."
                                ),
                                className="field-help",
                            ),
                        ],
                        className=(
                            "operator-message operator-message-warning setup-boundary-note"
                            if open_boundary
                            else "operator-message operator-message-success setup-boundary-note"
                        ),
                    ),
                    html.Div(
                        [
                            dcc.Dropdown(
                                id="setup-strategy-selector",
                                options=[],
                                value=None,
                                clearable=False,
                                disabled=True,
                            ),
                            html.Div(id="setup-parameter-controls"),
                            html.Div(
                                "No exact Candidate implementation is linked yet.",
                                id="idea-configuration-status",
                            ),
                            html.Button(
                                "Waiting for implementation",
                                id="save-idea-configuration",
                                n_clicks=0,
                                disabled=True,
                            ),
                        ],
                        className="setup-callback-controls",
                    ),
                ],
                className="setup-create-body",
            ),
        ],
        className="setup-create-disclosure",
    )


def _readiness_check(tone: str, label: str) -> html.Div:
    symbol = "✓" if tone == "complete" else "!" if tone == "missing" else "○"
    return html.Div(
        [html.Span(symbol, **{"aria-hidden": "true"}), html.Strong(label)],
        className=f"setup-readiness-check setup-readiness-check-{tone}",
    )
