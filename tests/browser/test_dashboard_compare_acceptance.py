"""Portable browser acceptance for persisted-run Compare rendering."""

from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

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
    _select,
    _wait_for_callbacks_to_settle,
)
from tests.test_compare_adapter import _comparison_stack, _persist_run


COMPARE_PATH = "/research/compare-backtests"
QUERY_HYDRATION_OUTPUT = (
    "..comparison-run-selector.value...comparison-query-message.children..."
    "comparison-query-message.className...comparison-exact-link.href..."
    "comparison-exact-link.style.."
)


def _attach_compare_diagnostics(page, events, action):
    pending_requests: set[int] = set()

    def record(kind: str, **details) -> None:
        events.append(
            {
                "timestamp": time.time(),
                "action": action["name"],
                "path": page.url,
                "kind": kind,
                **details,
            }
        )

    page.on("pageerror", lambda error: record("pageerror", message=str(error)))
    page.on(
        "console",
        lambda message: record("console", message=message.text)
        if message.type == "error"
        else None,
    )
    page.on(
        "request",
        lambda request: pending_requests.add(id(request))
        if "/_dash-update-component" in request.url
        else None,
    )
    page.on(
        "requestfinished",
        lambda request: pending_requests.discard(id(request))
        if "/_dash-update-component" in request.url
        else None,
    )
    page.on(
        "requestfailed",
        lambda request: (
            pending_requests.discard(id(request)),
            record(
                "requestfailed",
                url=request.url,
                failure=request.failure,
                request_body=request.post_data,
            ),
        )
        if "/_dash-update-component" in request.url
        else None,
    )
    return pending_requests


@pytest.fixture()
def compare_server(tmp_path: Path):
    database, artifact_root = _comparison_stack(tmp_path)
    fixtures = (
        ("browser-compare-a", (100.0, 105.0, 103.0), 10, 0.001),
        ("browser-compare-b", (100.0, 98.0, 110.0), 20, 0.002),
        ("browser-compare-c", (100.0, 101.0, 102.0), 30, 0.003),
    )
    for index, (run_id, equity, window, fee) in enumerate(fixtures):
        _persist_run(
            database,
            artifact_root,
            run_id=run_id,
            equity_values=equity,
            parameter_window=window,
            fee=fee,
            metrics={
                "total_return": equity[-1] / equity[0] - 1.0,
                "sharpe_ratio": 1.0 + index / 10.0,
                "number_of_trades": 4 + index,
            },
        )

    port = _free_port()
    server_log = tmp_path / "compare-server.log"
    code = """
import json
from pathlib import Path
import sys
from dashboard.app import create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from flask import request
from orchestration import FixtureRunService

database = Path(sys.argv[1])
artifact_root = Path(sys.argv[2])
port = int(sys.argv[3])
app = create_app(
    review_database=database,
    run_service=FixtureRunService(database=database),
    run_detail_adapter=RunDetailDashboardAdapter(
        database=database,
        artifact_root=artifact_root,
    ),
)
@app.server.after_request
def record_callback_status(response):
    if request.path == "/_dash-update-component":
        body = request.get_json(silent=True) or {}
        values = (*body.get("inputs", ()), *body.get("state", ()))
        pathname = next(
            (
                item.get("value")
                for item in values
                if item.get("id") == "url" and item.get("property") == "pathname"
            ),
            None,
        )
        print(
            "COMPARE_CALLBACK_STATUS "
            + json.dumps(
                {
                    "output": body.get("output"),
                    "pathname": pathname,
                    "status": response.status_code,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return response
app.run(host="127.0.0.1", port=port, debug=False)
"""
    env = dict(os.environ)
    env["QUANT_FACTORY_DB_PATH"] = str(database)
    with server_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", code, str(database), str(artifact_root), str(port)],
            cwd=REPOSITORY_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(base_url + COMPARE_PATH)
        yield base_url, server_log
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _plotly_data(page, component_id: str) -> list[dict[str, object]]:
    return page.locator(f"#{component_id}").evaluate(
        """
        (element) => {
          const plot = element.querySelector('.js-plotly-plot');
          if (!plot || !plot.data) return [];
          return plot.data.map((trace) => ({
            name: trace.name,
            x: Array.from(trace.x || []),
            y: Array.from(trace.y || []),
            connectgaps: trace.connectgaps
          }));
        }
        """
    )


def _assert_page_contained(page) -> None:
    document = page.evaluate(
        """
        () => ({
          client: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth,
          bodyClient: document.body.clientWidth,
          bodyScroll: document.body.scrollWidth
        })
        """
    )
    assert document["scroll"] <= document["client"] + 1
    assert document["bodyScroll"] <= document["bodyClient"] + 1
    surfaces = page.locator(
        ".compare-run-card, .compare-chart-card, .compare-table-scroll"
    ).evaluate_all(
        """
        (elements) => elements.map((element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return {
            left: rect.left,
            right: rect.right,
            client: element.clientWidth,
            scroll: element.scrollWidth,
            overflowX: style.overflowX
          };
        })
        """
    )
    for surface in surfaces:
        assert surface["left"] >= -1, surface
        assert surface["right"] <= page.viewport_size["width"] + 1, surface
        if surface["scroll"] > surface["client"] + 1:
            assert surface["overflowX"] in {"auto", "scroll"}, surface


