"""Approved research-configuration selection for the operator product."""

from __future__ import annotations

from pathlib import Path

from dash import dcc, html

from dashboard.candidate_workflow import (
    candidate_configuration_binding,
    candidate_review_state,
)
from dashboard.components.candidate_setup import (
    candidate_identity_summary,
    candidate_implementation_boundary,
)
from dashboard.components.configuration_summary import configuration_summary
from dashboard.run_adapter import (
    CatalogSnapshot,
    ConfigurationReadinessView,
    SavedConfigurationView,
    SetupStrategyView,
    configuration_readiness_by_id,
    list_idea_drafts,
    list_saved_configurations,
)


def layout(
    *,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    setup_strategies: tuple[SetupStrategyView, ...] | None = None,
    database: str | Path | None = None,
    catalog_snapshot: CatalogSnapshot | None = None,
    readiness_by_id: dict[str, ConfigurationReadinessView] | None = None,
    loading: bool = False,
) -> html.Div:
    """Select and inspect an immutable approved configuration without launching it."""

    available = (
        list_saved_configurations(database)
        if database is not None
        else configurations or ()
    )
    readiness_by_id = dict(readiness_by_id or {})
    missing_readiness = tuple(
        configuration
        for configuration in available
        if configuration.configuration_id not in readiness_by_id
    )
    if missing_readiness:
        readiness_by_id.update(
            configuration_readiness_by_id(missing_readiness, catalog_snapshot)
        )
    selected_draft = None
    binding = None
    drafts = ()
    if database is not None:
        drafts = list_idea_drafts(database)
        selected_draft = drafts[0] if drafts else None
        binding = candidate_configuration_binding(
            selected_draft.draft_id if selected_draft else None,
            database=database,
        )
    first = binding.configuration if binding is not None else None
    first_readiness = readiness_by_id.get(first.configuration_id) if first else None

    if first is not None:
        selector = dcc.Dropdown(
            id="configuration-selector",
            options=[
                {
                    "label": first.label,
                    "value": first.configuration_id,
                    "disabled": not first.launchable,
                }
            ],
            value=first.configuration_id,
            disabled=loading,
            clearable=False,
            persistence=True,
            persistence_type="session",
        )
        preview = configuration_summary(
            first_readiness,
            component_id="configuration-preview",
            loading=loading,
        )
    else:
        selector = dcc.Dropdown(
            id="configuration-selector",
            options=[],
            value=None,
            disabled=True,
            placeholder="No approved configuration is available",
            persistence=True,
            persistence_type="session",
        )
        preview = configuration_summary(
            None,
            component_id="configuration-preview",
            loading=loading,
            empty_title="Implementation needed",
            empty_message=(
                binding.blocker_reason
                if binding is not None and binding.blocker_reason
                else "Choose and accept a Candidate on Ideas before preparing a test."
            ),
            empty_action_href=None,
        )

    review_enabled = first_readiness is not None and first_readiness.ready and not loading

    initial_state = (
        "Ready to review"
        if first_readiness is not None and first_readiness.ready
        else "Setup blocked"
        if first_readiness is not None
        else "Implementation needed"
        if binding is not None and binding.blocker_code == "implementation_required"
        else "Candidate not ready"
    )
    return html.Div(
        [
            _page_header(),
            dcc.Store(
                id="selected-configuration-state",
                data=first.configuration_id if first else None,
                storage_type="session",
            ),
            dcc.Store(id="created-configuration-state", storage_type="session"),
            _campaign_context(selected_draft, binding, initial_state, review_enabled),
            html.Main(
                [
                    _idea_queue(drafts, selected_draft),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.P("CANDIDATE-BOUND SETUP", className="page-eyebrow"),
                                            html.H2("Review this Candidate's exact test"),
                                            html.P(
                                                "Every rule, cost, data choice and blocker remains visible before final review.",
                                                className="section-description",
                                            ),
                                        ]
                                    ),
                                    html.Span("Locked preview", className="surface-status-text"),
                                ],
                                className="setup-section-heading",
                            ),
                            _candidate_meaning(binding),
                            html.Div(
                                [
                                    html.Label(
                                        "Candidate implementation",
                                        id="configuration-selector-label",
                                        htmlFor="configuration-selector",
                                        className="field-label",
                                    ),
                                    selector,
                                    html.P(
                                        "Only the implementation linked to this exact Candidate can appear here. No fixture or unrelated strategy can be substituted.",
                                        className="field-help",
                                    ),
                                ],
                                className=(
                                    "setup-saved-selector"
                                    if first is not None
                                    else "setup-saved-selector setup-saved-selector-blocked"
                                ),
                                role="group",
                                **{"aria-labelledby": "configuration-selector-label"},
                            ),
                            html.Div(
                                preview,
                                className=(
                                    "setup-configuration-preview"
                                    if first is not None
                                    else "setup-configuration-preview setup-configuration-preview-hidden"
                                ),
                            ),
                        ],
                        className="setup-contract-workspace",
                    ),
                    html.Aside(
                        [
                            candidate_implementation_boundary(open_boundary=first is None),
                            html.P(
                                "Setup does not start tests. Run test is the separate start page.",
                                className="setup-footer-note",
                            ),
                        ],
                        className="setup-decision-rail",
                    ),
                ],
                className=(
                    "setup-workbench-grid"
                    if first is not None
                    else "setup-workbench-grid setup-workbench-grid-blocked"
                ),
            ),
        ],
        className="page-container setup-page",
    )


