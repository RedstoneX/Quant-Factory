"""Browser evidence for remaining Milestone 23 scenario gaps."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect, sync_playwright

from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService
from orchestration.run_service import FixtureRetryPolicy
from persistence import PersistenceService, RunStatus
from tests.browser.test_backtest_results_spym_stability import (
    BACKTEST_PATH,
    REPOSITORY_ROOT,
    _free_port,
    _launcher,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
    _attach_diagnostics,
    _select,
    _wait_for_callbacks_to_settle,
    _write_lifecycle_failure_artifacts,
)
from tests.test_milestone22e_acceptance import (
    _dashboard_fields,
    _database_path as _m22_database_path,
    _persist_corrupt_monte_carlo_file_case,
    _persist_failed_monte_carlo_case,
    _persist_missing_monte_carlo_file_case,
    _persist_passed_monte_carlo_case,
)
from tests.test_milestone_18_acceptance import (
    _attempt_late_completion,
    _blocking_launcher,
)
from tests.test_lockbox_gate import _service as _m22_service
from tests.test_run_service import _configuration


RETRY_RUN_ID = "m23-browser-retry"
TIMEOUT_RUN_ID = "m23-browser-timeout"
MONTE_CARLO_OPTION_TEXT = "Fixture Strategy · Monte Carlo validation · Created"


def _start_dashboard_process(
    *,
    database: Path,
    artifact_root: Path,
    tmp_path: Path,
):
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
        return process, base_url, server_log
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        raise


@pytest.fixture()
def retry_timeout_server(tmp_path: Path):
    database, configuration_id = _configuration(tmp_path)
    artifact_root = tmp_path
    retry_service = FixtureRunService(database=database, fixture_launcher=_launcher)
    retried = retry_service.launch_fixture(
        configuration_id=configuration_id,
        run_id=RETRY_RUN_ID,
        retry_policy=FixtureRetryPolicy(max_attempts=2),
        controlled_transient_failures=1,
    )
    assert retried.run.status == RunStatus.SUCCEEDED.value
    assert retried.run.attempt_count == 2

    timeout_started = threading.Event()
    timeout_release = threading.Event()
    timeout_finished = threading.Event()

    def timeout_after_release(persistence, kwargs, attempt_count):
        _attempt_late_completion(
            persistence,
            kwargs,
            attempt_count,
            "prefect-m23-browser-timeout",
        )

    timeout_service = FixtureRunService(
        database=database,
        fixture_launcher=_blocking_launcher(
            prefect_flow_run_id="prefect-m23-browser-timeout",
            started=timeout_started,
            release=timeout_release,
            finished=timeout_finished,
            after_release=timeout_after_release,
        ),
    )
    try:
        timeout = timeout_service.launch_fixture(
            configuration_id=configuration_id,
            run_id=TIMEOUT_RUN_ID,
            timeout_seconds=0.01,
        )
    finally:
        timeout_release.set()
    assert timeout_started.is_set()
    assert timeout_finished.wait(timeout=5)
    assert timeout.run.status == RunStatus.FAILED.value
    assert timeout.run.error_summary == "Fixture execution timed out after 0.01 seconds."

    persistence = PersistenceService(database)
    try:
        assert persistence.results.list_parameter_results(TIMEOUT_RUN_ID) == ()
        assert persistence.results.list_artifacts(TIMEOUT_RUN_ID) == ()
    finally:
        persistence.close()

    process, base_url, server_log = _start_dashboard_process(
        database=database,
        artifact_root=artifact_root,
        tmp_path=tmp_path,
    )
    try:
        yield base_url, server_log
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


@pytest.fixture(
    params=(
        ("passed", _persist_passed_monte_carlo_case),
        ("failed", _persist_failed_monte_carlo_case),
        ("invalid", _persist_corrupt_monte_carlo_file_case),
        ("insufficient_evidence", _persist_missing_monte_carlo_file_case),
    )
)
def normalized_outcome_server(tmp_path: Path, request):
    expected_status, arrange = request.param
    service = _m22_service(tmp_path)
    artifact_root = tmp_path / "artifacts"
    try:
        arrange(service, artifact_root)
    finally:
        service.close()

    expected_fields = _dashboard_fields(
        RunDetailDashboardAdapter(
            database=_m22_database_path(tmp_path),
            artifact_root=artifact_root,
        ).selected_run_detail("mc-run")
    )
    assert expected_fields["Normalized status"] == expected_status

    process, base_url, server_log = _start_dashboard_process(
        database=_m22_database_path(tmp_path),
        artifact_root=artifact_root,
        tmp_path=tmp_path,
    )
    try:
        yield base_url, server_log, expected_fields
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _open_details(page: Page, text: str) -> None:
    page.locator("summary", has_text=text).first.click()


def _selected_run_detail(page: Page):
    return page.locator("#selected-run-detail")


def test_retry_and_timeout_are_operator_visible_without_false_timeout_evidence(
    retry_timeout_server,
    tmp_path: Path,
) -> None:
    base_url, server_log = retry_timeout_server
    events: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "open retry and timeout scenario dashboard"}
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(f"{base_url}{BACKTEST_PATH}", wait_until="networkidle")
            action["name"] = "select retry run"
            _select(
                page,
                "selected-run-selector",
                "Infrastructure Fixture · Fixture backtest · Succeeded",
            )
            retry_detail = _selected_run_detail(page)
            expect(retry_detail).to_contain_text(RETRY_RUN_ID)
            expect(retry_detail).to_contain_text("succeeded")
            expect(retry_detail).to_contain_text("Attempt")
            expect(retry_detail).to_contain_text("2")
            _open_details(page, "Operations and diagnostics")
            expect(retry_detail).to_contain_text("run retry scheduled")
            expect(retry_detail).to_contain_text("Run completed successfully.")

            action["name"] = "select timeout run"
            _select(page, "selected-run-selector", "Infrastructure Fixture · Fixture backtest · Failed")
            timeout_detail = _selected_run_detail(page)
            expect(timeout_detail).to_contain_text(TIMEOUT_RUN_ID)
            expect(timeout_detail).to_contain_text("failed")
            expect(timeout_detail).to_contain_text(
                "Fixture execution timed out after 0.01 seconds."
            )
            expect(timeout_detail).to_contain_text("run timed out")
            expect(timeout_detail).to_contain_text(
                "Fixture execution exceeded its 0.01-second timeout."
            )
            expect(timeout_detail).to_contain_text(
                "No persisted parameter result summary is available"
            )
            expect(timeout_detail).to_contain_text("No artifact inventory is available")
            expect(timeout_detail.locator(".artifact-status-success")).to_have_count(0)
            page.screenshot(path=tmp_path / "retry-timeout-scenarios.png", full_page=True)
            _wait_for_callbacks_to_settle(page, pending)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


def test_normalized_validation_outcomes_render_consistently_in_browser(
    normalized_outcome_server,
    tmp_path: Path,
) -> None:
    base_url, server_log, expected_fields = normalized_outcome_server
    events: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": f"open normalized {expected_fields['Normalized status']} outcome"}
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(f"{base_url}{BACKTEST_PATH}", wait_until="networkidle")
            _select(page, "selected-run-selector", MONTE_CARLO_OPTION_TEXT)
            detail = _selected_run_detail(page)
            expect(detail).to_contain_text("Validation result")
            expect(detail).to_contain_text(expected_fields["Normalized status"])
            expect(detail).to_contain_text(expected_fields["Reasons"])
            _open_details(page, "Show technical details")
            for label in (
                "Stage",
                "Normalized status",
                "Reasons",
                "Protected-data state",
                "Evidence identity",
                "Artifact identity",
                "Lockbox eligibility",
                "Strategy progression",
            ):
                expect(detail).to_contain_text(label)
                expect(detail).to_contain_text(expected_fields[label])
            expect(detail).to_contain_text("No strategy progression occurred.")
            page.screenshot(
                path=tmp_path
                / f"normalized-{expected_fields['Normalized status']}.png",
                full_page=True,
            )
            _wait_for_callbacks_to_settle(page, pending)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()