def _assert_route_inactive_navigation_cancellations(
    events: list[dict[str, object]],
    *,
    pathname: str,
    expected_outputs: tuple[str, ...],
) -> None:
    """Retain and classify Dash 204 responses Chromium reports as aborted."""

    assert events, "Expected the recorded browser-navigation cancellation evidence."
    assert all(event["kind"] == "requestfailed" for event in events), events
    assert all(event["failure"] == "net::ERR_ABORTED" for event in events), events
    actual_outputs = []
    for event in events:
        body = json.loads(str(event["request_body"]))
        url_values = [
            value.get("value")
            for value in (*body.get("inputs", ()), *body.get("state", ()))
            if value.get("id") == "url" and value.get("property") == "pathname"
        ]
        assert url_values == [pathname], events
        actual_outputs.append(body["output"])
    assert Counter(actual_outputs) == Counter(expected_outputs), events


def _callback_statuses(server_log: Path) -> list[dict[str, object]]:
    text = server_log.read_text(encoding="utf-8", errors="replace")
    return [
        json.loads(match.group(1))
        for match in re.finditer(r"COMPARE_CALLBACK_STATUS (\{.*\})", text)
    ]


def _assert_status_evidence(
    server_log: Path,
    events: list[dict[str, object]],
) -> None:
    statuses = _callback_statuses(server_log)
    for event in events:
        body = json.loads(str(event["request_body"]))
        values = (*body.get("inputs", ()), *body.get("state", ()))
        pathname = next(
            value.get("value")
            for value in values
            if value.get("id") == "url" and value.get("property") == "pathname"
        )
        assert {
            "output": body["output"],
            "pathname": pathname,
            "status": 204,
        } in statuses
    assert {
        "output": "comparison-run-selector.options",
        "pathname": COMPARE_PATH,
        "status": 200,
    } in statuses
    assert {
        "output": "..run-comparison-output.children...run-comparison-output.className..",
        "pathname": COMPARE_PATH,
        "status": 200,
    } in statuses


