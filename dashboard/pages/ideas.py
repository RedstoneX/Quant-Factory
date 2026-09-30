"""Safe, non-executing Milestone 23 idea-draft page."""

from __future__ import annotations

from pathlib import Path

from dash import dcc, html

from dashboard.pages.common import page_heading
from dashboard.run_adapter import IdeaDraftView, list_idea_drafts


def _draft_options(drafts: tuple[IdeaDraftView, ...]) -> list[dict[str, str]]:
    return [
        {
            "label": (
                f"{draft.title} · {draft.updated_at}"
                + (" · setup saved" if draft.configuration_id else "")
            ),
            "value": draft.draft_id,
        }
        for draft in drafts
    ]


def layout(
    *,
    database: str | Path | None = None,
    drafts: tuple[IdeaDraftView, ...] | None = None,
) -> html.Div:
    """Return durable operator-authored intake with no research actions."""

    from dashboard.application import _strategy_research_path

    available = (
        list_idea_drafts(database)
        if drafts is None and database is not None
        else drafts or ()
    )
    selected = available[0] if available else None

    return html.Div(
        [
            page_heading(
                "RESEARCH / IDEAS",
                "Ideas",
                (
                    "Capture a private local draft for later setup without retrieving "
                    "or running anything."
                ),
            ),
            _strategy_research_path("/research/ideas"),
            dcc.Store(
                id="idea-draft-store",
                data=selected.to_store() if selected else {},
                storage_type="session",
            ),
            dcc.ConfirmDialog(
                id="confirm-discard-idea-draft",
                message="Delete this unlinked idea draft from local Quant Factory storage?",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span(
                                "Intake only — nothing will run",
                                className="pending-state-badge",
                            ),
                            html.P(
                                (
                                    "Links are stored as text only. Quant Factory will not "
                                    "open, preview, download, summarize, approve, or execute "
                                    "this draft."
                                ),
                                className="field-help",
                            ),
                        ],
                        className="operator-message operator-message-info",
                    ),
                    html.Label(
                        "Saved drafts",
                        htmlFor="idea-draft-selector",
                        className="field-label",
                    ),
                    dcc.Dropdown(
                        id="idea-draft-selector",
                        options=_draft_options(available),
                        value=selected.draft_id if selected else None,
                        placeholder="Start a new draft",
                        clearable=True,
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
                                id="continue-idea-to-setup",
                                href="/research/setup" if selected else None,
                                className="secondary-action",
                            ),
                        ],
                        className="page-actions idea-draft-actions",
                    ),
                    html.Div(
                        (
                            (
                                f"Draft saved locally at {selected.updated_at}. Nothing was "
                                "retrieved or run."
                            )
                            if selected
                            else "Empty draft — nothing is saved locally."
                        ),
                        id="idea-draft-status",
                        className="save-message",
                    ),
                ],
                className="panel idea-draft-panel",
            ),
        ],
        className="page-container ideas-page",
    )
