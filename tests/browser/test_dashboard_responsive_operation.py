"""Responsive browser proof for complete Milestone 23 operator actions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Locator, Page, expect, sync_playwright

from persistence import PersistenceService
from tests.browser.test_backtest_results_spym_stability import BACKTEST_PATH
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
    _attach_diagnostics,
    _select,
    _wait_for_callbacks_to_settle,
    _write_lifecycle_failure_artifacts,
    mounted_workflow_server,
    reproduction_browser_server,
    review_compare_server,
)
from tests.browser.test_dashboard_responsive_acceptance import (
    _assert_document_contained,
    _assert_visible_surfaces_contained,
)


RESPONSIVE_OPERATIONS = (
    ("desktop", {"width": 1440, "height": 1000}, 1),
    ("tablet", {"width": 1024, "height": 900}, 2),
    ("mobile", {"width": 390, "height": 844}, 4),
)


def _assert_action_contained(page: Page, selector: str) -> None:
    action = page.locator(selector)
    expect(action).to_be_visible()
    box = action.bounding_box()
    assert box is not None
    assert box["x"] >= -1
    assert box["x"] + box["width"] <= page.viewport_size["width"] + 1


def _assert_runtime_clean(
    page: Page,
    events: list[dict[str, Any]],
    server_log: Path,
) -> None:
    _assert_no_browser_errors(events)
    request_failures = [
        event for event in events if event["kind"] == "requestfailed"
    ]
    assert all(
        event["failure"] == "net::ERR_ABORTED"
        and "/_dash-update-component" in event["url"]
        for event in request_failures
    ), request_failures
    callback_204s = re.findall(
        r"POST /_dash-update-component HTTP/1\.1.* 204 -",
        server_log.read_text(encoding="utf-8", errors="replace"),
    )
    assert len(callback_204s) == len(request_failures), {
        "request_failures": request_failures,
        "callback_204_count": len(callback_204s),
    }
    assert page.locator("._dash-error-card").count() == 0
    assert page.locator("#_dash-error-container .dash-error-card").count() == 0


def _assert_quartet_rows(
    page: Page,
    selector: str | Locator,
    expected_rows: int,
) -> None:
    context = page.locator(selector) if isinstance(selector, str) else selector
    items = context.locator(".operator-context-item")
    expect(items).to_have_count(4)
    tops = items.evaluate_all(
        "elements => elements.map(element => "
        "Math.round(element.getBoundingClientRect().top))"
    )
    assert len(set(tops)) == expected_rows, {
        "selector": str(selector),
        "expected_rows": expected_rows,
        "tops": tops,
    }


def _persisted_run_ids(database: Path) -> tuple[str, ...]:
    service = PersistenceService(database)
    try:
        return tuple(run.run_id for run in service.runs.list())
    finally:
        service.close()


def _is_results_selector_refresh(response) -> bool:
    if "/_dash-update-component" not in response.url:
        return False
    try:
        body = json.loads(response.request.post_data or "{}")
    except json.JSONDecodeError:
        return False
    return body.get("output") == (
        "..selected-run-selector.options...selected-run-selector.value.."
    )


@pytest.mark.parametrize(
    ("viewport_name", "viewport", "quartet_rows"),
    RESPONSIVE_OPERATIONS,
    ids=("desktop", "tablet", "mobile"),
)
def test_launch_action_preserves_selected_setup_at_each_viewport(
    mounted_workflow_server,
    tmp_path: Path,
    viewport_name: str,
    viewport: dict[str, int],
    quartet_rows: int,
) -> None:
    base_url, server_log, _ = mounted_workflow_server
    database = server_log.parent / "state" / "mounted-workflow.sqlite3"
    before_run_ids = _persisted_run_ids(database)
    events: list[dict[str, Any]] = []
    action = {"name": f"{viewport_name} select saved setup"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/setup", wait_until="networkidle")
            _select(
                page,
                "configuration-selector",
                "workflow_second_operator_choice",
            )
            _wait_for_callbacks_to_settle(page, pending)
            selected_identity = page.locator(
                "#configuration-preview .configuration-identity"
            ).inner_text()
            _assert_action_contained(page, "#review-test-action")

            action["name"] = f"{viewport_name} review selected setup"
            page.locator("#review-test-action").click()
            expect(page).to_have_url(base_url + "/research/run-test")
            expect(
                page.locator(
                    "#run-configuration-preview .configuration-identity"
                )
            ).to_have_text(selected_identity)
            _assert_action_contained(page, "#launch-run")

            action["name"] = f"{viewport_name} launch exactly once"
            page.locator("#launch-run").click()
            expect(page.locator("#launch-message")).to_contain_text(
                "Submission: Acknowledged",
                timeout=60_000,
            )
            expect(page.locator("#launch-message")).to_contain_text(
                "Run status: Succeeded",
                timeout=60_000,
            )
            launched_id = page.locator(
                "#launch-message [data-run-id]"
            ).get_attribute("data-run-id")
            assert launched_id
            _wait_for_callbacks_to_settle(page, pending)
            _assert_quartet_rows(
                page,
                "#run-test-operator-context",
                quartet_rows,
            )
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)
            after_launch_ids = _persisted_run_ids(database)
            assert len(after_launch_ids) == len(before_run_ids) + 1

            action["name"] = f"{viewport_name} refresh after launch"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(
                page.locator(
                    "#run-configuration-preview .configuration-identity"
                )
            ).to_have_text(selected_identity)
            expect(page.locator("#launch-message [data-run-id]")).to_have_attribute(
                "data-run-id",
                launched_id,
            )
            assert _persisted_run_ids(database) == after_launch_ids
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)
            _assert_runtime_clean(page, events, server_log)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("viewport_name", "viewport", "quartet_rows"),
    RESPONSIVE_OPERATIONS,
    ids=("desktop", "tablet", "mobile"),
)
def test_inspect_review_and_compare_actions_work_at_each_viewport(
    review_compare_server,
    tmp_path: Path,
    viewport_name: str,
    viewport: dict[str, int],
    quartet_rows: int,
) -> None:
    base_url, server_log, target_run_id, peer_run_id = review_compare_server
    events: list[dict[str, Any]] = []
    action = {"name": f"{viewport_name} inspect persisted Results"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(
                f"{base_url}{BACKTEST_PATH}?run_id={target_run_id}",
                wait_until="networkidle",
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                target_run_id,
                timeout=10_000,
            )
            expect(page.locator("#selected-run-selector")).to_contain_text(
                "Out-of-sample evidence"
            )
            _assert_quartet_rows(page, "#results-operator-context", quartet_rows)
            quartet_top = page.locator("#results-operator-context").bounding_box()
            detail_top = page.locator("#selected-run-detail").bounding_box()
            assert quartet_top is not None and detail_top is not None
            assert quartet_top["y"] < detail_top["y"]

            action["name"] = f"{viewport_name} save durable review"
            expect(page.locator("#save-review")).to_be_enabled(timeout=10_000)
            _select(page, "review-status", "Watchlist")
            note = f"{viewport_name} responsive operation review"
            page.locator("#review-note").fill(note)
            _assert_action_contained(page, "#save-review")
            page.locator("#save-review").click()
            expect(page.locator("#review-message")).to_contain_text(note)
            expect(page.locator("#results-operator-context")).to_contain_text(
                "Watchlist"
            )
            _wait_for_callbacks_to_settle(page, pending)
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)

            action["name"] = f"{viewport_name} compare persisted runs"
            page.locator(
                "#route-research-backtest-results a.page-action",
                has_text="Compare",
            ).click()
            expect(page).to_have_url(base_url + "/research/compare-backtests")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page.locator(".compare-run-card")).to_have_count(2, timeout=10_000)
            compare_ids = page.locator(".compare-run-card").evaluate_all(
                "cards => cards.map(card => card.dataset.runId)"
            )
            assert set(compare_ids) == {target_run_id, peer_run_id}
            _assert_action_contained(page, "#compare-selected-runs")
            page.locator("#compare-selected-runs").click()
            expect(page.locator("#run-comparison-output")).to_contain_text(
                target_run_id,
                timeout=10_000,
            )
            expect(page.locator("#run-comparison-output")).to_contain_text(
                peer_run_id
            )
            reviewed_context = page.locator(
                f'#comparison-operator-contexts [data-run-id="{target_run_id}"]'
            )
            peer_context = page.locator(
                f'#comparison-operator-contexts [data-run-id="{peer_run_id}"]'
            )
            expect(reviewed_context).to_contain_text("Watchlist")
            expect(reviewed_context).not_to_contain_text("Unreviewed")
            expect(peer_context).to_contain_text("Unreviewed")
            expect(peer_context).not_to_contain_text("Watchlist")
            for context in (reviewed_context, peer_context):
                expect(context).to_contain_text("Run status")
                expect(context).to_contain_text("Evidence outcome")
                expect(context).to_contain_text("Human decision")
                expect(context).to_contain_text("Next safe action")
                _assert_quartet_rows(page, context, quartet_rows)
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)
            _assert_runtime_clean(page, events, server_log)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("viewport_name", "viewport", "quartet_rows"),
    RESPONSIVE_OPERATIONS,
    ids=("desktop", "tablet", "mobile"),
)
def test_reproduce_action_preserves_new_identity_at_each_viewport(
    reproduction_browser_server,
    tmp_path: Path,
    viewport_name: str,
    viewport: dict[str, int],
    quartet_rows: int,
) -> None:
    base_url, server_log, source_run_id, database = reproduction_browser_server
    before_run_ids = _persisted_run_ids(database)
    events: list[dict[str, Any]] = []
    action = {"name": f"{viewport_name} open reproducible Results"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(
                f"{base_url}{BACKTEST_PATH}?run_id={source_run_id}",
                wait_until="networkidle",
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                source_run_id,
                timeout=10_000,
            )
            _assert_quartet_rows(page, "#results-operator-context", quartet_rows)
            page.get_by_text(
                "Comparison and selected-backtest actions",
                exact=True,
            ).click()
            _assert_action_contained(page, "#reproduce-selected-run")
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)
            expect(page.locator("#reproduce-selected-run")).to_be_enabled()

            action["name"] = f"{viewport_name} reproduce persisted run"
            with page.expect_response(
                _is_results_selector_refresh,
                timeout=60_000,
            ):
                page.locator("#reproduce-selected-run").click()
            expect(page.locator("#reproduction-message")).to_contain_text(
                "Submission: Acknowledged",
                timeout=60_000,
            )
            expect(page.locator("#reproduction-message")).to_contain_text(
                "Run status: Succeeded",
                timeout=60_000,
            )
            reproduced_id = page.locator(
                "#reproduction-message [data-run-id]"
            ).get_attribute("data-run-id")
            assert reproduced_id and reproduced_id != source_run_id
            expect(page.locator("#selected-run-detail")).to_contain_text(
                reproduced_id,
                timeout=10_000,
            )
            _wait_for_callbacks_to_settle(page, pending)
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)
            after_run_ids = _persisted_run_ids(database)
            assert len(after_run_ids) == len(before_run_ids) + 1

            action["name"] = f"{viewport_name} reopen reproduction source"
            page.goto(
                f"{base_url}{BACKTEST_PATH}?run_id={source_run_id}",
                wait_until="networkidle",
            )
            expect(page).to_have_url(
                f"{base_url}{BACKTEST_PATH}?run_id={source_run_id}"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                source_run_id,
                timeout=10_000,
            )
            expect(
                page.locator("#reproduction-message [data-run-id]")
            ).to_have_attribute("data-run-id", reproduced_id)

            action["name"] = f"{viewport_name} refresh reproduction source"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page).to_have_url(
                f"{base_url}{BACKTEST_PATH}?run_id={source_run_id}"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                source_run_id,
                timeout=10_000,
            )
            expect(
                page.locator("#reproduction-message [data-run-id]")
            ).to_have_attribute("data-run-id", reproduced_id)
            assert _persisted_run_ids(database) == after_run_ids

            action["name"] = f"{viewport_name} open reproduced Results identity"
            page.goto(
                f"{base_url}{BACKTEST_PATH}?run_id={reproduced_id}",
                wait_until="networkidle",
            )
            expect(page).to_have_url(
                f"{base_url}{BACKTEST_PATH}?run_id={reproduced_id}"
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(
                reproduced_id,
                timeout=10_000,
            )
            _assert_document_contained(page)
            _assert_visible_surfaces_contained(page)
            _assert_runtime_clean(page, events, server_log)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()
