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
                            html.Div(
                                [
                                    html.Label(
                                        "Linked Candidate implementation",
                                        htmlFor="setup-strategy-selector",
                                        className="field-label",
                                    ),
                                    dcc.Dropdown(
                                        id="setup-strategy-selector",
                                        options=[],
                                        value=None,
                                        clearable=False,
                                        placeholder="No approved implementation available",
                                        disabled=True,
                                    ),
                                    html.P(
                                        "This remains empty until the exact accepted Candidate has approved strategy logic and an immutable saved configuration.",
                                        className="field-help",
                                    ),
                                ],
                                className="setup-create-field",
                            ),
                            html.Div(
                                [
                                    html.H3("Allowed choices"),
                                    html.P(
                                        "Only values declared by the approved strategy specification are available.",
                                        className="field-help",
                                    ),
                                    html.Div(id="setup-parameter-controls", className="setup-parameter-list"),
                                ],
                                className="setup-parameter-panel",
                            ),
                        ],
                        className="setup-create-grid",
                    ),
                    html.Div(
                        [
                            html.Div(
                                "No exact Candidate implementation is linked yet.",
                                id="idea-configuration-status",
                                className="save-message setup-save-status",
                            ),
                            html.Button(
                                "Waiting for implementation",
                                id="save-idea-configuration",
                                n_clicks=0,
                                disabled=True,
                                className="primary-action",
                            ),
                        ],
                        className="setup-create-actions",
                    ),
                    html.Div(
                        [
                            html.Strong("Why this may still be blocked"),
                            html.P(
                                "The Candidate identity, rules, data boundary and costs must match before Run test becomes available."
                            ),
                        ],
                        className="operator-message operator-message-warning setup-boundary-note",
                    ),
                ],
                className="setup-create-body",
            ),
        ],
        className="setup-create-disclosure",
        open=open_boundary,
    )
