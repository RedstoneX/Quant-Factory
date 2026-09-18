"""Browser checks for truthful health, catalog, and run-integrity states."""

from __future__ import annotations

import sqlite3
from pathlib import Path
import re

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from dashboard.routing import navigation_link_id
from tests.browser.test_backtest_results_spym_stability import (
    SPYM_OPTION_TEXT,
    TARGET_RUN_ID,
    dashboard_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _attach_diagnostics,
    _select,
    _wait_for_callbacks_to_settle,
)


def _open(page, base_url: str, path: str) -> None:
    page.goto(base_url + path, wait_until="networkidle")


def _artifact_target(server_log: Path, artifact_type: str) -> tuple[Path, str]:
    database = server_log.parent / "state" / "browser-fixture.sqlite3"
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT path, logical_name FROM artifact_references "
            "WHERE run_id=? AND artifact_type=? ORDER BY artifact_id LIMIT 1",
            (TARGET_RUN_ID, artifact_type),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    path, logical_name = row
    return server_log.parent / path, logical_name


def _open_spym_detail(page, base_url: str, pending: set[int]) -> None:
    _open(page, base_url, "/research/backtest-results")
    _select(page, "selected-run-selector", SPYM_OPTION_TEXT)
    _wait_for_callbacks_to_settle(page, pending)
    page.get_by_text("Technical Details", exact=True).click()
    page.get_by_text("Artifacts and validation", exact=True).click()


def _run_count(server_log: Path) -> int:
    database = server_log.parent / "state" / "browser-fixture.sqlite3"
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return connection.execute("SELECT count(*) FROM experiment_runs").fetchone()[0]
    finally:
        connection.close()


def test_market_data_and_system_health_are_truthful_in_browser(dashboard_server) -> None:
    base_url, _, _ = dashboard_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            _open(page, base_url, "/research/market-data")
            expect(page.locator("#route-research-market-data h1")).to_have_text("Market Data")
            expect(page.get_by_text("17", exact=True).first).to_be_visible()
            expect(page.get_by_text("Quarantined — not approved", exact=True).first).to_be_visible()
            expect(page.get_by_text("Provider connectivity, credential availability, and data freshness were not checked on this page.", exact=True)).to_be_visible()

            page.locator(f"#{navigation_link_id('/system')}").click()
            expect(page.locator("#route-system h1")).to_have_text("System Status")
            expect(page.get_by_text("Credentials", exact=True)).to_be_visible()
            expect(page.get_by_text("Not checked", exact=True).last).to_be_visible()
        finally:
            browser.close()


def test_missing_spym_artifact_is_visible_and_reproduction_is_blocked(dashboard_server) -> None:
    base_url, server_log, _ = dashboard_server
    target, logical_name = _artifact_target(server_log, "equity_curve")
    target.unlink()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            pending = _attach_diagnostics(page, [], {"name": "missing artifact"})
            _open_spym_detail(page, base_url, pending)
            card = page.locator(".artifact-card", has_text=logical_name)
            expect(card).to_have_class(re.compile(r"artifact-card-warning"))
            expect(card).to_contain_text("missing")
            before = _run_count(server_log)
            page.get_by_text("Comparison and selected-backtest actions", exact=True).click()
            page.locator("#reproduce-selected-run").click()
            expect(page.locator("#reproduction-message")).to_contain_text("Run reproduction failed")
            assert _run_count(server_log) == before
        finally:
            browser.close()


def test_corrupt_spym_artifact_is_visible_as_invalid(dashboard_server) -> None:
    base_url, server_log, _ = dashboard_server
    target, logical_name = _artifact_target(server_log, "equity_curve")
    target.write_bytes(b"corrupt artifact")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            pending = _attach_diagnostics(page, [], {"name": "corrupt artifact"})
            _open_spym_detail(page, base_url, pending)
            card = page.locator(".artifact-card", has_text=logical_name)
            expect(card).to_have_class(re.compile(r"artifact-card-error"))
            expect(card).to_contain_text("corrupt")
            expect(card.locator(".artifact-status")).to_have_text("corrupt")
        finally:
            browser.close()


def test_invalid_spym_lineage_is_visible_and_not_reproducible(dashboard_server) -> None:
    base_url, server_log, _ = dashboard_server
    database = server_log.parent / "state" / "browser-fixture.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE run_manifests SET manifest_json=? WHERE run_id=?",
            ("not valid json", TARGET_RUN_ID),
        )
        connection.commit()
    finally:
        connection.close()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            pending = _attach_diagnostics(page, [], {"name": "invalid lineage"})
            _open_spym_detail(page, base_url, pending)
            expect(page.locator(".run-detail-warning")).to_contain_text("persisted run manifest is invalid")
            expect(page.locator("#selected-run-detail .artifact-card-error .artifact-status").first).to_have_text("invalid")
            before = _run_count(server_log)
            page.get_by_text("Comparison and selected-backtest actions", exact=True).click()
            page.locator("#reproduce-selected-run").click()
            expect(page.locator("#reproduction-message")).to_contain_text("Run reproduction failed")
            assert _run_count(server_log) == before
        finally:
            browser.close()
