"""Presentation-only guidance for the two safe idea-intake paths."""

from __future__ import annotations

from typing import Any

from dash import dcc, html


def start_path_selector() -> html.Section:
    """Ask the owner for one plain-language starting path."""

    def option(letter: str, title: str, description: str) -> html.Div:
        return html.Div(
            [
                html.Span(letter, className="idea-start-letter"),
                html.Div([html.Strong(title), html.P(description)]),
                html.Span("Choose →", className="idea-start-choose"),
            ],
            className="idea-start-card-content",
        )

    return html.Section(
        [
            html.P("START HERE", className="page-eyebrow"),
            html.H2("How do you want to start?"),
            html.P(
                "Choose the path that matches what you have now. You can switch paths without running anything.",
                className="idea-start-lede",
            ),
            dcc.RadioItems(
                id="idea-start-path",
                options=[
                    {
                        "label": option(
                            "A",
                            "I have an idea",
                            "Write it in your own words and save it as a private draft. Nothing runs automatically.",
                        ),
                        "value": "manual",
                    },
                    {
                        "label": option(
                            "B",
                            "I want help researching or structuring an idea",
                            "Use Claude, Grok, ChatGPT, Gemini, or another researcher, then bring the result back here.",
                        ),
                        "value": "assisted",
                    },
                ],
                value=None,
                className="idea-start-options",
            ),
        ],
        className="idea-start-panel",
    )


def candidate_research_guide() -> html.Section:
    """Explain where a Candidate comes from before exposing import controls."""

    step_labels = (
        "Download QF Context",
        "Give it to your researcher or AI",
        "Get back a QF Candidate file",
        "Upload or paste it here",
        "Validate",
        "Read the plain-English brief",
        "Save",
    )
    return html.Section(
        [
            html.P("GUIDED RESEARCH PATH", className="page-eyebrow"),
            html.H2("Bring in a researched strategy idea"),
            html.P(
                "You do not write a technical Candidate file yourself. Follow these steps to ask a researcher or AI for one, then bring it back to Quant Factory.",
                className="idea-assisted-lede",
            ),
            html.Ol(
                [
                    html.Li([html.Span(str(index)), html.Strong(label)])
                    for index, label in enumerate(step_labels, start=1)
                ],
                className="candidate-step-strip",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("1", className="candidate-step-number"),
                            html.Div(
                                [
                                    html.H3("Download the Quant Factory research context"),
                                    html.P(
                                        "This tells the researcher what Quant Factory accepts, what evidence matters, and what is out of bounds. YAML and JSON are two versions of the same file; choose either one."
                                    ),
                                ]
                            ),
                        ],
                        className="candidate-guide-copy",
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Download JSON version",
                                id="export-research-context-json",
                                n_clicks=0,
                                className="secondary-action",
                            ),
                        ],
                        className="candidate-context-actions",
                    ),
                ],
                className="candidate-context-step",
            ),
            html.Div(
                [
                    html.Strong("Next, give that file to your researcher or AI."),
                    html.P(
                        "Ask it to return a QF Candidate v1 YAML or JSON file. That is simply a structured text file—you do not normally write or edit it yourself."
                    ),
                ],
                className="candidate-researcher-callout",
            ),
        ],
        className="idea-assisted-guide",
    )


def manual_idea_path() -> html.Main:
    """Render the owner-authored draft editor with its established callback IDs."""

    return html.Main(
        [
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.P("WRITE IT IN YOUR OWN WORDS", className="page-eyebrow"),
                                    html.H2("Capture your idea as a private draft"),
                                    html.P(
                                        "Describe what you think may be happening in the market. Quant Factory saves your words locally; nothing is researched, tested, or run automatically."
                                    ),
                                ]
                            ),
                            html.Button(
                                "New blank idea",
                                id="new-idea-draft",
                                n_clicks=0,
                                className="secondary-action idea-new-draft-action",
                            ),
                        ],
                        className="manual-path-heading",
                    ),
                ],
                className="manual-path-intro",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("Source & context"),
                                    html.P(
                                        "Record what prompted the idea. Links are stored as text only; Quant Factory will not open, preview, download, summarize, approve, or execute them here.",
                                        className="idea-panel-description",
                                    ),
                                ]
                            ),
                            html.Span("Text only", id="idea-source-state", className="idea-source-badge"),
                        ],
                        className="idea-panel-heading idea-panel-heading-split",
                    ),
                    _field("Idea title", "idea-title", dcc.Input(
                        id="idea-title",
                        type="text",
                        maxLength=120,
                        placeholder="e.g. First-hour momentum after a narrow overnight range",
                        className="idea-workbench-input",
                    )),
                    _field("What might be true?", "idea-description", dcc.Textarea(
                        id="idea-description",
                        maxLength=2000,
                        placeholder="Describe the market behavior or directional edge in plain language.",
                        className="idea-workbench-textarea idea-hypothesis-input",
                    )),
                    html.Div(
                        [
                            _field("Source link", "idea-source-url", dcc.Input(
                                id="idea-source-url",
                                type="text",
                                maxLength=2048,
                                placeholder="https://…",
                                className="idea-workbench-input",
                            )),
                            _field("Source / attribution", "idea-attribution", dcc.Input(
                                id="idea-attribution",
                                type="text",
                                maxLength=240,
                                placeholder="Paper, article, discussion, or observation",
                                className="idea-workbench-input",
                            )),
                        ],
                        className="idea-source-fields",
                    ),
                    _field(
                        "Questions, constraints & uncertainty",
                        "idea-notes",
                        dcc.Textarea(
                            id="idea-notes",
                            maxLength=2000,
                            placeholder="What needs clarification? What must not be optimized or assumed?",
                            className="idea-workbench-textarea",
                        ),
                    ),
                    html.Div(
                        [
                            html.Button("Save draft", id="save-idea-draft", n_clicks=0, className="primary-action"),
                            html.Button("Discard", id="discard-idea-draft", n_clicks=0, className="secondary-action"),
                        ],
                        className="idea-editor-actions",
                    ),
                ],
                className="idea-workbench-panel idea-editor-panel",
            ),
        ],
        id="manual-idea-path",
        className="idea-workbench-grid idea-path-panel idea-path-hidden",
    )


