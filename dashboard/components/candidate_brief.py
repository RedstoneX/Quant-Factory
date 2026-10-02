"""Readable, compact rendering for a validated QF Candidate packet."""

from __future__ import annotations

from typing import Any, Mapping

from dash import html

from research_intake import CandidateValidation


def candidate_brief(
    document: Mapping[str, Any], validation: CandidateValidation
) -> html.Div:
    """Render the approved plain-language review while retaining the packet."""

    candidate = _mapping(document.get("candidate"))
    hypothesis = _mapping(document.get("hypothesis"))
    questions = document.get("open_questions", []) or []
    high_questions = _high_question_count(questions)
    variables = _mapping(document.get("variables"))
    variants = document.get("variants", []) or []
    return html.Div(
        [
            _provenance(document, candidate),
            _session_explainer(document),
            _meaning_strip(document, variables, variants),
            _review_status(candidate, validation),
            _packet_details(
                document, hypothesis, questions, variables, variants, high_questions
            ),
        ],
        className="candidate-readable-brief",
    )


def _provenance(
    document: Mapping[str, Any], candidate: Mapping[str, Any]
) -> html.Dl:
    sources = document.get("sources") or []
    source = sources[0] if isinstance(sources, list) and sources else {}
    source = _mapping(source)
    proposed_by = str(
        source.get("creator") or source.get("author") or "Owner-provided idea"
    )
    family = str(candidate.get("family") or "Not specified").replace("_", " ").title()
    status = str(candidate.get("status") or "draft").replace("_", " ").title()
    return html.Dl(
        [
            _provenance_item("Proposed by", proposed_by),
            _provenance_item("Idea family", family),
            _provenance_item("Owner decision", status),
        ],
        className="candidate-provenance",
    )


def _provenance_item(label: str, value: str) -> html.Div:
    return html.Div([html.Dt(label), html.Dd(value)])


def _session_explainer(document: Mapping[str, Any]) -> html.Section:
    fixed = _mapping(document.get("fixed"))
    start = str(fixed.get("opening_range_start") or "Session open")
    end = str(fixed.get("opening_range_end") or "Range complete")
    finish = str(fixed.get("time_exit") or "Before session close")
    stages = (
        ("Build the opening range", f"{start} → {end}"),
        ("Watch for a qualified break", f"After {end} · fixed confirmation rules"),
        ("Finish the trade", f"Stop, target, or flat by {finish}"),
    )
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [html.H3("What would happen during one trading day"), html.P("A quick visual explanation of the proposed rule.")]
                    ),
                    html.Span("Explanation—not a result"),
                ],
                className="candidate-session-heading",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(str(index), className="candidate-session-number"),
                            html.Strong(title),
                            html.Small(detail),
                        ],
                        className=f"candidate-session-step candidate-session-step-{index}",
                    )
                    for index, (title, detail) in enumerate(stages, start=1)
                ],
                className="candidate-session-map",
            ),
        ],
        className="candidate-session",
    )


def _meaning_strip(
    document: Mapping[str, Any],
    variables: Mapping[str, Any],
    variants: Any,
) -> html.Div:
    hypothesis = _mapping(document.get("hypothesis"))
    reasons = hypothesis.get("edge_reasoning") or []
    failures = hypothesis.get("failure_theory") or []
    compared = (
        f"{len(variables)} fixed sweep dimension(s) and {len(variants) if isinstance(variants, list) else 0} structural variant(s)."
        if variables or variants
        else "One fixed formulation. Its rules may not change after results are seen."
    )
    meanings = (
        ("Why it might work", _sentence_summary(reasons, "The Candidate records no supporting mechanism.")),
        ("What would disprove it", _sentence_summary(failures, "The Candidate records no failure theory.")),
        ("What will be compared", compared),
    )
    return html.Div(
        [
            html.Section(
                [html.H3(title), html.P(copy)],
                className="candidate-meaning-item",
            )
            for title, copy in meanings
        ],
        className="candidate-meaning",
    )


def _sentence_summary(value: Any, empty: str) -> str:
    if isinstance(value, list):
        sentences = [str(item).strip() for item in value if str(item).strip()]
        return " ".join(sentences[:2]) or empty
    text = str(value or "").strip()
    return text or empty


def _review_status(
    candidate: Mapping[str, Any], validation: CandidateValidation
) -> html.Div:
    approved = str(candidate.get("status") or "") == "owner_approved"
    if approved:
        headline = "Candidate accepted."
        copy = "This exact version is locked for Set up."
    elif validation.review_ready:
        headline = "Candidate checks passed."
        copy = "The remaining step is your decision."
    else:
        headline = "Clarification is still required."
        copy = "Resolve the named questions before deciding."
    return html.Div(
        [html.Span("✓", **{"aria-hidden": "true"}), html.P([html.Strong(headline), f" {copy}"])],
        className="candidate-review-status",
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


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
