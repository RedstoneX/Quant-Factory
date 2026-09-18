"""Browser evidence for durable Results review integrity failures."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from backtesting.validation.evidence_decision_artifacts import (
    EVIDENCE_DECISION_LOGICAL_NAME,
)
from persistence import ArtifactType, PersistenceService
from persistence.database import transaction
from tests.browser.test_backtest_results_spym_stability import BACKTEST_PATH
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
    _attach_diagnostics,
    _select,
    _wait_for_callbacks_to_settle,
    _write_lifecycle_failure_artifacts,
    review_compare_server,
)


def _results_url(base_url: str, run_id: str) -> str:
    return f"{base_url}{BACKTEST_PATH}?{urlencode({'run_id': run_id})}"


def _review_snapshot(
    database: Path,
    artifact_root: Path,
    run_id: str,
) -> tuple[object, ...]:
    service = PersistenceService(database)
    try:
        current = service.reviews.get_current("run", run_id)
        current_state = (
            None
            if current is None
            else (
                current.target_type,
                current.target_id,
                current.state.value,
                current.note,
                current.operator,
                current.updated_at,
            )
        )
        history = tuple(
            tuple(sorted(event.items()))
            for event in service.reviews.history("run", run_id)
        )
        artifacts = tuple(service.list_run_artifacts(run_id))
        artifact_payloads = tuple(
            (
                artifact.location,
                (artifact_root / artifact.location).read_bytes(),
            )
            for artifact in artifacts
            if (artifact_root / artifact.location).is_file()
        )
        return (
            current_state,
            history,
            artifacts,
            artifact_payloads,
            service.read_persisted_run_manifest(run_id),
        )
    finally:
        service.close()


def _decision_artifact(database: Path, run_id: str):
    service = PersistenceService(database)
    try:
        return next(
            artifact
            for artifact in service.list_run_artifacts(run_id)
            if artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
            and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
        )
    finally:
        service.close()


def _open_selected_results(page, base_url: str, run_id: str, pending_requests) -> None:
    selected_url = _results_url(base_url, run_id)
    page.goto(selected_url, wait_until="networkidle")
    _wait_for_callbacks_to_settle(page, pending_requests)
    expect(page).to_have_url(selected_url)
    expect(page.locator("#selected-run-detail")).to_contain_text(
        run_id,
        timeout=10_000,
    )
    expect(page.locator("#save-review")).to_be_enabled(timeout=10_000)


def _save_review(page, *, label: str, note: str) -> None:
    _select(page, "review-status", label)
    page.locator("#review-note").fill(note)
    page.locator("#save-review").click()


def test_review_conflict_retains_identity_form_and_persisted_decision(
    review_compare_server,
    tmp_path: Path,
) -> None:
    base_url, server_log, run_id, _ = review_compare_server
    database = tmp_path / "state.sqlite3"
    artifact_root = tmp_path / "artifacts"
    events: list[dict[str, object]] = []
    action = {"name": "persist initial durable review"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        pending_requests = _attach_diagnostics(page, events, action)
        try:
            _open_selected_results(page, base_url, run_id, pending_requests)
            first_note = "Browser integrity proof: retain this durable decision."
            _save_review(page, label="Watchlist", note=first_note)
            expect(page.locator("#review-message")).to_contain_text(
                "Evidence decision artifact validated",
                timeout=10_000,
            )
            expect(page.locator("#review-history")).to_contain_text(first_note)
            _wait_for_callbacks_to_settle(page, pending_requests)
            before_conflict = _review_snapshot(database, artifact_root, run_id)

            action["name"] = "reject conflicting durable review"
            conflict_note = "Unsaved browser conflict must remain in this form."
            _save_review(page, label="Reject", note=conflict_note)
            expect(page.locator("#review-message")).to_contain_text(
                "conflicting evidence decision artifact",
                timeout=10_000,
            )
            expect(page.locator("#review-message")).to_contain_text(
                "No review change was saved"
            )
            expect(page.locator("#review-note")).to_have_value(conflict_note)
            expect(page.locator("#review-status")).to_contain_text("Reject")
            expect(page.locator("#review-history")).to_contain_text(first_note)
            expect(page.locator("#review-history")).not_to_contain_text(
                conflict_note
            )
            expect(page.locator("#selected-run-detail")).to_contain_text(run_id)
            expect(page.locator("#results-operator-context")).to_contain_text(
                "Watchlist"
            )
            expect(page).to_have_url(_results_url(base_url, run_id))
            _wait_for_callbacks_to_settle(page, pending_requests)

            assert _review_snapshot(database, artifact_root, run_id) == before_conflict
            assert pending_requests == set()
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()


@pytest.mark.parametrize("corruption", ["artifact", "history"])
def test_corrupt_review_state_is_visible_and_failed_save_does_not_mutate(
    review_compare_server,
    tmp_path: Path,
    corruption: str,
) -> None:
    base_url, server_log, run_id, _ = review_compare_server
    database = tmp_path / "state.sqlite3"
    artifact_root = tmp_path / "artifacts"
    events: list[dict[str, object]] = []
    action = {"name": f"prepare {corruption} review corruption"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        pending_requests = _attach_diagnostics(page, events, action)
        try:
            _open_selected_results(page, base_url, run_id, pending_requests)
            original_note = "Browser integrity proof before deliberate corruption."
            _save_review(page, label="Watchlist", note=original_note)
            expect(page.locator("#review-history")).to_contain_text(
                original_note,
                timeout=10_000,
            )
            _wait_for_callbacks_to_settle(page, pending_requests)

            if corruption == "artifact":
                decision = _decision_artifact(database, run_id)
                (artifact_root / decision.location).write_text(
                    '{"corrupt":true}',
                    encoding="utf-8",
                )
                visible_error = "artifact_size_mismatch"
                save_error = visible_error
            else:
                service = PersistenceService(database)
                try:
                    with transaction(service.connection):
                        service.connection.execute(
                            """
                            UPDATE review_audit_history
                            SET note=?
                            WHERE target_type='run' AND target_id=?
                            """,
                            ("deliberately corrupt audit note", run_id),
                        )
                finally:
                    service.close()
                visible_error = "does not match"
                save_error = "conflicting evidence decision artifact"
            corrupted_state = _review_snapshot(database, artifact_root, run_id)

            action["name"] = f"display {corruption} review failure"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending_requests)
            expect(page).to_have_url(_results_url(base_url, run_id))
            expect(page.locator("#selected-run-detail")).to_contain_text(run_id)
            expect(page.locator("#review-status")).to_contain_text("Unreviewed")
            expect(page.locator("#review-note")).to_have_value("")
            expect(page.locator("#review-history")).to_contain_text(
                visible_error,
                timeout=10_000,
            )
            expect(page.locator("#results-operator-context")).to_contain_text(
                "Unavailable"
            )

            action["name"] = f"reject save with {corruption} review failure"
            failed_note = f"Unsaved note after {corruption} corruption."
            _save_review(page, label="Reject", note=failed_note)
            expect(page.locator("#review-message")).to_contain_text(
                "No review change was saved",
                timeout=10_000,
            )
            expect(page.locator("#review-message")).to_contain_text(save_error)
            expect(page.locator("#review-note")).to_have_value(failed_note)
            expect(page.locator("#review-status")).to_contain_text("Reject")
            expect(page.locator("#review-history")).to_contain_text(visible_error)
            expect(page.locator("#selected-run-detail")).to_contain_text(run_id)
            expect(page.locator("#results-operator-context")).to_contain_text(
                "Unavailable"
            )
            expect(page).to_have_url(_results_url(base_url, run_id))
            _wait_for_callbacks_to_settle(page, pending_requests)

            assert _review_snapshot(database, artifact_root, run_id) == corrupted_state
            assert pending_requests == set()
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()
