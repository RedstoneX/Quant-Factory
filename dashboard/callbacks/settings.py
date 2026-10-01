"""Browser-local display preference callbacks."""

from __future__ import annotations

from dash import Dash, Input, Output, State, ctx, no_update


DEFAULTS = {"theme": "light", "density": "comfortable"}


def _normalized_preferences(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return dict(DEFAULTS)
    theme = value.get("theme") if value.get("theme") in {"light", "dark"} else "light"
    density = (
        value.get("density")
        if value.get("density") in {"comfortable", "compact"}
        else "comfortable"
    )
    return {"theme": theme, "density": density}


def register_settings_callbacks(app: Dash) -> None:
    @app.callback(
        Output("display-preferences", "data"),
        Output("settings-save-status", "children"),
        Output("settings-save-status", "className"),
        Input("save-display-preferences", "n_clicks"),
        Input("reset-display-preferences", "n_clicks"),
        State("settings-theme", "value"),
        State("settings-density", "value"),
        prevent_initial_call=True,
    )
    def save_preferences(
        _save_clicks: int | None,
        _reset_clicks: int | None,
        theme: str | None,
        density: str | None,
    ):
        if ctx.triggered_id == "reset-display-preferences":
            return dict(DEFAULTS), "Display defaults restored in this browser.", "save-message save-message-success"
        if ctx.triggered_id != "save-display-preferences":
            return no_update, no_update, no_update
        preferences = _normalized_preferences({"theme": theme, "density": density})
        return preferences, "Display preferences saved in this browser.", "save-message save-message-success"

    @app.callback(
        Output("application-shell", "className"),
        Output("settings-theme", "value"),
        Output("settings-density", "value"),
        Input("display-preferences", "data"),
    )
    def apply_preferences(value: object):
        preferences = _normalized_preferences(value)
        return (
            f"application-shell theme-{preferences['theme']} density-{preferences['density']}",
            preferences["theme"],
            preferences["density"],
        )
