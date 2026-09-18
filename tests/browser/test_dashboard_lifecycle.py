"""Real-browser mounted-route and durable operator workflow regressions."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from dashboard.routing import (
    NAVIGATION_ITEMS,
    NAVIGATION_LINKS,
    ROUTE_REGISTRY,
    navigation_item_id,
    navigation_link_id,
)
from orchestration import FixtureRunService
from persistence import (
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    ReviewState,
    canonical_json,
)
from persistence.database import transaction
from persistence.evidence_service import ValidationEvidenceArtifactService
from persistence.models import normalized_configuration_document
from tests.browser.test_backtest_results_spym_stability import (
    BACKTEST_PATH,
    REPOSITORY_ROOT,
    SPYM_OPTION_TEXT,
    _free_port,
    _prepare_initial_run,
    _visible_routes,
    _wait_for_server,
    _launcher,
    dashboard_server,
)
from tests.browser.dashboard_diagnostics import PendingCallbackRequests
from tests.test_review_context_artifacts import (
    REVIEW_PARAMETERS,
    _persist_review_prerequisites,
    _review_service,
    _source_lock_artifact,
)
from tests.test_dashboard import _reproduction_service


@pytest.fixture()
def reproduction_browser_server(tmp_path: Path):
    """Start a licensed-engine-free dashboard with reproducible persisted runs."""

    database, artifact_root, service, configuration_id = _reproduction_service(
        tmp_path
    )
    service.launch_fixture(
        configuration_id=configuration_id,
        run_id="browser_comparison_peer",
    )

    port = _free_port()
    server_log = tmp_path / "reproduction-browser-server.log"
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService
from tests.test_dashboard import _reproduction_launcher

database = Path(sys.argv[1])
artifact_root = Path(sys.argv[2])
port = int(sys.argv[3])
app = create_app(
    review_database=database,
    run_service=FixtureRunService(
        database=database,
        fixture_launcher=_reproduction_launcher(artifact_root),
    ),
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
        yield base_url, server_log, "source_reproduction_run", database
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture()
def mounted_workflow_server(tmp_path: Path):
    """Start the mounted shell with two generic, licensed-engine-free fixtures."""

    database = tmp_path / "state" / "mounted-workflow.sqlite3"
    initial_run_id = _prepare_initial_run(database)
    service = PersistenceService(database)
    try:
        service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="workflow_second_operator_choice",
                strategy_id="prefect_fixture_strategy",
                strategy_version="1.0.0",
                market_data={"kind": "none", "choice": "second"},
                parameters={"fixture": True, "choice": "second"},
                execution={"kind": "prefect_fixture"},
                ranking={
                    "columns": ("deterministic_value",),
                    "ascending": (False,),
                },
                screening={"kind": "none"},
            )
        )
    finally:
        service.close()

    port = _free_port()
    server_log = tmp_path / "mounted-workflow-server.log"
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app
from orchestration import FixtureRunService
from tests.browser.dashboard_diagnostics import install_callback_status_recorder
from tests.browser.test_backtest_results_spym_stability import _launcher

database = Path(sys.argv[1])
port = int(sys.argv[2])
app = create_app(
    review_database=database,
    run_service=FixtureRunService(database=database, fixture_launcher=_launcher),
)
install_callback_status_recorder(app.server)
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
        _wait_for_server(base_url)
        yield base_url, server_log, initial_run_id
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture()
def review_compare_server(tmp_path: Path, request):
    """Start a licensed-engine-free dashboard with valid durable-review context."""

    database = tmp_path / "state.sqlite3"
    artifact_root = tmp_path / "artifacts"
    service = _review_service(tmp_path)
    _persist_review_prerequisites(service, artifact_root)
    source = service.runs.get("wf-run")
    assert source is not None

    def persist_result_run(run_id: str, stage: RunStage) -> None:
        service.create_run(
            configuration_id=source.configuration_id,
            strategy_id=source.strategy_id,
            strategy_version=source.strategy_version,
            stage=stage,
            run_id=run_id,
            status=RunStatus.SUCCEEDED,
        )
        with transaction(service.connection):
            service.results.set_data_provenance(
                DataProvenanceRecord(
                    run_id=run_id,
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
                    run_id=run_id,
                    assumptions_json=canonical_json({"kind": "fixture"}),
                )
            )
            service.results.add_parameter_result(
                run_id=run_id,
                row_id=f"{run_id}-row",
                normalized_parameters=REVIEW_PARAMETERS,
                metrics={
                    "total_return": 0.1,
                    "max_drawdown": -0.03,
                    "number_of_trades": 5,
                },
                ranking_position=1,
                screening_status="passed",
            )
        service.persist_run_manifest(service.build_run_manifest(run_id))

    target_run_id = "browser_review_target"
    peer_run_id = "browser_unreviewed_peer"
    persist_result_run(target_run_id, RunStage.OOS)
    persist_result_run(peer_run_id, RunStage.FIXTURE)
    source_lock_artifact_id = _source_lock_artifact(
        service,
        artifact_root,
        run_id=target_run_id,
    )
    evidence = ValidationEvidenceArtifactService(service)
    evidence.persist_review_context(
        target_run_id=target_run_id,
        source_lock_run_id=target_run_id,
        source_lock_artifact_id=source_lock_artifact_id,
        walk_forward_run_id="wf-run",
        monte_carlo_run_id="mc-run",
        robustness_run_id="robust-run",
        protected_data_state="gated",
        artifact_root=artifact_root,
        created_at="2026-01-01T00:00:00+00:00",
    )
    if getattr(request, "param", False):
        gate = evidence.evaluate_persisted_review_context(
            target_run_id,
            artifact_root=artifact_root,
        )
        evidence.persist_evidence_decision(
            run_id=target_run_id,
            gate_result=gate,
            review_state=ReviewState.WATCHLIST,
            review_reason="Persisted browser comparison review.",
            reviewer="dashboard-operator",
            artifact_root=artifact_root,
            created_at="2026-01-02T00:00:00+00:00",
        )
    service.close()

    port = _free_port()
    server_log = tmp_path / "review-compare-server.log"
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
            [sys.executable, "-c", code, str(database), str(artifact_root), str(port)],
            cwd=REPOSITORY_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(base_url + BACKTEST_PATH)
        yield base_url, server_log, target_run_id, peer_run_id
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


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
    if path in dict(NAVIGATION_ITEMS):
        current = page.locator('[aria-current="page"]')
        expect(current).to_have_count(1)
        expect(current).to_have_attribute("id", navigation_item_id(path))
    else:
        expect(page.locator('[aria-current="page"]')).to_have_count(0)


def _attach_diagnostics(page, events, action):
    pending_requests = PendingCallbackRequests()

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
        lambda request: pending_requests.add(request)
        if "/_dash-update-component" in request.url
        else None,
    )
    page.on(
        "requestfinished",
        lambda request: pending_requests.discard(request)
        if "/_dash-update-component" in request.url
        else None,
    )
    page.on(
        "requestfailed",
        lambda request: (
            pending_requests.discard(request),
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


def _research_submission_snapshots(database: Path) -> dict[str, tuple[object, ...]]:
    service = PersistenceService(database)
    try:
        rows = service.connection.execute(
            """
            SELECT idempotency_key, run_id, configuration_id,
                   canonical_request_json, request_fingerprint, state,
                   prefect_flow_run_id, claimed_at, updated_at
            FROM research_run_submissions
            ORDER BY idempotency_key
            """
        ).fetchall()
        return {str(row[0]): tuple(row) for row in rows}
    finally:
        service.close()


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


def test_every_route_deep_link_refresh_and_navigation(mounted_workflow_server, tmp_path):
    base_url, server_log, _ = mounted_workflow_server
    events = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        try:
            for path, container in (
                *ROUTE_REGISTRY,
                ("/research/strategy-review", "route-not-found"),
                ("/unknown-route", "route-not-found"),
            ):
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


def test_setup_selection_survives_run_route_and_refresh(
    mounted_workflow_server,
    tmp_path,
):
    base_url, server_log, _ = mounted_workflow_server
    database = server_log.parent / "state" / "mounted-workflow.sqlite3"
    baseline_submissions = _research_submission_snapshots(database)
    events = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "launch first saved setup"}
        pending_requests = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/setup", wait_until="networkidle")
            first_identity = page.locator(
                "#configuration-preview .configuration-identity"
            ).inner_text()
            page.get_by_text("Review test", exact=True).click()
            _assert_route(
                page,
                base_url,
                "/research/run-test",
                "route-research-run-test",
            )
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page.locator("#launch-run")).to_be_enabled()
            page.locator("#launch-run").click()
            expect(page.locator("#launch-message")).to_contain_text(
                "Run status: Succeeded",
                timeout=60000,
            )
            _wait_for_callbacks_to_settle(page, pending_requests)
            first_submissions = _research_submission_snapshots(database)
            first_keys = set(first_submissions) - set(baseline_submissions)
            assert len(first_keys) == 1
            first_key = first_keys.pop()
            first_snapshot = first_submissions[first_key]

            action["name"] = "select second saved setup after first terminal launch"
            page.locator(
                f"#{navigation_link_id('/research/setup')}"
            ).click()
            _assert_route(page, base_url, "/research/setup", "route-research-setup")
            _select(page, "configuration-selector", "workflow_second_operator_choice")
            _wait_for_callbacks_to_settle(page, pending_requests)
            selected_identity = page.locator(
                "#configuration-preview .configuration-identity"
            ).inner_text()
            assert selected_identity != first_identity
            action["name"] = "continue to Run test"
            page.get_by_text("Review test", exact=True).click()
            _assert_route(
                page,
                base_url,
                "/research/run-test",
                "route-research-run-test",
            )
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(
                page.locator("#run-configuration-preview .configuration-identity")
            ).to_have_text(selected_identity)
            action["name"] = "refresh Run test"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(
                page.locator("#run-configuration-preview .configuration-identity")
            ).to_have_text(selected_identity)
            expect(page.locator("#launch-message")).not_to_contain_text(
                "Run ticket conflict"
            )
            expect(page.locator("#launch-run")).to_be_enabled()
            action["name"] = "launch second selected generic fixture"
            page.locator("#launch-run").click()
            expect(page.locator("#launch-message")).to_contain_text(
                "Run status: Succeeded",
                timeout=60000,
            )
            expect(page.locator("#run-test-operator-context")).to_contain_text(
                "Succeeded"
            )
            expect(page.locator("#run-test-operator-context")).to_contain_text(
                "Unavailable"
            )
            _wait_for_callbacks_to_settle(page, pending_requests)
            final_submissions = _research_submission_snapshots(database)
            second_keys = set(final_submissions) - set(first_submissions)
            assert len(second_keys) == 1
            second_key = second_keys.pop()
            assert second_key != first_key
            assert final_submissions[first_key] == first_snapshot
            assert final_submissions[second_key][1] != first_snapshot[1]
            assert final_submissions[second_key][2] != first_snapshot[2]
            page.go_back(wait_until="networkidle")
            _assert_route(page, base_url, "/research/setup", "route-research-setup")
            page.go_forward(wait_until="networkidle")
            _assert_route(
                page,
                base_url,
                "/research/run-test",
                "route-research-run-test",
            )
            page.screenshot(
                path=tmp_path / "setup-selection-run-test-refresh.png",
                full_page=True,
            )
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


def test_ideas_invalid_url_stays_local_and_requires_discard_confirmation(
    mounted_workflow_server,
    tmp_path,
):
    base_url, server_log, _ = mounted_workflow_server
    events = []
    external_requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "edit safe idea draft"}
        pending_requests = _attach_diagnostics(page, events, action)
        page.on(
            "request",
            lambda request: external_requests.append(request.url)
            if "example.invalid" in request.url
            else None,
        )
        try:
            page.goto(base_url + "/research/ideas", wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            page.locator("#idea-title").fill("Local-only idea")
            page.locator("#idea-source-url").fill(
                "https://user:secret@example.invalid/private"
            )
            expect(page.locator("#idea-draft-status")).to_contain_text(
                "Unsaved local changes"
            )
            page.locator("#save-idea-draft").click()
            expect(page.locator("#idea-draft-status")).to_contain_text(
                "Your text is unchanged"
            )
            expect(page.locator("#idea-source-url")).to_have_value(
                "https://user:secret@example.invalid/private"
            )
            assert external_requests == []

            page.locator("#idea-source-url").fill("https://example.invalid/source")
            page.locator("#save-idea-draft").click()
            expect(page.locator("#idea-draft-status")).to_contain_text(
                "Draft saved in this browser session at"
            )
            assert external_requests == []

            action["name"] = "confirm idea draft discard"
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("#discard-idea-draft").click()
            expect(page.locator("#idea-draft-status")).to_contain_text(
                "Draft discarded"
            )
            expect(page.locator("#idea-title")).to_have_value("")
            page.screenshot(path=tmp_path / "ideas-safe-draft.png", full_page=True)
            _wait_for_callbacks_to_settle(page, pending_requests)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


def test_run_history_grid_opens_older_run_and_survives_refresh(
    mounted_workflow_server,
    tmp_path,
):
    base_url, server_log, _ = mounted_workflow_server
    database = server_log.parent / "state" / "mounted-workflow.sqlite3"
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
            _wait_for_callbacks_to_settle(page, pending_requests)
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
            target_cell = page.locator("#run-history-grid").get_by_text("OLDROW")
            expect(target_cell).to_be_visible()
            target_cell.click()
            target_row = target_cell.locator("xpath=ancestor::div[@role='row']")
            expect(target_row).to_have_attribute("aria-selected", "true")
            expect(page.locator("#selected-run-detail")).to_contain_text(
                target_run_id,
                timeout=10000,
            )
            _wait_for_callbacks_to_settle(page, pending_requests)
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


def test_results_review_persists_in_browser(review_compare_server, tmp_path):
    base_url, server_log, target_run_id, _ = review_compare_server
    events = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "open Results review"}
        pending_requests = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + BACKTEST_PATH, wait_until="networkidle")
            _select(page, "selected-run-selector", "Out-of-sample evidence")
            expect(page.locator("#selected-run-detail")).to_contain_text(
                target_run_id
            )
            expect(page.locator("#save-review")).to_be_enabled(timeout=10000)
            _select(page, "review-status", "Watchlist")
            note = "Infrastructure browser acceptance: preserve this review across refresh."
            page.locator("#review-note").fill(note)
            page.locator("#save-review").click()
            expect(page.locator("#review-message")).to_contain_text(note)
            expect(page.locator("#results-operator-context")).to_contain_text(
                "Watchlist"
            )
            expect(page.locator("#review-history")).to_contain_text(note)
            _wait_for_callbacks_to_settle(page, pending_requests)
            page.reload(wait_until="networkidle")
            expect(page.locator("#selected-run-detail")).to_contain_text(
                target_run_id,
                timeout=10000,
            )
            expect(page.locator("#review-note")).to_have_value(note)
            expect(page.locator("#review-status")).to_contain_text("Watchlist")
            expect(page.locator("#results-operator-context")).to_contain_text(
                "Watchlist"
            )
            page.screenshot(path=tmp_path / "durable-review.png", full_page=True)
            _wait_for_callbacks_to_settle(page, pending_requests)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


@pytest.mark.parametrize("review_compare_server", [True], indirect=True)
def test_compare_renders_independent_quartets_in_browser(
    review_compare_server,
    tmp_path,
):
    base_url, server_log, target_run_id, peer_run_id = review_compare_server
    events = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "open Compare with two persisted runs"}
        pending_requests = _attach_diagnostics(page, events, action)
        try:
            page.goto(
                base_url + "/research/compare-backtests",
                wait_until="networkidle",
            )
            reviewed_context = page.locator(
                f'#comparison-operator-contexts [data-run-id="{target_run_id}"]'
            )
            peer_context = page.locator(
                f'#comparison-operator-contexts [data-run-id="{peer_run_id}"]'
            )
            expect(reviewed_context).to_contain_text("Watchlist", timeout=10000)
            expect(reviewed_context).not_to_contain_text("Unreviewed")
            expect(peer_context).to_contain_text("Unreviewed", timeout=10000)
            expect(peer_context).not_to_contain_text("Watchlist")
            for context in (reviewed_context, peer_context):
                expect(context).to_contain_text("Run status")
                expect(context).to_contain_text("Evidence outcome")
                expect(context).to_contain_text("Human decision")
                expect(context).to_contain_text("Next safe action")
            expect(
                page.locator("#comparison-operator-contexts .operator-context")
            ).to_have_count(2)
            _wait_for_callbacks_to_settle(page, pending_requests)
            page.screenshot(path=tmp_path / "independent-quartets.png", full_page=True)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


def test_results_owns_reproduction_without_mutating_compare_selection(
    reproduction_browser_server,
    tmp_path,
):
    base_url, server_log, source_run_id, database = reproduction_browser_server
    events = []

    def persisted_runs():
        persistence = PersistenceService(database)
        try:
            return tuple(persistence.runs.list())
        finally:
            persistence.close()

    def is_results_selector_refresh(response) -> bool:
        if "/_dash-update-component" not in response.url:
            return False
        try:
            body = json.loads(response.request.post_data or "{}")
        except json.JSONDecodeError:
            return False
        return body.get("output") == (
            "..selected-run-selector.options...selected-run-selector.value.."
        )

    before_runs = persisted_runs()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        action = {"name": "open Compare before Results reproduction"}
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(
                base_url + "/research/compare-backtests",
                wait_until="networkidle",
            )
            expect(page.locator(".compare-run-card")).to_have_count(2, timeout=10000)
            original_compare_ids = page.locator(".compare-run-card").evaluate_all(
                "cards => cards.map((card) => card.dataset.runId)"
            )

            action["name"] = "dispatch stale reproduction event while Results is inactive"
            page.locator("#reproduce-selected-run").evaluate(
                "button => { button.disabled = false; button.click(); }"
            )
            _wait_for_callbacks_to_settle(page, pending)
            assert [run.run_id for run in persisted_runs()] == [
                run.run_id for run in before_runs
            ]

            action["name"] = "reproduce source from active Results"
            page.goto(
                f"{base_url}{BACKTEST_PATH}?run_id={source_run_id}",
                wait_until="networkidle",
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                source_run_id,
                timeout=10000,
            )
            page.get_by_text(
                "Comparison and selected-backtest actions",
                exact=True,
            ).click()
            expect(page.locator("#reproduce-selected-run")).to_be_enabled()
            with page.expect_response(
                is_results_selector_refresh,
                timeout=60000,
            ) as selector_refresh:
                page.locator("#reproduce-selected-run").click()
            expect(page.locator("#reproduction-message")).to_contain_text(
                f"Reproduced {source_run_id} as",
                timeout=60000,
            )
            reproduced_id = page.locator(
                "#reproduction-message [data-run-id]"
            ).get_attribute("data-run-id")
            assert reproduced_id
            assert reproduced_id != source_run_id
            expect(page.locator("#selected-run-detail")).to_contain_text(
                reproduced_id,
                timeout=10000,
            )
            selector_payload = selector_refresh.value.json()
            assert selector_payload["response"]["selected-run-selector"][
                "value"
            ] == reproduced_id
            expect(page.locator("#selected-run-selector")).to_contain_text(
                "Reproduction Strategy · Fixture backtest · Succeeded",
            )
            _wait_for_callbacks_to_settle(page, pending)

            after_runs = persisted_runs()
            assert len(after_runs) == len(before_runs) + 1
            source = next(run for run in after_runs if run.run_id == source_run_id)
            reproduction = next(run for run in after_runs if run.run_id == reproduced_id)
            assert reproduction.configuration_id == source.configuration_id
            reproduction_environment = json.loads(reproduction.environment_json)
            assert reproduction_environment["reproduction"]["source_run_id"] == (
                source_run_id
            )

            action["name"] = "return to independently selected Compare runs"
            page.locator("#navigation-link-research-compare-backtests").click()
            _wait_for_callbacks_to_settle(page, pending)
            expect(page.locator(".compare-run-card")).to_have_count(2, timeout=10000)
            assert page.locator(".compare-run-card").evaluate_all(
                "cards => cards.map((card) => card.dataset.runId)"
            ) == original_compare_ids

            action["name"] = "reopen source Results deep link"
            page.goto(
                f"{base_url}{BACKTEST_PATH}?run_id={source_run_id}",
                wait_until="networkidle",
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                source_run_id,
                timeout=10000,
            )
            expect(page.locator("#selected-run-detail")).not_to_contain_text(
                reproduced_id,
            )
            _wait_for_callbacks_to_settle(page, pending)
            page.screenshot(
                path=tmp_path / "results-owned-reproduction.png",
                full_page=True,
            )
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
            page.goto(base_url + "/research/setup", wait_until="networkidle")
            _select(page, "configuration-selector", SPYM_OPTION_TEXT)
            selected_configuration = page.locator(
                "#configuration-preview .configuration-identity"
            ).inner_text()
            page.get_by_text("Review test", exact=True).click()
            _assert_route(
                page,
                base_url,
                "/research/run-test",
                "route-research-run-test",
            )
            expect(
                page.locator("#run-configuration-preview .configuration-identity")
            ).to_have_text(selected_configuration)
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(
                page.locator("#run-configuration-preview .configuration-identity")
            ).to_have_text(selected_configuration)
            expect(page.locator("#launch-run")).to_be_enabled()
            page.locator("#launch-run").click()
            expect(page.locator("#launch-message")).to_contain_text("Status: succeeded", timeout=60000)
            expect(page.locator("#run-test-operator-context")).to_contain_text(
                "Succeeded"
            )
            expect(page.locator("#run-test-operator-context")).to_contain_text(
                "Unavailable"
            )
            _wait_for_callbacks_to_settle(page, pending)
            page.screenshot(path=tmp_path / "launched-spym.png", full_page=True)

            action["name"] = "inspect a controlled failed run"
            page.get_by_text("View results", exact=True).click()
            _assert_route(
                page,
                base_url,
                "/research/backtest-results",
                "route-research-backtest-results",
            )
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
