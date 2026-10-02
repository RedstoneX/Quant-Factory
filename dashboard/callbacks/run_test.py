"""Small page-owned callbacks for the final Run Test confirmation."""

from __future__ import annotations

from dash import Dash, Input, Output


def register_run_test_confirmation_callback(app: Dash) -> None:
    """Clear consent whenever a different saved test becomes current."""

    @app.callback(
        Output("confirm-run-test", "value"),
        Input("selected-configuration-state", "data"),
        prevent_initial_call=True,
    )
    def reset_run_confirmation(_configuration_id: str | None):
        return []
