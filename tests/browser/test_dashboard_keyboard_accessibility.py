"""Real-browser keyboard evidence for non-Results dashboard access."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from tests.browser.dashboard_diagnostics import (
    assert_browser_diagnostics_clean,
    attach_browser_diagnostics,
)
from tests.browser.test_dashboard_lifecycle import (
    _wait_for_callbacks_to_settle,
    mounted_workflow_server,
)


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
