"""Real-browser mounted-route and durable operator workflow regressions."""

import json
from pathlib import Path
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from dashboard.routing import NAVIGATION_LINKS, ROUTE_REGISTRY, navigation_link_id
from orchestration import FixtureRunService
from persistence import (
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
from tests.browser.test_backtest_results_spym_stability import (
    BACKTEST_PATH,
    SPYM_OPTION_TEXT,
    _visible_routes,
    _launcher,
    dashboard_server,
)


def _select(page, selector, label, index=0):
    page.locator(f"#{selector}").click()
    page.get_by_placeholder("Search", exact=True).fill(label)
    page.locator(".dash-options-list-option-text", has_text=label).nth(index).click()


def _assert_route(page, base_url, path, container):
    expect(page).to_have_url(base_url + path)
    expect(page.locator(f"#{container}")).to_be_visible()
    assert _visible_routes(page) == [container]
    active = page.locator(".navigation-link-active")
    if path in dict(NAVIGATION_LINKS):
        expect(active).to_have_count(1)
        expect(active).to_have_attribute("id", navigation_link_id(path))
    else:
        expect(active).to_have_count(0)


def _attach_diagnostics(page, events, action):
    pending_requests = set()

    def record(kind, **details):
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
            ),
        )
        if "/_dash-update-component" in request.url
        else None,
    )
    return pending_requests


def _assert_no_browser_errors(events):
    errors = [event for event in events if event["kind"] in {"pageerror", "console"}]
    assert errors == []


