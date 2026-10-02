"""Approved research-configuration selection for the operator product."""

from __future__ import annotations

from pathlib import Path

from dash import dcc, html

from dashboard.components.configuration_summary import configuration_summary
from dashboard.run_adapter import (
    CatalogSnapshot,
    ConfigurationReadinessView,
    SavedConfigurationView,
    SetupStrategyView,
    configuration_readiness_by_id,
    list_saved_configurations,
    list_setup_strategies,
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
    approved_strategies = (
        list_setup_strategies(database)
        if setup_strategies is None and database is not None
        else setup_strategies or ()
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
    first = next(
        (
            configuration
            for configuration in available
            if readiness_by_id[configuration.configuration_id].ready
        ),
        available[0] if available else None,
    )
    first_readiness = readiness_by_id.get(first.configuration_id) if first else None

    if available:
        selector = dcc.Dropdown(
            id="configuration-selector",
            options=[
                {
                    "label": configuration.label,
                    "value": configuration.configuration_id,
                    "disabled": not configuration.launchable,
                }
                for configuration in available
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
            empty_title="No approved choices",
            empty_message=(
                "An approved saved research configuration is required before a test can be reviewed or run."
            ),
        )

    review_enabled = first_readiness is not None and first_readiness.ready and not loading

    initial_state = (
        "Ready to review"
        if first_readiness is not None and first_readiness.ready
        else "Setup blocked"
        if first_readiness is not None
        else "No saved setup"
    )

    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P("RESEARCH / SET UP", className="page-eyebrow"),
                            html.H1("Prepare a strategy test", className="page-title"),
                            html.P(
                                "Connect a saved idea to an existing approved implementation, or review a setup that is already prepared.",
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
                            html.P("START HERE", className="page-eyebrow"),
                            html.H2("Know what is ready before you change anything"),
                            html.P(
                                "A saved Candidate is a research proposal. A runnable setup additionally needs an approved implementation, bounded parameters, and compatible local data.",
                                className="setup-guidance-lede",
                            ),
                        ],
                        className="setup-guidance-heading",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("YOUR SAVED IDEA", className="setup-state-label"),
                                    html.Strong(
                                        "Choose and save a draft on Ideas first.",
                                        id="setup-idea-title",
                                    ),
                                    html.P(
                                        "The idea and its source context stay unchanged here.",
                                        className="field-help",
                                    ),
                                ],
                                className="setup-state-card setup-state-card-idea",
                            ),
                            html.Div(
                                [
                                    html.Span("WHAT A TEST NEEDS", className="setup-state-label"),
                                    html.Strong("Approved implementation + fixed choices + data"),
                                    html.P(
                                        "Setup records those exact inputs. It does not invent strategy logic.",
                                        className="field-help",
                                    ),
                                ],
                                className="setup-state-card",
                            ),
                            html.Div(
                                [
                                    html.Span("CURRENT RESULT", className="setup-state-label"),
                                    html.Strong(initial_state, className="setup-context-state"),
                                    html.P(
                                        (
                                            "The selected saved setup can move to final review."
                                            if review_enabled
                                            else "Read the blocker below before trying to continue."
                                            if first_readiness is not None
                                            else "There is no saved setup to review yet."
                                        ),
                                        className="field-help",
                                    ),
                                ],
                                className=(
                                    "setup-state-card setup-state-card-ready"
                                    if review_enabled
                                    else "setup-state-card setup-state-card-blocked"
                                ),
                            ),
                        ],
                        className="setup-state-grid",
                    ),
                    html.Div(
                        [
                            html.Strong("Important boundary"),
                            html.P(
                                "Importing a Candidate does not make it runnable, and choosing a similar existing strategy does not implement it. Nothing launches from this page."
                            ),
                        ],
                        className="setup-boundary-callout",
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
                                            html.P("EXISTING SAVED SETUPS", className="page-eyebrow"),
                                            html.H2("Review exactly what can already be tested"),
                                            html.P(
                                                "Choose a saved setup to see its strategy, data, parameters, assumptions, and any blocker before moving forward.",
                                                className="section-description",
                                            ),
                                        ]
                                    ),
                                    html.Span("Read only", className="surface-badge"),
                                ],
                                className="setup-section-heading",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Saved setup",
                                        id="configuration-selector-label",
                                        htmlFor="configuration-selector",
                                        className="field-label",
                                    ),
                                    selector,
                                    html.P(
                                        "Changing this selection only changes the preview. It does not run a test.",
                                        className="field-help",
                                    ),
                                ],
                                className="setup-saved-selector",
                                role="group",
                                **{"aria-labelledby": "configuration-selector-label"},
                            ),
                            preview,
                        ],
                        className="setup-contract-workspace",
                    ),
                    html.Details(
                        [
                            html.Summary(
                                [
                                    html.Div(
                                        [
                                            html.Span("OPTIONAL", className="setup-state-label"),
                                            html.Strong("Create a new bounded setup"),
                                            html.Small("Only from an implementation that already exists and is approved"),
                                        ]
                                    ),
                                    html.Span("Open →", className="setup-disclosure-action"),
                                ],
                                className="setup-create-summary",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.H2("Create from an approved implementation"),
                                                    html.P(
                                                        "Use this only when the saved idea is the exact strategy represented by an implementation already registered in Quant Factory.",
                                                        className="section-description",
                                                    ),
                                                ]
                                            ),
                                            html.Span("Specification-bound", className="surface-badge surface-badge-safe"),
                                        ],
                                        className="setup-section-heading setup-create-heading",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "Existing approved implementation",
                                                        htmlFor="setup-strategy-selector",
                                                        className="field-label",
                                                    ),
                                                    dcc.Dropdown(
                                                        id="setup-strategy-selector",
                                                        options=[
                                                            {
                                                                "label": f"{strategy.name} · {strategy.lifecycle}",
                                                                "value": strategy.identity,
                                                            }
                                                            for strategy in approved_strategies
                                                        ],
                                                        value=(approved_strategies[0].identity if approved_strategies else None),
                                                        clearable=False,
                                                        placeholder="No approved implementation available",
                                                        disabled=not approved_strategies,
                                                    ),
                                                    html.P(
                                                        "An imported Candidate will not appear here until its strategy logic has been separately approved and implemented.",
                                                        className="field-help",
                                                    ),
                                                ],
                                                className="setup-create-field",
                                            ),
                                            html.Div(
                                                [
                                                    html.H3("Allowed choices"),
                                                    html.P(
                                                        "Only values declared by the approved strategy specification are available.",
                                                        className="field-help",
                                                    ),
                                                    html.Div(id="setup-parameter-controls", className="setup-parameter-list"),
                                                ],
                                                className="setup-parameter-panel",
                                            ),
                                        ],
                                        className="setup-create-grid",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                "No setup has been created from the selected idea.",
                                                id="idea-configuration-status",
                                                className="save-message setup-save-status",
                                            ),
                                            html.Button(
                                                "Save bounded setup",
                                                id="save-idea-configuration",
                                                n_clicks=0,
                                                disabled=not approved_strategies,
                                                className="primary-action",
                                            ),
                                        ],
                                        className="setup-create-actions",
                                    ),
                                    html.Div(
                                        [
                                            html.Strong("Why this may still be blocked"),
                                            html.P(
                                                "Saving records the permitted choices. Approval, a concrete data binding, and a passing readiness check are still required before Run test becomes available."
                                            ),
                                        ],
                                        className="operator-message operator-message-warning setup-boundary-note",
                                    ),
                                ],
                                className="setup-create-body",
                            ),
                        ],
                        className="setup-create-disclosure",
                        open=not available,
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Span("NEXT SAFE ACTION", className="setup-state-label"),
                                    html.H2("Review the selected saved setup"),
                                    html.P(
                                        "Continue only when the preview above says it is ready. The next page asks for a final review before any launch.",
                                        className="section-description",
                                    ),
                                ]
                            ),
                            dcc.Link(
                                "Review test",
                                id="review-test-action",
                                href="/research/run-test" if review_enabled else None,
                                className=(
                                    "primary-action"
                                    if review_enabled
                                    else "primary-action action-disabled"
                                ),
                                title=(
                                    "Review this immutable saved setup before running it."
                                    if review_enabled
                                    else "Resolve every preflight blocker before reviewing this test."
                                ),
                            ),
                        ],
                        className="setup-next-panel",
                    ),
                    html.P(
                        "Fixture results prove mechanics, not profit. No setup or test grants paper or live trading authority.",
                        className="setup-footer-note",
                    ),
                ],
                className="setup-workbench-grid",
            ),
        ],
        className="page-container setup-page",
    )
