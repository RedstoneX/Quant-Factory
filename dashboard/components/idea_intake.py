"""Presentation-only guidance for the two safe idea-intake paths."""

from __future__ import annotations

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
