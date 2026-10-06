"""Set up page callback ownership for the exact saved Candidate."""

from __future__ import annotations

from pathlib import Path

from typing import Any

from dash import Dash, Input, Output, dcc, html

from dashboard.callbacks.candidate_setup import register_candidate_setup_callbacks
from dashboard.callbacks.run_test import register_run_test_confirmation_callback
from dashboard.run_adapter import ConfigurationReadinessView, SetupStrategyView


def _parameter_controls(
    strategy_identity: str | None,
    strategies: tuple[SetupStrategyView, ...],
) -> list[Any]:
    """Retain the bounded-specification helper for existing non-browser checks."""
    selected = next((strategy for strategy in strategies if strategy.identity == strategy_identity), None)
    if selected is None:
        return [html.P("Choose an approved strategy specification.", className="field-help")]
    if not selected.parameters:
        return [html.P("This approved specification has no configurable parameters.", className="field-help")]
    controls: list[Any] = []
    for parameter in selected.parameters:
        controls.extend((
            html.Label(parameter.label, className="field-label"),
            dcc.Dropdown(
                id={"type": "setup-parameter", "name": parameter.name},
                options=[{"label": str(value), "value": value} for value in parameter.allowed_values],
                value=parameter.default,
                clearable=False,
            ),
            html.P(parameter.description, className="field-help"),
        ))
    return controls


def register_setup_callbacks(
    app: Dash,
    *,
    readiness_by_id: dict[str, ConfigurationReadinessView],
    database: str | Path,
) -> None:
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
