"""True process/new-browser proof for exact Results and Compare reopening."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlencode

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from persistence import (
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    ReviewState,
    RunStage,
    RunStatus,
    canonical_json,
)
from persistence.database import transaction
from persistence.evidence_service import ValidationEvidenceArtifactService
from tests.browser.test_backtest_results_spym_stability import (
    REPOSITORY_ROOT,
    _free_port,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import _wait_for_callbacks_to_settle
from tests.test_review_context_artifacts import (
    REVIEW_PARAMETERS,
    _persist_review_prerequisites,
    _review_service,
    _source_lock_artifact,
)


RESULTS_PATH = "/research/backtest-results"
COMPARE_PATH = "/research/compare-backtests"
TARGET_RUN_ID = "restart_review_target"
FAILED_RUN_ID = "restart_failed_peer"
REVIEW_NOTE = "Durable review survives a real dashboard process restart."
FAILURE_SUMMARY = "Controlled synthetic failure retained across restart."


def _seed_state(tmp_path: Path) -> tuple[Path, Path]:
    database = tmp_path / "state.sqlite3"
    artifact_root = tmp_path / "artifacts"
    service = _review_service(tmp_path)
    _persist_review_prerequisites(service, artifact_root)
    source = service.runs.get("wf-run")
    assert source is not None

    service.create_run(
        configuration_id=source.configuration_id,
        strategy_id=source.strategy_id,
        strategy_version=source.strategy_version,
        stage=RunStage.OOS,
        run_id=TARGET_RUN_ID,
        status=RunStatus.SUCCEEDED,
    )
    with transaction(service.connection):
        service.results.set_data_provenance(
            DataProvenanceRecord(
                run_id=TARGET_RUN_ID,
                provider="fixture",
                provider_implementation="fixture-provider",
                symbol="SPY",
                interval="1 day",
                timezone="UTC",
                requested_coverage="2020-01-01",
                actual_coverage="2020-01-01..2020-04-30",
                adjusted=True,
                row_count=120,
                cache_action="fixture",
                validation_summary_json=canonical_json({"status": "valid"}),
                manifest_reference="data/manifests/fixture.json",
                checksum="dataset-checksum",
            )
        )
        service.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=TARGET_RUN_ID,
                assumptions_json=canonical_json({"kind": "fixture"}),
            )
        )
        service.results.add_parameter_result(
            run_id=TARGET_RUN_ID,
            row_id=f"{TARGET_RUN_ID}-row",
            normalized_parameters=REVIEW_PARAMETERS,
            metrics={
                "total_return": 0.1,
                "max_drawdown": -0.03,
                "number_of_trades": 5,
            },
            ranking_position=1,
            screening_status="passed",
        )
    service.persist_run_manifest(service.build_run_manifest(TARGET_RUN_ID))
    source_lock_artifact_id = _source_lock_artifact(
        service,
        artifact_root,
        run_id=TARGET_RUN_ID,
    )
    evidence = ValidationEvidenceArtifactService(service)
    evidence.persist_review_context(
        target_run_id=TARGET_RUN_ID,
        source_lock_run_id=TARGET_RUN_ID,
        source_lock_artifact_id=source_lock_artifact_id,
        walk_forward_run_id="wf-run",
        monte_carlo_run_id="mc-run",
        robustness_run_id="robust-run",
        protected_data_state="gated",
        artifact_root=artifact_root,
        created_at="2026-01-01T00:00:00+00:00",
    )
    gate = evidence.evaluate_persisted_review_context(
        TARGET_RUN_ID,
        artifact_root=artifact_root,
    )
    evidence.persist_evidence_decision(
        run_id=TARGET_RUN_ID,
        gate_result=gate,
        review_state=ReviewState.WATCHLIST,
        review_reason=REVIEW_NOTE,
        reviewer="restart-proof-operator",
        artifact_root=artifact_root,
        created_at="2026-01-02T00:00:00+00:00",
    )

    service.create_run(
        configuration_id=source.configuration_id,
        strategy_id=source.strategy_id,
        strategy_version=source.strategy_version,
        stage=RunStage.FIXTURE,
        run_id=FAILED_RUN_ID,
    )
    service.transition_run(FAILED_RUN_ID, RunStatus.RUNNING)
    service.transition_run(
        FAILED_RUN_ID,
        RunStatus.FAILED,
        error_summary=FAILURE_SUMMARY,
    )
    service.close()
    return database, artifact_root


@contextmanager
def _dashboard_process(
    database: Path,
    artifact_root: Path,
    server_log: Path,
):
    port = _free_port()
    code = r'''
import json
from pathlib import Path
import sys
from dashboard.app import create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from flask import request
from orchestration import FixtureRunService

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
@app.server.after_request
def record_callback_status(response):
    if request.path == "/_dash-update-component":
        body = request.get_json(silent=True) or {}
        values = (*body.get("inputs", ()), *body.get("state", ()))
        def value(component_id, prop):
            return next(
                (
                    item.get("value")
                    for item in values
                    if item.get("id") == component_id
                    and item.get("property") == prop
                ),
                None,
            )
        print(
            "RESTART_CALLBACK_STATUS "
            + json.dumps(
                {
                    "output": body.get("output"),
                    "pathname": value("url", "pathname"),
                    "search": value("url", "search"),
                    "status": response.status_code,
                },
                sort_keys=True,
            ),
            flush=True,
        )
    return response
app.run(host="127.0.0.1", port=port, debug=False)
'''
    env = dict(os.environ)
    env["QUANT_FACTORY_DB_PATH"] = str(database)
    with server_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
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
        _wait_for_server(base_url + RESULTS_PATH)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _attach_diagnostics(page, events, action):
    pending: set[int] = set()

    def record(kind: str, **details) -> None:
        events.append(
            {
                "action": action["name"],
                "page_url": page.url,
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
        "response",
        lambda response: record(
            "http-error", status=response.status, url=response.url
        )
        if response.status >= 400
        else None,
    )
    page.on(
        "request",
        lambda request: pending.add(id(request))
        if "/_dash-update-component" in request.url
        else None,
    )
    page.on(
        "requestfinished",
        lambda request: pending.discard(id(request))
        if "/_dash-update-component" in request.url
        else None,
    )
    page.on(
        "requestfailed",
        lambda request: (
            pending.discard(id(request)),
            record(
                "requestfailed",
                url=request.url,
                failure=request.failure,
                request_body=request.post_data,
            ),
        )
        if "/_dash-update-component" in request.url
        else record(
            "requestfailed",
            url=request.url,
            failure=request.failure,
            request_body=request.post_data,
        ),
    )
    return pending


def _results_url(base_url: str, run_id: str) -> str:
    return f"{base_url}{RESULTS_PATH}?{urlencode({'run_id': run_id})}"


def _compare_query() -> str:
    return urlencode(
        (("run_id", TARGET_RUN_ID), ("run_id", FAILED_RUN_ID))
    )


def _assert_target_results(page) -> None:
    expect(page.locator("#selected-run-detail")).to_contain_text(
        TARGET_RUN_ID,
        timeout=10_000,
    )
    expect(page.locator("#review-status")).to_contain_text("Watchlist")
    expect(page.locator("#review-note")).to_have_value(REVIEW_NOTE)
    expect(page.locator("#review-history")).to_contain_text(REVIEW_NOTE)


def _assert_exact_compare(page) -> None:
    cards = page.locator(".compare-run-card")
    expect(cards).to_have_count(2, timeout=10_000)
    assert cards.evaluate_all(
        "items => items.map((item) => item.dataset.runId)"
    ) == [TARGET_RUN_ID, FAILED_RUN_ID]
    expect(cards.nth(0)).to_contain_text("Watchlist")
    expect(cards.nth(1)).to_contain_text("Failed")
    hrefs = page.locator(".compare-results-link").evaluate_all(
        "items => items.map((item) => item.getAttribute('href'))"
    )
    assert hrefs == [
        f"{RESULTS_PATH}?{urlencode({'run_id': TARGET_RUN_ID})}",
        f"{RESULTS_PATH}?{urlencode({'run_id': FAILED_RUN_ID})}",
    ]
    expect(page.locator("#comparison-exact-link")).to_have_attribute(
        "href",
        f"{COMPARE_PATH}?{_compare_query()}",
    )
    expect(page.locator("#comparison-query-message")).to_contain_text(
        "URL controls"
    )


def _assert_renderer_clean(page) -> None:
    assert page.locator("._dash-error-card").count() == 0
    assert page.locator("#_dash-error-container .dash-error-card").count() == 0


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): _file_hash(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _logical_counts(database: Path) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        tables = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        )
        return {
            table: int(
                connection.execute(
                    f'SELECT COUNT(*) FROM "{table.replace(chr(34), chr(34) * 2)}"'
                ).fetchone()[0]
            )
            for table in tables
        }
    finally:
        connection.close()


def _callback_statuses(server_logs: tuple[Path, ...]) -> list[dict[str, object]]:
    statuses: list[dict[str, object]] = []
    decoder = json.JSONDecoder()
    marker = "RESTART_CALLBACK_STATUS "
    for server_log in server_logs:
        text = server_log.read_text(encoding="utf-8", errors="replace")
        for fragment in text.split(marker)[1:]:
            status, _ = decoder.raw_decode(fragment.lstrip())
            statuses.append(status)
    return statuses


def _assert_diagnostics(
    events: list[dict[str, object]],
    server_logs: tuple[Path, ...],
) -> None:
    statuses = _callback_statuses(server_logs)
    assert any(status["status"] == 204 for status in statuses), statuses
    unclassified = [
        event
        for event in events
        if event["kind"] in {"pageerror", "console", "http-error"}
    ]
    for event in (item for item in events if item["kind"] == "requestfailed"):
        if (
            "/_dash-update-component" not in str(event["url"])
            or event["failure"] != "net::ERR_ABORTED"
            or not event["request_body"]
        ):
            unclassified.append(event)
            continue
        body = json.loads(str(event["request_body"]))
        values = (*body.get("inputs", ()), *body.get("state", ()))

        def value(component_id: str, prop: str):
            return next(
                (
                    item.get("value")
                    for item in values
                    if item.get("id") == component_id
                    and item.get("property") == prop
                ),
                None,
            )

        expected = {
            "output": body.get("output"),
            "pathname": value("url", "pathname"),
            "search": value("url", "search"),
            "status": 204,
        }
        if expected not in statuses:
            unclassified.append(event)
    assert unclassified == []


def test_results_and_exact_compare_reopen_after_process_and_browser_restart(
    tmp_path: Path,
) -> None:
    database, artifact_root = _seed_state(tmp_path)
    before_database = _file_hash(database)
    before_artifacts = _artifact_hashes(artifact_root)
    before_counts = _logical_counts(database)
    log_a = tmp_path / "dashboard-process-a.log"
    log_b = tmp_path / "dashboard-process-b.log"
    events: list[dict[str, object]] = []
    compare_url_path = f"{COMPARE_PATH}?{_compare_query()}"

    with sync_playwright() as playwright:
        with _dashboard_process(database, artifact_root, log_a) as base_url_a:
            browser_a = playwright.chromium.launch(headless=True)
            context_a = browser_a.new_context()
            page_a = context_a.new_page()
            action_a = {"name": "process A exact Results"}
            pending_a = _attach_diagnostics(page_a, events, action_a)
            page_a.goto(
                _results_url(base_url_a, TARGET_RUN_ID),
                wait_until="networkidle",
            )
            _wait_for_callbacks_to_settle(page_a, pending_a)
            _assert_target_results(page_a)

            action_a["name"] = "process A exact Compare"
            page_a.goto(base_url_a + compare_url_path, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page_a, pending_a)
            _assert_exact_compare(page_a)
            _assert_renderer_clean(page_a)
            assert pending_a == set()
            context_a.close()
            browser_a.close()

        with _dashboard_process(database, artifact_root, log_b) as base_url_b:
            browser_b = playwright.chromium.launch(headless=True)
            context_b = browser_b.new_context()
            page_b = context_b.new_page()
            action_b = {"name": "process B exact Results in new browser"}
            pending_b = _attach_diagnostics(page_b, events, action_b)
            page_b.goto(
                _results_url(base_url_b, TARGET_RUN_ID),
                wait_until="networkidle",
            )
            _wait_for_callbacks_to_settle(page_b, pending_b)
            _assert_target_results(page_b)

            action_b["name"] = "process B exact Compare in new browser"
            page_b.goto(base_url_b + compare_url_path, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page_b, pending_b)
            _assert_exact_compare(page_b)

            action_b["name"] = "open failed peer Results link"
            page_b.goto(
                _results_url(base_url_b, FAILED_RUN_ID),
                wait_until="networkidle",
            )
            _wait_for_callbacks_to_settle(page_b, pending_b)
            expect(page_b.locator("#selected-run-detail")).to_contain_text(
                FAILED_RUN_ID,
                timeout=10_000,
            )
            expect(page_b.locator("#selected-run-detail")).to_contain_text(
                FAILURE_SUMMARY
            )
            _assert_renderer_clean(page_b)
            assert pending_b == set()
            context_b.close()
            browser_b.close()

    assert _file_hash(database) == before_database
    assert _artifact_hashes(artifact_root) == before_artifacts
    assert _logical_counts(database) == before_counts
    _assert_diagnostics(events, (log_a, log_b))
