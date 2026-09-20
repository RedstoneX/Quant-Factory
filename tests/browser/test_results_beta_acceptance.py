"""Focused real-browser proof for the selected-run Results beta."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect, sync_playwright

from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.models import normalized_configuration_document
from tests.browser.dashboard_diagnostics import (
    assert_browser_diagnostics_clean,
    attach_browser_diagnostics,
)
from tests.browser.test_backtest_results_spym_stability import (
    BACKTEST_PATH,
    REPOSITORY_ROOT,
    _free_port,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import _wait_for_callbacks_to_settle


RUN_ID = "portable-r07-screening-run"
ENTRY_TIME = "2026-01-02T14:40:00+00:00"
EXIT_TIME = "2026-01-02T15:35:00+00:00"


def _persist_json_artifact(
    service: PersistenceService,
    artifact_root: Path,
    *,
    artifact_type: ArtifactType,
    logical_name: str,
    payload: dict[str, object],
) -> None:
    location = f"artifacts/{RUN_ID}/{logical_name}.json"
    content = canonical_json(payload).encode("utf-8")
    target = artifact_root / location
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    service.register_artifact(
        run_id=RUN_ID,
        artifact_type=artifact_type,
        logical_name=logical_name,
        media_type="application/json",
        format="json",
        location=location,
        content=content,
    )


def _seed_results_beta_run(database: Path, artifact_root: Path) -> None:
    service = PersistenceService(database)
    try:
        strategy = service.register_strategy(
            strategy_id="mes_opening_range_breakout_long",
            strategy_version="1.0.0",
            display_name="MES Opening Range Breakout Long",
            description="Synthetic R07-shaped selected-run browser fixture",
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="portable_r07_screening",
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                market_data={
                    "provider": "fixture",
                    "symbol": "MES",
                    "interval": "5m",
                },
                parameters={"range_minutes": [5, 15, 30, 45, 60]},
                execution={
                    "kind": "theoretical_backtest",
                    "fill_model": "next_open",
                    "order_size": 1.0,
                    "price_multiplier": 5.0,
                    "fixed_fee_per_contract_per_side": 0.62,
                    "slippage_ticks": 1.0,
                },
                ranking={"columns": ("total_return",), "ascending": (False,)},
                screening={"kind": "bounded_r07"},
            )
        )
        service.create_run(
            configuration_id=configuration.configuration_id,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            stage=RunStage.SCREENING,
            run_id=RUN_ID,
            status=RunStatus.SUCCEEDED,
        )
        with transaction(service.connection):
            service.results.set_data_provenance(
                DataProvenanceRecord(
                    run_id=RUN_ID,
                    provider="fixture",
                    provider_implementation="portable-results-beta-browser",
                    symbol="MES",
                    interval="5m",
                    timezone="UTC",
                    requested_coverage="2019-05-05T22:00:00+00:00/2026-02-13T21:55:00+00:00",
                    actual_coverage="2019-05-05T22:00:00+00:00/2026-02-13T21:55:00+00:00",
                    adjusted=False,
                    row_count=120,
                    cache_action="fixture",
                    validation_summary_json=canonical_json({"status": "valid"}),
                    manifest_reference="portable-results-beta-fixture",
                    checksum="portable-results-beta-checksum",
                )
            )
            service.results.set_execution_assumptions(
                ExecutionAssumptionsRecord(
                    run_id=RUN_ID,
                    assumptions_json=canonical_json(
                        {
                            "kind": "theoretical_backtest",
                            "fill_model": "next_open",
                            "order_size": 1.0,
                            "price_multiplier": 5.0,
                            "fixed_fee_per_contract_per_side": 0.62,
                            "slippage_ticks": 1.0,
                        }
                    ),
                )
            )
            for rank in range(1, 16):
                service.results.add_parameter_result(
                    run_id=RUN_ID,
                    row_id=f"portable-r07-row-{rank}",
                    normalized_parameters={
                        "range_minutes": (5, 15, 30, 45, 60)[(rank - 1) // 3],
                        "breakout_offset_ticks": (rank - 1) % 3,
                    },
                    metrics={
                        "total_return": 0.0542477 if rank == 1 else 0.04 - rank / 1000,
                        "annualized_return": 0.0117 if rank == 1 else 0.01 - rank / 5000,
                        "sharpe_ratio": 0.5 - rank / 100,
                        "max_drawdown": -0.015 - rank / 1000,
                        "number_of_trades": 100 + rank,
                        "win_rate": 0.5,
                    },
                    ranking_position=rank,
                    screening_status="screened_out",
                    rejection_reasons=f"R07 threshold rejection {rank}",
                )

        start = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
        prices: list[dict[str, object]] = []
        equity: list[dict[str, object]] = []
        for index in range(120):
            timestamp = (start + timedelta(minutes=index * 5)).isoformat()
            open_price = 6000.0 + (index * 0.25)
            close = open_price + (0.12 if index % 2 == 0 else -0.05)
            prices.append(
                {
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": max(open_price, close) + 0.15,
                    "low": min(open_price, close) - 0.15,
                    "close": close,
                }
            )
            equity.append({"timestamp": timestamp, "value": 10_000.0 + index * 4})

        _persist_json_artifact(
            service,
            artifact_root,
            artifact_type=ArtifactType.EQUITY_CURVE,
            logical_name="equity_curve",
            payload={
                "equity_curve": equity,
                "price_series": prices,
                "benchmark_omission": "No truthful futures benchmark is declared.",
            },
        )
        _persist_json_artifact(
            service,
            artifact_root,
            artifact_type=ArtifactType.TRADES_OR_ORDERS,
            logical_name="trades_and_orders",
            payload={
                "instrument": "MES",
                "price_unit": "index_points",
                "pnl_unit": "USD",
                "price_multiplier": 5.0,
                "trades": [
                    {
                        "Status": "Closed",
                        "Direction": "Long",
                        "Entry Index": ENTRY_TIME,
                        "Exit Index": EXIT_TIME,
                        "Avg Entry Price": 6000.50,
                        "Avg Exit Price": 6003.25,
                        "Size": 1.0,
                        "Entry Fees": 0.62,
                        "Exit Fees": 0.62,
                        "PnL": 12.51,
                        "Return": 0.0206,
                    },
                    {
                        "Status": "Closed",
                        "Direction": "Short",
                        "Entry Index": "2026-01-02T15:45:00+00:00",
                        "Exit Index": "2026-01-02T16:05:00+00:00",
                        "Avg Entry Price": 6004.0,
                        "Avg Exit Price": 6003.5,
                        "Size": 1.0,
                        "PnL": 0.3,
                        "Return": 0.0029,
                    },
                ],
                "orders": [],
            },
        )
        _persist_json_artifact(
            service,
            artifact_root,
            artifact_type=ArtifactType.METRICS,
            logical_name="metrics",
            payload={
                "parameter_row_id": "portable-r07-row-1",
                "ranking_position": 1,
                "metrics": {
                    "total_return": 0.0542477,
                    "annualized_return": 0.0117,
                    "sharpe_ratio": 0.49,
                    "max_drawdown": -0.016,
                    "number_of_trades": 101,
                    "win_rate": 0.5,
                },
            },
        )
        _persist_json_artifact(
            service,
            artifact_root,
            artifact_type=ArtifactType.RUN_SUMMARY,
            logical_name="run_summary",
            payload={
                "stage": "screening",
                "evidence_classification": (
                    "development/reference evidence only; not independent, OOS, protected, or edge proof"
                ),
                "promotion_eligible": False,
                "broker_orders": "disabled",
            },
        )
        _persist_json_artifact(
            service,
            artifact_root,
            artifact_type=ArtifactType.VALIDATION_EVIDENCE,
            logical_name="validation_evidence",
            payload={
                "stage": "screening",
                "evidence_label": "synthetic R07-shaped development/reference fixture",
                "evidence_classification": (
                    "development/reference evidence only; not independent, OOS, protected, or edge proof"
                ),
                "protected_data_used": False,
                "promotion_eligible": False,
                "promotion_blockers": ["All bounded variants screened out."],
                "screening": {
                    "evaluated_combinations": 15,
                    "passed": 0,
                    "screened_out": 15,
                },
            },
        )
        service.persist_run_manifest(service.build_run_manifest(RUN_ID))
    finally:
        service.close()


@pytest.fixture()
def results_beta_server(tmp_path: Path):
    database = tmp_path / "state" / "results-beta.sqlite3"
    artifact_root = tmp_path / "artifact-root"
    _seed_results_beta_run(database, artifact_root)
    port = _free_port()
    server_log = tmp_path / "results-beta-server.log"
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService
from tests.browser.dashboard_diagnostics import install_callback_status_recorder

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
install_callback_status_recorder(app.server)
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
                str(artifact_root),
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
        _wait_for_server(base_url + BACKTEST_PATH)
        yield base_url, server_log
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _graph_state(page: Page) -> dict[str, object]:
    return page.locator("#price-marker-chart .js-plotly-plot").evaluate(
        """
        graph => ({
          bars: graph.data.filter(trace => trace.type === "candlestick" && trace.visible !== false)
            .map(trace => trace.name),
          range: graph._fullLayout.xaxis.range.map(String),
          barsActive: graph.layout.updatemenus[0].active,
          viewActive: graph.layout.updatemenus[1].active,
          selectedMarkers: graph.data.filter(trace => trace.type === "scatter")
            .flatMap(trace => (trace.customdata || []).map((item, index) => ({
              trade: Number(item[0]),
              event: String(trace.name).toLowerCase().includes("entry") ? "entry" : "exit",
              size: Array.isArray(trace.marker.size) ? Number(trace.marker.size[index]) : Number(trace.marker.size),
              color: Array.isArray(trace.marker.color) ? trace.marker.color[index] : trace.marker.color,
              exact: item[1]
            }))).filter(marker => marker.size === 17)
        })
        """
    )


def _dimensions(page: Page) -> dict[str, object]:
    return page.locator(".results-beta-workspace").evaluate(
        """
        workspace => {
          const chart = workspace.querySelector(".results-chart-region");
          const report = workspace.querySelector(".results-report-region");
          return {
            chart: Math.round(chart.getBoundingClientRect().height),
            report: Math.round(report.getBoundingClientRect().height),
            chartVariable: workspace.style.getPropertyValue("--qf-results-chart-height"),
            reportVariable: workspace.style.getPropertyValue("--qf-results-report-min-height")
          };
        }
        """
    )


def _assert_no_horizontal_overflow(page: Page) -> None:
    widths = page.evaluate(
        """
        () => ({
          documentClient: document.documentElement.clientWidth,
          documentScroll: document.documentElement.scrollWidth,
          bodyClient: document.body.clientWidth,
          bodyScroll: document.body.scrollWidth
        })
        """
    )
    assert widths["documentScroll"] <= widths["documentClient"] + 1, widths
    assert widths["bodyScroll"] <= widths["bodyClient"] + 1, widths


def _assert_report_normal_flow(page: Page, *, expect_grid: bool) -> None:
    flow = page.locator(".results-report-region").evaluate(
        """
        report => {
          const viewport = report.querySelector(".ag-body-viewport");
          return {
            overflowY: getComputedStyle(report).overflowY,
            clientHeight: report.clientHeight,
            scrollHeight: report.scrollHeight,
            gridOverflowY: viewport ? getComputedStyle(viewport).overflowY : null
          };
        }
        """
    )
    assert flow["overflowY"] not in {"auto", "scroll"}
    assert flow["scrollHeight"] <= flow["clientHeight"] + 1
    if expect_grid:
        assert flow["gridOverflowY"] not in {"auto", "scroll"}


def test_selected_run_results_beta_browser_contract(results_beta_server) -> None:
    base_url, server_log = results_beta_server
    url = f"{base_url}{BACKTEST_PATH}?{urlencode({'run_id': RUN_ID})}"
    events: list[dict[str, object]] = []
    external_requests: list[str] = []
    action = {"name": "open selected-run Results beta"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        pending = attach_browser_diagnostics(page, events, action)
        page.on(
            "request",
            lambda request: external_requests.append(request.url)
            if not request.url.startswith(base_url)
            and not request.url.startswith(("data:", "blob:"))
            else None,
        )
        try:
            page.goto(base_url + BACKTEST_PATH, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            page.locator(".results-change-run-history summary").click()
            target_cell = page.locator("#run-history-grid").get_by_text("MES").first
            expect(target_cell).to_be_visible()
            target_cell.click()
            _wait_for_callbacks_to_settle(page, pending)
            exact_link = page.get_by_role("link", name="Open exact saved-run link")
            expect(exact_link).to_have_attribute(
                "href", f"{BACKTEST_PATH}?{urlencode({'run_id': RUN_ID})}"
            )
            page.goto(base_url + exact_link.get_attribute("href"), wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page).to_have_url(url)
            expect(page.locator("#selected-run-detail")).to_contain_text(RUN_ID)
            expect(page.locator("#price-marker-chart")).to_be_visible()
            expect(page.locator(".results-chart-region")).to_be_visible()
            _assert_no_horizontal_overflow(page)

            chart = page.locator("#price-marker-chart .js-plotly-plot")
            initial = _graph_state(page)
            assert initial["bars"] == ["Observed MES (5m)"]
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "1m: Bars interval 1m is finer than the persisted 5m source"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "MES price (index points)"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "Recorded MES assumptions"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "engine outputs under these persisted backtest costs"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "Annualized return (recorded engine output)"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text("1.17%")
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "Calendar CAGR (derived from recorded coverage)"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text("0.78%")
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "basis were not persisted"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "not the engine annualization or a new screening metric"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "Development/reference only"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "Promotion is blocked"
            )

            page.locator("#price-marker-chart .updatemenu-button", has_text="1D").last.click()
            page.wait_for_timeout(150)
            view_state = _graph_state(page)
            assert view_state["bars"] == initial["bars"]
            assert view_state["viewActive"] != initial["viewActive"]
            page.locator("#price-marker-chart .updatemenu-button", has_text="15m").first.click()
            page.wait_for_timeout(150)
            bars_state = _graph_state(page)
            assert bars_state["bars"] == ["Observed MES (15m)"]
            assert bars_state["viewActive"] == view_state["viewActive"]

            before_pan = bars_state["range"]
            box = chart.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.55)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * 0.35, box["y"] + box["height"] * 0.55, steps=8)
            page.mouse.up()
            page.wait_for_timeout(200)
            after_pan = _graph_state(page)["range"]
            assert after_pan != before_pan
            page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.55)
            page.mouse.wheel(0, -500)
            page.wait_for_timeout(200)
            after_wheel = _graph_state(page)["range"]
            assert after_wheel != after_pan

            _assert_report_normal_flow(page, expect_grid=False)
            page.locator("#results-report-tabs .tab", has_text="Trades").click()
            _wait_for_callbacks_to_settle(page, pending)
            row = page.locator("#selected-trade-grid .ag-center-cols-container .ag-row").first
            expect(row).to_be_visible()
            row.click()
            _wait_for_callbacks_to_settle(page, pending)
            row.focus()
            expect(row).to_have_attribute("aria-selected", "true")
            assert page.evaluate("document.activeElement?.getAttribute('row-index')") == "0"
            status = page.locator("#results-chart-focus-status")
            expect(status).to_contain_text("Trade 1 identified on chart")
            expect(status).to_contain_text(ENTRY_TIME)
            expect(status).to_contain_text(EXIT_TIME)
            selected = _graph_state(page)["selectedMarkers"]
            assert {(marker["trade"], marker["event"], marker["exact"]) for marker in selected} == {
                (1, "entry", ENTRY_TIME),
                (1, "exit", EXIT_TIME),
            }

            _assert_report_normal_flow(page, expect_grid=True)
            expect(page.locator("#selected-trade-detail")).to_contain_text("index points")
            expect(page.locator("#selected-trade-detail")).to_contain_text("$1.24")

            page.locator("#results-report-tabs .tab", has_text="Metrics").click()
            page.locator(".run-validation-details summary").click()
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "R07 threshold rejection 1"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "R07 threshold rejection 15"
            )
            page.locator("#results-report-tabs .tab", has_text="Trades").click()

            initial_dimensions = _dimensions(page)
            handles = page.locator("[data-results-resizer]")
            expect(handles).to_have_count(3)
            handles.nth(0).focus()
            page.keyboard.press("ArrowUp")
            top_dimensions = _dimensions(page)
            assert top_dimensions["chart"] > initial_dimensions["chart"]
            handles.nth(1).focus()
            page.keyboard.press("ArrowDown")
            shared_dimensions = _dimensions(page)
            assert shared_dimensions["chart"] > top_dimensions["chart"]
            assert shared_dimensions["report"] < top_dimensions["report"]
            handles.nth(2).focus()
            page.keyboard.press("ArrowDown")
            bottom_dimensions = _dimensions(page)
            assert bottom_dimensions["report"] > shared_dimensions["report"]

            state_before_reset = _graph_state(page)
            selected_before_reset = page.evaluate(
                """
                async () => (await window.dash_ag_grid.getApiAsync("selected-trade-grid"))
                  .getSelectedRows().map(row => row.__trade_index)
                """
            )
            page.locator("#results-reset-layout").click()
            reset_dimensions = _dimensions(page)
            assert reset_dimensions["chartVariable"] == ""
            assert reset_dimensions["reportVariable"] == ""
            assert reset_dimensions["chart"] == initial_dimensions["chart"]
            assert reset_dimensions["report"] == initial_dimensions["report"]
            assert _graph_state(page)["bars"] == state_before_reset["bars"]
            assert _graph_state(page)["viewActive"] == state_before_reset["viewActive"]
            expect(page.locator("#results-report-tabs .tab--selected")).to_have_text("Trades")
            assert page.evaluate(
                """
                async () => (await window.dash_ag_grid.getApiAsync("selected-trade-grid"))
                  .getSelectedRows().map(row => row.__trade_index)
                """
            ) == selected_before_reset
            expect(page).to_have_url(url)

            action["name"] = "refresh and traverse Results history"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page).to_have_url(url)
            expect(page.locator("#selected-run-detail")).to_contain_text(RUN_ID)
            page.goto(base_url + "/research/compare-backtests", wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            page.go_back(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page).to_have_url(url)
            expect(page.locator("#selected-run-detail")).to_contain_text(RUN_ID)
            page.go_forward(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            page.go_back(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page.locator("#selected-run-detail")).to_contain_text(RUN_ID)

            for viewport in ({"width": 1024, "height": 768}, {"width": 390, "height": 844}):
                page.set_viewport_size(viewport)
                page.wait_for_timeout(200)
                _assert_no_horizontal_overflow(page)
                if viewport["width"] == 390:
                    for index in range(3):
                        expect(handles.nth(index)).to_be_hidden()

            assert not pending
            assert external_requests == []
            assert_browser_diagnostics_clean(page, events, (server_log,))
        finally:
            browser.close()
