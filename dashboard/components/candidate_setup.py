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


def candidate_implementation_boundary(*, open_boundary: bool) -> html.Details:
    """Explain the truthful stop when the exact strategy logic is unavailable."""

    return html.Details(
        [
            html.Summary(
                [
                    html.Div(
                        [
                            html.Span("IMPLEMENTATION", className="setup-state-label"),
                            html.Strong("Exact implementation required"),
                            html.Small("An agent must implement and bind this accepted Candidate"),
                        ]
                    ),
                    html.Span("Open →", className="setup-disclosure-action"),
                ],
                className="setup-create-summary",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("No substitute implementation"),
                                    html.P(
                                        "Quant Factory will not let an existing fixture or unrelated strategy stand in for the Candidate you accepted.",
                                        className="section-description",
                                    ),
                                ]
                            ),
                            html.Span("Specification-bound", className="surface-badge surface-badge-safe"),
                        ],
                        className="setup-section-heading setup-create-heading",
                    ),
                    html.Div(
                        [
                            _boundary_step(
                                "1",
                                "Implement the exact rules",
                                "Use this Candidate's declared entry, exit, session and cost assumptions.",
                            ),
                            _boundary_step(
                                "2",
                                "Bind one immutable version",
                                "The saved configuration must identify this Candidate—not a fixture or another strategy.",
                            ),
                            _boundary_step(
                                "3",
                                "Verify local data",
                                "Only then can final review and one research run become available.",
                            ),
                        ],
                        className="setup-boundary-steps",
                    ),
                    html.Div(
                        [
                            html.Strong("Blocked truthfully"),
                            html.P(
                                "No test can be prepared until an agent implements and binds this exact accepted Candidate.",
                                className="field-help",
                            ),
                        ],
                        className="operator-message operator-message-warning setup-boundary-note",
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
        open=open_boundary,
    )


def _boundary_step(number: str, title: str, description: str) -> html.Div:
    return html.Div(
        [
            html.Span(number, className="setup-boundary-step-number"),
            html.Div([html.Strong(title), html.P(description, className="field-help")]),
        ],
        className="setup-boundary-step",
    )
