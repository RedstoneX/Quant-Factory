"""Portable browser evidence for cancellation and stale-run recovery controls."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, Iterator

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect, sync_playwright

from orchestration import FixtureRunService
from persistence import PersistenceService, RunStatus
from persistence.service import RunCompletionRejectedError
from prefect_spike.fixture_flow import (
    ControlledFixtureCancellation,
    PrefectFixtureResult,
    PrefectRunReference,
    _create_or_reference_run,
    _persist_fixture_result,
    acknowledge_fixture_cancellation,
    reconcile_quant_factory_run_status,
)
from tests.browser.test_backtest_results_spym_stability import (
    BACKTEST_PATH,
    REPOSITORY_ROOT,
    _free_port,
    _visible_routes,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
    _attach_diagnostics,
    _wait_for_callbacks_to_settle,
)
from tests.browser.test_dashboard_responsive_acceptance import (
    _assert_document_contained,
)
from tests.test_run_service import _configuration, _launcher
from tests.test_run_stale_recovery import STALE_BEFORE, _create_run


CANCEL_RUN_ID = "browser-cancellation-active-run"
STALE_RUN_ID = "browser-stale-running-run"


@contextmanager
def _dashboard_server(database: Path, tmp_path: Path) -> Iterator[tuple[str, Path]]:
    port = _free_port()
    server_log = tmp_path / "recovery-controls-server.log"
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app
from orchestration import FixtureRunService
from tests.test_run_service import _launcher

database = Path(sys.argv[1])
port = int(sys.argv[2])
app = create_app(
    review_database=database,
    run_service=FixtureRunService(database=database, fixture_launcher=_launcher),
)
app.run(host="127.0.0.1", port=port, debug=False)
"""
    env = dict(os.environ)
    env["QUANT_FACTORY_DB_PATH"] = str(database)
    with server_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(database), str(port)],
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


def _assert_results_identity(page: Page, base_url: str) -> None:
    expect(page).to_have_url(base_url + BACKTEST_PATH)
    expect(page.locator("#route-research-backtest-results")).to_be_visible()
    assert _visible_routes(page) == ["route-research-backtest-results"]
    expect(page.locator("#responsive-active-page")).to_have_text("Results")


def _assert_diagnostics_clean(events: list[dict[str, Any]]) -> None:
    _assert_no_browser_errors(events)
    assert [event for event in events if event["kind"] == "requestfailed"] == []


