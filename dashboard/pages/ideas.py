"""Durable operator idea workbench for the existing research workflow."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from dash import dcc, html

from dashboard.candidate_workflow import candidate_review_state
from dashboard.components.idea_intake import candidate_research_guide, start_path_selector
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
        _candidate_brief(validation.document, validation),
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


def _candidate_brief(
    document: Mapping[str, Any],
    validation: CandidateValidation,
) -> html.Div:
    candidate = _mapping(document.get("candidate"))
    hypothesis = _mapping(document.get("hypothesis"))
    questions = document.get("open_questions", []) or []
    high_questions = sum(
        1
        for question in questions
        if isinstance(question, Mapping)
        and str(question.get("importance", "")).lower() == "high"
    )
    variables = _mapping(document.get("variables"))
    variants = document.get("variants", []) or []
    status = str(candidate.get("status") or "draft").replace("_", " ").title()
    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P("QF CANDIDATE V1", className="page-eyebrow"),
                            html.H2(str(candidate.get("title") or "Untitled Candidate")),
                            html.P(
                                str(candidate.get("one_line") or hypothesis.get("behavior") or "No one-line summary supplied."),
                                className="candidate-brief-lede",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span(status, className="candidate-status-pill"),
                            html.Span(
                                "Owner review ready" if validation.review_ready else "Clarification required",
                                className=(
                                    "candidate-status-pill candidate-status-ready"
                                    if validation.review_ready
                                    else "candidate-status-pill candidate-status-warning"
                                ),
                            ),
                        ],
                        className="candidate-status-group",
                    ),
                ],
                className="candidate-brief-header",
            ),
            html.Div(
                [
                    _candidate_metric("Sweep dimensions", str(len(variables)), "VectorBT-bounded variables"),
                    _candidate_metric("Combinations", f"{validation.parameter_combinations:,}", "Declared grid only"),
                    _candidate_metric("Structural variants", str(len(variants) if isinstance(variants, list) else 0), "Never invented automatically"),
                    _candidate_metric("High questions", str(high_questions), "Must remain visible"),
                ],
                className="candidate-metric-strip",
            ),
            html.Details(
                [
                    html.Summary("Review the complete Candidate packet"),
                    html.Div(
                        [
                            _candidate_section(
                                "Hypothesis", "Why it might work—and fail", hypothesis
                            ),
                            _candidate_section(
                                "Market & session",
                                "Trader-readable scope and holding boundary",
                                document.get("market", {}),
                            ),
                            _candidate_section(
                                "Open questions",
                                "Unresolved means unresolved",
                                questions,
                                warning=bool(high_questions),
                            ),
                            _candidate_section(
                                "Evaluation boundary",
                                "Evidence contract, not profitability",
                                document.get("evaluation", {}),
                            ),
                            _candidate_section(
                                "Source attribution",
                                "Original producers and references",
                                document.get("sources", []),
                            ),
                            _candidate_section(
                                "Source rules",
                                "What the source actually states",
                                document.get("source_rules", {}),
                            ),
                            _candidate_section(
                                "QF interpretation",
                                "Explicit interpretation, never silently inferred",
                                document.get("qf_interpretation", {}),
                                warning=not bool(document.get("qf_interpretation")),
                            ),
                            _candidate_section(
                                "Testable rules",
                                "Structured English; never executable code",
                                document.get("rules", {}),
                            ),
                            _candidate_section(
                                "Fixed rules",
                                "Candidate identity; never swept",
                                document.get("fixed", {}),
                            ),
                            _candidate_section(
                                "VectorBT sweep variables",
                                "Only these bounded dimensions may be enumerated",
                                variables,
                                accent="sweep",
                            ),
                            _candidate_section(
                                "Structural variants",
                                "Different logic paths; support or implementation required",
                                variants,
                                accent="variant",
                            ),
                            _candidate_section(
                                "Data needs",
                                "Requirements, not an availability claim",
                                document.get("data_needs", {}),
                            ),
                            _candidate_section(
                                "Exclusions",
                                "Explicitly outside this Candidate",
                                document.get("exclusions", []),
                            ),
                            _candidate_section(
                                "Prior-work claims",
                                "Imported claims remain unverified by QF",
                                document.get("prior_work", {}),
                                warning=bool(document.get("prior_work")),
                            ),
                        ],
                        className="candidate-brief-grid candidate-brief-technical-grid",
                    ),
                ],
                className="technical-details candidate-technical-details",
            ),
            html.Div(
                [
                    html.Strong("Intake boundary"),
                    html.P(
                        "Saving this Candidate records a research proposal only. It does not approve or implement logic, create a runnable configuration, launch VectorBT, inspect protected data, promote a strategy, or submit an order."
                    ),
                ],
                className="candidate-boundary-callout",
            ),
        ],
        className="candidate-readable-brief",
    )


def _candidate_metric(label: str, value: str, detail: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value), html.Small(detail)], className="candidate-metric")


def _candidate_section(
    title: str,
    subtitle: str,
    value: Any,
    *,
    warning: bool = False,
    accent: str = "",
) -> html.Section:
    classes = "candidate-brief-section"
    if warning:
        classes += " candidate-brief-section-warning"
    if accent:
        classes += f" candidate-brief-section-{accent}"
    return html.Section(
        [
            html.Div([html.H3(title), html.P(subtitle)], className="candidate-section-heading"),
            _readable_candidate_value(value),
        ],
        className=classes,
    )


def _readable_candidate_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if not value:
            return html.P("Not specified.", className="candidate-empty-value")
        return html.Dl(
            [
                html.Div(
                    [
                        html.Dt(str(key).replace("_", " ").title()),
                        html.Dd(_readable_candidate_value(item)),
                    ]
                )
                for key, item in value.items()
            ],
            className="candidate-readable-map",
        )
    if isinstance(value, list):
        if not value:
            return html.P("None recorded.", className="candidate-empty-value")
        return html.Ul(
            [html.Li(_readable_candidate_value(item)) for item in value],
            className="candidate-readable-list",
        )
    if value is None or value == "":
        return html.Span("Not specified", className="candidate-empty-value")
    if isinstance(value, bool):
        return html.Span("Yes" if value else "No")
    return html.Span(str(value))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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
            ),
            html.Div(id="idea-intake"),
            start_path_selector(),
            html.Main(
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
                ],
                id="manual-idea-path",
                className="idea-workbench-grid idea-path-panel idea-path-hidden",
            ),
            html.Div(
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
                                                    html.Label(
                                                        "Candidate file contents",
                                                        htmlFor="candidate-packet-input",
                                                        className="field-label",
                                                    ),
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
                                    html.Aside(
                                        [
                                            html.Span("5", className="candidate-step-number"),
                                            html.H3("Check the file"),
                                            html.P(
                                                "Validation checks that the returned idea is complete enough to review. It never approves or runs it.",
                                                className="field-help",
                                            ),
                                            html.Button(
                                                "Validate Candidate",
                                                id="validate-candidate-packet",
                                                n_clicks=0,
                                                className="primary-action",
                                            ),
                                            html.Div(candidate_status, id="candidate-validation-status"),
                                            html.Div(
                                                [
                                                    html.Button(
                                                        "Save this Candidate",
                                                        id="save-candidate-packet",
                                                        n_clicks=0,
                                                        disabled=not bool(candidate_validation.get("valid")),
                                                        className="primary-action",
                                                    ),
                                                    html.Div(
                                                        (
                                                            "Candidate saved locally. It is still not approved, implemented, or runnable."
                                                            if selected and selected.candidate_json
                                                            else "Review the plain-English brief, then save when you are satisfied."
                                                        ),
                                                        id="candidate-action-status",
                                                        className="field-help candidate-action-status",
                                                    ),
                                                ],
                                                id="candidate-valid-actions",
                                                className=(
                                                    "candidate-valid-actions"
                                                    if candidate_validation.get("valid")
                                                    else "candidate-valid-actions idea-path-hidden"
                                                ),
                                            ),
                                        ],
                                        className="candidate-control-rail",
                                    ),
                                ],
                                className="candidate-intake-grid",
                            ),
                        ],
                        className="idea-workbench-panel candidate-intake-panel",
                    ),
                ],
                id="assisted-idea-path",
                className="idea-path-panel idea-path-hidden",
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
                ],
                id="idea-action-bar",
                className="idea-action-bar idea-path-hidden",
            ),
        ],
        className="page-container ideas-page idea-workbench-page",
    )
