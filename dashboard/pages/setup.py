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
                            html.H1("Define the experiment", className="page-title"),
                            html.P(
                                "See exactly what the research engine can test before an immutable setup is saved.",
                                className="page-description",
                            ),
                        ]
                    ),
                    html.Button(
                        "Save setup draft",
                        id="save-idea-configuration",
                        n_clicks=0,
                        disabled=not approved_strategies,
                        className="primary-action page-action",
                    ),
                ],
                className="page-heading page-heading-with-actions setup-page-heading",
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
                            html.Span("From idea", className="setup-context-label"),
                            html.Strong(
                                "Choose and save a draft on Ideas first.",
                                id="setup-idea-title",
                            ),
                            html.Small("Owner-authored source capture"),
                        ],
                        className="setup-context-item",
                    ),
                    html.Div(
                        [
                            html.Label(
                                "Approved strategy or fixture",
                                htmlFor="setup-strategy-selector",
                                className="setup-context-label",
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
                                placeholder="No approved specification available",
                                disabled=not approved_strategies,
                            ),
                        ],
                        className="setup-context-item",
                    ),
                    html.Div(
                        [
                            html.Label(
                                "Saved setup",
                                id="configuration-selector-label",
                                htmlFor="configuration-selector",
                                className="setup-context-label",
                            ),
                            selector,
                        ],
                        className="setup-context-item",
                        role="group",
                        **{"aria-labelledby": "configuration-selector-label"},
                    ),
                    html.Div(
                        [
                            html.Span(initial_state, className="setup-context-state"),
                            html.Small("No test starts from this page"),
                        ],
                        className="setup-context-item setup-context-readiness",
                    ),
                ],
                className="setup-context-strip",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2("Immutable contract preview"),
                                            html.P(
                                                "Every recorded input, assumption, data boundary, and launch blocker stays visible before anything can run.",
                                                className="section-description",
                                            ),
                                        ]
                                    ),
                                    html.Span("Read only until saved", className="surface-badge"),
                                ],
                                className="surface-heading",
                            ),
                            preview,
                        ],
                        className="setup-contract-workspace",
                    ),
                    html.Aside(
                        [
                            html.Section(
                                [
                                    html.Div(
                                        [
                                            html.H2("Bounded setup controls"),
                                            html.Span("Specification-bound", className="surface-badge surface-badge-safe"),
                                        ],
                                        className="surface-heading",
                                    ),
                                    html.P(
                                        "Only values permitted by the approved specification can be selected.",
                                        className="field-help",
                                    ),
                                    html.Div(id="setup-parameter-controls", className="setup-parameter-list"),
                                    html.Div(
                                        "No setup has been created from the selected idea.",
                                        id="idea-configuration-status",
                                        className="save-message setup-save-status",
                                    ),
                                ],
                                className="panel setup-control-panel",
                            ),
                            html.Section(
                                [
                                    html.Strong("Idea-to-code boundary"),
                                    html.P(
                                        (
                                            "Saving preserves a bounded setup draft. A new idea still needs explicit hypothesis approval, deterministic strategy implementation, and concrete data binding before Run test can become available."
                                        ),
                                        className="field-help",
                                    ),
                                ],
                                className="operator-message operator-message-warning setup-boundary-note",
                            ),
                            html.Section(
                                [
                                    html.Strong("Next safe action"),
                                    html.P(
                                        "Review test is enabled only for an already approved setup whose local data and runtime binding pass preflight.",
                                        className="field-help",
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
                                className="panel setup-next-panel",
                            ),
                            html.P(
                                "Fixture results prove mechanics, not profit. No setup or test grants paper or live trading authority.",
                                className="setup-footer-note",
                            ),
                        ],
                        className="setup-controls-rail",
                    ),
                ],
                className="setup-workbench-grid",
            ),
        ],
        className="page-container setup-page",
    )
