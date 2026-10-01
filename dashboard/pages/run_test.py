"""Final approved-research review and explicit launch page."""

from __future__ import annotations

from dash import dcc, html

from dashboard.components.configuration_summary import configuration_summary
from dashboard.components.operator_context import operator_context
from dashboard.pages.common import page_heading
from dashboard.run_adapter import (
    CatalogSnapshot,
    ConfigurationReadinessView,
    SavedConfigurationView,
    configuration_readiness_by_id,
    list_saved_configurations,
)


def layout(
    *,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    catalog_snapshot: CatalogSnapshot | None = None,
    readiness_by_id: dict[str, ConfigurationReadinessView] | None = None,
    loading: bool = False,
) -> html.Div:
    """Render one explicit, route-gated research launch control."""

    available = (
        list_saved_configurations()
        if configurations is None
        else configurations
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
                "Review before running",
                "Confirm the immutable setup, provenance, and launch boundary before starting exactly one recorded test.",
            ),
            operator_context(component_id="run-test-operator-context"),
            dcc.Store(
                id="run-test-launch-state",
                storage_type="session",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2("Immutable run contract"),
                                            html.P(
                                                "This is the exact persisted setup the engine will receive.",
                                                className="section-description",
                                            ),
                                        ]
                                    ),
                                    html.Span("No hidden expansion", className="surface-badge"),
                                ],
                                className="surface-heading",
                            ),
                            preview,
                            html.Div(
                                [
                                    html.Div([html.Span("Input"), html.Strong("1 persisted setup")], className="launch-flow-step"),
                                    html.Span("→", className="launch-flow-arrow", **{"aria-hidden": "true"}),
                                    html.Div([html.Span("Engine"), html.Strong("VectorBT research run")], className="launch-flow-step"),
                                    html.Span("→", className="launch-flow-arrow", **{"aria-hidden": "true"}),
                                    html.Div([html.Span("Persistence"), html.Strong("Run, artifacts, lineage")], className="launch-flow-step"),
                                    html.Span("→", className="launch-flow-arrow", **{"aria-hidden": "true"}),
                                    html.Div([html.Span("Destination"), html.Strong("Results")], className="launch-flow-step"),
                                ],
                                className="launch-flow",
                            ),
                        ],
                        className="run-contract-workspace",
                    ),
                    html.Aside(
                        [
                            html.Section(
                                [
                                    html.Div(
                                        [
                                            html.H2("Launch gate"),
                                            html.Span("Fail closed", className="surface-badge surface-badge-safe"),
                                        ],
                                        className="surface-heading",
                                    ),
                                    html.Ul(
                                        [
                                            html.Li("An immutable saved setup must be selected."),
                                            html.Li("Its approved strategy implementation must be active."),
                                            html.Li("Its exact local data binding must pass verification."),
                                            html.Li("No earlier submission may remain unresolved."),
                                        ],
                                        className="launch-check-list",
                                    ),
                                    html.Div(
                                        [
                                            html.Strong("Research test only"),
                                            html.P(
                                                "This control cannot submit paper or live orders, change parameters, or promote a result.",
                                                className="field-help",
                                            ),
                                        ],
                                        className="operator-message operator-message-warning",
                                    ),
                                ],
                                className="panel run-launch-gate",
                            ),
                            html.Section(
                                [
                                    html.Strong("Ready to start one run"),
                                    html.P(
                                        "The button disables immediately while the durable submission is unresolved.",
                                        className="field-help",
                                    ),
                                    html.Button(
                                        "Run test",
                                        id="launch-run",
                                        n_clicks=0,
                                        disabled=launch_disabled,
                                        title=launch_title,
                                        className="primary-action run-launch-button",
                                    ),
                                    html.Div(
                                        "No test has been started from this page.",
                                        id="launch-message",
                                        className="save-message",
                                    ),
                                    dcc.Link(
                                        "Open Results",
                                        href="/research/backtest-results",
                                        className="secondary-action run-results-link",
                                    ),
                                ],
                                className="panel run-launch-action",
                            ),
                        ],
                        className="run-launch-rail",
                    ),
                ],
                className="run-review-grid",
            ),
            html.Div(
                [
                    html.Strong("After launch:"),
                    html.Span(
                        " this page keeps the same run visible through queued, running, retrying, failed, or succeeded states. Results remains the separate analysis step."
                    ),
                ],
                className="run-review-footer",
            ),
        ],
        className="page-container run-test-page",
    )
