"""Route-shell callback ownership for the mounted dashboard."""

from __future__ import annotations

from dash import Dash, Input, Output
from dash.exceptions import PreventUpdate

from dashboard.routing import (
    NAVIGATION_LINKS,
    ROUTE_CONTAINER_IDS,
    navigation_classes_for_path,
    navigation_link_id,
    route_container_styles_for_path,
)


OWNED_STATE = {
    "active_route": "url.pathname",
}


def register_routing_callbacks(app: Dash) -> None:
    """Register the only callbacks that derive UI state from the active route."""

    @app.callback(
        *[Output(container_id, "style") for container_id in ROUTE_CONTAINER_IDS],
        Input("url", "pathname"),
    )
    def update_route_visibility(pathname: str | None):
        if pathname is None:
            raise PreventUpdate
        return route_container_styles_for_path(pathname)

    @app.callback(
        *[
            Output(navigation_link_id(path), "className")
            for path, _ in NAVIGATION_LINKS
        ],
        Input("url", "pathname"),
    )
    def update_navigation_active_state(pathname: str | None):
        if pathname is None:
            raise PreventUpdate
        return navigation_classes_for_path(pathname)
