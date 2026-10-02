"""Set up page callback ownership for saved configuration selection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import ALL, Dash, Input, Output, State, dcc, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.components.configuration_summary import configuration_summary
from dashboard.callbacks.run_test import register_run_test_confirmation_callback
from dashboard.run_adapter import (
    ConfigurationReadinessView,
    SetupStrategyView,
    configuration_readiness,
    list_saved_configurations,
    list_setup_strategies,
    persist_bounded_idea_configuration,
)


def _parameter_controls(
    strategy_identity: str | None,
    strategies: tuple[SetupStrategyView, ...],
) -> list[Any]:
    selected = next(
        (strategy for strategy in strategies if strategy.identity == strategy_identity),
        None,
    )
    if selected is None:
        return [html.P("Choose an approved strategy specification.", className="field-help")]
    if not selected.parameters:
        return [
            html.P(
                "This approved specification has no configurable parameters.",
                className="field-help",
            )
        ]
    controls: list[Any] = []
    for parameter in selected.parameters:
        controls.extend(
            [
                html.Label(parameter.label, className="field-label"),
                dcc.Dropdown(
                    id={"type": "setup-parameter", "name": parameter.name},
                    options=[
                        {"label": str(value), "value": value}
                        for value in parameter.allowed_values
                    ],
                    value=parameter.default,
                    clearable=False,
                ),
                html.P(parameter.description, className="field-help"),
            ]
        )
    return controls


def _preview_setup_outputs(
    configuration_id: str | None,
    readiness_by_id: dict[str, ConfigurationReadinessView],
) -> tuple[Any, str | None, str, str, str, str]:
    readiness = readiness_by_id.get(configuration_id or "")
    summary = configuration_summary(readiness, component_id="configuration-preview-content")
    if readiness is None:
        return (
            summary.children,
            None,
            "primary-action action-disabled",
            "Choose an approved saved setup before continuing.",
            "No saved setup",
            "setup-campaign-item setup-campaign-item-blocked",
        )
    if not readiness.ready:
        return (
            summary.children,
            None,
            "primary-action action-disabled",
            "Resolve every preflight blocker before reviewing this test.",
            "Setup blocked",
            "setup-campaign-item setup-campaign-item-blocked",
        )
    return (
        summary.children,
        "/research/run-test",
        "primary-action",
        "Review this immutable saved setup before running it.",
        "Ready to review",
        "setup-campaign-item setup-campaign-item-ready",
    )


def register_setup_callbacks(
    app: Dash,
    *,
    readiness_by_id: dict[str, ConfigurationReadinessView],
    database: str | Path,
) -> None:
    """Register callbacks whose writable outputs all belong to Set up."""

    register_run_test_confirmation_callback(app)

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
        Output("setup-context-state", "children"),
        Output("setup-current-state", "className"),
        Input("selected-configuration-state", "data"),
    )
    def preview_setup_configuration(configuration_id: str | None):
        return _preview_setup_outputs(configuration_id, readiness_by_id)

    strategies = list_setup_strategies(database)

    @app.callback(
        Output("setup-parameter-controls", "children"),
        Input("setup-strategy-selector", "value"),
    )
    def show_setup_parameters(strategy_identity: str | None):
        return _parameter_controls(strategy_identity, strategies)

    @app.callback(
        Output("setup-idea-title", "children"),
        Input("idea-draft-store", "data"),
    )
    def show_selected_idea(draft: dict[str, Any] | None):
        if not draft or not draft.get("draft_id"):
            return "Selected idea: choose and save a draft on Ideas first."
        suffix = " · setup already saved" if draft.get("configuration_id") else ""
        return f"Selected idea: {draft.get('title', 'Untitled')}{suffix}"

    @app.callback(
        Output("idea-configuration-status", "children"),
        Output("idea-configuration-status", "className"),
        Output("created-configuration-state", "data"),
        Output("configuration-selector", "options"),
        Output("configuration-selector", "value"),
        Input("save-idea-configuration", "n_clicks"),
        State("idea-draft-store", "data"),
        State("setup-strategy-selector", "value"),
        State({"type": "setup-parameter", "name": ALL}, "id"),
        State({"type": "setup-parameter", "name": ALL}, "value"),
        prevent_initial_call=True,
    )
    def save_idea_configuration(
        n_clicks: int | None,
        draft: dict[str, Any] | None,
        strategy_identity: str | None,
        parameter_ids: list[dict[str, str]],
        parameter_values: list[Any],
    ):
        if not n_clicks:
            raise PreventUpdate
        draft_id = (draft or {}).get("draft_id")
        if not draft_id:
            return (
                "Setup not saved. Save an idea draft first.",
                "save-message error-state",
                None,
                [
                    {
                        "label": configuration.label,
                        "value": configuration.configuration_id,
                        "disabled": not configuration.launchable,
                    }
                    for configuration in list_saved_configurations(database)
                ],
                no_update,
            )
        parameters = {
            identity["name"]: value
            for identity, value in zip(parameter_ids, parameter_values, strict=True)
        }
        try:
            configuration_id = persist_bounded_idea_configuration(
                draft_id=draft_id,
                strategy_identity=strategy_identity or "",
                parameters=parameters,
                database=database,
            )
        except (TypeError, ValueError) as exc:
            return (
                f"Setup not saved. {exc}",
                "save-message error-state",
                None,
                no_update,
                no_update,
            )

        configurations = list_saved_configurations(database)
        created = next(
            item for item in configurations if item.configuration_id == configuration_id
        )
        readiness_by_id[configuration_id] = configuration_readiness(created, None)
        return (
            (
                f"Research setup draft saved as {configuration_id[:12]}. Approval and "
                "concrete data binding are required before it can run."
            ),
            "save-message save-message-success",
            {"configuration_id": configuration_id, "draft_id": draft_id},
            [
                {
                    "label": configuration.label,
                    "value": configuration.configuration_id,
                    "disabled": not configuration.launchable,
                }
                for configuration in configurations
            ],
            configuration_id,
        )
