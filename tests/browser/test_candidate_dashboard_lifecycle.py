"""Real-browser smoke for deterministic candidate dashboard routing."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from persistence import PersistenceService
from tests.browser.dashboard_diagnostics import attach_browser_diagnostics
from tests.browser.test_backtest_results_spym_stability import (
    BACKTEST_PATH,
    REPOSITORY_ROOT,
    _free_port,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
)
from tests.test_candidate_dashboard_runtime import prepare_strict_candidate_database


@pytest.fixture()
def candidate_dashboard_server(tmp_path: Path):
    database = tmp_path / "state" / "candidate-browser.sqlite3"
    artifact_root = tmp_path / "artifacts"
    configuration_id = prepare_strict_candidate_database(database, tmp_path)
    port = _free_port()
    server_log = tmp_path / "candidate-browser-server.log"
    code = """
from pathlib import Path
import sys

from dashboard.app import create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import (
    CANDIDATE_SCREENING_LAUNCH_CONTRACT,
    DurableResearchLaunchService,
    FixtureRunService,
)
from tests.browser.dashboard_diagnostics import install_callback_status_recorder
from tests.test_candidate_dashboard_runtime import deterministic_default_runtime_adapter

database = Path(sys.argv[1])
artifact_root = Path(sys.argv[2])
port = int(sys.argv[3])
def deterministic_adapter(*, runtime, submission):
    claims = DurableResearchLaunchService(
        database=runtime.database,
        launch_contract=CANDIDATE_SCREENING_LAUNCH_CONTRACT,
        initialize_schema=False,
    )
    return deterministic_default_runtime_adapter(
        runtime,
        submission,
        claims,
        delay_seconds=4.0,
    )

app = create_app(
    review_database=database,
    run_service=FixtureRunService(database=database),
    candidate_pipeline_launcher=deterministic_adapter,
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
        _wait_for_server(base_url + "/research/setup")
        yield base_url, server_log, database, configuration_id
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _run_ids(database: Path) -> tuple[str, ...]:
    persistence = PersistenceService(database)
    try:
        return tuple(run.run_id for run in persistence.runs.list())
    finally:
        persistence.close()


def _run_status(database: Path, run_id: str) -> str | None:
    persistence = PersistenceService(database)
    try:
        run = persistence.runs.get(run_id)
        return run.status.value if run is not None else None
    finally:
        persistence.close()


def _wait_for_run_status(
    database: Path,
    run_id: str,
    expected: str,
    *,
    timeout: float = 15.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _run_status(database, run_id) == expected:
            return
        time.sleep(0.05)
    raise AssertionError(
        f"run {run_id} did not reach {expected}; current={_run_status(database, run_id)}"
    )


def test_candidate_selection_launch_results_and_reproduction_smoke(
    candidate_dashboard_server,
) -> None:
    base_url, server_log, database, configuration_id = candidate_dashboard_server
    events: list[dict[str, object]] = []
    action = {"name": "candidate setup"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        attach_browser_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/setup", wait_until="networkidle")
            expect(page.locator("#configuration-selector")).to_contain_text(
                "RSI Mean Reversion"
            )
            expect(page.locator("#configuration-preview")).to_contain_text(
                "owner-approved candidate"
            )
            expect(page.locator("#review-test-action")).to_have_attribute(
                "href", "/research/run-test"
            )

            action["name"] = "candidate review"
            page.locator("#review-test-action").click()
            expect(page).to_have_url(base_url + "/research/run-test")
            expect(page.locator("#run-configuration-preview")).to_contain_text(
                configuration_id[:10]
            )
            expect(page.locator("#launch-run")).to_be_enabled(timeout=10_000)

            action["name"] = "candidate launch"
            page.locator("#launch-run").click()
            deadline = time.monotonic() + 15.0
            source_run_id = None
            while time.monotonic() < deadline:
                run_ids = _run_ids(database)
                if run_ids:
                    source_run_id = run_ids[0]
                    if _run_status(database, source_run_id) == "running":
                        break
                time.sleep(0.05)
            assert source_run_id
            assert _run_status(database, source_run_id) == "running"

            action["name"] = "candidate running refresh"
            page.reload(wait_until="networkidle")
            expect(page.locator("#launch-message")).to_contain_text(
                "Run status: Running",
                timeout=10_000,
            )
            _wait_for_run_status(database, source_run_id, "succeeded")
            page.reload(wait_until="networkidle")
            expect(page.locator("#launch-message")).to_contain_text(
                "Run status: Succeeded",
                timeout=10_000,
            )
            displayed_source_run_id = page.locator(
                "#launch-message [data-run-id]"
            ).get_attribute("data-run-id")
            assert displayed_source_run_id == source_run_id
            assert _run_ids(database) == (source_run_id,)

            action["name"] = "candidate results"
            page.goto(
                f"{base_url}{BACKTEST_PATH}?run_id={source_run_id}",
                wait_until="networkidle",
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                source_run_id,
                timeout=20_000,
            )
            page.get_by_text(
                "Comparison and selected-backtest actions",
                exact=True,
            ).click()
            expect(page.locator("#reproduce-selected-run")).to_be_enabled(
                timeout=10_000
            )

            action["name"] = "candidate reproduction"
            page.locator("#reproduce-selected-run").click()
            expect(page.locator("#reproduction-message")).to_contain_text(
                "Run status: Succeeded",
                timeout=60_000,
            )
            reproduced_run_id = page.locator(
                "#reproduction-message [data-run-id]"
            ).get_attribute("data-run-id")
            assert reproduced_run_id and reproduced_run_id != source_run_id
            assert set(_run_ids(database)) == {source_run_id, reproduced_run_id}
            _assert_no_browser_errors(events)
            assert page.locator("._dash-error-card").count() == 0
        except Exception:
            page.screenshot(
                path=server_log.parent / "candidate-dashboard-failure.png",
                full_page=True,
            )
            raise
        finally:
            browser.close()