def assisted_idea_path(
    *,
    candidate_text: str,
    candidate_status: Any,
    candidate_valid: bool,
    candidate_saved: bool,
) -> html.Div:
    """Render upload/validation controls without cluttering the review surface."""

    return html.Div(
        [
            candidate_research_guide(),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.P("STEPS 4–5", className="page-eyebrow"),
                                    html.H2("Upload and check the Candidate file"),
                                    html.P(
                                        "Bring back the YAML or JSON file from your researcher. Quant Factory checks its structure locally; it does not run a strategy.",
                                        className="idea-panel-description",
                                    ),
                                ]
                            ),
                            html.Span("Nothing runs", className="surface-badge"),
                        ],
                        className="candidate-intake-heading",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    dcc.Upload(
                                        id="candidate-file-upload",
                                        accept=".yaml,.yml,.json,application/json,application/yaml,text/yaml",
                                        multiple=False,
                                        children=html.Div(
                                            [
                                                html.Strong("Choose the Candidate file you received"),
                                                html.Span("Drop it here, or browse for .yaml, .yml, or .json"),
                                            ]
                                        ),
                                        className="candidate-upload",
                                    ),
                                    html.Div(
                                        "No Candidate file selected yet.",
                                        id="candidate-upload-status",
                                        className="field-help",
                                    ),
                                    html.Details(
                                        [
                                            html.Summary("Or paste the file contents"),
                                            html.P(
                                                "Use this only when your researcher returned text instead of a downloadable file.",
                                                className="field-help",
                                            ),
                                            html.Label("Candidate file contents", htmlFor="candidate-packet-input", className="field-label"),
                                            dcc.Textarea(
                                                id="candidate-packet-input",
                                                value=candidate_text,
                                                placeholder="Paste the complete QF Candidate text here…",
                                                className="candidate-packet-input",
                                            ),
                                        ],
                                        className="candidate-paste-disclosure",
                                    ),
                                ],
                                className="candidate-editor",
                            ),
                            _candidate_control_rail(candidate_status, candidate_valid, candidate_saved),
                        ],
                        className="candidate-intake-grid",
                    ),
                ],
                className="idea-workbench-panel candidate-intake-panel",
            ),
        ],
        id="assisted-idea-path",
        className="idea-path-panel idea-path-hidden",
    )


def idea_action_footer(saved_at: str | None) -> html.Footer:
    return html.Footer(
        [
            html.Div(
                [
                    html.Strong("Intake only — nothing will run"),
                    html.Div(
                        f"Saved locally {saved_at}." if saved_at else "Nothing is saved yet.",
                        id="idea-draft-status",
                        className="save-message",
                    ),
                ],
                className="idea-action-copy",
            ),
        ],
        id="idea-action-bar",
        className="idea-action-bar idea-path-hidden",
    )


def _field(label: str, component_id: str, control: Any) -> html.Div:
    return html.Div(
        [html.Label(label, htmlFor=component_id, className="field-label"), control],
        className="idea-workbench-field",
    )


def _candidate_control_rail(
    candidate_status: Any, candidate_valid: bool, candidate_saved: bool
) -> html.Aside:
    return html.Aside(
        [
            html.Span("5", className="candidate-step-number"),
            html.H3("Check the file"),
            html.P(
                "Validation checks that the returned idea is complete enough to review. It never approves or runs it.",
                className="field-help",
            ),
            html.Button("Validate Candidate", id="validate-candidate-packet", n_clicks=0, className="primary-action"),
            html.Div(candidate_status, id="candidate-validation-status"),
            html.Div(
                [
                    html.Button(
                        "Save this Candidate",
                        id="save-candidate-packet",
                        n_clicks=0,
                        disabled=not candidate_valid,
                        className="primary-action",
                    ),
                    html.Div(
                        "Candidate saved locally. It is still not approved, implemented, or runnable."
                        if candidate_saved
                        else "Review the plain-English brief, then save when you are satisfied.",
                        id="candidate-action-status",
                        className="field-help candidate-action-status",
                    ),
                ],
                id="candidate-valid-actions",
                className="candidate-valid-actions" if candidate_valid else "candidate-valid-actions idea-path-hidden",
            ),
        ],
        className="candidate-control-rail",
    )
