"""Permanent dashboard shell and mounted route containers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dash import dcc, html

from dashboard.pages.common import not_found_page
from dashboard.routing import (
    NAVIGATION_GROUPS,
    NAVIGATION_LINKS,
    ROUTE_REGISTRY,
    navigation_item_id,
    navigation_link_id,
    route_container_styles_for_path,
)


RESPONSIVE_PAGE_LABELS = {
    "/": "Home",
    **dict(NAVIGATION_LINKS),
}


def responsive_page_label(pathname: str | None) -> str:
    """Return the operator-facing active-page name for the responsive header."""

    route = pathname or "/"
    return RESPONSIVE_PAGE_LABELS.get(route, "Page not found")


def responsive_drawer_class(is_open: bool) -> str:
    """Return the drawer class without changing the persistent navigation tree."""

    return (
        "navigation-drawer-panel navigation-drawer-panel-open"
        if is_open
        else "navigation-drawer-panel"
    )


def navigation(pathname: str = "/") -> html.Nav:
    active_path = pathname or "/"
    groups: list[Any] = []
    for group_label, links in NAVIGATION_GROUPS:
        if group_label != "Global":
            groups.append(html.P(group_label, className="sidebar-section-label"))
        groups.append(
            html.Div(
                [
                    html.Div(
                        dcc.Link(
                            [
                                html.Span(label),
                                html.Span(
                                    "Current page",
                                    className="navigation-current-label",
                                ),
                            ],
                            id=navigation_link_id(path),
                            href=path,
                            className=(
                                "navigation-link navigation-link-active"
                                if path == active_path
                                else "navigation-link"
                            ),
                        ),
                        id=navigation_item_id(path),
                        className="navigation-item",
                        role="listitem",
                        **(
                            {"aria-current": "page"}
                            if path == active_path
                            else {}
                        ),
                    )
                    for path, label in links
                ],
                className=(
                    "navigation-links sidebar-utility-links"
                    if group_label == "Global"
                    else "navigation-links"
                ),
                role="list",
            )
        )
    return html.Nav(
        [
            html.Div(
                dcc.Link(
                    [
                        html.Span("QF", className="sidebar-logo"),
                        html.Div(
                            [
                                html.P("QUANT", className="sidebar-title-line"),
                                html.P("FACTORY", className="sidebar-title-line"),
                            ],
                            className="sidebar-title-lockup",
                        ),
                        html.Span(
                            "Current page",
                            className="navigation-current-label",
                        ),
                    ],
                    href="/",
                    title="Quant Factory Home",
                    className="sidebar-brand",
                ),
                id=navigation_item_id("/"),
                className="sidebar-brand-item navigation-item",
                **(
                    {"aria-current": "page"}
                    if active_path == "/"
                    else {}
                ),
            ),
            html.Div(groups, className="sidebar-navigation-groups"),
            html.Div(
                [
                    html.Span("DO", className="sidebar-user-avatar"),
                    html.Div(
                        [
                            html.Strong("Demo Operator"),
                            html.Small("Operator"),
                        ],
                        className="sidebar-user-copy",
                    ),
                ],
                className="sidebar-status",
            ),
        ],
        id="primary-navigation",
        n_clicks=0,
        className="sidebar",
        **{"aria-label": "Primary navigation"},
    )


def mounted_route_containers(
    page_factory: Callable[..., html.Div],
    context: Any,
    configurations: Any = None,
    *,
    initial_pathname: str = "/",
    recent_runs: tuple[Any, ...] = (),
    recent_events: tuple[Any, ...] = (),
    selected_run_panel: Any | None = None,
    selected_run_id: str | None = None,
    all_runs: tuple[Any, ...] = (),
    history_rows: tuple[dict[str, object], ...] = (),
) -> list[html.Div]:
    containers: list[html.Div] = []
    initial_styles = route_container_styles_for_path(initial_pathname)
    for index, (path, container_id) in enumerate(ROUTE_REGISTRY):
        containers.append(
            html.Div(
                page_factory(
                    path,
                    context,
                    configurations,
                    recent_runs=recent_runs,
                    recent_events=recent_events,
                    selected_run_panel=selected_run_panel,
                    selected_run_id=selected_run_id,
                    all_runs=all_runs,
                    history_rows=history_rows,
                ),
                id=container_id,
                className="route-container",
                style=initial_styles[index],
            )
        )
    containers.append(
        html.Div(
            not_found_page("this address"),
            id="route-not-found",
            className="route-container",
            style=initial_styles[-1],
        )
    )
    return containers


def create_dashboard_layout(
    context: Any,
    configurations: Any,
    *,
    page_factory: Callable[..., html.Div],
    initial_pathname: str = "/",
    recent_runs: tuple[Any, ...] = (),
    recent_events: tuple[Any, ...] = (),
    selected_run_panel: Any | None = None,
    selected_run_id: str | None = None,
    all_runs: tuple[Any, ...] = (),
    history_rows: tuple[dict[str, object], ...] = (),
) -> html.Div:
    return html.Div(
        [
            html.A(
                "Skip to main content",
                href="#page-content",
                className="skip-link",
            ),
            dcc.Location(
                id="url",
                refresh="callback-nav",
            ),
            dcc.Store(
                id="navigation-drawer-state",
                data=False,
                storage_type="memory",
            ),
            html.Div(
                [
                    html.Header(
                        [
                            html.Button(
                                [
                                    html.Span(
                                        "☰",
                                        className="navigation-menu-icon",
                                        **{"aria-hidden": "true"},
                                    ),
                                    html.Span("Menu"),
                                ],
                                id="navigation-drawer-toggle",
                                n_clicks=0,
                                type="button",
                                className="navigation-drawer-toggle",
                                **{
                                    "aria-controls": "navigation-drawer-panel",
                                    "aria-expanded": "false",
                                    "aria-label": "Toggle navigation menu",
                                },
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        "Current page",
                                        className="responsive-page-label",
                                    ),
                                    html.Strong(
                                        responsive_page_label(initial_pathname),
                                        id="responsive-active-page",
                                    ),
                                ],
                                className="responsive-page-identity",
                            ),
                            dcc.Link(
                                "Quant Factory",
                                href="/",
                                className="responsive-home-link",
                            ),
                        ],
                        className="responsive-navigation-header",
                    ),
                    html.Div(
                        navigation(initial_pathname),
                        id="navigation-drawer-panel",
                        className=responsive_drawer_class(False),
                    ),
                ],
                id="navigation-container",
            ),
            html.Main(
                mounted_route_containers(
                    page_factory,
                    context,
                    configurations,
                    initial_pathname=initial_pathname,
                    recent_runs=recent_runs,
                    recent_events=recent_events,
                    selected_run_panel=selected_run_panel,
                    selected_run_id=selected_run_id,
                    all_runs=all_runs,
                    history_rows=history_rows,
                ),
                id="page-content",
                className="application-content",
                tabIndex=-1,
            ),
        ],
        id="application-shell",
        className="application-shell theme-light",
    )