def _write_failure_evidence(
    page: Page,
    tmp_path: Path,
    name: str,
    events: list[dict[str, Any]],
    server_log: Path,
) -> None:
    page.screenshot(path=tmp_path / f"{name}-failure.png", full_page=True)
    (tmp_path / f"{name}-diagnostics.json").write_text(
        json.dumps(
            {
                "events": events,
                "server_log": server_log.read_text(
                    encoding="utf-8", errors="replace"
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_mobile_operator_cancels_active_run_and_late_completion_stays_blocked(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    late_completion_blocked = threading.Event()
    launch_errors: list[BaseException] = []

    def blocking_launcher(**kwargs: Any) -> PrefectFixtureResult:
        persistence = PersistenceService(kwargs["database_path"])
        try:
            _create_or_reference_run(
                persistence,
                configuration_id=kwargs["configuration_id"],
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_reference=PrefectRunReference(
                    flow_run_id="prefect-browser-cancellation"
                ),
                reference_source="browser_cancellation_test",
            )
            persistence.increment_run_attempt(kwargs["quant_factory_run_id"])
            reconcile_quant_factory_run_status(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_state="Running",
            )
            started.set()
            if not release.wait(timeout=30):
                raise AssertionError("Browser did not release the blocking fixture")
            try:
                acknowledge_fixture_cancellation(
                    persistence,
                    quant_factory_run_id=kwargs["quant_factory_run_id"],
                )
            except ControlledFixtureCancellation:
                try:
                    _persist_fixture_result(
                        persistence,
                        quant_factory_run_id=kwargs["quant_factory_run_id"],
                        configuration_id=kwargs["configuration_id"],
                        prefect_flow_run_id="prefect-browser-cancellation",
                        deterministic_value=1729,
                        attempt_count=1,
                    )
                except RunCompletionRejectedError:
                    late_completion_blocked.set()
                else:  # pragma: no cover - safety assertion
                    raise AssertionError("Late completion overwrote cancellation")
            reconcile_quant_factory_run_status(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_state="Completed",
            )
            return PrefectFixtureResult(
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_flow_run_id="prefect-browser-cancellation",
                configuration_id=kwargs["configuration_id"],
                deterministic_value=1729,
                attempt_count=1,
            )
        finally:
            persistence.close()
            finished.set()

    launch_service = FixtureRunService(
        database=database,
        fixture_launcher=blocking_launcher,
    )

    def launch() -> None:
        try:
            launch_service.launch_fixture(
                configuration_id=configuration_id,
                run_id=CANCEL_RUN_ID,
            )
        except BaseException as exc:  # assertion below reports worker failures
            launch_errors.append(exc)

    worker = threading.Thread(target=launch, name="browser-cancellation-fixture")
    worker.start()
    assert started.wait(timeout=10)

    events: list[dict[str, Any]] = []
    try:
        with _dashboard_server(database, tmp_path) as (base_url, server_log):
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 390, "height": 844})
                page = context.new_page()
                action = {"name": "open active cancellation run on mobile"}
                pending = _attach_diagnostics(page, events, action)
                try:
                    page.goto(base_url + BACKTEST_PATH, wait_until="networkidle")
                    _wait_for_callbacks_to_settle(page, pending)
                    _assert_results_identity(page, base_url)
                    _assert_document_contained(page)
                    expect(page.locator("#results-operator-context")).to_contain_text(
                        "Run statusRunning"
                    )

                    page.get_by_text(
                        "Comparison and selected-backtest actions", exact=True
                    ).click()
                    cancel = page.locator("#cancel-selected-run")
                    expect(cancel).to_be_visible()
                    expect(cancel).to_be_enabled()

                    action["name"] = "request cancellation on mobile"
                    cancel.click()
                    expect(page.locator("#cancellation-message")).to_contain_text(
                        "Cancellation requested"
                    )
                    expect(page.locator("#cancellation-message")).to_contain_text(
                        "waiting for fixture acknowledgement"
                    )
                    _wait_for_callbacks_to_settle(page, pending)

                    action["name"] = "repeat pending cancellation on mobile"
                    cancel.click()
                    _wait_for_callbacks_to_settle(page, pending)
                    expect(page.locator("#cancellation-message")).to_contain_text(
                        "Cancellation requested"
                    )
                    assert [
                        event.event_type
                        for event in launch_service.events_for_run(CANCEL_RUN_ID)
                    ].count("run_cancellation_requested") == 1

                    release.set()
                    assert finished.wait(timeout=10)
                    worker.join(timeout=10)
                    assert not worker.is_alive()
                    assert launch_errors == []
                    assert late_completion_blocked.is_set()

                    action["name"] = "refresh terminal cancellation on mobile"
                    page.locator("#refresh-runs").click()
                    _wait_for_callbacks_to_settle(page, pending)
                    expect(page.locator("#results-operator-context")).to_contain_text(
                        "Run statusCancelled"
                    )
                    expect(page.locator("#results-operator-context")).to_contain_text(
                        "Next safe actionReview failure"
                    )
                    expect(page.locator("#selected-run-detail")).to_contain_text(
                        "Run cancelled after fixture acknowledgement."
                    )
                    expect(cancel).to_be_disabled()
                    _assert_document_contained(page)

                    action["name"] = "reload terminal cancellation on mobile"
                    page.reload(wait_until="networkidle")
                    _wait_for_callbacks_to_settle(page, pending)
                    _assert_results_identity(page, base_url)
                    expect(page.locator("#selected-run-detail")).to_contain_text(
                        CANCEL_RUN_ID
                    )
                    expect(page.locator("#results-operator-context")).to_contain_text(
                        "Run statusCancelled"
                    )
                    _assert_document_contained(page)
                    _assert_diagnostics_clean(events)
                except Exception:
                    _write_failure_evidence(
                        page, tmp_path, "mobile-cancellation", events, server_log
                    )
                    raise
                finally:
                    context.close()
                    browser.close()
    finally:
        release.set()
        worker.join(timeout=10)

    persisted = launch_service.get_run(CANCEL_RUN_ID)
    assert persisted is not None
    assert persisted.status == RunStatus.CANCELLED.value
    event_types = [
        event.event_type for event in launch_service.events_for_run(CANCEL_RUN_ID)
    ]
    assert event_types.count("run_cancellation_requested") == 1
    assert event_types.count("run_cancelled") == 1
    assert "run_succeeded" not in event_types


def test_tablet_operator_recovers_stale_run_and_repeat_is_safe(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    _create_run(
        database,
        configuration_id,
        run_id=STALE_RUN_ID,
        status=RunStatus.RUNNING,
        old=True,
        attempts=2,
    )
    service = FixtureRunService(database=database)
    events: list[dict[str, Any]] = []

    with _dashboard_server(database, tmp_path) as (base_url, server_log):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1024, "height": 900})
            page = context.new_page()
            action = {"name": "open stale running run on tablet"}
            pending = _attach_diagnostics(page, events, action)
            try:
                page.goto(base_url + BACKTEST_PATH, wait_until="networkidle")
                _wait_for_callbacks_to_settle(page, pending)
                _assert_results_identity(page, base_url)
                expect(page.locator("#results-operator-context")).to_contain_text(
                    "Run statusRunning"
                )
                _assert_document_contained(page)

                page.get_by_text("Recovery and operator events", exact=True).click()
                cutoff = page.locator("#stale-before-input")
                recover = page.locator("#recover-stale-runs")
                expect(cutoff).to_be_visible()
                expect(recover).to_be_visible()

                action["name"] = "recover stale running run on tablet"
                cutoff.fill(STALE_BEFORE)
                cutoff.press("Tab")
                recover.click()
                _wait_for_callbacks_to_settle(page, pending)
                message = page.locator("#stale-recovery-message")
                expect(message).to_contain_text("Recovered 1 stale fixture run.")
                expect(message).to_contain_text(STALE_RUN_ID)
                expect(message).to_contain_text(
                    "remained running beyond the stale recovery cutoff"
                )
                expect(page.locator("#results-operator-context")).to_contain_text(
                    "Run statusFailed"
                )
                expect(page.locator("#results-operator-context")).to_contain_text(
                    "Next safe actionReview failure"
                )
                expect(page.locator("#selected-run-detail")).to_contain_text(
                    "Fixture run remained running beyond the stale recovery cutoff."
                )
                _assert_document_contained(page)

                recovered_events = service.events_for_run(STALE_RUN_ID)
                assert [event.event_type for event in recovered_events].count(
                    "run_stale_recovered"
                ) == 1

                action["name"] = "reload recovered stale run on tablet"
                page.reload(wait_until="networkidle")
                _wait_for_callbacks_to_settle(page, pending)
                _assert_results_identity(page, base_url)
                expect(page.locator("#selected-run-detail")).to_contain_text(
                    STALE_RUN_ID
                )
                expect(page.locator("#results-operator-context")).to_contain_text(
                    "Run statusFailed"
                )
                _assert_document_contained(page)

                page.get_by_text("Recovery and operator events", exact=True).click()
                cutoff = page.locator("#stale-before-input")
                recover = page.locator("#recover-stale-runs")
                action["name"] = "repeat stale recovery on tablet"
                cutoff.fill(STALE_BEFORE)
                cutoff.press("Tab")
                recover.click()
                _wait_for_callbacks_to_settle(page, pending)
                expect(page.locator("#stale-recovery-message")).to_have_text(
                    "No stale fixture runs matched the supplied cutoff."
                )
                repeated_events = service.events_for_run(STALE_RUN_ID)
                assert [event.event_type for event in repeated_events].count(
                    "run_stale_recovered"
                ) == 1
                assert [event.event_type for event in repeated_events].count(
                    "run_failed"
                ) == 1
                _assert_document_contained(page)
                _assert_diagnostics_clean(events)
            except Exception:
                _write_failure_evidence(
                    page, tmp_path, "tablet-stale-recovery", events, server_log
                )
                raise
            finally:
                context.close()
                browser.close()
