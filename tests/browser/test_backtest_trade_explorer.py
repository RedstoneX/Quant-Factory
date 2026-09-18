"""Browser checks for the Backtest Results trade explorer."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from tests.browser.test_backtest_results_spym_stability import (
    BACKTEST_PATH,
    REPOSITORY_ROOT,
    SPYM_OPTION_TEXT,
    _free_port,
    _wait_for_server,
    dashboard_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _attach_diagnostics,
    _select,
    _wait_for_callbacks_to_settle,
)


@pytest.fixture()
def empty_dashboard_server(tmp_path: Path):
    database = tmp_path / "empty-dashboard.sqlite3"
    port = _free_port()
    server_log = tmp_path / "empty-dashboard-server.log"
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app

database = Path(sys.argv[1])
port = int(sys.argv[2])
app = create_app(review_database=database)
app.run(host="127.0.0.1", port=port, debug=False)
"""
    env = dict(os.environ)
    env["QUANT_FACTORY_DB_PATH"] = str(database)
    with server_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(database), str(port)],
            cwd=REPOSITORY_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(f"{base_url}{BACKTEST_PATH}")
        yield base_url, server_log
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _assert_no_errors(events: list[dict[str, object]]) -> None:
    errors = [event for event in events if event.get("kind") in {"console", "pageerror"}]
    assert errors == []


def test_trade_explorer_mounts_with_empty_database(empty_dashboard_server) -> None:
    base_url, _ = empty_dashboard_server
    events: list[dict[str, object]] = []
    action = {"name": "open empty backtest trade explorer"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1360, "height": 900})
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + BACKTEST_PATH, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)

            expect(page.locator("#trade-outcome-filter")).to_be_visible()
            expect(page.locator("#trade-direction-filter")).to_be_visible()
            expect(page.locator("#trade-date-range")).to_be_visible()
            expect(page.locator("#selected-trade-grid")).to_be_visible()
            expect(page.locator("#selected-trade-detail")).to_contain_text(
                "Select a trade row"
            )
            expect(page.locator("#trade-explorer-summary")).to_contain_text(
                "Select a persisted backtest"
            )
            _assert_no_errors(events)
        finally:
            browser.close()


def test_spym_trade_explorer_filters_and_opens_row_detail(dashboard_server) -> None:
    base_url, _, _ = dashboard_server
    events: list[dict[str, object]] = []
    action = {"name": "filter SPYM trade explorer"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + BACKTEST_PATH, wait_until="networkidle")
            _select(page, "selected-run-selector", SPYM_OPTION_TEXT)
            _wait_for_callbacks_to_settle(page, pending)

            expect(page.locator("#trade-explorer-summary")).to_contain_text(
                "Showing 366 of 366 persisted backtest trade rows"
            )
            expect(page.locator("#trade-explorer-summary")).to_contain_text(
                "Date range uses closed trade exit date"
            )

            _select(page, "trade-outcome-filter", "Loss")
            _select(page, "trade-direction-filter", "Long")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page.locator("#trade-explorer-summary")).to_contain_text(
                "persisted backtest trade rows"
            )
            expect(page.locator("#selected-trade-grid")).to_contain_text("Loss")
            expect(page.locator("#selected-trade-grid")).to_contain_text("Long")

            page.locator("#selected-trade-grid .ag-center-cols-container .ag-row").first.click()
            _wait_for_callbacks_to_settle(page, pending)
            detail = page.locator("#selected-trade-detail")
            expect(detail).to_contain_text("Selected trade detail")
            expect(detail).to_contain_text("Theoretical backtest execution")
            expect(detail).to_contain_text("Actual broker fills")
            expect(detail).to_contain_text("Not recorded for this research backtest")
            expect(detail).to_contain_text("no per-trade realized broker slippage")
            _assert_no_errors(events)
        finally:
            browser.close()
