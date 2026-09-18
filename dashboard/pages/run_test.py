"""Final fixture review and explicit launch page for Milestone 23."""

from __future__ import annotations

from dash import dcc, html

from dashboard.components.configuration_summary import configuration_summary
from dashboard.components.operator_context import operator_context
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
    """Render one explicit, route-gated fixture launch control."""

    available = (
        list_saved_configurations()
        if configurations is None
        else configurations
    )
    from dashboard.application import _strategy_research_path

    readiness_by_id = configuration_readiness_by_id(available, catalog_snapshot)
    selected = next(
        (
            configuration
            for configuration in available
            if readiness_by_id[configuration.configuration_id].ready
        ),
        available[0] if available else None,
    )
    readiness = readiness_by_id.get(selected.configuration_id) if selected else None
    preview = configuration_summary(
        readiness,
        component_id="run-configuration-preview",
        loading=loading,
    )
    # The page-owned callback prepares a browser-session key before enabling.
    launch_disabled = True
    launch_title = "Preparing a durable browser-session run ticket."

    return html.Div(
        [
            page_heading(
                "RESEARCH / RUN TEST",
                "Run test",
                "Review the saved setup, launch exactly once, and observe the recorded outcome.",
            ),
            _strategy_research_path("/research/run-test"),
            operator_context(component_id="run-test-operator-context"),
            dcc.Store(
                id="run-test-launch-state",
                storage_type="session",
            ),
            html.Div(
                [
                    html.Span("Fixture-only test", className="pending-state-badge"),
                    html.P(
                        "This action launches research infrastructure only. It cannot submit paper or live orders.",
                        className="field-help",
                    ),
                ],
                className="operator-message operator-message-info",
            ),
            preview,
            html.Section(
                [
                    html.H2("Final review"),
                    html.P(
                        "The test uses the immutable saved setup shown above. Starting it requires this explicit click.",
                        className="field-help",
                    ),
                    html.Button(
                        "Run test",
                        id="launch-run",
                        n_clicks=0,
                        disabled=launch_disabled,
                        title=launch_title,
                        className="primary-action",
                    ),
                    html.Div(
                        "No test has been started from this page.",
                        id="launch-message",
                        className="save-message",
                    ),
                    dcc.Link(
                        "View results",
                        href="/research/backtest-results",
                        className="secondary-action",
                    ),
                ],
                className="panel launch-controls-panel",
            ),
        ],
        className="page-container run-test-page",
    )
