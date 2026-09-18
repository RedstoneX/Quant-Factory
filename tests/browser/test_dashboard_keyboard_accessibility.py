"""Real-browser keyboard evidence for non-Results dashboard access."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from dashboard.routing import navigation_item_id
from tests.browser.dashboard_diagnostics import (
    assert_browser_diagnostics_clean,
    attach_browser_diagnostics,
)
from tests.browser.test_dashboard_lifecycle import (
    _wait_for_callbacks_to_settle,
    mounted_workflow_server,
)


def _assert_accessible_current_page_link(
    page,
    *,
    path: str,
    accessible_name: str,
) -> None:
    current = page.locator('[aria-current="page"]')
    expect(current).to_have_count(1)
    expect(current).to_have_attribute("id", navigation_item_id(path))
    expect(
        page.get_by_role(
            "link",
            name=re.compile(rf"^{re.escape(accessible_name)}\s+Current page$", re.I),
        )
    ).to_have_count(1)
    expect(
        page.get_by_role("link", name=re.compile(r"Current page", re.I))
    ).to_have_count(1)


def _assert_current_link_contained(
    page,
    *,
    expected_height: float | None = None,
) -> None:
    current_box = page.locator('[aria-current="page"]').bounding_box()
    link_box = page.locator('[aria-current="page"] a').bounding_box()
    sidebar_box = page.locator("#primary-navigation").bounding_box()
    assert current_box is not None
    assert link_box is not None
    assert sidebar_box is not None
    tolerance = 0.5
    if expected_height is not None:
        assert abs(link_box["height"] - expected_height) <= tolerance
        assert abs(current_box["height"] - expected_height) <= tolerance
    assert link_box["x"] >= current_box["x"] - tolerance
    assert link_box["x"] + link_box["width"] <= (
        current_box["x"] + current_box["width"] + tolerance
    )
    assert link_box["x"] >= sidebar_box["x"] - tolerance
    assert link_box["x"] + link_box["width"] <= (
        sidebar_box["x"] + sidebar_box["width"] + tolerance
    )


def _open_responsive_navigation(page, viewport: dict[str, int]) -> None:
    if viewport["width"] >= 1200:
        return
    page.locator("#navigation-drawer-toggle").click()
    expect(page.locator("#navigation-drawer-panel")).to_be_visible()
    page.wait_for_timeout(300)


@pytest.mark.parametrize(
    "viewport",
    (
        pytest.param({"width": 1440, "height": 1000}, id="desktop"),
        pytest.param({"width": 390, "height": 844}, id="mobile"),
    ),
)
def test_setup_has_keyboard_bypass_and_named_selector_group(
    mounted_workflow_server,
    viewport: dict[str, int],
) -> None:
    base_url, server_log, _run_id = mounted_workflow_server
    events: list[dict[str, object]] = []
    action = {"name": "open Setup with keyboard"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        pending = attach_browser_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/setup", wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)

            page.keyboard.press("Tab")
            skip_link = page.get_by_role("link", name="Skip to main content")
            expect(skip_link).to_be_focused()
            assert skip_link.evaluate("element => element.matches(':focus-visible')")
            box = skip_link.bounding_box()
            assert box is not None
            assert box["x"] >= 0 and box["y"] >= 0

            page.keyboard.press("Enter")
            expect(page.locator("#page-content")).to_be_focused()
            expect(page).to_have_url(base_url + "/research/setup#page-content")

            selector_group = page.get_by_role("group", name="Saved setup")
            expect(selector_group).to_be_visible()
            selector = selector_group.locator("#configuration-selector")
            selector.focus()
            page.keyboard.press("Enter")
            expect(selector).to_have_attribute("aria-expanded", "true")
            expect(page.get_by_role("listbox")).to_be_visible()
            page.keyboard.press("Escape")
            expect(selector).to_have_attribute("aria-expanded", "false")

            assert_browser_diagnostics_clean(page, events, (server_log,))
        finally:
            browser.close()


@pytest.mark.parametrize(
    "viewport",
    (
        pytest.param({"width": 1440, "height": 1000}, id="desktop"),
        pytest.param({"width": 1024, "height": 768}, id="tablet"),
        pytest.param({"width": 390, "height": 844}, id="mobile"),
    ),
)
def test_active_navigation_item_tracks_browser_history_semantically(
    mounted_workflow_server,
    viewport: dict[str, int],
) -> None:
    base_url, server_log, _run_id = mounted_workflow_server
    events: list[dict[str, object]] = []
    action = {"name": "open Setup directly"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        pending = attach_browser_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/setup", wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _open_responsive_navigation(page, viewport)
            _assert_accessible_current_page_link(
                page,
                path="/research/setup",
                accessible_name="Set up",
            )

            action["name"] = "refresh Setup"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _open_responsive_navigation(page, viewport)
            _assert_accessible_current_page_link(
                page,
                path="/research/setup",
                accessible_name="Set up",
            )

            _assert_current_link_contained(
                page,
                expected_height=62 if viewport["width"] >= 1200 else None,
            )

            action["name"] = "navigate to Run test"
            page.locator("#navigation-link-research-run-test").click()
            _wait_for_callbacks_to_settle(page, pending)
            _open_responsive_navigation(page, viewport)
            _assert_accessible_current_page_link(
                page,
                path="/research/run-test",
                accessible_name="Run test",
            )

            action["name"] = "go back to Setup"
            page.go_back(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _open_responsive_navigation(page, viewport)
            _assert_accessible_current_page_link(
                page,
                path="/research/setup",
                accessible_name="Set up",
            )

            action["name"] = "go forward to Run test"
            page.go_forward(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _open_responsive_navigation(page, viewport)
            _assert_accessible_current_page_link(
                page,
                path="/research/run-test",
                accessible_name="Run test",
            )

            action["name"] = "navigate to Home through the brand"
            page.locator(".sidebar-brand").click()
            _wait_for_callbacks_to_settle(page, pending)
            _open_responsive_navigation(page, viewport)
            _assert_accessible_current_page_link(
                page,
                path="/",
                accessible_name="QF QUANT FACTORY",
            )

            action["name"] = "open an unknown route"
            page.goto(base_url + "/genuinely-unknown", wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _open_responsive_navigation(page, viewport)
            expect(page.locator('[aria-current="page"]')).to_have_count(0)
            expect(
                page.get_by_role("link", name=re.compile(r"Current page", re.I))
            ).to_have_count(0)
            assert_browser_diagnostics_clean(page, events, (server_log,))
        finally:
            browser.close()
