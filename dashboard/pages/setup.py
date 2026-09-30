"""Approved fixture configuration selection for Milestone 23."""

from __future__ import annotations

from pathlib import Path

from dash import dcc, html

from dashboard.components.configuration_summary import configuration_summary
from dashboard.pages.common import page_heading
from dashboard.run_adapter import (
    CatalogSnapshot,
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
    from dashboard.application import _strategy_research_path

    readiness_by_id = configuration_readiness_by_id(available, catalog_snapshot)
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
                "An approved saved fixture configuration is required before a test can be reviewed or run."
            ),
        )

    review_enabled = first_readiness is not None and first_readiness.ready and not loading

    return html.Div(
        [
            page_heading(
                "RESEARCH / SET UP",
                "Set up a test",
                (
                    "Turn an idea into a bounded research setup draft, or choose an "
                    "already approved runnable setup."
                ),
            ),
            _strategy_research_path("/research/setup"),
            dcc.Store(
                id="selected-configuration-state",
                data=first.configuration_id if first else None,
                storage_type="session",
            ),
            dcc.Store(id="created-configuration-state", storage_type="session"),
            html.Section(
                [
                    html.H2("Create a research setup draft from a saved idea"),
                    html.P(
                        "Selected idea: choose and save a draft on Ideas first.",
                        id="setup-idea-title",
                        className="field-help",
                    ),
                    html.Label(
                        "Approved strategy specification",
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
                        placeholder="No active approved specification is available",
                        disabled=not approved_strategies,
                    ),
                    html.Div(id="setup-parameter-controls"),
                    html.P(
                        (
                            "Only values already allowed by the approved strategy "
                            "specification are offered. Saving creates an immutable draft; "
                            "approval and concrete data binding are still required before "
                            "Run test becomes available. After you accept a named candidate, "
                            "Codex implements and binds that exact strategy; this page does "
                            "not turn a free-form idea into trading code."
                        ),
                        className="field-help",
                    ),
                    html.Button(
                        "Save setup draft",
                        id="save-idea-configuration",
                        n_clicks=0,
                        disabled=not approved_strategies,
                        className="primary-action",
                    ),
                    html.Div(
                        "No setup has been created from the selected idea.",
                        id="idea-configuration-status",
                        className="save-message",
                    ),
                ],
                className="panel idea-configuration-panel",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.Label(
                                "Saved setup",
                                id="configuration-selector-label",
                                htmlFor="configuration-selector",
                                className="field-label",
                            ),
                            selector,
                            html.P(
                                (
                                    "Run test uses an already approved setup with concrete "
                                    "data. New idea-based drafts stay blocked until those "
                                    "requirements are supplied under the existing authority."
                                ),
                                className="field-help",
                            ),
                            html.P(
                                "Only approved infrastructure fixtures are available during Milestone 23.",
                                className="field-help",
                            ),
                        ],
                        className="panel configuration-selector-panel",
                        role="group",
                        **{"aria-labelledby": "configuration-selector-label"},
                    ),
                    html.Section(
                        [
                            html.Strong("Infrastructure fixture — not profit evidence"),
                            html.P(
                                "A successful test proves the workflow and evidence path; it does not qualify a strategy for paper or live trading.",
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
                        className="panel launch-controls-panel",
                    ),
                ],
                className="run-launch-row",
            ),
            preview,
        ],
        className="page-container setup-page",
    )
