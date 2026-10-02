"""Durable operator idea workbench for the existing research workflow."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from dash import dcc, html

from dashboard.candidate_workflow import candidate_review_state
from dashboard.components.candidate_brief import candidate_brief
from dashboard.components.idea_intake import (
    assisted_idea_path,
    idea_action_footer,
    manual_idea_path,
    start_path_selector,
)
from dashboard.components.idea_review import idea_review_workspace
from dashboard.run_adapter import IdeaDraftView, list_idea_drafts
from research_intake import CandidateValidation, parse_candidate_packet, validate_candidate_packet


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
                                (
                                    "Setup saved"
                                    if draft.configuration_id
                                    else "Candidate"
                                    if draft.candidate_json
                                    else "Draft"
                                ),
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


def _candidate_validation_data(validation: CandidateValidation) -> dict[str, Any]:
    return {
        "document": validation.document,
        "canonical_json": validation.canonical_json,
        "issues": [
            {
                "severity": issue.severity,
                "code": issue.code,
                "path": issue.path,
                "message": issue.message,
            }
            for issue in validation.issues
        ],
        "valid": validation.valid,
        "review_ready": validation.review_ready,
        "parameter_combinations": validation.parameter_combinations,
    }


def _stored_candidate_state(
    candidate_json: str,
) -> tuple[str, dict[str, Any], Any, Any]:
    if not candidate_json:
        return "", {}, _candidate_prompt(), _candidate_status_prompt()
    try:
        document = parse_candidate_packet(candidate_json, format_hint="json")
        validation = validate_candidate_packet(document)
    except ValueError:
        return candidate_json, {}, _candidate_prompt(), html.Div(
            [
                html.Strong("Saved Candidate cannot be read"),
                html.P("The stored packet needs repair before it can be reviewed or exported."),
            ],
            className="candidate-validation candidate-validation-error",
        )
    return (
        json.dumps(validation.document, indent=2, ensure_ascii=False, sort_keys=True),
        _candidate_validation_data(validation),
        candidate_brief(validation.document, validation),
        _candidate_status(validation, saved=True),
    )


def _candidate_status(
    validation: CandidateValidation,
    *,
    saved: bool = False,
) -> html.Div:
    errors = len(validation.errors)
    warnings = len(validation.warnings)
    high_questions = sum(
        1
        for question in validation.document.get("open_questions", []) or []
        if isinstance(question, Mapping)
        and str(question.get("importance", "")).lower() == "high"
    )
    if errors:
        headline = f"{errors} validation error{'s' if errors != 1 else ''}"
        tone = "error"
    elif high_questions:
        headline = f"Valid packet · {high_questions} high-importance question{'s' if high_questions != 1 else ''} unresolved"
        tone = "warning"
    else:
        headline = "Valid Candidate · ready for owner review"
        tone = "success"
    return html.Div(
        [
            html.Div(
                [
                    html.Strong(("Saved · " if saved else "") + headline),
                    html.Span(
                        f"{validation.parameter_combinations:,} bounded sweep combinations",
                        className="candidate-validation-count",
                    ),
                ],
                className="candidate-validation-heading",
            ),
            html.P(
                "Validation never approves, implements, launches, or tests this Candidate.",
                className="field-help",
            ),
            html.Ul(
                [
                    html.Li(
                        [
                            html.Strong(f"{issue.path}: "),
                            issue.message,
                        ],
                        className=f"candidate-issue candidate-issue-{issue.severity}",
                    )
                    for issue in validation.issues
                ]
                or [html.Li("No validation warnings or errors.")],
                className="candidate-issue-list",
            ),
        ],
        className=f"candidate-validation candidate-validation-{tone}",
    )


def _candidate_status_prompt() -> html.Div:
    return html.Div(
        [
            html.Strong("No Candidate validated"),
            html.P("Paste or upload QF Candidate v1, then validate it locally."),
        ],
        className="candidate-validation candidate-validation-neutral",
    )


def _candidate_prompt() -> html.Div:
    return html.Div(
        [
            html.Strong("The readable Candidate brief will appear here."),
            html.P(
                "Ordinary idea capture above remains available. Candidate import is an optional standardized intake path."
            ),
        ],
        className="candidate-empty-state",
    )


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
    candidate_text, candidate_validation, candidate_brief, candidate_status = (
        _stored_candidate_state(selected.candidate_json if selected else "")
    )
    candidate_status_value, can_continue = candidate_review_state(selected)
    candidate_document = candidate_validation.get("document") or {}
    candidate_record = (
        candidate_document.get("candidate")
        if isinstance(candidate_document, Mapping)
        else {}
    )
    candidate_record = candidate_record if isinstance(candidate_record, Mapping) else {}
    candidate_family = str(candidate_record.get("family") or "Selected idea")
    selected_kicker = candidate_family.replace("_", " ").title()
    if candidate_status_value:
        selected_kicker += f" · {candidate_status_value.replace('_', ' ').title()}"
    candidate_statuses = tuple(candidate_review_state(draft)[0] for draft in available)
    queue_counts = (
        sum(status not in {"owner_approved", "rejected"} for status in candidate_statuses),
        candidate_statuses.count("owner_approved"),
        candidate_statuses.count("rejected"),
    )

    return html.Div(
        [
            dcc.Store(
                id="idea-draft-store",
                data=selected_data,
                storage_type="session",
            ),
            dcc.Store(
                id="candidate-validation-store",
                data=candidate_validation,
                storage_type="memory",
            ),
            dcc.Store(
                id="candidate-editor-draft-id",
                data=selected.draft_id if selected else None,
                storage_type="memory",
            ),
            dcc.Download(id="candidate-download"),
            dcc.Download(id="research-context-download"),
            dcc.ConfirmDialog(
                id="confirm-discard-idea-draft",
                message="Delete this unlinked idea draft from local Quant Factory storage?",
            ),
            html.Header(
                [
                    html.Div(
                        [
                            html.P("RESEARCH / IDEAS", className="page-eyebrow"),
                            html.H1(
                                "Review research ideas",
                                id="idea-workbench-title",
                                className="page-title",
                            ),
                            html.P(
                                "Agent suggestions and your own ideas arrive in one place. Review, revise, and prepare only the idea you choose.",
                                className="page-description",
                            ),
                        ],
                        className="idea-workbench-heading-copy",
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Research context",
                                id="export-research-context-yaml",
                                n_clicks=0,
                                className="secondary-action idea-context-download",
                            ),
                            html.A(
                                [html.Span("+", **{"aria-hidden": "true"}), "Add / import"],
                                href="#idea-intake",
                                className="primary-action idea-new-action",
                            ),
                        ],
                        className="idea-heading-actions",
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
                            html.Span("QF Candidate v1", className="idea-context-chip"),
                            html.Span("No automatic execution", className="idea-context-chip"),
                        ],
                        className="idea-context-chips",
                    ),
                ],
                id="idea-context-bar",
                className="idea-context-bar idea-path-hidden",
            ),
            *idea_review_workspace(
                draft_count=len(available),
                draft_options=_draft_options(available),
                selected=selected,
                candidate_brief=candidate_brief,
                candidate_valid=bool(candidate_validation.get("valid")),
                candidate_status=candidate_status_value,
                can_continue=can_continue,
                queue_counts=queue_counts,
                selected_kicker=selected_kicker,
            ),
            html.Div(id="idea-intake"),
            start_path_selector(),
            manual_idea_path(),
            assisted_idea_path(
                candidate_text=candidate_text,
                candidate_status=candidate_status,
                candidate_valid=bool(candidate_validation.get("valid")),
                candidate_saved=bool(selected and selected.candidate_json),
            ),
            idea_action_footer(
                _readable_time(selected.updated_at) if selected else None
            ),
        ],
        className="page-container ideas-page idea-workbench-page",
    )
