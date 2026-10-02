"""Set up page callback ownership for saved configuration selection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import ALL, Dash, Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate

from dashboard.callbacks.candidate_setup import register_candidate_setup_callbacks
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


def register_setup_callbacks(
    app: Dash,
    *,
    readiness_by_id: dict[str, ConfigurationReadinessView],
    database: str | Path,
) -> None:
    """Register callbacks whose writable outputs all belong to Set up."""

    register_run_test_confirmation_callback(app)
    register_candidate_setup_callbacks(
        app,
        readiness_by_id=readiness_by_id,
        database=database,
    )

    @app.callback(
        Output("selected-configuration-state", "data"),
        Input("configuration-selector", "value"),
        prevent_initial_call=True,
    )
    def preserve_selected_configuration(configuration_id: str | None):
        return configuration_id

    strategies = list_setup_strategies(database)

    @app.callback(
        Output("setup-parameter-controls", "children"),
        Input("setup-strategy-selector", "value"),
    )
    def show_setup_parameters(strategy_identity: str | None):
        return _parameter_controls(strategy_identity, strategies)

    @app.callback(
        Output("idea-configuration-status", "children"),
        Output("idea-configuration-status", "className"),
        Output("created-configuration-state", "data"),
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
        )