def test_compare_browser_renders_three_persisted_runs_and_survives_refresh(
    compare_server,
    tmp_path: Path,
) -> None:
    base_url, server_log = compare_server
    events: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "settle mounted shell before Compare"}
        pending = _attach_compare_diagnostics(page, events, action)
        try:
            page.goto(base_url, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _assert_no_browser_errors(events)
            _assert_route_inactive_navigation_cancellations(
                events,
                pathname="/",
                    expected_outputs=(
                        "comparison-run-selector.options",
                        QUERY_HYDRATION_OUTPUT,
                        "..run-comparison-output.children...run-comparison-output.className..",
                    "..selected-trade-grid.rowData...trade-explorer-summary.children...selected-trade-grid.selectedRows..",
                ),
            )
            compare_phase_start = len(events)
            action["name"] = "open persisted Compare evidence"
            page.locator("#navigation-link-research-compare-backtests").click()
            _wait_for_callbacks_to_settle(page, pending)
            _assert_route_inactive_navigation_cancellations(
                events[compare_phase_start:],
                pathname=COMPARE_PATH,
                expected_outputs=(
                    "..selected-trade-grid.rowData...trade-explorer-summary.children...selected-trade-grid.selectedRows..",
                ),
            )
            route = page.locator("#route-research-compare-backtests")
            expect(route.locator("h1")).to_have_text("Compare results")
            expect(page.locator("#comparison-read-model")).to_be_visible(timeout=10000)
            expect(page.locator(".compare-run-card")).to_have_count(2)
            expect(route.locator(".operator-context")).to_have_count(2)
            expect(page.locator("#comparison-findings")).to_contain_text(
                "Direct comparison is supported"
            )
            expect(page.locator("#comparison-findings")).to_contain_text(
                "different execution and costs values"
            )
            expect(page.locator("#comparison-equity-chart")).to_be_visible()
            expect(page.locator("#comparison-drawdown-chart")).to_be_visible()

            first_equity = _plotly_data(page, "comparison-equity-chart")
            assert len(first_equity) == 2
            assert all(trace["connectgaps"] is False for trace in first_equity)
            assert all("browser-compare-" in str(trace["name"]) for trace in first_equity)

            action["name"] = "add a third persisted run"
            selected_ids = set(
                page.locator(".compare-run-card").evaluate_all(
                    "cards => cards.map((card) => card.dataset.runId)"
                )
            )
            missing_id = (
                {"browser-compare-a", "browser-compare-b", "browser-compare-c"}
                - selected_ids
            ).pop()
            _select(page, "comparison-run-selector", missing_id)
            page.locator("#compare-selected-runs").click()
            expect(page.locator(".compare-run-card")).to_have_count(3, timeout=10000)
            expect(page.locator(".compare-results-link")).to_have_count(3)
            expect(page.locator(".compare-metric-table")).to_contain_text(
                "Rank 1 persisted parameter result"
            )
            expect(page.locator('[data-difference-group="parameters"]')).to_contain_text(
                "Window"
            )
            expect(page.locator('[data-difference-group="data"]')).to_contain_text(
                "Dataset Identity"
            )
            equity = _plotly_data(page, "comparison-equity-chart")
            drawdown = _plotly_data(page, "comparison-drawdown-chart")
            assert len(equity) == len(drawdown) == 3
            actual_equity = sorted(tuple(trace["y"]) for trace in equity)
            expected_equity = sorted(
                ((100.0, 105.0, 103.0), (100.0, 98.0, 110.0), (100.0, 101.0, 102.0))
            )
            for actual, expected_values in zip(
                actual_equity,
                expected_equity,
                strict=True,
            ):
                assert actual == pytest.approx(expected_values)
            assert all(trace["connectgaps"] is False for trace in (*equity, *drawdown))

            hrefs = page.locator(".compare-results-link").evaluate_all(
                "links => links.map((link) => link.getAttribute('href'))"
            )
            assert all(href.startswith("/research/backtest-results?run_id=") for href in hrefs)

            action["name"] = "refresh Compare with session selection"
            refresh_phase_start = len(events)
            page.reload(wait_until="networkidle")
            expect(route.locator("h1")).to_have_text("Compare results")
            expect(page.locator(".compare-run-card")).to_have_count(3, timeout=10000)
            assert len(_plotly_data(page, "comparison-equity-chart")) == 3
            _assert_page_contained(page)
            _wait_for_callbacks_to_settle(page, pending)
            page.screenshot(path=tmp_path / "compare-desktop.png", full_page=True)
            _assert_no_browser_errors(events)
            _assert_route_inactive_navigation_cancellations(
                events[refresh_phase_start:],
                pathname=COMPARE_PATH,
                expected_outputs=(
                    "..selected-trade-grid.rowData...trade-explorer-summary.children...selected-trade-grid.selectedRows..",
                ),
            )
            _assert_status_evidence(server_log, events)
        except Exception:
            page.screenshot(path=tmp_path / "compare-desktop-failure.png", full_page=True)
            (tmp_path / "compare-desktop-diagnostics.json").write_text(
                json.dumps(events, indent=2),
                encoding="utf-8",
            )
            (tmp_path / "compare-server.log.copy").write_text(
                server_log.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
            raise
        finally:
            browser.close()


def test_compare_mobile_contains_quartets_charts_tables_and_actions(
    compare_server,
    tmp_path: Path,
) -> None:
    base_url, server_log = compare_server
    events: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        action = {"name": "settle mounted mobile shell before Compare"}
        pending = _attach_compare_diagnostics(page, events, action)
        try:
            page.goto(base_url, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _assert_no_browser_errors(events)
            _assert_route_inactive_navigation_cancellations(
                events,
                pathname="/",
                    expected_outputs=(
                        "comparison-run-selector.options",
                        QUERY_HYDRATION_OUTPUT,
                        "..run-comparison-output.children...run-comparison-output.className..",
                    "..selected-trade-grid.rowData...trade-explorer-summary.children...selected-trade-grid.selectedRows..",
                ),
            )
            compare_phase_start = len(events)
            action["name"] = "open Compare on mobile"
            page.locator("#navigation-drawer-toggle").click()
            expect(page.locator("#navigation-drawer-panel")).to_be_visible()
            page.locator("#navigation-link-research-compare-backtests").click()
            _wait_for_callbacks_to_settle(page, pending)
            route = page.locator("#route-research-compare-backtests")
            expect(page.locator("#comparison-read-model")).to_be_visible(timeout=10000)
            expect(page.locator(".compare-run-card")).to_have_count(2)
            expect(route.locator(".operator-context-item")).to_have_count(8)
            expect(page.locator("#comparison-equity-chart")).to_be_visible()
            expect(page.locator("#comparison-drawdown-chart")).to_be_visible()
            expect(page.locator("#compare-selected-runs")).to_be_visible()
            expect(page.locator(".compare-results-link")).to_have_count(2)
            columns = route.locator(".operator-context-grid").first.evaluate(
                "element => getComputedStyle(element).gridTemplateColumns.split(' ').length"
            )
            assert columns == 1
            _assert_page_contained(page)
            _wait_for_callbacks_to_settle(page, pending)
            page.screenshot(path=tmp_path / "compare-mobile.png", full_page=True)
            _assert_no_browser_errors(events)
            _assert_route_inactive_navigation_cancellations(
                events[compare_phase_start:],
                pathname=COMPARE_PATH,
                expected_outputs=(
                    "..selected-trade-grid.rowData...trade-explorer-summary.children...selected-trade-grid.selectedRows..",
                ),
            )
            _assert_status_evidence(server_log, events)
        except Exception:
            page.screenshot(path=tmp_path / "compare-mobile-failure.png", full_page=True)
            (tmp_path / "compare-mobile-diagnostics.json").write_text(
                json.dumps(events, indent=2),
                encoding="utf-8",
            )
            (tmp_path / "compare-mobile-server.log.copy").write_text(
                server_log.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
            raise
        finally:
            browser.close()
