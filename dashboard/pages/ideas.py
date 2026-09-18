"""Safe, non-executing Milestone 23 idea-draft page."""

from __future__ import annotations

from dash import dcc, html

from dashboard.pages.common import page_heading


def layout() -> html.Div:
    """Return an operator-authored draft surface with no research actions."""

    return html.Div(
        [
            page_heading(
                "RESEARCH / IDEAS",
                "Ideas",
                "Capture a private draft for later review without retrieving or running anything.",
            ),
            dcc.Store(id="idea-draft-store", storage_type="session"),
            dcc.ConfirmDialog(
                id="confirm-discard-idea-draft",
                message="Discard the unsaved idea draft from this browser session?",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span(
                                "Draft only — nothing will run",
                                className="pending-state-badge",
                            ),
                            html.P(
                                "Links are stored as text only. Quant Factory will not open, preview, download, summarize, approve, or execute this draft.",
                                className="field-help",
                            ),
                        ],
                        className="operator-message operator-message-info",
                    ),
                    html.Label("Idea title", htmlFor="idea-title", className="field-label"),
                    dcc.Input(
                        id="idea-title",
                        type="text",
                        maxLength=120,
                        placeholder="Short operator-authored title",
                        className="idea-draft-input",
                    ),
                    html.Label(
                        "Description",
                        htmlFor="idea-description",
                        className="field-label",
                    ),
                    dcc.Textarea(
                        id="idea-description",
                        maxLength=2000,
                        placeholder="What might be worth testing later?",
                        className="idea-draft-textarea",
                    ),
                    html.Label(
                        "Source URL (optional text only)",
                        htmlFor="idea-source-url",
                        className="field-label",
                    ),
                    dcc.Input(
                        id="idea-source-url",
                        type="text",
                        maxLength=2048,
                        placeholder="https://example.com/source",
                        className="idea-draft-input",
                    ),
                    html.Label(
                        "Source type and attribution",
                        htmlFor="idea-attribution",
                        className="field-label",
                    ),
                    dcc.Input(
                        id="idea-attribution",
                        type="text",
                        maxLength=240,
                        placeholder="Article, paper, discussion, or owner observation",
                        className="idea-draft-input",
                    ),
                    html.Label(
                        "Assumptions, questions, and uncertainty",
                        htmlFor="idea-notes",
                        className="field-label",
                    ),
                    dcc.Textarea(
                        id="idea-notes",
                        maxLength=2000,
                        placeholder="Record uncertainty before any later approval or research.",
                        className="idea-draft-textarea",
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Save draft",
                                id="save-idea-draft",
                                n_clicks=0,
                                className="primary-action",
                            ),
                            html.Button(
                                "Discard draft",
                                id="discard-idea-draft",
                                n_clicks=0,
                                className="secondary-action",
                            ),
                            dcc.Link(
                                "Continue to Set up",
                                href="/research/setup",
                                className="secondary-action",
                            ),
                        ],
                        className="page-actions idea-draft-actions",
                    ),
                    html.Div(
                        "Empty draft — nothing is saved in this browser session.",
                        id="idea-draft-status",
                        className="save-message",
                    ),
                ],
                className="panel idea-draft-panel",
            ),
        ],
        className="page-container ideas-page",
    )
