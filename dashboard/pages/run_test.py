"""Final fixture review and explicit launch page for Milestone 23."""

from __future__ import annotations

from dash import dcc, html

from dashboard.pages.common import page_heading
from dashboard.run_adapter import SavedConfigurationView, list_saved_configurations


def layout(
    *,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
) -> html.Div:
    """Render one explicit, route-gated fixture launch control."""

    available = (
        list_saved_configurations()
        if configurations is None
        else configurations
    )
    from dashboard.application import _configuration_preview

    selected = available[0] if available else None
    if selected is None:
        preview = html.Div(
            [
                html.H2("No saved setup selected"),
                html.P(
                    "Return to Set up and choose an approved saved fixture configuration.",
                    className="empty-state-copy",
                ),
                dcc.Link("Return to Set up", href="/research/setup", className="secondary-action"),
            ],
            id="run-configuration-preview",
            className="panel empty-state",
        )
        launch_disabled = True
        launch_title = "No approved saved configuration is available."
    else:
        preview_component = _configuration_preview(selected)
        preview = html.Div(
            preview_component.children,
            id="run-configuration-preview",
            className="run-configuration-preview",
        )
        launch_disabled = not selected.launchable
        launch_title = (
            "Run this immutable saved fixture configuration."
            if selected.launchable
            else "This saved configuration is not launchable."
        )

    return html.Div(
        [
            page_heading(
                "RESEARCH / RUN TEST",
                "Run test",
                "Review the saved setup, launch exactly once, and observe the recorded outcome.",
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
