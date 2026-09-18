"""Browser evidence for remaining Milestone 23 scenario gaps."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect, sync_playwright

from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService
from orchestration.research_launch_claims import ResearchLaunchInvocationError
from persistence import PersistenceService, RunStatus
import prefect_spike.fixture_flow as fixture_flow
from prefect_spike.fixture_flow import (
    PrefectRunReference,
    _validated_claim_boundary,
    deterministic_fixture_body,
)
from tests.browser.test_backtest_results_spym_stability import (
    BACKTEST_PATH,
    REPOSITORY_ROOT,
    _free_port,
    _launcher,
    _prepare_initial_run,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
    _attach_diagnostics,
    _select,
    _wait_for_callbacks_to_settle,
    _write_lifecycle_failure_artifacts,
)
from tests.browser.test_dashboard_responsive_acceptance import (
    _assert_document_contained,
    _assert_visible_surfaces_contained,
)
from tests.browser.test_dashboard_responsive_operation import _assert_runtime_clean
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
CONTROLLED_FAILURE_MARKER_ENV = "QF_CONTROLLED_FAILURE_INVOCATION_MARKER"


def _controlled_failure_launcher(**kwargs):
    """Record and execute one acknowledged deterministic fixture failure."""

    marker = Path(os.environ[CONTROLLED_FAILURE_MARKER_ENV])
    marker.parent.mkdir(parents=True, exist_ok=True)
    with marker.open("a", encoding="utf-8") as handle:
        handle.write(f"{kwargs['quant_factory_run_id']}\n")
    kwargs.pop("attempt_marker_path", None)
    kwargs["fail_after_run_start"] = True
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


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
def controlled_failure_browser_server(tmp_path: Path):
    database = tmp_path / "state" / "controlled-failure-browser.sqlite3"
    _prepare_initial_run(database)
    marker = tmp_path / "controlled-failure-invocations.txt"
    port = _free_port()
    server_log = tmp_path / "controlled-failure-browser-server.log"
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService
from tests.browser.test_milestone23_scenario_acceptance import _controlled_failure_launcher

database = Path(sys.argv[1])
port = int(sys.argv[2])
app = create_app(
    review_database=database,
    run_service=FixtureRunService(
        database=database,
        fixture_launcher=_controlled_failure_launcher,
    ),
    run_detail_adapter=RunDetailDashboardAdapter(
        database=database,
        artifact_root=database.parent.parent,
    ),
)
app.run(host="127.0.0.1", port=port, debug=False)
"""
    env = dict(os.environ)
    env["QUANT_FACTORY_DB_PATH"] = str(database)
    env[CONTROLLED_FAILURE_MARKER_ENV] = str(marker)
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
        _wait_for_server(f"{base_url}/research/run-test")
        yield base_url, server_log, database, marker
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


@pytest.fixture()
def retry_timeout_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database, configuration_id = _configuration(tmp_path)
    retry_marker = tmp_path / "attempts" / "internal-retry.txt"
    retry_invocations: list[str] = []
    assert fixture_flow.deterministic_retry_task is not None
    monkeypatch.setattr(
        fixture_flow,
        "get_run_logger",
        lambda: SimpleNamespace(warning=lambda *_args: None, info=lambda *_args: None),
    )

    def internal_retry_launcher(**kwargs):
        retry_invocations.append(kwargs["quant_factory_run_id"])
        marker = kwargs.pop("attempt_marker_path")
        _validated_claim_boundary(
            database_path=kwargs["database_path"],
            idempotency_key=kwargs["idempotency_key"],
            configuration_id=kwargs["configuration_id"],
            quant_factory_run_id=kwargs["quant_factory_run_id"],
            canonical_request_json=kwargs["canonical_request_json"],
            request_fingerprint=kwargs["request_fingerprint"],
            operation_kind=kwargs["operation_kind"],
            source_run_id=kwargs["source_run_id"],
            source_lineage=kwargs["source_lineage"],
            prefect_reference=PrefectRunReference(
                flow_run_id="prefect-m23-browser-retry"
            ),
        )
        task_body = fixture_flow.deterministic_retry_task.fn
        with pytest.raises(RuntimeError, match="controlled first-attempt failure"):
            task_body(str(database), kwargs["quant_factory_run_id"], str(marker))
        assert task_body(
            str(database), kwargs["quant_factory_run_id"], str(marker)
        ) == {"deterministic_value": 1729}
        return deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id="prefect-m23-browser-retry",
        )

    artifact_root = tmp_path
    retry_service = FixtureRunService(
        database=database,
        fixture_launcher=internal_retry_launcher,
    )
    retried = retry_service.launch_fixture(
        configuration_id=configuration_id,
        run_id=RETRY_RUN_ID,
        attempt_marker_path=retry_marker,
    )
    assert retried.run.status == RunStatus.SUCCEEDED.value
    assert retried.run.attempt_count == 1
    assert retry_invocations == [RETRY_RUN_ID]

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
        with pytest.raises(ResearchLaunchInvocationError):
            timeout_service.launch_fixture(
                configuration_id=configuration_id,
                run_id=TIMEOUT_RUN_ID,
                timeout_seconds=0.01,
            )
    finally:
        timeout_release.set()
    assert timeout_started.is_set()
    assert timeout_finished.wait(timeout=5)
    timeout = timeout_service.get_run(TIMEOUT_RUN_ID)
    assert timeout is not None
    assert timeout.status == RunStatus.SUCCEEDED.value
    assert timeout.error_summary is None

    persistence = PersistenceService(database)
    try:
        assert persistence.results.list_parameter_results(TIMEOUT_RUN_ID)
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