def _page_header() -> html.Header:
    return html.Header(
        [
            html.P("RESEARCH / SET UP", className="page-eyebrow"),
            html.H1("Prepare the next test", className="page-title"),
            html.P(
                "Turn an agent suggestion—or your own idea—into one clear, fixed test.",
                className="page-description",
            ),
        ],
        className="page-heading setup-page-heading",
    )


def _idea_queue(drafts, selected_draft) -> html.Aside:
    rows = []
    for draft in drafts[:5]:
        status, _ = candidate_review_state(draft)
        label = {
            "owner_approved": "Accepted",
            "rejected": "Closed",
        }.get(status, "Needs review")
        selected = selected_draft is not None and draft.draft_id == selected_draft.draft_id
        rows.append(
            html.Div(
                [
                    html.Strong(draft.title),
                    html.Div(
                        [
                            html.Span(draft.attribution or "Owner import"),
                            html.Span(label),
                        ],
                        className="setup-queue-meta",
                    ),
                    (
                        html.Span("Selected", className="setup-queue-row-action")
                        if selected
                        else dcc.Link(
                            "Review on Ideas →",
                            href="/research/ideas",
                            className="setup-queue-row-action setup-queue-row-link",
                        )
                    ),
                ],
                className=(
                    "setup-queue-row setup-queue-row-selected"
                    if selected
                    else "setup-queue-row"
                ),
            )
        )
    if not rows:
        rows.append(
            html.P(
                "Accept an idea before preparing a test.",
                className="empty-state-copy",
            )
        )
    return html.Aside(
        [
            html.Div(
                [
                    html.H2("Idea queue"),
                    html.Span(f"{len(drafts)} total", className="surface-status-text"),
                ],
                className="surface-heading",
            ),
            html.P(
                "Accepted agent and owner ideas share one history.",
                className="setup-queue-help",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("IDEA SELECTION", className="setup-state-label"),
                            html.Strong("Choose or change ideas on the Ideas page"),
                        ]
                    ),
                    dcc.Link("Change", href="/research/ideas", className="secondary-action setup-source-change"),
                ],
                className="setup-source-control",
            ),
            html.Div(
                [
                    html.Span("Choose an idea"),
                    html.Strong(f"{len(drafts)} available"),
                ],
                className="setup-queue-list-label",
            ),
            html.Div(rows, className="setup-queue-list"),
            dcc.Link("Review ideas", href="/research/ideas", className="secondary-action setup-queue-action"),
        ],
        className="setup-idea-queue",
    )


