"""Browser acceptance for the full-history Find & Compare page."""

from __future__ import annotations

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
from tests.test_compare_adapter import _comparison_stack, _persist_run


COMPARE_PATH = "/research/compare-backtests"


@pytest.fixture()
def find_compare_server(tmp_path: Path):
    database, artifact_root = _comparison_stack(tmp_path)
    fixtures = (
        ("browser-compare-a", (100.0, 105.0, 103.0), 10, 0.001),
        ("browser-compare-b", (100.0, 98.0, 110.0), 20, 0.002),
        ("browser-compare-c", (100.0, 101.0, 102.0), 30, 0.003),
        ("browser-compare-d", (100.0, 99.0, 104.0), 40, 0.004),
        ("browser-compare-e", (100.0, 102.0, 106.0), 50, 0.005),
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
                "max_drawdown": -0.01 * (index + 1),
                "win_rate": 0.50 + index / 100.0,
                "sharpe_ratio": 1.0 + index / 10.0,
                "number_of_trades": 4 + index,
            },
        )

    port = _free_port()
    server_log = tmp_path / "find-compare-server.log"
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService

class ThousandRowRunService(FixtureRunService):
    def all_history(self, *, artifact_root=None):
        rows = list(super().all_history(artifact_root=artifact_root))
        for index in range(len(rows), 1000):
            rows.append({
                'run_id': f'synthetic-saved-test-{index:04d}',
                'created_at': f'2026-09-{20 - (index % 20):02d}T14:00:00Z',
                'instrument': 'MES' if index % 2 else 'SPY',
                'interval': '5m' if index % 2 else '1d',
                'strategy': (
                    'Unique search target'
                    if index == 5
                    else 'Synthetic responsiveness fixture'
                ),
                'stage': 'Screening',
                'status': 'Succeeded',
                'review': 'Not reviewed',
                'evidence': 'Screened Out',
                'metric_basis': 'Top-ranked variation · Rank 1 · Screening Screened Out',
                'total_return': (index % 17 - 8) / 100,
                'max_drawdown': -(index % 9 + 1) / 100,
                'win_rate': 0.42 + (index % 15) / 100,
                'sharpe_ratio': (index % 23 - 8) / 10,
                'number_of_trades': 120 + index,
            })
        return tuple(rows)

database = Path(sys.argv[1])
artifact_root = Path(sys.argv[2])
port = int(sys.argv[3])
app = create_app(
    review_database=database,
    run_service=ThousandRowRunService(database=database),
    run_detail_adapter=RunDetailDashboardAdapter(
        database=database,
        artifact_root=artifact_root,
    ),
)
app.run(host='127.0.0.1', port=port, debug=False)
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


def _select_row(page, index: int) -> None:
    page.locator("#find-compare-grid .ag-row").nth(index).locator(
        ".ag-selection-checkbox"
    ).click()


def _assert_no_horizontal_scroll(page) -> None:
    dimensions = page.locator("#find-compare-grid .ag-center-cols-viewport").evaluate(
        "element => ({client: element.clientWidth, scroll: element.scrollWidth})"
    )
    assert dimensions["scroll"] <= dimensions["client"] + 1, dimensions


def test_find_compare_thousand_rows_links_hydration_and_reset(
    find_compare_server,
    tmp_path: Path,
) -> None:
    base_url, server_log = find_compare_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        try:
            page.goto(base_url + COMPARE_PATH, wait_until="networkidle")
            route = page.locator("#route-research-compare-backtests")
            expect(route.locator("h1")).to_have_text("Find & Compare")
            expect(page.locator("#find-compare-grid-count")).to_contain_text(
                "1,000 matched · 0 selected"
            )
            expect(page.get_by_text("1 to 25 of 1,000", exact=True)).to_be_visible()
            _assert_no_horizontal_scroll(page)

            _select_row(page, 0)
            expect(page.locator("#find-compare-grid-count")).to_contain_text(
                "1 selected"
            )
            expect(page.locator("#find-compare-results-link")).to_be_visible()
            expect(page.locator("#find-compare-exact-link")).to_be_hidden()

            _select_row(page, 1)
            compare_link = page.locator("#find-compare-exact-link")
            expect(compare_link).to_be_visible()
            href = compare_link.get_attribute("href")
            assert href is not None and href.count("run_id=") == 2

            page.goto(base_url + href, wait_until="networkidle")
            expect(page.locator("#comparison-read-model")).to_be_visible()
            expect(page.locator("#find-compare-grid .ag-row-selected")).to_have_count(2)

            _select_row(page, 2)
            expect(page.locator("#find-compare-grid-count")).to_contain_text(
                "3 selected"
            )
            href = compare_link.get_attribute("href")
            assert href is not None and href.count("run_id=") == 3
            _select_row(page, 3)
            expect(page.locator("#find-compare-grid-count")).to_contain_text(
                "4 selected"
            )
            href = compare_link.get_attribute("href")
            assert href is not None and href.count("run_id=") == 4
            _select_row(page, 4)
            expect(page.locator("#find-compare-grid-count")).to_contain_text(
                "5 selected"
            )
            expect(compare_link).to_be_hidden()
            expect(page.locator("#find-compare-selection-message")).to_contain_text(
                "reduce the selection"
            )

            search = page.locator("#find-compare-search")
            search.fill("Unique search target")
            search.press("Enter")
            expect(page.locator("#find-compare-grid-count")).to_contain_text(
                "1 matched"
            )
            page.locator("#find-compare-reset-view").click()
            expect(search).to_have_value("")
            expect(page.locator("#find-compare-grid-count")).to_contain_text(
                "1,000 matched"
            )
            _assert_no_horizontal_scroll(page)
            page.screenshot(
                path=tmp_path / "find-compare-1000-desktop.png",
                full_page=True,
            )
        except Exception:
            page.screenshot(
                path=tmp_path / "find-compare-1000-failure.png",
                full_page=True,
            )
            raise AssertionError(server_log.read_text(encoding="utf-8"))
        finally:
            browser.close()
