"""Browser proof for Results-owned persisted-run deep links."""

from __future__ import annotations

from urllib.parse import urlencode

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from tests.browser.dashboard_diagnostics import (
    assert_browser_diagnostics_clean,
    attach_browser_diagnostics,
)
from tests.browser.test_backtest_results_spym_stability import BACKTEST_PATH
from tests.browser.test_dashboard_lifecycle import (
    _wait_for_callbacks_to_settle,
    review_compare_server,
)


def _results_url(base_url: str, run_id: str) -> str:
    return f"{base_url}{BACKTEST_PATH}?{urlencode({'run_id': run_id})}"


def _expect_selected_run(page, run_id: str) -> None:
    expect(page.locator("#selected-run-detail")).to_contain_text(
        run_id,
        timeout=10_000,
    )


def test_results_deep_link_refresh_history_and_rejection_are_deterministic(
    review_compare_server,
) -> None:
    base_url, server_log, target_run_id, peer_run_id = review_compare_server
    events: list[dict[str, object]] = []
    action = {"name": "open persisted Results deep link"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        pending_requests = attach_browser_diagnostics(page, events, action)
        try:
            target_url = _results_url(base_url, target_run_id)
            peer_url = _results_url(base_url, peer_run_id)

            page.goto(target_url, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page).to_have_url(target_url)
            _expect_selected_run(page, target_run_id)

            action["name"] = "refresh persisted Results deep link"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page).to_have_url(target_url)
            _expect_selected_run(page, target_run_id)

            action["name"] = "navigate between persisted Results deep links"
            page.goto(peer_url, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            _expect_selected_run(page, peer_run_id)
            page.go_back(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page).to_have_url(target_url)
            _expect_selected_run(page, target_run_id)
            page.go_forward(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page).to_have_url(peer_url)
            _expect_selected_run(page, peer_run_id)

            action["name"] = "show unknown persisted Results deep link"
            unknown_url = _results_url(base_url, "unknown-browser-run")
            page.goto(unknown_url, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page).to_have_url(unknown_url)
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "Requested run not found"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "unknown-browser-run"
            )
            expect(page.locator("#selected-run-detail")).not_to_contain_text(
                peer_run_id
            )

            action["name"] = "show malformed persisted Results deep link"
            malformed_url = (
                f"{base_url}{BACKTEST_PATH}?run_id={target_run_id}"
                f"&run_id={peer_run_id}"
            )
            page.goto(malformed_url, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page).to_have_url(malformed_url)
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "Invalid Results link"
            )
            expect(page.locator("#selected-run-detail")).not_to_contain_text(
                target_run_id
            )
            expect(page.locator("#selected-run-detail")).not_to_contain_text(
                peer_run_id
            )

            assert not pending_requests
            assert_browser_diagnostics_clean(
                page, events, (server_log,)
            )
        finally:
            browser.close()