def _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log):
    page.screenshot(path=tmp_path / "dashboard-lifecycle-failure.png", full_page=True)
    (tmp_path / "dashboard-lifecycle-diagnostics.json").write_text(
        json.dumps(
            {
                "events": events,
                "server_log": server_log.read_text(encoding="utf-8", errors="replace"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _wait_for_callbacks_to_settle(page, pending_requests):
    deadline = time.monotonic() + 60
    quiet_since = None
    while time.monotonic() < deadline:
        loading = page.locator('[data-dash-is-loading="true"]').count() > 0
        if not pending_requests and not loading:
            quiet_since = quiet_since or time.monotonic()
            if time.monotonic() - quiet_since >= 0.25:
                return
        else:
            quiet_since = None
        page.wait_for_timeout(50)
    loading_ids = page.locator('[data-dash-is-loading="true"]').evaluate_all(
        "elements => elements.map(element => element.id || element.className)"
    )
    raise AssertionError(f"Dash callbacks did not settle before navigation: pending={len(pending_requests)}, loading={loading_ids}")


def _create_history_run(
    service: PersistenceService,
    *,
    run_id: str,
    symbol: str,
    total_return: float,
) -> None:
    strategy = service.register_strategy(
        strategy_id="history_browser_strategy",
        strategy_version="1.0.0",
        display_name="History Browser Strategy",
        description="Browser history-grid selection fixture",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    configuration = service.upsert_configuration(
        normalized_configuration_document(
            experiment_id=f"history_browser_{symbol.lower()}",
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            market_data={"provider": "fixture", "symbol": symbol, "interval": "1d"},
            parameters={"window": 14, "symbol": symbol},
            execution={"kind": "fixture"},
            ranking={"columns": ("total_return",), "ascending": (False,)},
            screening={"kind": "none"},
        )
    )
    service.create_run(
        configuration_id=configuration.configuration_id,
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.strategy_version,
        stage=RunStage.FIXTURE,
        run_id=run_id,
        status=RunStatus.SUCCEEDED,
    )
    with transaction(service.connection):
        service.results.set_data_provenance(
            DataProvenanceRecord(
                run_id=run_id,
                provider="fixture",
                provider_implementation="browser-history-test",
                symbol=symbol,
                interval="1d",
                timezone="America/New_York",
                requested_coverage="2024-01-01/2024-01-31",
                actual_coverage="2024-01-01/2024-01-31",
                adjusted=True,
                row_count=21,
                cache_action="fixture",
                validation_summary_json=canonical_json({"status": "valid"}),
                manifest_reference=f"manifest-{run_id}",
                checksum=f"checksum-{run_id}",
            )
        )
        service.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=run_id,
                assumptions_json=canonical_json({"kind": "fixture"}),
            )
        )
        service.results.add_parameter_result(
            run_id=run_id,
            row_id=f"{run_id}-rank-1",
            normalized_parameters={"window": 14},
            metrics={
                "total_return": total_return,
                "annualized_return": total_return / 2,
                "sharpe_ratio": 1.25,
                "number_of_trades": 7,
            },
            ranking_position=1,
            screening_status="passed",
        )


def _seed_history_browser_runs(database: Path) -> str:
    target_run_id = "history_browser_old_run"
    service = PersistenceService(database)
    try:
        _create_history_run(
            service,
            run_id=target_run_id,
            symbol="OLDROW",
            total_return=0.42,
        )
        for index in range(21):
            _create_history_run(
                service,
                run_id=f"history_browser_recent_{index:02d}",
                symbol="SPY",
                total_return=0.01 + index / 100,
            )
    finally:
        service.close()
    return target_run_id


def test_every_route_deep_link_refresh_and_navigation(dashboard_server, tmp_path):
    base_url, server_log, _ = dashboard_server
    events = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        try:
            for path, container in (*ROUTE_REGISTRY, ("/unknown-route", "route-not-found")):
                page = context.new_page()
                action = {"name": f"open {path}"}
                pending_requests = _attach_diagnostics(page, events, action)
                page.goto(base_url + path, wait_until="networkidle")
                _assert_route(page, base_url, path, container)
                _wait_for_callbacks_to_settle(page, pending_requests)
                _assert_no_browser_errors(events)
                action["name"] = f"refresh {path}"
                page.reload(wait_until="networkidle")
                _assert_route(page, base_url, path, container)
                _wait_for_callbacks_to_settle(page, pending_requests)
                _assert_no_browser_errors(events)
                page.screenshot(path=tmp_path / f"{container}.png", full_page=True)
                page.close()

            page = context.new_page()
            action = {"name": "open home for sidebar navigation"}
            pending_requests = _attach_diagnostics(page, events, action)
            page.goto(base_url, wait_until="networkidle")
            for path, _ in NAVIGATION_LINKS:
                action["name"] = f"sidebar navigation to {path}"
                page.locator(f"#{navigation_link_id(path)}").click()
                _assert_route(page, base_url, path, dict(ROUTE_REGISTRY)[path])
                _wait_for_callbacks_to_settle(page, pending_requests)
            page.go_back(wait_until="networkidle")
            _assert_route(page, base_url, "/system/providers", "route-system-providers")
            page.go_forward(wait_until="networkidle")
            _assert_route(page, base_url, "/settings", "route-settings")
            page.locator(".sidebar-brand").click()
            _assert_route(page, base_url, "/", "route-home")
            _wait_for_callbacks_to_settle(page, pending_requests)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            context.close()
            browser.close()


def test_run_history_grid_opens_older_run_and_survives_refresh(
    dashboard_server,
    tmp_path,
):
    base_url, server_log, _ = dashboard_server
    database = server_log.parent / "state" / "browser-fixture.sqlite3"
    target_run_id = _seed_history_browser_runs(database)
    events = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "open Backtest Results history grid"}
        pending_requests = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + BACKTEST_PATH, wait_until="networkidle")
            expect(page.locator("#run-history-grid")).to_be_visible(timeout=10000)
            page.evaluate(
                """
                async () => {
                  const api = await window.dash_ag_grid.getApiAsync("run-history-grid");
                  api.applyColumnState({
                    state: [{colId: "total_return", sort: "desc"}],
                    defaultState: {sort: null}
                  });
                  api.setFilterModel({
                    instrument: {filterType: "text", type: "contains", filter: "OLDROW"}
                  });
                  api.onFilterChanged();
                }
                """
            )
            expect(page.locator("#run-history-grid").get_by_text("OLDROW")).to_be_visible()
            page.locator("#run-history-grid").get_by_text("OLDROW").click()
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page.locator("#selected-run-detail")).to_contain_text(target_run_id)
            expect(page.locator("#selected-run-detail")).to_contain_text(
                "History Browser Strategy"
            )
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page.locator("#selected-run-detail")).to_contain_text(
                target_run_id,
                timeout=10000,
            )
            page.screenshot(path=tmp_path / "run-history-grid-old-run.png", full_page=True)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


