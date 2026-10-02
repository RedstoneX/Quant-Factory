"""Readable, compact rendering for a validated QF Candidate packet."""

from __future__ import annotations

from typing import Any, Mapping

from dash import html

from research_intake import CandidateValidation


def candidate_brief(
    document: Mapping[str, Any], validation: CandidateValidation
) -> html.Div:
    """Keep the decision surface concise while retaining the entire packet."""

    candidate = _mapping(document.get("candidate"))
    hypothesis = _mapping(document.get("hypothesis"))
    questions = document.get("open_questions", []) or []
    high_questions = _high_question_count(questions)
    variables = _mapping(document.get("variables"))
    variants = document.get("variants", []) or []
    return html.Div(
        [
            _brief_header(candidate, hypothesis, validation),
            _metric_strip(variables, variants, high_questions, validation),
            _packet_details(
                document, hypothesis, questions, variables, variants, high_questions
            ),
            _boundary_callout(),
        ],
        className="candidate-readable-brief",
    )


def _brief_header(
    candidate: Mapping[str, Any],
    hypothesis: Mapping[str, Any],
    validation: CandidateValidation,
) -> html.Header:
    status = str(candidate.get("status") or "draft").replace("_", " ").title()
    return html.Header(
        [
            html.Div(
                [
                    html.P("QF CANDIDATE V1", className="page-eyebrow"),
                    html.H2(str(candidate.get("title") or "Untitled Candidate")),
                    html.P(
                        str(
                            candidate.get("one_line")
                            or hypothesis.get("behavior")
                            or "No one-line summary supplied."
                        ),
                        className="candidate-brief-lede",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Span(status, className="candidate-status-pill"),
                    html.Span(
                        "Owner review ready"
                        if validation.review_ready
                        else "Clarification required",
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
    )


def _metric_strip(
    variables: Mapping[str, Any],
    variants: Any,
    high_questions: int,
    validation: CandidateValidation,
) -> html.Div:
    variant_count = len(variants) if isinstance(variants, list) else 0
    metrics = (
        ("Sweep dimensions", str(len(variables)), "VectorBT-bounded variables"),
        ("Combinations", f"{validation.parameter_combinations:,}", "Declared grid only"),
        ("Structural variants", str(variant_count), "Never invented automatically"),
        ("High questions", str(high_questions), "Must remain visible"),
    )
    return html.Div(
        [
            html.Div(
                [html.Span(label), html.Strong(value), html.Small(detail)],
                className="candidate-metric",
            )
            for label, value, detail in metrics
        ],
        className="candidate-metric-strip",
    )


def _packet_details(
    document: Mapping[str, Any],
    hypothesis: Mapping[str, Any],
    questions: Any,
    variables: Mapping[str, Any],
    variants: Any,
    high_questions: int,
) -> html.Details:
    sections = (
        ("Hypothesis", "Why it might work—and fail", hypothesis, False, ""),
        ("Market & session", "Trader-readable scope and holding boundary", document.get("market", {}), False, ""),
        ("Open questions", "Unresolved means unresolved", questions, bool(high_questions), ""),
        ("Evaluation boundary", "Evidence contract, not profitability", document.get("evaluation", {}), False, ""),
        ("Source attribution", "Original producers and references", document.get("sources", []), False, ""),
        ("Source rules", "What the source actually states", document.get("source_rules", {}), False, ""),
        ("QF interpretation", "Explicit interpretation, never silently inferred", document.get("qf_interpretation", {}), not bool(document.get("qf_interpretation")), ""),
        ("Testable rules", "Structured English; never executable code", document.get("rules", {}), False, ""),
        ("Fixed rules", "Candidate identity; never swept", document.get("fixed", {}), False, ""),
        ("VectorBT sweep variables", "Only these bounded dimensions may be enumerated", variables, False, "sweep"),
        ("Structural variants", "Different logic paths; support or implementation required", variants, False, "variant"),
        ("Data needs", "Requirements, not an availability claim", document.get("data_needs", {}), False, ""),
        ("Exclusions", "Explicitly outside this Candidate", document.get("exclusions", []), False, ""),
        ("Prior-work claims", "Imported claims remain unverified by QF", document.get("prior_work", {}), bool(document.get("prior_work")), ""),
    )
    return html.Details(
        [
            html.Summary("Review the complete Candidate packet"),
            html.Div(
                [_candidate_section(*section) for section in sections],
                className="candidate-brief-grid candidate-brief-technical-grid",
            ),
        ],
        className="technical-details candidate-technical-details",
    )


def _candidate_section(
    title: str, subtitle: str, value: Any, warning: bool, accent: str
) -> html.Section:
    classes = "candidate-brief-section"
    if warning:
        classes += " candidate-brief-section-warning"
    if accent:
        classes += f" candidate-brief-section-{accent}"
    return html.Section(
        [
            html.Div(
                [html.H3(title), html.P(subtitle)],
                className="candidate-section-heading",
            ),
            _readable_value(value),
        ],
        className=classes,
    )


def _readable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if not value:
            return html.P("Not specified.", className="candidate-empty-value")
        return html.Dl(
            [
                html.Div(
                    [
                        html.Dt(str(key).replace("_", " ").title()),
                        html.Dd(_readable_value(item)),
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
            [html.Li(_readable_value(item)) for item in value],
            className="candidate-readable-list",
        )
    if value is None or value == "":
        return html.Span("Not specified", className="candidate-empty-value")
    if isinstance(value, bool):
        return html.Span("Yes" if value else "No")
    return html.Span(str(value))


def _high_question_count(questions: Any) -> int:
    return sum(
        1
        for question in questions
        if isinstance(question, Mapping)
        and str(question.get("importance", "")).lower() == "high"
    )


def _boundary_callout() -> html.Div:
    return html.Div(
        [
            html.Strong("Intake boundary"),
            html.P(
                "Saving this Candidate records a research proposal only. It does not approve or implement logic, create a runnable configuration, launch VectorBT, inspect protected data, promote a strategy, or submit an order."
            ),
        ],
        className="candidate-boundary-callout",
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
