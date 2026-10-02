"""Browser proof for fail-closed recovery after dashboard process loss."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from typing import TextIO
from urllib.parse import urlencode

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect, sync_playwright

from orchestration import FixtureRunService
from persistence import ResearchSubmissionState
from tests.browser.dashboard_diagnostics import (
    assert_browser_diagnostics_clean,
    attach_browser_diagnostics,
)
from tests.browser.test_backtest_results_spym_stability import (
    REPOSITORY_ROOT,
    _free_port,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import _wait_for_callbacks_to_settle
from tests.browser.test_dashboard_responsive_acceptance import (
    _assert_document_contained,
)
from tests.test_run_service import _configuration


RUN_TEST_PATH = "/research/run-test"
RESULTS_PATH = "/research/backtest-results"
EXIT_EVIDENCE = "process-exit-proof:browser-process-a-killed"


def _start_dashboard(
    *,
    database: Path,
    invocation_log: Path,
    port: int,
    server_log: Path,
    block_launcher: bool,
) -> tuple[subprocess.Popen[str], TextIO]:
    code = r'''
import json
import os
from pathlib import Path
import sys
import time

from dashboard.app import create_app
from orchestration import FixtureRunService
from tests.browser.dashboard_diagnostics import install_callback_status_recorder

database = Path(sys.argv[1])
invocation_log = Path(sys.argv[2])
port = int(sys.argv[3])
block_launcher = sys.argv[4] == "block"

def launcher(**kwargs):
    with invocation_log.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "idempotency_key": kwargs["idempotency_key"],
                    "run_id": kwargs["quant_factory_run_id"],
                },
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
    if block_launcher:
        time.sleep(300)
    raise AssertionError("restart replay must not invoke the fixture launcher")

app = create_app(
    review_database=database,
    run_service=FixtureRunService(
        database=database,
        fixture_launcher=launcher,
    ),
)
install_callback_status_recorder(app.server)
app.run(host="127.0.0.1", port=port, debug=False)
'''
    environment = dict(os.environ)
    environment["QUANT_FACTORY_DB_PATH"] = str(database)
    log_handle = server_log.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            code,
            str(database),
            str(invocation_log),
            str(port),
            "block" if block_launcher else "forbid",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_server(f"http://127.0.0.1:{port}{RUN_TEST_PATH}")
    except BaseException:
        try:
            _stop_dashboard(process, log_handle)
        finally:
            raise
    return process, log_handle


def _stop_dashboard(process: subprocess.Popen[str], log_handle: TextIO) -> None:
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    finally:
        if not log_handle.closed:
            log_handle.close()


def _invocations(path: Path) -> tuple[dict[str, str], ...]:
    if not path.exists():
        return ()
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


def _wait_for_invocation(path: Path) -> tuple[dict[str, str], ...]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        recorded = _invocations(path)
        if recorded:
            return recorded
        time.sleep(0.05)
    raise AssertionError("the blocking fixture launcher was not entered")


def _durable_state(database: Path) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        submission = connection.execute(
            """
            SELECT idempotency_key, run_id, state, dispatcher_instance_id,
                   prefect_flow_run_id, unknown_evidence_reference
            FROM research_run_submissions
            """
        ).fetchall()
        runs = connection.execute(
            "SELECT run_id, status FROM experiment_runs ORDER BY run_id"
        ).fetchall()
        events = connection.execute(
            """
            SELECT run_id, event_type
            FROM run_operator_events
            ORDER BY event_id
            """
        ).fetchall()
        return {
            "submissions": submission,
            "runs": runs,
            "events": events,
        }
    finally:
        connection.close()


def _assert_unknown_run_test(page: Page, run_id: str) -> None:
    expect(page.locator("#launch-run")).to_be_disabled(timeout=10_000)
    expect(page.locator("#launch-run")).to_have_text("Submission unknown")
    expect(page.locator("#launch-message")).to_contain_text(
        "Submission outcome unknown"
    )
    expect(page.locator("#launch-message")).to_contain_text(run_id)
    expect(page.locator("#launch-message")).to_contain_text("Run status: Created")
    expect(page.locator("#launch-message")).to_contain_text(
        "Do not retry, cancel, or launch"
    )
    expect(page.locator("#run-test-operator-context")).to_contain_text(
        "Reconciliation required"
    )
    _assert_document_contained(page)


def _assert_unknown_results(page: Page, run_id: str) -> None:
    expect(page.locator("#selected-run-detail")).to_contain_text(
        run_id,
        timeout=10_000,
    )
    expect(page.locator("#launch-selected-run-configuration")).to_be_disabled()
    expect(page.locator("#historical-launch-message")).to_contain_text(
        "unknown submission outcome"
    )
    expect(page.locator("#reproduce-selected-run")).to_be_disabled()
    expect(page.locator("#reproduction-message")).to_contain_text(
        "unknown submission outcome"
    )
    expect(page.locator("#cancel-selected-run")).to_be_disabled()
    expect(page.locator("#cancel-selected-run")).to_have_attribute(
        "title",
        "Submission outcome is unknown. Reconcile it before cancellation.",
    )
    _assert_document_contained(page)


def test_dashboard_startup_failure_reaps_process_and_closes_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, _ = _configuration(tmp_path)
    invocation_log = tmp_path / "startup-failure-invocations.jsonl"
    server_log = tmp_path / "startup-failure-dashboard.log"
    processes: list[subprocess.Popen[str]] = []
    log_handles: list[TextIO] = []
    real_popen = subprocess.Popen
    real_path_open = Path.open

    def tracked_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    def tracked_path_open(path: Path, *args, **kwargs):
        handle = real_path_open(path, *args, **kwargs)
        if path == server_log:
            log_handles.append(handle)
        return handle

    def fail_readiness(_url: str) -> None:
        raise RuntimeError("controlled readiness failure")

    monkeypatch.setattr(subprocess, "Popen", tracked_popen)
    monkeypatch.setattr(Path, "open", tracked_path_open)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_wait_for_server",
        fail_readiness,
    )

    with pytest.raises(RuntimeError, match="controlled readiness failure"):
        _start_dashboard(
            database=database,
            invocation_log=invocation_log,
            port=_free_port(),
            server_log=server_log,
            block_launcher=True,
        )

    assert len(processes) == 1
    assert processes[0].poll() is not None
    assert len(log_handles) == 1
    assert log_handles[0].closed
    assert _invocations(invocation_log) == ()


def test_killed_invoking_ticket_reopens_unknown_without_duplicate_mutation(
    tmp_path: Path,
) -> None:
    database, _ = _configuration(tmp_path)
    invocation_log = tmp_path / "fixture-invocations.jsonl"
    server_a_log = tmp_path / "dashboard-a.log"
    server_b_log = tmp_path / "dashboard-b.log"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    process_a, log_a = _start_dashboard(
        database=database,
        invocation_log=invocation_log,
        port=port,
        server_log=server_a_log,
        block_launcher=True,
    )
    process_b: subprocess.Popen[str] | None = None
    log_b: TextIO | None = None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.goto(base_url + RUN_TEST_PATH, wait_until="networkidle")
            expect(page.locator("#launch-run")).to_be_enabled(timeout=10_000)

            page.locator("#launch-run").click(no_wait_after=True)
            first_invocations = _wait_for_invocation(invocation_log)
            assert len(first_invocations) == 1

            invoking = _durable_state(database)
            assert len(invoking["submissions"]) == 1
            assert len(invoking["runs"]) == 1
            assert len(invoking["events"]) == 1
            (
                key,
                run_id,
                state,
                dispatcher_id,
                prefect_flow_run_id,
                unknown_evidence_reference,
            ) = invoking["submissions"][0]
            assert first_invocations == ({"idempotency_key": key, "run_id": run_id},)
            assert state == ResearchSubmissionState.INVOKING.value
            assert prefect_flow_run_id is None
            assert unknown_evidence_reference is None
            assert invoking["runs"] == [(run_id, "created")]
            assert invoking["events"] == [(run_id, "run_created")]

            process_a.kill()
            process_a.wait(timeout=10)
            log_a.close()
            assert process_a.returncode is not None and process_a.returncode < 0
            assert _durable_state(database) == invoking

            recovered = FixtureRunService(
                database=database
            ).recover_invoking_after_process_exit(
                idempotency_key=key,
                departed_dispatcher_instance_id=dispatcher_id,
                process_exit_evidence_reference=EXIT_EVIDENCE,
            )
            assert recovered.state == ResearchSubmissionState.SUBMISSION_UNKNOWN
            unknown = _durable_state(database)
            assert unknown["submissions"] == [
                (
                    key,
                    run_id,
                    ResearchSubmissionState.SUBMISSION_UNKNOWN.value,
                    dispatcher_id,
                    None,
                    EXIT_EVIDENCE,
                )
            ]
            assert unknown["runs"] == invoking["runs"]
            assert unknown["events"] == invoking["events"]

            process_b, log_b = _start_dashboard(
                database=database,
                invocation_log=invocation_log,
                port=port,
                server_log=server_b_log,
                block_launcher=False,
            )
            assert process_b.poll() is None
            diagnostics: list[dict[str, object]] = []
            action = {"name": "restart and reopen the submitted run ticket"}
            pending = attach_browser_diagnostics(page, diagnostics, action)

            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _assert_unknown_run_test(page, run_id)

            action["name"] = "open the unknown run by direct Results link"
            results_url = (
                f"{base_url}{RESULTS_PATH}?"
                + urlencode({"run_id": run_id})
            )
            page.goto(results_url, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _assert_unknown_results(page, run_id)

            action["name"] = "refresh the unknown Results deep link"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _assert_unknown_results(page, run_id)

            action["name"] = "go back to the unknown Run test ticket"
            page.go_back(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _assert_unknown_run_test(page, run_id)

            action["name"] = "go forward to the same unknown Results run"
            page.go_forward(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            _assert_unknown_results(page, run_id)

            assert not pending
            assert _invocations(invocation_log) == first_invocations
            assert _durable_state(database) == unknown
            assert_browser_diagnostics_clean(page, diagnostics, (server_b_log,))

            context.close()
            browser.close()
    finally:
        _stop_dashboard(process_a, log_a)
        if process_b is not None and log_b is not None:
            _stop_dashboard(process_b, log_b)
