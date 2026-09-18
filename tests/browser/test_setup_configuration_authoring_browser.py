"""Real-browser proof for fixture-only immutable Setup authoring."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

from dashboard.run_adapter import list_saved_configurations
from dashboard.setup_draft import (
    draft_fields,
    evaluate_setup_draft,
    load_persisted_base,
)
from persistence import PersistenceService, canonical_json
from persistence.database import transaction
from tests.browser.test_backtest_results_spym_stability import (
    REPOSITORY_ROOT,
    _free_port,
    _wait_for_server,
)
from tests.browser.test_dashboard_lifecycle import (
    _assert_no_browser_errors,
    _attach_diagnostics,
    _wait_for_callbacks_to_settle,
    _write_lifecycle_failure_artifacts,
)
from tests.test_setup_configuration_authoring import _seed_configuration


@pytest.fixture()
def setup_authoring_server(tmp_path: Path):
    database, original_id = _seed_configuration(tmp_path)
    port = _free_port()
    server_log = tmp_path / "setup-authoring-server.log"
    code = """
from pathlib import Path
import sys
from dashboard.app import create_app

database = Path(sys.argv[1])
port = int(sys.argv[2])
app = create_app(review_database=database)
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
        yield base_url, server_log, database, original_id
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize(
    "viewport",
    (
        {"width": 390, "height": 844},
        {"width": 1024, "height": 900},
    ),
    ids=("mobile", "tablet"),
)
def test_operator_saves_reuses_and_reloads_immutable_fixture_draft(
    setup_authoring_server,
    tmp_path: Path,
    viewport: dict[str, int],
) -> None:
    base_url, server_log, database, original_id = setup_authoring_server
    service = PersistenceService(database)
    try:
        original = service.configurations.get(original_id)
        assert original is not None
        original_json = original.canonical_config_json
    finally:
        service.close()

    events: list[dict[str, object]] = []
    action = {"name": "open fixture Setup draft"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport=viewport)
        page = context.new_page()
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/setup", wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            fee = page.locator(
                '[data-setup-section="execution"][data-setup-path="/fees"] input'
            )
            expect(fee).to_be_enabled()

            action["name"] = "edit a bounded fee assumption"
            fee.fill("0.001")
            fee.press("Tab")
            expect(page.locator("#setup-draft-status")).to_contain_text(
                "Unsaved changes are ready"
            )
            expect(page.locator("#save-configuration")).to_be_enabled()
            assert page.locator("#review-test-action").get_attribute("href") is None

            action["name"] = "save a new immutable setup"
            page.locator("#save-configuration").click()
            expect(page.locator("#setup-save-message")).to_contain_text(
                "Saved a new immutable setup"
            )
            saved_message = page.locator(
                "#setup-save-message [data-configuration-id]"
            )
            saved_id = saved_message.get_attribute("data-configuration-id")
            assert saved_id and saved_id != original_id
            expect(page.locator("#review-test-action")).to_have_attribute(
                "href", "/research/run-test"
            )

            action["name"] = "reload selected immutable setup"
            page.reload(wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)
            fee = page.locator(
                '[data-setup-section="execution"][data-setup-path="/fees"] input'
            )
            expect(fee).to_have_value("0.001")
            expect(page.locator("#review-test-action")).to_have_attribute(
                "href", "/research/run-test"
            )

            action["name"] = "reuse exact original setup without duplication"
            fee.fill("0")
            fee.press("Tab")
            expect(page.locator("#save-configuration")).to_be_enabled()
            page.locator("#save-configuration").click()
            expect(page.locator("#setup-save-message")).to_contain_text(
                "already saved; no duplicate was created"
            )
            reused_id = page.locator(
                "#setup-save-message [data-configuration-id]"
            ).get_attribute("data-configuration-id")
            assert reused_id == original_id
            fee = page.locator(
                '[data-setup-section="execution"][data-setup-path="/fees"] input'
            )
            expect(fee).to_have_value("0")
            expect(page.locator("#setup-draft-status")).to_contain_text(
                "no unsaved changes"
            )
            expect(page.locator("#review-test-action")).to_have_attribute(
                "href", "/research/run-test"
            )

            action["name"] = "reject an invalid cost before persistence"
            fee.fill("-0.01")
            fee.press("Tab")
            expect(page.locator("#setup-draft-status")).to_contain_text(
                "need correction"
            )
            expect(page.locator("#configuration-preview")).to_contain_text(
                "Fees must not be negative"
            )
            expect(page.locator("#save-configuration")).to_be_disabled()
            assert page.locator("#review-test-action").get_attribute("href") is None

            widths = page.evaluate(
                "() => ({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth})"
            )
            assert widths["scroll"] <= widths["client"]
            _wait_for_callbacks_to_settle(page, pending)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            context.close()
            browser.close()

    service = PersistenceService(database)
    try:
        assert len(service.configurations.list()) == 2
        original = service.configurations.get(original_id)
        assert original is not None
        assert original.canonical_config_json == original_json
        assert service.runs.list() == ()
    finally:
        service.close()