def test_durable_review_and_reproduction_in_browser(dashboard_server, tmp_path):
    base_url, server_log, _ = dashboard_server
    events = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "open strategy review"}
        pending_requests = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/strategy-review", wait_until="networkidle")
            _select(page, "review-run-selector", SPYM_OPTION_TEXT)
            expect(page.locator("#save-review")).to_be_enabled(timeout=10000)
            _select(page, "review-status", "Watchlist")
            note = "Infrastructure browser acceptance: preserve this review across refresh."
            page.locator("#review-note").fill(note)
            page.locator("#save-review").click()
            expect(page.locator("#review-message")).to_contain_text(note)
            _wait_for_callbacks_to_settle(page, pending_requests)
            page.reload(wait_until="networkidle")
            _select(page, "review-run-selector", SPYM_OPTION_TEXT)
            expect(page.locator("#review-note")).to_have_value(note)
            expect(page.locator("#review-status")).to_contain_text("Watchlist")
            page.screenshot(path=tmp_path / "durable-review.png", full_page=True)

            action["name"] = "open Backtest Results"
            page.locator(f"#{navigation_link_id('/research/backtest-results')}").click()
            _select(page, "selected-run-selector", SPYM_OPTION_TEXT)
            expect(page.locator("#reproduce-selected-run")).to_be_enabled()
            action["name"] = "open selected-backtest actions"
            page.get_by_text("Comparison and selected-backtest actions", exact=True).click()
            expect(page.locator("#reproduce-selected-run")).to_be_visible()
            action["name"] = "reproduce selected SPYM run"
            page.locator("#reproduce-selected-run").click()
            expect(page.locator("#reproduction-message")).to_contain_text("Reproduced", timeout=60000)
            action["name"] = "open Compare Backtests"
            page.locator(f"#{navigation_link_id('/research/compare-backtests')}").click()
            action["name"] = "compare reproduced runs"
            page.locator("#compare-selected-runs").click()
            expect(page.locator("#run-comparison-output")).to_contain_text("Backtest comparison")
            page.screenshot(path=tmp_path / "comparison.png", full_page=True)
            _wait_for_callbacks_to_settle(page, pending_requests)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


def test_launch_spym_and_diagnose_controlled_failure(dashboard_server, tmp_path):
    base_url, server_log, initial_run_id = dashboard_server
    database = server_log.parent / "state" / "browser-fixture.sqlite3"
    service = FixtureRunService(database=database, fixture_launcher=_launcher)
    initial = service.get_run(initial_run_id)
    failure = service.launch_fixture(
        configuration_id=initial.configuration_id,
        run_id="browser_controlled_failure",
        fail_after_run_start=True,
    )
    assert failure.run.status == "failed"
    events = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "launch approved SPYM fixture"}
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/backtest-results", wait_until="networkidle")
            page.get_by_text("Strategy settings and launch", exact=True).click()
            _select(page, "configuration-selector", SPYM_OPTION_TEXT)
            expect(page.locator("#launch-run")).to_be_enabled()
            page.locator("#launch-run").click()
            expect(page.locator("#launch-message")).to_contain_text("Status: succeeded", timeout=60000)
            _wait_for_callbacks_to_settle(page, pending)
            page.screenshot(path=tmp_path / "launched-spym.png", full_page=True)

            action["name"] = "inspect a controlled failed run"
            page.locator("#refresh-runs").click()
            _wait_for_callbacks_to_settle(page, pending)
            _select(page, "selected-run-selector", "Infrastructure Fixture · Fixture backtest · Failed")
            _wait_for_callbacks_to_settle(page, pending)
            error = page.locator("#selected-run-detail").get_by_text(failure.run.error_summary, exact=True)
            expect(error.first).to_be_visible(timeout=10000)
            page.screenshot(path=tmp_path / "controlled-failure.png", full_page=True)
            _wait_for_callbacks_to_settle(page, pending)
            page.reload(wait_until="networkidle")
            _select(page, "selected-run-selector", "Infrastructure Fixture · Fixture backtest · Failed")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page.locator("#selected-run-detail").get_by_text(failure.run.error_summary, exact=True).first).to_be_visible()
            _wait_for_callbacks_to_settle(page, pending)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()