def _durable_identities(database: Path) -> tuple[set[str], set[str]]:
    service = PersistenceService(database)
    try:
        run_ids = {
            str(row[0])
            for row in service.connection.execute(
                "SELECT run_id FROM experiment_runs"
            ).fetchall()
        }
        submission_keys = {
            str(row[0])
            for row in service.connection.execute(
                "SELECT idempotency_key FROM research_run_submissions"
            ).fetchall()
        }
        return run_ids, submission_keys
    finally:
        service.close()


def test_run_test_controlled_failure_is_truthful_replay_safe_and_diagnosable(
    controlled_failure_browser_server,
    tmp_path: Path,
) -> None:
    base_url, server_log, database, marker = controlled_failure_browser_server
    baseline_runs, baseline_submissions = _durable_identities(database)
    events: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        action = {"name": "open Run test controlled failure fixture"}
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(f"{base_url}/research/run-test", wait_until="networkidle")
            expect(page.locator("#launch-run")).to_be_enabled()
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)

            action["name"] = "explicitly launch one controlled failing test"
            page.locator("#launch-run").click()
            launch_message = page.locator("#launch-message")
            expect(launch_message).to_contain_text(
                "Submission: Acknowledged",
                timeout=60_000,
            )
            expect(launch_message).to_contain_text("Run status: Failed")
            expect(page.locator("#run-test-operator-context")).to_contain_text(
                "Failed"
            )
            expect(page.locator("#run-test-operator-context")).to_contain_text(
                "Review failure"
            )
            run_id = launch_message.locator("[data-run-id]").get_attribute(
                "data-run-id"
            )
            assert run_id
            _wait_for_callbacks_to_settle(page, pending)
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)

            after_launch_runs, after_launch_submissions = _durable_identities(database)
            assert after_launch_runs - baseline_runs == {run_id}
            assert len(after_launch_submissions - baseline_submissions) == 1
            assert marker.read_text(encoding="utf-8").splitlines() == [run_id]

            service = PersistenceService(database)
            try:
                run = service.runs.get(run_id)
                assert run is not None
                assert run.status == RunStatus.FAILED
                assert run.attempt_count == 1
                assert run.error_summary == "controlled Prefect fixture failure"
                assert service.results.list_parameter_results(run_id) == ()
                assert service.results.list_artifacts(run_id) == ()
                assert service.read_persisted_run_manifest(run_id) is None
            finally:
                service.close()

            action["name"] = "refresh the same failed Run test ticket"
            page.reload(wait_until="networkidle")
            expect(page.locator("#launch-message [data-run-id]")).to_have_attribute(
                "data-run-id",
                run_id,
            )
            expect(page.locator("#launch-message")).to_contain_text(
                "Run status: Failed"
            )
            expect(page.locator("#run-test-operator-context")).to_contain_text(
                "Review failure"
            )
            _wait_for_callbacks_to_settle(page, pending)

            action["name"] = "open the failed run by direct Results link"
            page.goto(
                f"{base_url}{BACKTEST_PATH}?run_id={run_id}",
                wait_until="networkidle",
            )
            detail = _selected_run_detail(page)
            expect(detail).to_contain_text(run_id)
            expect(detail.get_by_text("failed", exact=True).first).to_be_visible()
            expect(detail).to_contain_text("controlled Prefect fixture failure")
            expect(detail).to_contain_text("No artifact inventory is available")
            expect(detail).to_contain_text(
                "No persisted parameter result summary is available"
            )
            _wait_for_callbacks_to_settle(page, pending)
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)

            action["name"] = "refresh and reopen the failed run"
            page.reload(wait_until="networkidle")
            expect(_selected_run_detail(page)).to_contain_text(run_id)
            expect(_selected_run_detail(page)).to_contain_text(
                "controlled Prefect fixture failure"
            )
            _wait_for_callbacks_to_settle(page, pending)
            page.goto(f"{base_url}/research/run-test", wait_until="networkidle")
            expect(page.locator("#launch-message [data-run-id]")).to_have_attribute(
                "data-run-id",
                run_id,
            )
            expect(page.locator("#run-test-operator-context")).to_contain_text(
                "Review failure"
            )
            _wait_for_callbacks_to_settle(page, pending)

            assert _durable_identities(database) == (
                after_launch_runs,
                after_launch_submissions,
            )
            assert marker.read_text(encoding="utf-8").splitlines() == [run_id]
            _assert_runtime_clean(page, events, server_log)
            page.screenshot(
                path=tmp_path / "controlled-failure-run-test-reopen.png",
                full_page=True,
            )
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


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
                index=1,
            )
            retry_detail = _selected_run_detail(page)
            expect(retry_detail).to_contain_text(RETRY_RUN_ID)
            expect(retry_detail).to_contain_text("succeeded")
            expect(retry_detail).to_contain_text("Attempt")
            expect(retry_detail).to_contain_text("1")
            _open_details(page, "Operations and diagnostics")
            expect(retry_detail).to_contain_text("run retry scheduled")
            expect(retry_detail).to_contain_text("Run completed successfully.")

            action["name"] = "select timeout run"
            _select(
                page,
                "selected-run-selector",
                "Infrastructure Fixture · Fixture backtest · Succeeded",
                index=0,
            )
            timeout_detail = _selected_run_detail(page)
            expect(timeout_detail).to_contain_text(TIMEOUT_RUN_ID)
            expect(timeout_detail).to_contain_text("succeeded")
            expect(timeout_detail).not_to_contain_text("timed out")
            expect(timeout_detail).to_contain_text("Run completed successfully.")
            expect(timeout_detail).to_contain_text("deterministic_value")
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
