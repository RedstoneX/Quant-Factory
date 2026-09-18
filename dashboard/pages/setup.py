"""Approved fixture configuration selection for Milestone 23."""

from __future__ import annotations

from dash import dcc, html

from dashboard.components.configuration_summary import configuration_summary
from dashboard.pages.common import page_heading
from dashboard.run_adapter import (
    CatalogSnapshot,
    SavedConfigurationView,
    configuration_readiness_by_id,
    list_saved_configurations,
)


def layout(
    *,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    catalog_snapshot: CatalogSnapshot | None = None,
    loading: bool = False,
) -> html.Div:
    """Select and inspect an immutable approved configuration without launching it."""

    available = (
        list_saved_configurations()
        if configurations is None
        else configurations
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
                "Choose and inspect an approved immutable fixture configuration before any work starts.",
            ),
            _strategy_research_path("/research/setup"),
            dcc.Store(
                id="selected-configuration-state",
                data=first.configuration_id if first else None,
                storage_type="session",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.Label(
                                "Saved setup",
                                htmlFor="configuration-selector",
                                className="field-label",
                            ),
                            selector,
                            html.P(
                                "Only approved infrastructure fixtures are available during Milestone 23.",
                                className="field-help",
                            ),
                        ],
                        className="panel configuration-selector-panel",
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
