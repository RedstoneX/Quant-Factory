"""Responsive browser acceptance for the permanent mounted-route shell."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect, sync_playwright

from dashboard.routing import NAVIGATION_LINKS, ROUTE_REGISTRY, navigation_link_id
from dashboard.shell import responsive_page_label
from tests.browser.test_backtest_results_spym_stability import _visible_routes
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
    _attach_diagnostics,
    _wait_for_callbacks_to_settle,
    mounted_workflow_server,
)


VIEWPORTS = (
    ("desktop", {"width": 1440, "height": 1000}),
    ("tablet", {"width": 1024, "height": 900}),
    ("mobile", {"width": 390, "height": 844}),
)

BREAKPOINT_PROBES = (
    (1440, 1, False),
    (1200, 1, False),
    (1199, 2, True),
    (1024, 2, True),
    (768, 2, True),
    (767, 4, True),
    (390, 4, True),
)

PRIMARY_WORKFLOW_PATHS = (
    "/research/ideas",
    "/research/setup",
    "/research/run-test",
    "/research/backtest-results",
    "/research/compare-backtests",
)


def _assert_document_contained(page: Page) -> dict[str, int]:
    measurements = page.evaluate(
        """
        () => ({
          viewport: window.innerWidth,
          documentClient: document.documentElement.clientWidth,
          documentScroll: document.documentElement.scrollWidth,
          bodyClient: document.body.clientWidth,
          bodyScroll: document.body.scrollWidth
        })
        """
    )
    assert measurements["documentScroll"] <= measurements["documentClient"] + 1
    assert measurements["bodyScroll"] <= measurements["bodyClient"] + 1
    return measurements


def _assert_visible_surfaces_contained(page: Page) -> list[dict[str, Any]]:
    measurements = page.locator(
        ".qf-data-grid, .run-comparison-result, .run-analysis-tabs, .dash-graph"
    ).evaluate_all(
        """
        (elements) => elements
          .filter((element) => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
              && rect.width > 0 && rect.height > 0;
          })
          .map((element) => {
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return {
              id: element.id || element.className,
              left: rect.left,
              right: rect.right,
              width: rect.width,
              clientWidth: element.clientWidth,
              scrollWidth: element.scrollWidth,
              overflowX: style.overflowX
            };
          })
        """
    )
    for measurement in measurements:
        assert measurement["left"] >= -1, measurement
        assert measurement["right"] <= page.viewport_size["width"] + 1, measurement
        if measurement["scrollWidth"] > measurement["clientWidth"] + 1:
            assert measurement["overflowX"] in {"auto", "scroll"}, measurement
    return measurements


def _assert_shell_mode(page: Page, *, width: int) -> None:
    header = page.locator(".responsive-navigation-header")
    drawer = page.locator("#navigation-drawer-panel")
    toggle = page.locator("#navigation-drawer-toggle")
    if width >= 1200:
        expect(header).to_be_hidden()
        expect(drawer).to_be_visible()
        expect(page.locator("#navigation-drawer-panel .sidebar")).to_be_visible()
    else:
        expect(header).to_be_visible()
        expect(toggle).to_be_visible()
        expect(toggle).to_have_attribute("aria-label", "Toggle navigation menu")
        expect(toggle).to_have_attribute("aria-expanded", "false")
        expect(drawer).to_be_hidden()


def _assert_route(page: Page, base_url: str, path: str, container_id: str) -> None:
    expect(page).to_have_url(base_url + path)
    expect(page.locator(f"#{container_id}")).to_be_visible()
    assert _visible_routes(page) == [container_id]
    expect(page.locator("#responsive-active-page")).to_have_text(
        responsive_page_label(path)
    )
    active = page.locator(".navigation-link-active")
    if path in dict(NAVIGATION_LINKS):
        expect(active).to_have_count(1)
        expect(active).to_have_attribute("id", navigation_link_id(path))
    else:
        expect(active).to_have_count(0)


def _write_evidence(
    root: Path,
    name: str,
    *,
    records: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.json").write_text(
        json.dumps({"records": records, "events": events}, indent=2),
        encoding="utf-8",
    )


@pytest.mark.parametrize("viewport_name,viewport", VIEWPORTS, ids=lambda value: str(value))
def test_every_route_direct_refresh_and_containment_at_each_viewport(
    mounted_workflow_server,
    tmp_path: Path,
    viewport_name: str,
    viewport: dict[str, int],
) -> None:
    base_url, server_log, _ = mounted_workflow_server
    events: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    routes = (*ROUTE_REGISTRY, ("/unknown-route", "route-not-found"))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport=viewport)
        try:
            for path, container_id in routes:
                page = context.new_page()
                action = {"name": f"{viewport_name} direct {path}"}
                pending = _attach_diagnostics(page, events, action)
                try:
                    page.goto(base_url + path, wait_until="networkidle")
                    _wait_for_callbacks_to_settle(page, pending)
                    _assert_route(page, base_url, path, container_id)
                    _assert_shell_mode(page, width=viewport["width"])
                    direct_widths = _assert_document_contained(page)
                    direct_surfaces = _assert_visible_surfaces_contained(page)

                    action["name"] = f"{viewport_name} refresh {path}"
                    page.reload(wait_until="networkidle")
                    _wait_for_callbacks_to_settle(page, pending)
                    _assert_route(page, base_url, path, container_id)
                    _assert_shell_mode(page, width=viewport["width"])
                    refresh_widths = _assert_document_contained(page)
                    refresh_surfaces = _assert_visible_surfaces_contained(page)
                    _assert_no_browser_errors(events)
                    records.append(
                        {
                            "path": path,
                            "container": container_id,
                            "direct": direct_widths,
                            "refresh": refresh_widths,
                            "direct_surfaces": direct_surfaces,
                            "refresh_surfaces": refresh_surfaces,
                        }
                    )
                    page.screenshot(
                        path=tmp_path / f"{viewport_name}-{container_id}.png",
                        full_page=True,
                    )
                except Exception:
                    page.screenshot(
                        path=tmp_path / f"{viewport_name}-{container_id}-failure.png",
                        full_page=True,
                    )
                    (tmp_path / f"{viewport_name}-server.log").write_text(
                        server_log.read_text(encoding="utf-8", errors="replace"),
                        encoding="utf-8",
                    )
                    raise
                finally:
                    page.close()
        finally:
            _write_evidence(
                tmp_path,
                f"responsive-routes-{viewport_name}",
                records=records,
                events=events,
            )
            context.close()
            browser.close()


@pytest.mark.parametrize("viewport_name,viewport", VIEWPORTS, ids=lambda value: str(value))
def test_navigation_drawer_back_forward_and_home_at_each_viewport(
    mounted_workflow_server,
    tmp_path: Path,
    viewport_name: str,
    viewport: dict[str, int],
) -> None:
    base_url, server_log, _ = mounted_workflow_server
    events: list[dict[str, Any]] = []
    action = {"name": f"{viewport_name} workflow navigation"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            for path in PRIMARY_WORKFLOW_PATHS:
                action["name"] = f"{viewport_name} navigate {path}"
                if viewport["width"] < 1200:
                    page.locator("#navigation-drawer-toggle").click()
                    expect(page.locator("#navigation-drawer-toggle")).to_have_attribute(
                        "aria-expanded", "true"
                    )
                    expect(page.locator("#navigation-drawer-panel")).to_be_visible()
                page.locator(f"#{navigation_link_id(path)}").click()
                _wait_for_callbacks_to_settle(page, pending)
                _assert_route(page, base_url, path, dict(ROUTE_REGISTRY)[path])
                if viewport["width"] < 1200:
                    expect(page.locator("#navigation-drawer-toggle")).to_have_attribute(
                        "aria-expanded", "false"
                    )
                    expect(page.locator("#navigation-drawer-panel")).to_be_hidden()
                _assert_document_contained(page)

            if viewport["width"] < 1200:
                page.locator("#navigation-drawer-toggle").click()
                expect(page.locator("#navigation-drawer-panel")).to_be_visible()
                page.locator(
                    f"#{navigation_link_id('/research/compare-backtests')}"
                ).click()
                _wait_for_callbacks_to_settle(page, pending)
                expect(page.locator("#navigation-drawer-panel")).to_be_hidden()
                _assert_route(
                    page,
                    base_url,
                    "/research/compare-backtests",
                    "route-research-compare-backtests",
                )

            page.go_back(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            if viewport["width"] < 1200:
                _assert_route(
                    page,
                    base_url,
                    "/research/compare-backtests",
                    "route-research-compare-backtests",
                )
                page.go_back(wait_until="networkidle")
                _wait_for_callbacks_to_settle(page, pending)
            _assert_route(
                page,
                base_url,
                "/research/backtest-results",
                "route-research-backtest-results",
            )
            page.go_forward(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _assert_route(
                page,
                base_url,
                "/research/compare-backtests",
                "route-research-compare-backtests",
            )

            if viewport["width"] < 1200:
                page.locator("#navigation-drawer-toggle").click()
                expect(page.locator("#navigation-drawer-panel")).to_be_visible()
            page.locator("#navigation-drawer-panel .sidebar-brand").click()
            _wait_for_callbacks_to_settle(page, pending)
            _assert_route(page, base_url, "/", "route-home")
            _assert_document_contained(page)
            _assert_no_browser_errors(events)
            page.screenshot(
                path=tmp_path / f"responsive-navigation-{viewport_name}.png",
                full_page=True,
            )
        except Exception:
            page.screenshot(
                path=tmp_path / f"responsive-navigation-{viewport_name}-failure.png",
                full_page=True,
            )
            (tmp_path / f"responsive-navigation-{viewport_name}-server.log").write_text(
                server_log.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
            raise
        finally:
            _write_evidence(
                tmp_path,
                f"responsive-navigation-{viewport_name}",
                records=[{"final_path": page.url.removeprefix(base_url)}],
                events=events,
            )
            browser.close()


@pytest.mark.parametrize(
    "width,expected_rows,drawer_expected",
    BREAKPOINT_PROBES,
    ids=lambda value: str(value),
)
def test_shell_and_quartet_breakpoint_boundaries(
    mounted_workflow_server,
    width: int,
    expected_rows: int,
    drawer_expected: bool,
) -> None:
    base_url, _, _ = mounted_workflow_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900})
        try:
            page.goto(base_url + "/research/backtest-results", wait_until="networkidle")
            items = page.locator("#results-operator-context .operator-context-item")
            expect(items).to_have_count(4)
            tops = items.evaluate_all(
                "elements => elements.map(element => Math.round(element.getBoundingClientRect().top))"
            )
            row_count = len({top for top in tops})
            assert row_count == expected_rows, {"width": width, "tops": tops}
            assert page.locator(".responsive-navigation-header").is_visible() is drawer_expected
            assert page.locator("#navigation-drawer-panel").is_visible() is (not drawer_expected)
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)
        finally:
            browser.close()
