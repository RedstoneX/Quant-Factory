"""Focused contract tests for the responsive permanent dashboard shell."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import dcc, html

from dashboard.callbacks.routing import responsive_navigation_state
from dashboard.routing import NAVIGATION_LINKS, ROUTE_REGISTRY
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


def test_responsive_page_labels_cover_registered_routes_and_unknowns() -> None:
    labels = {path: responsive_page_label(path) for path, _ in ROUTE_REGISTRY}

    assert labels["/"] == "Home"
    assert all(label != "Page not found" for label in labels.values())
    assert responsive_page_label("/genuinely-unknown") == "Page not found"
    assert responsive_page_label("/research/strategy-review") == "Page not found"


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