def _candidate_meaning(binding) -> html.Section | None:
    identity = binding.identity if binding is not None else None
    if identity is None:
        return html.Section(
            candidate_identity_summary(None, binding),
            className="setup-candidate-meaning setup-candidate-meaning-empty",
        )
    return html.Section(
        [
            html.Div(
                [
                    _identity_card(
                        "Selected idea",
                        candidate_identity_summary(binding.draft, binding),
                    ),
                    _identity_card("Idea family", identity.family.replace("_", " ").title()),
                    _identity_card("Idea version", identity.short_version),
                    _identity_card("Saved test version", "Not created yet"),
                ],
                className="setup-identity-grid",
            ),
            html.Div(
                [
                    html.Span("Proposed by", className="setup-state-label"),
                    html.Strong(identity.attribution),
                    html.Span("Exact imported wording and lineage retained."),
                ],
                className="setup-provenance-row",
            ),
            html.Div(
                [
                    html.Span("IDEA IN PLAIN ENGLISH", className="setup-state-label"),
                    html.Strong(identity.rationale),
                ],
                className="setup-candidate-lede",
            ),
            _session_rule_map(),
            html.Div(
                [
                    html.H2("The test, in plain English"),
                    html.Span("Every choice remains visible before saving"),
                ],
                className="setup-contract-heading",
            ),
            html.Div(
                [
                    _meaning_card(
                        "Market / session",
                        "The Candidate's declared market, session, timeframe and same-day boundary.",
                    ),
                    _meaning_card(
                        "Entry / exit",
                        "The exact imported entry and exit rules; no substitute implementation.",
                    ),
                    _meaning_card(
                        "Costs",
                        "The Candidate's fixed commission, slippage and position assumptions.",
                    ),
                    _meaning_card(
                        "Success checks",
                        "The recorded evidence contract—not a profitability promise.",
                    ),
                ],
                className="setup-meaning-grid",
            ),
        ],
        className="setup-candidate-meaning",
    )


def _campaign_context(selected_draft, binding, state: str, ready: bool) -> html.Section:
    identity = binding.identity if binding is not None else None
    return html.Section(
        [
            html.Span(
                [html.Strong("Candidate: "), identity.title if identity else "None selected"]
            ),
            html.Span(
                html.Span(state, id="setup-context-state"),
                id="setup-current-state",
                className=(
                    "setup-context-state setup-context-state-ready"
                    if ready
                    else "setup-context-state setup-context-state-blocked"
                ),
            ),
            html.Span(
                [
                    html.Strong("Source: "),
                    selected_draft.attribution if selected_draft is not None else "—",
                ]
            ),
            html.Span([html.Strong("Boundary: "), "Nothing runs from Set up"]),
        ],
        className="setup-campaign-bar",
        **{"aria-label": "Selected Candidate context"},
    )


def _identity_card(label: str, value) -> html.Div:
    return html.Div(
        [html.Span(label), html.Strong(value or "Not specified")],
        className="setup-identity-card",
    )


def _meaning_card(label: str, value: str) -> html.Div:
    return html.Div(
        [html.Span(label), html.Strong(value or "Not specified")],
        className="setup-meaning-card",
    )


def _session_rule_map() -> html.Section:
    """Keep the approved one-day visual explanation in the Setup hierarchy."""

    return html.Section(
        [
            html.Div(
                [
                    html.H3("How the rule fits in one trading day"),
                    html.Span("Explanation only · not a result"),
                ],
                className="setup-rule-heading",
            ),
            html.Div(
                [
                    html.Div(
                        [html.Strong("Define the session"), html.Span("Fixed observation window")],
                        className="setup-rule-stage setup-rule-stage-observe",
                    ),
                    html.Div(
                        [html.Strong("Apply the entry rule"), html.Span("Only the declared trigger")],
                        className="setup-rule-stage setup-rule-stage-entry",
                    ),
                    html.Div(
                        [html.Strong("Finish the test trade"), html.Span("Exit inside the same session")],
                        className="setup-rule-stage setup-rule-stage-exit",
                    ),
                ],
                className="setup-rule-track",
            ),
        ],
        className="setup-rule-map",
    )
