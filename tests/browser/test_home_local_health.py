"""Portable browser proof for truthful local-only Home health."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from persistence import PersistenceService, StrategyLifecycle
from persistence.models import normalized_configuration_document
from tests.browser.test_backtest_results_spym_stability import (
    REPOSITORY_ROOT,
    _free_port,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
    _attach_diagnostics,
    _wait_for_callbacks_to_settle,
)


def _write_catalog(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "market-data"
    manifest_root = tmp_path / "manifests"
    manifest_root.mkdir()
    for dataset_id, status in (
        ("health-fixture", "validated"),
        ("health-fixture-quarantined", "quarantined"),
    ):
        content = f"portable local health fixture: {dataset_id}".encode()
        relative_directory = "quarantine" if status == "quarantined" else "equities"
        relative_path = f"{relative_directory}/{dataset_id}.parquet"
        target = data_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        (manifest_root / f"{dataset_id}.json").write_text(
            json.dumps(
                {
                    "dataset_id": dataset_id,
                    "status": status,
                    "asset_class": "equity",
                    "symbol": "SPY",
                    "provider": "Browser fixture",
                    "timeframe": "1d",
                    "format": "parquet",
                    "canonical_relative_path": relative_path,
                    "sha256": sha256(content).hexdigest(),
                    "size_bytes": len(content),
                    "row_count": 1,
                }
            ),
            encoding="utf-8",
        )
    config = tmp_path / "data_locations.toml"
    config.write_text(
        "\n".join(
            (
                "[data]",
                f'root = "{data_root}"',
                f'manifests = "{data_root / "manifests"}"',
                f'quarantine = "{data_root / "quarantine"}"',
                "[policy]",
                "allow_raw_data_in_repository = false",
                "verify_sha256_before_use = true",
            )
        ),
        encoding="utf-8",
    )
    return config, manifest_root


def _seed_active_configuration(database: Path) -> None:
    service = PersistenceService(database)
    try:
        service.register_strategy(
            strategy_id="home_health_fixture",
            strategy_version="1.0.0",
            display_name="Home Health Fixture",
            description="Portable browser fixture for read-only local health.",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
            active=True,
        )
        service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="home_health_browser_fixture",
                strategy_id="home_health_fixture",
                strategy_version="1.0.0",
                market_data={
                    "dataset_id": "health-fixture",
                    "provider": "Browser fixture",
                    "symbol": "SPY",
                    "timeframe": "1d",
                },
                parameters={"fixture": True},
                execution={"kind": "fixture"},
                ranking={"columns": ("value",), "ascending": (False,)},
                screening={"kind": "none"},
            )
        )
    finally:
        service.close()


@pytest.fixture()
def home_health_server(tmp_path: Path):
    database = tmp_path / "state" / "home-health.sqlite3"
    _seed_active_configuration(database)
    config, manifest_root = _write_catalog(tmp_path)
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    sentinel = artifact_root / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")

    port = _free_port()
    server_log = tmp_path / "home-health-server.log"
    code = """
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from dashboard.app import create_app
from dashboard.health import inspect_catalog
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService

