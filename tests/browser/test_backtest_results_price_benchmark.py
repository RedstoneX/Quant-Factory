"""Browser coverage for persisted SPYM price and benchmark charts."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from tests.browser.test_backtest_results_spym_stability import (
    BACKTEST_PATH,
    SPYM_OPTION_TEXT,
    dashboard_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _attach_diagnostics,
    _select,
    _wait_for_callbacks_to_settle,
)


def _plotly_traces(page, selector: str):
    page.locator(selector).wait_for(timeout=10000)
    return page.locator(selector).evaluate(
        """
        element => element.data.map(trace => ({
            name: trace.name,
            type: trace.type,
            points: trace.x.length
        }))
        """
    )


def test_spym_price_markers_and_benchmark_render_from_persisted_evidence(
    dashboard_server,
) -> None:
    base_url, _, _ = dashboard_server
    events: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            pending = _attach_diagnostics(
                page,
                events,
                {"name": "price benchmark"},
            )
            page.goto(f"{base_url}{BACKTEST_PATH}", wait_until="networkidle")
            _select(page, "selected-run-selector", SPYM_OPTION_TEXT)
            _wait_for_callbacks_to_settle(page, pending)

            expect(
                page.get_by_text(
                    "Portfolio value and buy-and-hold comparison",
                    exact=True,
                )
            ).to_be_visible()
            expect(
                page.get_by_text(
                    "Underlying price, entries, and exits",
                    exact=True,
                )
            ).to_be_visible()
            expect(
                page.locator(".run-benchmark-panel")
                .get_by_text("SPYM same-instrument buy-and-hold", exact=True)
                .last
            ).to_be_visible()
            expect(page.get_by_text("$10,000.00", exact=True)).to_be_visible()
            expect(page.get_by_text("0.000%", exact=True).first).to_be_visible()
            expect(
                page.get_by_text(
                    "Full observed SPYM 1m series: 53,528 bars. "
                    "No synthetic bars and no chart resampling are applied.",
                    exact=True,
                )
            ).to_be_visible()

            price_traces = _plotly_traces(page, "#price-marker-chart .js-plotly-plot")
            assert price_traces == [
                {"name": "SPYM close", "type": "scattergl", "points": 53528},
                {"name": "Long entry markers", "type": "scatter", "points": 366},
                {"name": "Long exit markers", "type": "scatter", "points": 366},
            ]
            benchmark_traces = _plotly_traces(
                page,
                "#portfolio-benchmark-chart .js-plotly-plot",
            )
            assert benchmark_traces == [
                {
                    "name": "Portfolio value vs same-instrument buy-and-hold",
                    "type": "scatter",
                    "points": 53528,
                },
                {
                    "name": "SPYM same-instrument buy-and-hold",
                    "type": "scattergl",
                    "points": 53528,
                },
            ]
            assert [
                event for event in events if event["kind"] in {"pageerror", "console"}
            ] == []
        finally:
            browser.close()
