"""Route-shell callback ownership for the mounted dashboard."""

from __future__ import annotations

from dash import Dash, Input, Output, State, ctx
from dash.exceptions import PreventUpdate

from dashboard.routing import (
    NAVIGATION_ITEMS,
    NAVIGATION_LINKS,
    ROUTE_CONTAINER_IDS,
    navigation_classes_for_path,
    navigation_current_states_for_path,
    navigation_item_id,
    navigation_link_id,
    route_container_styles_for_path,
)
from dashboard.shell import responsive_drawer_class, responsive_page_label


OWNED_STATE = {
    "active_route": "url.pathname",
    "navigation_drawer": "navigation-drawer-state.data",
}


def responsive_navigation_state(
    pathname: str | None,
    current_open: bool | None,
    *,
    triggered_id: str | None,
) -> tuple[str, bool, str, str]:
    """Derive active-page copy and drawer presentation from explicit input."""

    is_open = (
        not bool(current_open)
        if triggered_id == "navigation-drawer-toggle"
        else False
    )
    return (
        responsive_page_label(pathname),
        is_open,
        "true" if is_open else "false",
        responsive_drawer_class(is_open),
    )


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
        *[
            Output(navigation_item_id(path), "aria-current")
            for path, _ in NAVIGATION_ITEMS
        ],
        Input("url", "pathname"),
    )
    def update_navigation_active_state(pathname: str | None):
        if pathname is None:
            raise PreventUpdate
        return (
            *navigation_classes_for_path(pathname),
            *navigation_current_states_for_path(pathname),
        )

    @app.callback(
        Output("responsive-active-page", "children"),
        Output("navigation-drawer-state", "data"),
        Output("navigation-drawer-toggle", "aria-expanded"),
        Output("navigation-drawer-panel", "className"),
        Input("url", "pathname"),
        Input("navigation-drawer-toggle", "n_clicks"),
        Input("primary-navigation", "n_clicks"),
        State("navigation-drawer-state", "data"),
    )
    def update_responsive_navigation(
        pathname: str | None,
        _toggle_clicks: int | None,
        _navigation_clicks: int | None,
        current_open: bool | None,
    ):
        return responsive_navigation_state(
            pathname,
            current_open,
            triggered_id=ctx.triggered_id,
        )