database = Path(sys.argv[1])
artifact_root = Path(sys.argv[2])
config = Path(sys.argv[3])
manifest_root = Path(sys.argv[4])
port = int(sys.argv[5])
catalog_snapshot = inspect_catalog(config_path=config, manifest_dir=manifest_root)
app = create_app(
    review_database=database,
    run_service=FixtureRunService(database=database),
    run_detail_adapter=RunDetailDashboardAdapter(
        database=database,
        artifact_root=artifact_root,
    ),
    catalog_snapshot=catalog_snapshot,
    catalog_checked_at=datetime.now(timezone.utc),
    health_stale_after=timedelta(seconds=8),
    health_refresh_interval_ms=1000,
)
app.run(host="127.0.0.1", port=port, debug=False)
"""
    environment = dict(os.environ)
    environment["QUANT_FACTORY_DB_PATH"] = str(database)
    with server_log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                code,
                str(database),
                str(artifact_root),
                str(config),
                str(manifest_root),
                str(port),
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(base_url)
        yield base_url, server_log, database, sentinel
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _expect_health_card(page, area: str, status: str, *, timestamped: bool) -> None:
    card = page.locator(f"#home-health-{area}")
    expect(card.locator("small")).to_contain_text(status)
    if timestamped:
        assert "Last checked: Not checked" not in (card.get_attribute("title") or "")
    else:
        expect(card).to_have_attribute("title", re.compile(r"Last checked: Not checked$"))


def test_home_and_system_render_local_health_without_claiming_remote_checks(
    home_health_server,
) -> None:
    base_url, _server_log, database, sentinel = home_health_server
    sentinel_before = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns)
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        run_count_before = connection.execute(
            "SELECT count(*) FROM experiment_runs"
        ).fetchone()[0]
    finally:
        connection.close()
    events: list[dict[str, object]] = []
    action = {"name": "open Home local health"}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url, wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page.locator("#route-home h1")).to_have_text(
                "Dashboard · Research Atlas"
            )
            for area in ("database", "cache", "artifact"):
                _expect_health_card(page, area, "Available", timestamped=True)
            for area in ("worker", "provider", "credential"):
                _expect_health_card(page, area, "Not checked", timestamped=False)

            home_route = page.locator("#route-home").element_handle()
            system_route = page.locator("#route-system").element_handle()
            expect(
                page.locator("#home-health-database small")
            ).to_have_text("Stale — Available · stale", timeout=12_000)
            expect(page).to_have_url(base_url + "/")
            assert page.evaluate(
                "node => node === document.querySelector('#route-home')",
                home_route,
            )
            assert page.evaluate(
                "node => node === document.querySelector('#route-system')",
                system_route,
            )

            for viewport in (
                {"width": 1280, "height": 900},
                {"width": 1024, "height": 768},
                {"width": 390, "height": 844},
            ):
                page.set_viewport_size(viewport)
                expect(page.locator("#route-home h1")).to_have_text(
                    "Dashboard · Research Atlas"
                )
                assert (
                    page.evaluate("document.documentElement.scrollWidth")
                    <= viewport["width"] + 1
                )
                assert (
                    page.evaluate("document.body.scrollWidth")
                    <= viewport["width"] + 1
                )

            action["name"] = "open System Status local health"
            page.set_viewport_size({"width": 1280, "height": 900})
            system_link = page.locator("#navigation-link-system")
            system_link.focus()
            expect(system_link).to_be_focused()
            system_link.press("Enter")
            _wait_for_callbacks_to_settle(page, pending)
            expect(page).to_have_url(base_url + "/system")
            expect(page.locator("#route-system h1")).to_have_text(
                "Know whether research can operate"
            )
            system = page.locator("#route-system")
            for label in ("Research database", "Artifact storage", "Local data"):
                pulse = system.locator(".health-pulse", has_text=label)
                expect(pulse.locator("strong")).to_have_text(
                    "Stale — Available"
                )
                component = system.locator(".health-component-row", has_text=label)
                expect(component.locator("time")).not_to_have_text(
                    "Last checked: Not checked"
                )
            for label in ("Orchestrator", "Credentials"):
                pulse = system.locator(".health-pulse", has_text=label)
                expect(pulse.locator("strong")).to_have_text("Not checked")
                component = system.locator(".health-component-row", has_text=label)
                expect(component).to_contain_text("Last checked: Not checked")

            assert page.evaluate(
                "node => node === document.querySelector('#route-home')",
                home_route,
            )
            assert page.evaluate(
                "node => node === document.querySelector('#route-system')",
                system_route,
            )

            assert not pending
            _assert_no_browser_errors(events)
        finally:
            browser.close()

    assert (sentinel.read_bytes(), sentinel.stat().st_mtime_ns) == sentinel_before
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT count(*) FROM experiment_runs"
        ).fetchone()[0] == run_count_before
    finally:
        connection.close()