def test_identity_collision_is_visible_and_retains_page_local_draft(
    setup_authoring_server,
    tmp_path: Path,
) -> None:
    base_url, server_log, database, original_id = setup_authoring_server
    events: list[dict[str, object]] = []
    action = {"name": "open Setup before injecting a collision"}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        pending = _attach_diagnostics(page, events, action)
        try:
            page.goto(base_url + "/research/setup", wait_until="networkidle")
            _wait_for_callbacks_to_settle(page, pending)

            view = next(
                item
                for item in list_saved_configurations(database)
                if item.configuration_id == original_id
            )
            base = load_persisted_base(database, view)
            identities = []
            values = []
            for field in draft_fields(base):
                if not isinstance(field.value, (str, int, float, bool)):
                    continue
                identities.append(
                    {
                        "configuration": original_id,
                        "section": field.section,
                        "path": field.path,
                    }
                )
                values.append(0.002 if field.section == "execution" and field.path == "/fees" else field.value)
            evaluation = evaluate_setup_draft(
                base,
                field_ids=identities,
                field_values=values,
                catalog_snapshot=None,
            )
            target_id = evaluation.readiness.configuration_id
            conflicting = dict(evaluation.document)
            conflicting["experiment_id"] = "collision_evidence"
            service = PersistenceService(database)
            try:
                with transaction(service.connection):
                    service.connection.execute(
                        """
                        INSERT INTO experiment_configurations
                        (configuration_id, experiment_id, strategy_id, strategy_version,
                         canonical_config_json, config_hash, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            target_id,
                            conflicting["experiment_id"],
                            conflicting["strategy_id"],
                            conflicting["strategy_version"],
                            canonical_json(conflicting),
                            target_id,
                            "2026-09-18T00:00:00+00:00",
                        ),
                    )
                before = tuple(service.configurations.list())
            finally:
                service.close()

            action["name"] = "reject colliding immutable identity"
            fee = page.locator(
                '[data-setup-section="execution"][data-setup-path="/fees"] input'
            )
            fee.fill("0.002")
            fee.press("Tab")
            page.locator("#save-configuration").click()
            expect(page.locator("#setup-save-message")).to_contain_text(
                "identity collision"
            )
            expect(page.locator("#setup-save-message")).to_contain_text(
                "page-local draft is still available"
            )
            expect(fee).to_have_value("0.002")
            assert page.locator("#review-test-action").get_attribute("href") is None
            _wait_for_callbacks_to_settle(page, pending)
            _assert_no_browser_errors(events)
        except Exception:
            _write_lifecycle_failure_artifacts(page, tmp_path, events, server_log)
            raise
        finally:
            browser.close()

    service = PersistenceService(database)
    try:
        assert tuple(service.configurations.list()) == before
        assert service.runs.list() == ()
    finally:
        service.close()
