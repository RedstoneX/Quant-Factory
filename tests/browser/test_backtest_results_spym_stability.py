"""Browser acceptance coverage for Backtest Results SPYM stability."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, sync_playwright

from orchestration import FixtureRunService
from persistence import PersistenceService, StrategyLifecycle
from persistence.models import normalized_configuration_document
from prefect_spike.fixture_flow import deterministic_fixture_body
from prefect_spike.milestone23_browser_fixture import (
    TARGET_RUN_ID,
    prepare_milestone23_browser_fixture,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKTEST_PATH = "/research/backtest-results"
SPYM_OPTION_TEXT = "SPYM RSI Mean Reversion Fixture"
INITIAL_OPTION_TEXT = "Infrastructure Fixture"


def _launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def _prepare_initial_run(database: Path) -> str:
    persistence = PersistenceService(database)
    try:
        persistence.register_strategy(
            strategy_id="prefect_fixture_strategy",
            strategy_version="1.0.0",
            display_name="Prefect Fixture Strategy",
            description="Synthetic fixture for browser selector initialization",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configuration = persistence.upsert_configuration(
            normalized_configuration_document(
                experiment_id="spym_selector_stability_initial_fixture",
                strategy_id="prefect_fixture_strategy",
                strategy_version="1.0.0",
                market_data={"kind": "none"},
                parameters={"fixture": True},
                execution={"kind": "prefect_fixture"},
                ranking={
                    "columns": ("deterministic_value",),
                    "ascending": (False,),
                },
                screening={"kind": "none"},
            )
        )
    finally:
        persistence.close()
    initial_run_id = "spym_selector_stability_initial_run"
    result = FixtureRunService(
        database=database,
        fixture_launcher=_launcher,
    ).launch_fixture(
        configuration_id=configuration.configuration_id,
        run_id=initial_run_id,
    )
    assert result.run.status == "succeeded"
    return initial_run_id


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, *, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            urlopen(url, timeout=1).read(1)
            return
        except Exception as exc:  # pragma: no cover - diagnostic only
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(f"Dashboard server did not start at {url}: {last_error}")


@pytest.fixture()
def dashboard_server(tmp_path: Path):
    fixture_root = tmp_path
    database = fixture_root / "state" / "browser-fixture.sqlite3"
    artifact_root = fixture_root
    summary = prepare_milestone23_browser_fixture(
        database=database,
        artifact_root=artifact_root,
        fixture_launcher=_launcher,
    )
    assert summary.target_run_id == TARGET_RUN_ID
    initial_run_id = _prepare_initial_run(database)

    port = _free_port()
    server_log = tmp_path / "dashboard-server.log"
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService

from tests.browser.test_backtest_results_spym_stability import _launcher

database = Path(sys.argv[1])
artifact_root = Path(sys.argv[2])
port = int(sys.argv[3])
app = create_app(
    review_database=database,
    run_service=FixtureRunService(database=database, fixture_launcher=_launcher),
    run_detail_adapter=RunDetailDashboardAdapter(
        database=database,
        artifact_root=artifact_root,
    ),
)
app.run(host="127.0.0.1", port=port, debug=False)
"""
    env = dict(os.environ)
    env["QUANT_FACTORY_DB_PATH"] = str(database)
    with server_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(database), str(artifact_root), str(port)],
            cwd=REPOSITORY_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(f"{base_url}{BACKTEST_PATH}")
        yield base_url, server_log, initial_run_id
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _visible_routes(page: Page) -> list[str]:
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('[id^="route-"]'))
          .filter((el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none'
              && style.visibility !== 'hidden'
              && rect.width > 0
              && rect.height > 0;
          })
          .map((el) => el.id)
        """
    )


def _state(page: Page, base_url: str) -> dict[str, object]:
    return {
        "url": page.url.removeprefix(base_url),
        "visible_routes": _visible_routes(page),
        "selected_run": page.locator("#selected-run-selector").inner_text(timeout=5000),
        "h1": [text.strip() for text in page.locator("h1").all_inner_texts() if text.strip()],
        "plotly_charts": page.locator(".js-plotly-plot").count(),
        "graph_containers": page.locator(".dash-graph").count(),
        "has_portfolio_panel": page.get_by_text(
            "Portfolio value and buy-and-hold comparison", exact=True
        ).count() > 0,
        "has_trade_pnl_panel": page.get_by_text("Cumulative trade P&L").count() > 0,
    }


def _write_failure_artifacts(
    *,
    page: Page,
    tmp_path: Path,
    states: list[dict[str, object]],
    console_errors: list[dict[str, object]],
    page_errors: list[str],
    dash_requests: list[dict[str, object]],
    history_events: list[dict[str, object]],
    server_log: Path,
) -> None:
    page.screenshot(path=tmp_path / "backtest-results-spym-failure.png", full_page=True)
    diagnostics = {
        "states": states,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "history_events": history_events,
        "dash_requests": dash_requests,
        "server_log": server_log.read_text(encoding="utf-8", errors="replace"),
    }
    (tmp_path / "backtest-results-spym-diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2),
        encoding="utf-8",
    )


def test_backtest_results_spym_selection_remains_stable(
    dashboard_server,
    tmp_path: Path,
) -> None:
    base_url, server_log, initial_run_id = dashboard_server
    console_errors: list[dict[str, object]] = []
    page_errors: list[str] = []
    dash_requests: list[dict[str, object]] = []
    states: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(
            """
            (() => {
              window.__qfHistoryEvents = [];
              for (const name of ['pushState', 'replaceState']) {
                const original = history[name];
                history[name] = function(state, title, url) {
                  window.__qfHistoryEvents.push({
                    kind: name,
                    url: String(url),
                    before: location.pathname,
                    timestamp: Date.now()
                  });
                  return original.apply(this, arguments);
                };
              }
              window.addEventListener('popstate', () => {
                window.__qfHistoryEvents.push({
                  kind: 'popstate',
                  path: location.pathname,
                  timestamp: Date.now()
                });
              }, true);
            })();
            """
        )
        page = context.new_page()
        page.on(
            "console",
            lambda message: console_errors.append(
                {
                    "type": message.type,
                    "text": message.text,
                    "location": message.location,
                }
            )
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "request",
            lambda request: dash_requests.append(
                {
                    "method": request.method,
                    "url": request.url,
                    "post_data": request.post_data,
                }
            )
            if "/_dash-update-component" in request.url
            else None,
        )

        try:
            page.goto(f"{base_url}{BACKTEST_PATH}", wait_until="networkidle")
            page.locator("#selected-run-selector").wait_for(timeout=10000)
            states.append({"label": "opened", **_state(page, base_url)})
            assert INITIAL_OPTION_TEXT in str(states[-1]["selected_run"])
            assert SPYM_OPTION_TEXT not in str(states[-1]["selected_run"])
            assert initial_run_id != TARGET_RUN_ID

            page.locator("#selected-run-selector").click()
            page.locator(
                ".dash-options-list-option-text",
                has_text=SPYM_OPTION_TEXT,
            ).first.click(timeout=10000)
            page.wait_for_load_state("networkidle")
            states.append({"label": "selected", **_state(page, base_url)})

            page.wait_for_timeout(20_000)
            states.append({"label": "after-wait", **_state(page, base_url)})
            history_events = page.evaluate("window.__qfHistoryEvents || []")

            final = states[-1]
            assert final["url"] == BACKTEST_PATH
            assert final["visible_routes"] == ["route-research-backtest-results"]
            assert "Results" in final["h1"]
            assert SPYM_OPTION_TEXT in str(final["selected_run"])
            assert int(final["plotly_charts"]) > 0
            assert final["has_portfolio_panel"] is True
            assert final["has_trade_pnl_panel"] is True
            assert history_events == []
            assert console_errors == []
            assert page_errors == []
        except Exception:
            history_events = page.evaluate("window.__qfHistoryEvents || []")
            _write_failure_artifacts(
                page=page,
                tmp_path=tmp_path,
                states=states,
                console_errors=console_errors,
                page_errors=page_errors,
                dash_requests=dash_requests,
                history_events=history_events,
                server_log=server_log,
            )
            raise
        finally:
            context.close()
            browser.close()
