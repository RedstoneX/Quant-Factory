"""Approved fixture configuration selection for Milestone 23."""

from __future__ import annotations

from dash import dcc, html

from dashboard.pages.common import page_heading
from dashboard.run_adapter import SavedConfigurationView, list_saved_configurations


def layout(
    *,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
) -> html.Div:
    """Select and inspect an immutable approved configuration without launching it."""

    available = (
        list_saved_configurations()
        if configurations is None
        else configurations
    )
    from dashboard.application import _configuration_preview, _strategy_research_path

    if available:
        first = available[0]
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
            clearable=False,
            persistence=True,
            persistence_type="session",
        )
        preview = _configuration_preview(first)
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
        preview = html.Div(
            [
                html.H2("No approved choices"),
                html.P(
                    "An approved saved fixture configuration is required before a test can be reviewed or run.",
                    className="empty-state-copy",
                ),
                dcc.Link(
                    "Inspect Market data",
                    href="/research/market-data",
                    className="secondary-action",
                ),
            ],
            id="configuration-preview",
            className="panel empty-state",
        )

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
                data=available[0].configuration_id if available else None,
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
                                href="/research/run-test",
                                className="primary-action",
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
