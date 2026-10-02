"""Approved research-configuration selection for the operator product."""

from __future__ import annotations

from pathlib import Path

from dash import dcc, html

from dashboard.candidate_workflow import candidate_configuration_binding
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
            html.Header(
                [
                    html.Div(
                        [
                            html.P("RESEARCH / SET UP", className="page-eyebrow"),
                            html.H1("Prepare the next test", className="page-title"),
                            html.P(
                                "Turn an accepted idea into one clear, fixed research test.",
                                className="page-description",
                            ),
                        ]
                    ),
                ],
                className="page-heading setup-page-heading",
            ),
            dcc.Store(
                id="selected-configuration-state",
                data=first.configuration_id if first else None,
                storage_type="session",
            ),
            dcc.Store(id="created-configuration-state", storage_type="session"),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Selected idea", className="setup-state-label"),
                            candidate_identity_summary(selected_draft, binding),
                        ],
                        className="setup-campaign-item setup-campaign-item-primary",
                    ),
                    html.Div(
                        [
                            html.Span("Current state", className="setup-state-label"),
                            html.Strong(
                                initial_state,
                                id="setup-context-state",
                                className="setup-context-state",
                            ),
                        ],
                        className=(
                            "setup-campaign-item setup-campaign-item-ready"
                            if review_enabled
                            else "setup-campaign-item setup-campaign-item-blocked"
                        ),
                        id="setup-current-state",
                    ),
                    html.Div(
                        [
                            html.Span("Boundary", className="setup-state-label"),
                            html.Strong("Setup saves a test plan; it never starts a test."),
                        ],
                        className="setup-campaign-item",
                    ),
                ],
                className="setup-guidance-panel",
            ),
            html.Main(
                [
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
                            preview,
                        ],
                        className="setup-contract-workspace",
                    ),
                    candidate_implementation_boundary(open_boundary=first is None),
                    _next_step(review_enabled),
                    html.P(
                        "Fixture results prove mechanics, not profit. No setup or test grants paper or live trading authority.",
                        className="setup-footer-note",
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


def _next_step(review_enabled: bool) -> html.Section:
    if review_enabled:
        eyebrow = "YOUR DECISION"
        heading = "Is this test ready for final review?"
        copy = (
            "If anything is wrong, revise the idea or create a new bounded setup. "
            "Nothing starts here."
        )
        label = "Continue"
        href = "/research/run-test"
        action_class = "primary-action"
        title = "Review this immutable saved setup before running it."
    else:
        eyebrow = "NEXT STEP"
        heading = "Waiting for the exact implementation"
        copy = (
            "There is no owner action here until the accepted Candidate has been "
            "implemented and bound."
        )
        label = "Not ready"
        href = None
        action_class = "surface-status-text surface-status-blocked"
        title = "Resolve every preflight blocker before reviewing this test."
    return html.Section(
        [
            html.Div(
                [
                    html.Span(eyebrow, className="setup-state-label"),
                    html.H2(heading),
                    html.P(copy, className="section-description"),
                ]
            ),
            dcc.Link(
                label,
                id="review-test-action",
                href=href,
                className=action_class,
                title=title,
            ),
        ],
        className="setup-next-panel",
    )
