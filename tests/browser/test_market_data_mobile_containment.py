"""Mobile containment regression for long local market-data paths."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from tests.browser.test_backtest_results_spym_stability import (
    REPOSITORY_ROOT,
    _free_port,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
    _attach_diagnostics,
    _wait_for_callbacks_to_settle,
)


@pytest.fixture()
def long_path_market_data_server(tmp_path: Path):
    """Start a portable dashboard whose missing data config has a long path."""

    long_segment = "machine-specific-market-data-root-" + ("x" * 128)
    config_path = tmp_path / long_segment / "data_locations.local.toml"
    database = tmp_path / "state" / "dashboard.sqlite3"
    server_log = tmp_path / "market-data-containment-server.log"
    port = _free_port()
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app
from dashboard.health import inspect_catalog

database = Path(sys.argv[1])
config_path = Path(sys.argv[2])
port = int(sys.argv[3])
app = create_app(
    review_database=database,
    catalog_snapshot=inspect_catalog(config_path=config_path),
)
app.run(host="127.0.0.1", port=port, debug=False)
"""
    env = dict(os.environ)
    env["QUANT_FACTORY_DB_PATH"] = str(database)
    with server_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                code,
                str(database),
                str(config_path),
                str(port),
            ],
            cwd=REPOSITORY_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(base_url + "/research/market-data")
        yield base_url, server_log, config_path
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _horizontal_overflow_nodes(
    page, *, route_selector: str
) -> list[dict[str, object]]:
    return page.locator(f"{route_selector} *").evaluate_all(
        """
        (elements) => {
          const overflows = (element) => {
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            if (style.display === 'none' || style.visibility === 'hidden'
                || rect.width <= 0 || rect.height <= 0) {
              return false;
            }
            const extendsPastViewport = rect.left < -1
              || rect.right > window.innerWidth + 1;
            const exposesOverflow = element.scrollWidth > element.clientWidth + 1
              && !['auto', 'scroll', 'hidden', 'clip'].includes(style.overflowX);
            return extendsPastViewport || exposesOverflow;
          };
          return elements.flatMap((element) => {
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            if (!overflows(element)
                || Array.from(element.children).some(overflows)) {
              return [];
            }
            return [{
              tag: element.tagName,
              id: element.id,
              className: String(element.className || ''),
              left: rect.left,
              right: rect.right,
              width: rect.width,
              clientWidth: element.clientWidth,
              scrollWidth: element.scrollWidth,
              overflowWrap: style.overflowWrap,
              text: (element.textContent || '').trim().slice(0, 240)
            }];
          });
        }
        """
    )


def test_long_market_data_path_stays_contained_at_mobile_width(
    long_path_market_data_server,
) -> None:
    base_url, _server_log, config_path = long_path_market_data_server
    events: list[dict[str, object]] = []
    action = {"name": "open Market Data with a long local configuration path"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/market-data", wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page.locator("#route-research-market-data h1")).to_have_text(
                "Market Data"
            )
            warning = page.locator(
                "#route-research-market-data .operator-message-warning"
            )
            expect(warning).to_contain_text(str(config_path))
            page.get_by_text("Technical manifest references", exact=True).click()
            technical_references = page.locator(
                "#route-research-market-data details li"
            )
            expect(technical_references.first).to_be_visible()
            overflow_nodes = _horizontal_overflow_nodes(
                page, route_selector="#route-research-market-data"
            )
            assert overflow_nodes == [], json.dumps(overflow_nodes, indent=2)
            assert page.evaluate("document.documentElement.scrollWidth") <= 391
            assert page.evaluate("document.body.scrollWidth") <= 391
            _assert_no_browser_errors(events)

            action["name"] = "refresh Market Data with a long local configuration path"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(warning).to_contain_text(str(config_path))
            page.get_by_text("Technical manifest references", exact=True).click()
            expect(technical_references.first).to_be_visible()
            overflow_nodes = _horizontal_overflow_nodes(
                page, route_selector="#route-research-market-data"
            )
            assert overflow_nodes == [], json.dumps(overflow_nodes, indent=2)
            assert page.evaluate("document.documentElement.scrollWidth") <= 391
            assert page.evaluate("document.body.scrollWidth") <= 391
            _assert_no_browser_errors(events)
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("path", "container_id", "heading"),
    (
        ("/system", "route-system", "System Status"),
        ("/system/providers", "route-system-providers", "Data Sources"),
    ),
    ids=("system-status", "data-sources"),
)
def test_long_missing_data_config_path_stays_contained_on_system_routes(
    long_path_market_data_server, path: str, container_id: str, heading: str
) -> None:
    base_url, _server_log, config_path = long_path_market_data_server
    events: list[dict[str, object]] = []
    action = {"name": f"open {heading} with a long local configuration path"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + path, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            route = page.locator(f"#{container_id}")
            expect(route.locator("h1")).to_have_text(heading)
            expect(route).to_contain_text(str(config_path))
            overflow_nodes = _horizontal_overflow_nodes(
                page, route_selector=f"#{container_id}"
            )
            assert overflow_nodes == [], json.dumps(overflow_nodes, indent=2)
            assert page.evaluate("document.documentElement.scrollWidth") <= 391
            assert page.evaluate("document.body.scrollWidth") <= 391
            _assert_no_browser_errors(events)

            action["name"] = (
                f"refresh {heading} with a long local configuration path"
            )
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(route).to_contain_text(str(config_path))
            overflow_nodes = _horizontal_overflow_nodes(
                page, route_selector=f"#{container_id}"
            )
            assert overflow_nodes == [], json.dumps(overflow_nodes, indent=2)
            assert page.evaluate("document.documentElement.scrollWidth") <= 391
            assert page.evaluate("document.body.scrollWidth") <= 391
            _assert_no_browser_errors(events)
        finally:
            browser.close()
