"""Permanent dashboard shell and mounted route containers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dash import dcc, html

from dashboard.pages.common import not_found_page
from dashboard.routing import (
    NAVIGATION_GROUPS,
    ROUTE_REGISTRY,
    navigation_link_id,
    route_container_styles_for_path,
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
                    dcc.Link(
                        label,
                        id=navigation_link_id(path),
                        href=path,
                        className=(
                            "navigation-link navigation-link-active"
                            if path == active_path
                            else "navigation-link"
                        ),
                    )
                    for path, label in links
                ],
                className=(
                    "navigation-links sidebar-utility-links"
                    if group_label == "Global"
                    else "navigation-links"
                ),
            )
        )
    return html.Nav(
        [
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
                ],
                href="/",
                title="Quant Factory Home",
                className="sidebar-brand",
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
            dcc.Location(
                id="url",
                pathname=initial_pathname,
                refresh="callback-nav",
            ),
            html.Div(
                navigation(initial_pathname),
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
            ),
        ],
        id="application-shell",
        className="application-shell theme-light",
    )
