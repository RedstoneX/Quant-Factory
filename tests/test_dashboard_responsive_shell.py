"""Focused contract tests for the responsive permanent dashboard shell."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import Dash, dcc, html, no_update

from dashboard.callbacks.routing import register_routing_callbacks, responsive_navigation_state
from dashboard.routing import NAVIGATION_LINKS, ROUTE_CONTAINER_IDS, ROUTE_REGISTRY
from dashboard.shell import (
    create_dashboard_layout,
    responsive_drawer_class,
    responsive_page_label,
)
from dashboard.state_ownership import STATE_OWNERS


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None:
        yield from _walk(children)


def _page_factory(path: str, _context: Any, _configurations: Any, **_kwargs: Any):
    return html.Div(html.H1(path))


def test_responsive_shell_mounts_one_location_and_accessible_drawer_controls() -> None:
    layout = create_dashboard_layout(
        None,
        (),
        page_factory=_page_factory,
        initial_pathname="/research/setup",
    )
    components = list(_walk(layout))
    ids = {str(component.id) for component in components if getattr(component, "id", None)}
    locations = [component for component in components if isinstance(component, dcc.Location)]
    toggle = next(component for component in components if getattr(component, "id", None) == "navigation-drawer-toggle")

    assert len(locations) == 1
    assert locations[0].id == "url"
    assert {
        "navigation-drawer-state",
        "navigation-drawer-toggle",
        "primary-navigation",
        "responsive-active-page",
        "navigation-drawer-panel",
        "navigation-container",
        "page-content",
    } <= ids
    assert getattr(toggle, "aria-controls") == "navigation-drawer-panel"
    assert getattr(toggle, "aria-expanded") == "false"
    assert getattr(toggle, "aria-label") == "Toggle navigation menu"
    assert next(
        component
        for component in components
        if getattr(component, "id", None) == "responsive-active-page"
    ).children == "Set up"


def test_progressive_shell_renders_only_the_requested_route_content() -> None:
    rendered_paths: list[str] = []

    def page_factory(path: str, *_args: Any, **_kwargs: Any):
        rendered_paths.append(path)
        return html.Div(path)

    layout = create_dashboard_layout(
        None,
        (),
        page_factory=page_factory,
        initial_pathname="/research/backtest-results",
        progressive_routes=True,
    )
    containers = {
        component.id: component
        for component in _walk(layout)
        if getattr(component, "id", None)
        and str(component.id).startswith("route-")
    }

    assert rendered_paths == ["/research/backtest-results"]
    assert containers["route-research-backtest-results"].children is not None
    assert containers["route-research-setup"].children is None
    assert containers["route-home"].children is None


def test_route_navigation_hydrates_only_the_newly_active_container() -> None:
    app = Dash(__name__)
    register_routing_callbacks(
        app,
        route_renderer=lambda path: html.Div(path, id="rendered-route"),
    )
    entry = next(
        value
        for key, value in app.callback_map.items()
        if "route-home.children" in key
    )
    callback = getattr(entry["callback"], "__wrapped__", entry["callback"])

    result = callback("/research/setup")
    target_index = ROUTE_CONTAINER_IDS.index("route-research-setup")

    assert result[target_index].children == "/research/setup"
    assert all(
        value is no_update
        for index, value in enumerate(result)
        if index != target_index
    )


def test_responsive_page_labels_cover_registered_routes_and_unknowns() -> None:
    labels = {path: responsive_page_label(path) for path, _ in ROUTE_REGISTRY}

    assert labels["/"] == "Dashboard"
    assert all(label != "Page not found" for label in labels.values())
    assert responsive_page_label("/genuinely-unknown") == "Page not found"
    assert responsive_page_label("/research/strategy-review") == "Page not found"


def test_paper_is_contextual_not_primary_navigation() -> None:
    primary_paths = dict(NAVIGATION_LINKS)

    assert "/paper/fleet" not in primary_paths
    assert "/paper/strategy" not in primary_paths
    assert responsive_page_label("/paper/fleet") == "Paper trading"


def test_strategy_review_route_is_retired_without_duplicate_navigation() -> None:
    assert "/research/strategy-review" not in dict(ROUTE_REGISTRY)
    assert "/research/strategy-review" not in dict(NAVIGATION_LINKS)


def test_responsive_navigation_toggles_explicitly_and_closes_on_route_change() -> None:
    opened = responsive_navigation_state(
        "/research/ideas",
        False,
        triggered_id="navigation-drawer-toggle",
    )
    closed_by_toggle = responsive_navigation_state(
        "/research/ideas",
        True,
        triggered_id="navigation-drawer-toggle",
    )
    closed_by_route = responsive_navigation_state(
        "/research/setup",
        True,
        triggered_id="url",
    )
    closed_by_selection = responsive_navigation_state(
        "/research/setup",
        True,
        triggered_id="primary-navigation",
    )

    assert opened == (
        "Ideas",
        True,
        "true",
        "navigation-drawer-panel navigation-drawer-panel-open",
    )
    assert closed_by_toggle == (
        "Ideas",
        False,
        "false",
        "navigation-drawer-panel",
    )
    assert closed_by_route == (
        "Set up",
        False,
        "false",
        "navigation-drawer-panel",
    )
    assert closed_by_selection == closed_by_route
    assert responsive_drawer_class(False) == "navigation-drawer-panel"


def test_navigation_drawer_has_one_documented_state_owner() -> None:
    assert STATE_OWNERS["navigation_drawer"] == {
        "source": "navigation-drawer-state.data",
        "owner": "dashboard.callbacks.routing",
        "rule": (
            "An explicit menu-button click toggles the responsive drawer; every "
            "primary-navigation selection or pathname change closes it without "
            "rebuilding navigation or writing the URL."
        ),
    }


def test_stylesheet_declares_exact_breakpoints_and_quartet_profiles() -> None:
    css = (Path(__file__).parents[1] / "dashboard" / "assets" / "style.css").read_text()

    assert "@media (min-width: 1200px)" in css
    assert "@media (max-width: 1199px)" in css
    assert "@media (min-width: 768px) and (max-width: 1199px)" in css
    assert "@media (max-width: 767px)" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".run-analysis-tabs" in css and "overflow-x: auto;" in css
    assert ".qf-data-grid" in css and ".run-comparison-result" in css
