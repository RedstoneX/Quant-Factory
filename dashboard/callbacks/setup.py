"""Set up page callback ownership for saved configuration selection."""

from __future__ import annotations

from dash import Dash, Input, Output
from dash.exceptions import PreventUpdate

from dashboard.components.configuration_summary import configuration_summary
from dashboard.run_adapter import ConfigurationReadinessView


def register_setup_callbacks(
    app: Dash,
    *,
    readiness_by_id: dict[str, ConfigurationReadinessView],
) -> None:
    """Register callbacks whose writable outputs all belong to Set up."""

    @app.callback(
        Output("selected-configuration-state", "data"),
        Input("configuration-selector", "value"),
        prevent_initial_call=True,
    )
    def preserve_selected_configuration(configuration_id: str | None):
        if not configuration_id:
            raise PreventUpdate
        return configuration_id

    @app.callback(
        Output("configuration-preview", "children"),
        Output("review-test-action", "href"),
        Output("review-test-action", "className"),
        Output("review-test-action", "title"),
        Input("selected-configuration-state", "data"),
    )
    def preview_setup_configuration(configuration_id: str | None):
        readiness = readiness_by_id.get(configuration_id or "")
        summary = configuration_summary(
            readiness,
            component_id="configuration-preview-content",
        )
        if readiness is None:
            return (
                summary.children,
                None,
                "primary-action action-disabled",
                "Choose an approved saved setup before continuing.",
            )
        if not readiness.ready:
            return (
                summary.children,
                None,
                "primary-action action-disabled",
                "Resolve every preflight blocker before reviewing this test.",
            )
        return (
            summary.children,
            "/research/run-test",
            "primary-action",
            "Review this immutable saved setup before running it.",
        )
