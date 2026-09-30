"""Durable operator idea workbench for the existing research workflow."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dash import dcc, html

from dashboard.run_adapter import IdeaDraftView, list_idea_drafts


def _readable_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return value
    return parsed.strftime("%b %-d, %H:%M UTC")


def _draft_options(drafts: tuple[IdeaDraftView, ...]) -> list[dict[str, object]]:
    return [
        {
            "label": html.Div(
                [
                    html.Strong(draft.title, className="idea-history-title"),
                    html.Div(
                        [
                            html.Span(
                                "Setup saved" if draft.configuration_id else "Draft",
                                className=(
                                    "idea-history-state idea-history-state-ready"
                                    if draft.configuration_id
                                    else "idea-history-state"
                                ),
                            ),
                            html.Time(
                                _readable_time(draft.updated_at),
                                dateTime=draft.updated_at,
                            ),
                        ],
                        className="idea-history-meta",
                    ),
                ],
                className="idea-history-label",
            ),
            "value": draft.draft_id,
        }
        for draft in drafts
    ]


def _brief_value(value: str | None, empty: str) -> str:
    return value.strip() if value and value.strip() else empty


def layout(
    *,
    database: str | Path | None = None,
    drafts: tuple[IdeaDraftView, ...] | None = None,
) -> html.Div:
    """Return the working intake UI without retrieving or executing a source."""

    available = (
        list_idea_drafts(database)
        if drafts is None and database is not None
        else drafts or ()
    )
    selected = available[0] if available else None
    selected_data = selected.to_store() if selected else {}

    return html.Div(
        [
            dcc.Store(
                id="idea-draft-store",
                data=selected_data,
                storage_type="session",
            ),
            dcc.ConfirmDialog(
                id="confirm-discard-idea-draft",
                message="Delete this unlinked idea draft from local Quant Factory storage?",
            ),
            html.Header(
                [
                    html.Div(
                        [
                            html.P("RESEARCH / IDEA WORKBENCH", className="page-eyebrow"),
                            html.H1(
                                selected.title if selected else "New research idea",
                                id="idea-workbench-title",
                                className="page-title",
                            ),
                            html.P(
                                "Keep the source, your reasoning, and the evolving research brief together.",
                                className="page-description",
                            ),
                        ],
                        className="idea-workbench-heading-copy",
                    ),
                    html.Button(
                        [html.Span("+", **{"aria-hidden": "true"}), "New idea"],
                        id="new-idea-draft",
                        n_clicks=0,
                        className="primary-action idea-new-action",
                    ),
                ],
                className="page-heading idea-workbench-heading",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                "Draft saved" if selected else "New draft",
                                id="idea-workbench-state",
                                className=(
                                    "idea-state-badge idea-state-saved"
                                    if selected
                                    else "idea-state-badge"
                                ),
                            ),
                            html.Span(
                                (
                                    f"Updated {_readable_time(selected.updated_at)}"
                                    if selected
                                    else "Nothing runs until you deliberately continue"
                                ),
                                id="idea-workbench-meta",
                                className="idea-context-meta",
                            ),
                        ],
                        className="idea-context-status",
                    ),
                    html.Div(
                        [
                            html.Span("Local draft", className="idea-context-chip"),
                            html.Span("No automatic execution", className="idea-context-chip"),
                        ],
                        className="idea-context-chips",
                    ),
                ],
                className="idea-context-bar",
            ),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2("Idea history"),
                                            html.Span(
                                                str(len(available)),
                                                id="idea-history-count",
                                                className="idea-count-badge",
                                            ),
                                        ],
                                        className="idea-panel-title-row",
                                    ),
                                    html.P(
                                        "Open any saved ingestion without losing its context.",
                                        className="idea-panel-description",
                                    ),
                                ],
                                className="idea-panel-heading",
                            ),
                            dcc.RadioItems(
                                id="idea-draft-selector",
                                options=_draft_options(available),
                                value=selected.draft_id if selected else None,
                                className="idea-history-selector",
                            ),
                            html.Div(
                                [
                                    html.Strong("No saved ideas yet"),
                                    html.P("Your first saved draft will appear here."),
                                ],
                                id="idea-history-empty",
                                className="idea-history-empty",
                                style={} if not available else {"display": "none"},
                            ),
                        ],
                        className="idea-workbench-panel idea-history-panel",
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
                            html.Div(
                                [
                                    html.Label("Idea title", htmlFor="idea-title", className="field-label"),
                                    dcc.Input(
                                        id="idea-title",
                                        type="text",
                                        maxLength=120,
                                        placeholder="e.g. First-hour momentum after a narrow overnight range",
                                        className="idea-workbench-input",
                                    ),
                                ],
                                className="idea-workbench-field",
                            ),
                            html.Div(
                                [
                                    html.Label("What might be true?", htmlFor="idea-description", className="field-label"),
                                    dcc.Textarea(
                                        id="idea-description",
                                        maxLength=2000,
                                        placeholder="Describe the market behavior or directional edge in plain language.",
                                        className="idea-workbench-textarea idea-hypothesis-input",
                                    ),
                                ],
                                className="idea-workbench-field",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label("Source link", htmlFor="idea-source-url", className="field-label"),
                                            dcc.Input(
                                                id="idea-source-url",
                                                type="text",
                                                maxLength=2048,
                                                placeholder="https://…",
                                                className="idea-workbench-input",
                                            ),
                                        ],
                                        className="idea-workbench-field",
                                    ),
                                    html.Div(
                                        [
                                            html.Label("Source / attribution", htmlFor="idea-attribution", className="field-label"),
                                            dcc.Input(
                                                id="idea-attribution",
                                                type="text",
                                                maxLength=240,
                                                placeholder="Paper, article, discussion, or observation",
                                                className="idea-workbench-input",
                                            ),
                                        ],
                                        className="idea-workbench-field",
                                    ),
                                ],
                                className="idea-source-fields",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Questions, constraints & uncertainty",
                                        htmlFor="idea-notes",
                                        className="field-label",
                                    ),
                                    dcc.Textarea(
                                        id="idea-notes",
                                        maxLength=2000,
                                        placeholder="What needs clarification? What must not be optimized or assumed?",
                                        className="idea-workbench-textarea",
                                    ),
                                ],
                                className="idea-workbench-field",
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
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2("Research brief"),
                                            html.P(
                                                "A scannable view of the draft that will move into setup.",
                                                className="idea-panel-description",
                                            ),
                                        ]
                                    ),
                                    html.Span("Needs your input", id="idea-brief-state", className="idea-brief-badge"),
                                ],
                                className="idea-panel-heading idea-panel-heading-split",
                            ),
                            html.Dl(
                                [
                                    html.Div(
                                        [
                                            html.Dt("Hypothesis"),
                                            html.Dd(
                                                _brief_value(
                                                    selected.description if selected else "",
                                                    "Describe the behavior you want to investigate.",
                                                ),
                                                id="idea-brief-hypothesis",
                                            ),
                                        ],
                                        className="idea-brief-row idea-brief-row-primary",
                                    ),
                                    html.Div(
                                        [
                                            html.Dt("Source basis"),
                                            html.Dd(
                                                _brief_value(
                                                    selected.attribution if selected else "",
                                                    "No source or owner observation recorded yet.",
                                                ),
                                                id="idea-brief-source",
                                            ),
                                        ],
                                        className="idea-brief-row",
                                    ),
                                    html.Div(
                                        [
                                            html.Dt("Open questions"),
                                            html.Dd(
                                                _brief_value(
                                                    selected.notes if selected else "",
                                                    "Record the uncertainties that must be resolved before testing.",
                                                ),
                                                id="idea-brief-questions",
                                            ),
                                        ],
                                        className="idea-brief-row",
                                    ),
                                    html.Div(
                                        [
                                            html.Dt("Setup"),
                                            html.Dd(
                                                "Bounded setup saved" if selected and selected.configuration_id else "Not prepared",
                                                id="idea-brief-setup",
                                            ),
                                        ],
                                        className="idea-brief-row",
                                    ),
                                ],
                                className="idea-brief-list",
                            ),
                            html.Div(
                                [
                                    html.Span("Next useful action", className="idea-next-label"),
                                    html.Strong(
                                        "Save this draft, then continue to Set up."
                                        if selected
                                        else "Add a title and hypothesis, then save the draft.",
                                        id="idea-next-action-copy",
                                    ),
                                ],
                                className="idea-next-action",
                            ),
                        ],
                        className="idea-workbench-panel idea-brief-panel",
                    ),
                ],
                className="idea-workbench-grid",
            ),
            html.Footer(
                [
                    html.Div(
                        [
                            html.Strong("Intake only — nothing will run"),
                            html.Div(
                                f"Saved locally {_readable_time(selected.updated_at)}." if selected else "Nothing is saved yet.",
                                id="idea-draft-status",
                                className="save-message",
                            ),
                        ],
                        className="idea-action-copy",
                    ),
                    dcc.Link(
                        "Continue to Set up →",
                        id="continue-idea-to-setup",
                        href="/research/setup" if selected else None,
                        className="primary-action" if selected else "primary-action action-disabled",
                    ),
                ],
                className="idea-action-bar",
            ),
        ],
        className="page-container ideas-page idea-workbench-page",
    )
