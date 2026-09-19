"""Milestone 20E dashboard acceptance coverage."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import threading

import pandas as pd
import pytest
from dash import no_update

from dashboard.app import DashboardContext, create_app
from dashboard.application import _run_launch_summary
from dashboard.run_adapter import list_saved_configurations
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService
from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    EventSeverity,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunEventType,
    RunStage,
    RunStatus,
    canonical_json,
)
from persistence.repositories import utc_now
from prefect_spike.fixture_flow import (
    ControlledFixtureCancellation,
    PrefectFixtureResult,
    PrefectRunReference,
    _validated_claim_boundary,
    _persist_fixture_result,
    acknowledge_fixture_cancellation,
    deterministic_fixture_body,
)
from tests.test_dashboard import _audit, _callback_function, _data, _ranked_row
from tests.test_run_service import _configuration
from tests.test_run_stale_recovery import _create_run


def _runtime_lineage_document(label: str = "acceptance") -> dict[str, object]:
    contract = {
        "git": {
            "commit_sha": f"{label}-commit",
            "commit_available": True,
            "dirty_state": "clean",
            "dirty_available": True,
            "dirty_entry_count": 0,
            "dirty_fingerprint": f"{label}-dirty-fingerprint",
        },
        "python": {
            "implementation": "CPython",
            "version": "3.12.0",
            "cache_tag": "cpython-312",
        },
        "vectorbtpro": {"version": None, "available": False},
        "packages": {
            "fingerprint": f"{label}-package-fingerprint",
            "fingerprint_algorithm": (
                "sha256:canonical-json:normalized-package-name-version-pairs:v1"
            ),
            "count": 2,
        },
        "platform": {"system": "Linux", "machine": "x86_64"},
    }
    from persistence.service import _identity

    return {"runtime_identity": _identity(contract), **contract}


def _context() -> DashboardContext:
    data = _data()
    return DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))


def _launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def _failure_launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    kwargs["fail_after_run_start"] = True
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def _seed_dashboard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fixture_launcher=_launcher,
) -> tuple[Path, str, FixtureRunService, RunDetailDashboardAdapter]:
    database, configuration_id = _configuration(tmp_path)
    monkeypatch.setattr(
        "orchestration.run_service.capture_runtime_lineage_document",
        lambda: _runtime_lineage_document("launch"),
    )
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda selected_database=None: list_saved_configurations(database),
    )
    service = FixtureRunService(database=database, fixture_launcher=fixture_launcher)
    adapter = RunDetailDashboardAdapter(
        database=database,
        artifact_root=tmp_path / "artifact-root",
    )
    return database, configuration_id, service, adapter


def _app(service: FixtureRunService, adapter: RunDetailDashboardAdapter, tmp_path: Path):
    return create_app(
        _context(),
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=adapter,
    )


def _add_lineage_inputs(database: Path, run_id: str) -> None:
    service = PersistenceService(database)
    try:
        service.results.set_data_provenance(
            DataProvenanceRecord(
                run_id=run_id,
                provider="deterministic_fixture",
                provider_implementation="prefect_fixture",
                symbol="SPY",
                interval="1 day",
                timezone="America/New_York",
                requested_coverage="fixture",
                actual_coverage="fixture",
                adjusted=True,
                row_count=1,
                cache_action="fixture",
                validation_summary_json=canonical_json(
                    {
                        "duplicate_timestamp_count": 0,
                        "missing_open_count": 0,
                        "missing_high_count": 0,
                        "missing_low_count": 0,
                        "missing_close_count": 0,
                        "missing_volume_count": 0,
                        "expected_session_gap_count": 0,
                        "unexpected_session_gaps": [],
                    }
                ),
                manifest_reference="data/manifests/deterministic_fixture.json",
                checksum="fixture-dataset-checksum",
            )
        )
        run = service.runs.get(run_id)
        assert run is not None
        configuration = service.configurations.get(run.configuration_id)
        assert configuration is not None
        document = json.loads(configuration.canonical_config_json)
        service.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=run_id,
                assumptions_json=canonical_json(document["execution"]),
            )
        )
        service.connection.commit()
    finally:
        service.close()


def _register_artifact(
    database: Path,
    root: Path,
    run_id: str,
    *,
    artifact_type: ArtifactType,
    name: str,
    content: bytes,
    write_content: bytes | None = None,
) -> None:
    location = f"artifacts/{run_id}/{name}.json"
    target = root / location
    if write_content is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(write_content)
    service = PersistenceService(database)
    try:
        service.register_artifact(
            run_id=run_id,
            artifact_type=artifact_type,
            logical_name=name,
            media_type="application/json",
            format="json",
            location=location,
            content=BytesIO(content),
        )
    finally:
        service.close()


def _persist_manifest(database: Path, run_id: str) -> None:
    service = PersistenceService(database)
    try:
        manifest = service.build_run_manifest(
            run_id,
            created_at="2026-07-13T00:00:00Z",
        )
        service.persist_run_manifest(manifest)
    finally:
        service.close()


def _prepare_success_run_artifacts(database: Path, root: Path, run_id: str) -> None:
    _add_lineage_inputs(database, run_id)
    _register_artifact(
        database,
        root,
        run_id,
        artifact_type=ArtifactType.RUN_SUMMARY,
        name="run-summary",
        content=b'{"status":"succeeded"}',
        write_content=b'{"status":"succeeded"}',
    )
    _register_artifact(
        database,
        root,
        run_id,
        artifact_type=ArtifactType.METRICS,
        name="metrics",
        content=b'{"deterministic_value":1729}',
        write_content=b'{"deterministic_value":1729}',
    )
    _persist_manifest(database, run_id)


def _render_selected(app, run_id: str) -> str:
    inspect = _callback_function(app, "selected-run-detail")
    return str(
        inspect(run_id, 1, 0, 0, 0, 0, "/research/backtest-results")
    )


def test_dashboard_success_workflow_and_restart_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(tmp_path, monkeypatch)
    app = _app(service, adapter, tmp_path)

    launch = _callback_function(app, "launch-message")
    (
        launch_content,
        launch_class,
        launch_context,
        launch_context_class,
    ) = launch(1, configuration_id)
    run_id = service.recent_runs(limit=1)[0].run_id
    _prepare_success_run_artifacts(database, tmp_path / "artifact-root", run_id)

    assert launch_class == "save-message"
    assert run_id in str(launch_content)
    assert "succeeded" in str(launch_content)
    assert "prefect-" in str(launch_content)
    assert "Attempt count: 1" in str(launch_content)
    assert launch_context_class == "operator-context"
    rendered_launch_context = str(launch_context)
    assert "Run status" in rendered_launch_context
    assert "Succeeded" in rendered_launch_context
    assert "Evidence outcome" in rendered_launch_context
    assert "Human decision" in rendered_launch_context
    assert rendered_launch_context.count("Unavailable") == 2
    assert "Next safe action" in rendered_launch_context
    assert "Inspect evidence" in rendered_launch_context

    refresh_monitor = _callback_function(app, "recent-runs-monitor")
    runs_panel, events_panel = refresh_monitor(1, 1, 0, 0, 0, 0)
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "launch-run",
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    options, selected = refresh_selectors(1, 1, 0, 0, None, None, [])

    assert selected == run_id
    assert options[0]["value"] == run_id
    assert run_id in str(runs_panel)
    assert "Run succeeded" in str(events_panel)

    rendered = _render_selected(app, run_id)
    assert "Strategy Settings" in rendered
    assert configuration_id in rendered
    assert "Research History" in rendered
    assert "launch-commit" in rendered
    assert "launch-package-fingerprint" in rendered
    assert "Strategy Checks" in rendered
    assert "artifact-status-success" in rendered
    assert "Persisted deterministic fixture result summary" in rendered
    assert "does not imply profitability" in rendered

    restarted_service = FixtureRunService(database=database, fixture_launcher=_launcher)
    restarted_adapter = RunDetailDashboardAdapter(
        database=database,
        artifact_root=tmp_path / "artifact-root",
    )
    restarted_app = _app(restarted_service, restarted_adapter, tmp_path)

    restarted_runs, restarted_events = _callback_function(
        restarted_app,
        "recent-runs-monitor",
    )(2, 0, 0, 0, 0, 0)
    restarted_options, restarted_selected_update = _callback_function(
        restarted_app,
        "selected-run-selector.options",
    )(
        2,
        0,
        0,
        0,
        run_id,
        run_id,
        options,
    )
    restarted_selected = (
        run_id if restarted_selected_update is no_update else restarted_selected_update
    )
    restarted_options = (
        options if restarted_options is no_update else restarted_options
    )
    restarted_rendered = _render_selected(restarted_app, run_id)

    assert restarted_selected == run_id
    assert restarted_options[0]["value"] == run_id
    assert run_id in str(restarted_runs)
    assert "Run succeeded" in str(restarted_events)
    assert configuration_id in restarted_rendered
    assert "launch-commit" in restarted_rendered
    assert "artifact-status-success" in restarted_rendered
    assert "deterministic_value: 1729" in restarted_rendered


def test_dashboard_failure_reconciliation_remains_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(
        tmp_path,
        monkeypatch,
        fixture_launcher=_failure_launcher,
    )
    app = _app(service, adapter, tmp_path)

    content, class_name, launch_context, launch_context_class = _callback_function(
        app,
        "launch-message",
    )(1, configuration_id)
    run_id = service.recent_runs(limit=1)[0].run_id

    assert class_name == "save-message"
    assert "failed" in str(content)
    assert "controlled Prefect fixture failure" in str(content)
    assert run_id in str(content)
    assert launch_context_class == "operator-context"
    rendered_launch_context = str(launch_context)
    assert "Run status" in rendered_launch_context
    assert "Failed" in rendered_launch_context
    assert "Evidence outcome" in rendered_launch_context
    assert "Human decision" in rendered_launch_context
    assert rendered_launch_context.count("Unavailable") == 2
    assert "Next safe action" in rendered_launch_context
    assert "Review failure" in rendered_launch_context

    rendered = _render_selected(app, run_id)
    assert "failed" in rendered
    assert "controlled Prefect fixture failure" in rendered
    assert "Run failed; see the Prefect reference for technical details." in rendered
    assert "No artifact inventory is available" in rendered
    assert "No persisted parameter result summary is available" in rendered


def test_dashboard_cancellation_reconciliation_waits_for_fixture_acknowledgement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(tmp_path, monkeypatch)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking_launcher(**kwargs):
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
            prefect_reference=PrefectRunReference(flow_run_id="prefect-cancel"),
        )
        persistence = PersistenceService(kwargs["database_path"])
        try:
            persistence.increment_run_attempt(kwargs["quant_factory_run_id"])
            started.set()
            assert release.wait(timeout=5)
            with pytest.raises(ControlledFixtureCancellation):
                acknowledge_fixture_cancellation(
                    persistence,
                    quant_factory_run_id=kwargs["quant_factory_run_id"],
                )
            return PrefectFixtureResult(
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_flow_run_id="prefect-cancel",
                configuration_id=kwargs["configuration_id"],
                deterministic_value=1729,
                attempt_count=1,
            )
        finally:
            persistence.close()
            finished.set()

    service = FixtureRunService(database=database, fixture_launcher=blocking_launcher)
    app = _app(service, adapter, tmp_path)
    errors: list[BaseException] = []

    def launch() -> None:
        try:
            service.launch_fixture(configuration_id=configuration_id, run_id="qf-ui-cancel")
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=launch)
    worker.start()
    assert started.wait(timeout=5)

    cancel_message, cancel_class = _callback_function(app, "cancellation-message")(
        1,
        "qf-ui-cancel",
    )
    running_render = _render_selected(app, "qf-ui-cancel")

    assert "waiting for fixture acknowledgement" in cancel_message
    assert cancel_class == "cancellation-message cancellation-message-pending"
    assert "running" in running_render
    assert "Cancellation requested; waiting for fixture acknowledgement." in running_render
    assert "cancelled" not in running_render

    release.set()
    assert finished.wait(timeout=5)
    worker.join(timeout=5)
    assert errors == []

    terminal_render = _render_selected(app, "qf-ui-cancel")
    assert "cancelled" in terminal_render
    assert "Run cancelled after fixture acknowledgement." in terminal_render
    assert service.get_run("qf-ui-cancel").status == RunStatus.CANCELLED.value


def test_dashboard_stale_recovery_reopens_reconciled_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(tmp_path, monkeypatch)
    _create_run(
        database,
        configuration_id,
        run_id="qf-stale-ui-created",
        status=RunStatus.CREATED,
        old=True,
    )
    _create_run(
        database,
        configuration_id,
        run_id="qf-stale-ui-running",
        status=RunStatus.RUNNING,
        old=True,
    )
    app = _app(service, adapter, tmp_path)

    message, class_name = _callback_function(app, "stale-recovery-message")(
        1,
        "2025-01-01T00:00:00Z",
    )
    rendered_message = str(message)

    assert class_name == "stale-recovery-message error-state"
    assert "age-only fixture recovery is disabled" in rendered_message

    detail = _render_selected(app, "qf-stale-ui-running")
    assert "running" in detail
    assert service.get_run("qf-stale-ui-created").status == RunStatus.CREATED.value
    assert service.get_run("qf-stale-ui-running").status == RunStatus.RUNNING.value


def test_dashboard_historical_relaunch_creates_new_run_and_preserves_old_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(tmp_path, monkeypatch)
    app = _app(service, adapter, tmp_path)
    _callback_function(app, "launch-message")(1, configuration_id)
    old_run = service.recent_runs(limit=1)[0]
    _prepare_success_run_artifacts(database, tmp_path / "artifact-root", old_run.run_id)

    historical_launch = _callback_function(app, "historical-launch-message")
    content, class_name = historical_launch(1, old_run.run_id)
    new_run = service.recent_runs(limit=1)[0]

    assert class_name == "historical-launch-message historical-launch-message-success"
    assert new_run.run_id != old_run.run_id
    assert new_run.configuration_id == old_run.configuration_id == configuration_id
    assert new_run.run_id in str(content)
    assert old_run.run_id not in str(content)
    assert service.get_run(old_run.run_id) == old_run

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "historical-launch-message",
    )
    options, selected = _callback_function(app, "selected-run-selector.options")(
        2,
        0,
        content,
        0,
        old_run.run_id,
        old_run.run_id,
        [],
    )
    assert selected == new_run.run_id
    assert {option["value"] for option in options[:2]} == {old_run.run_id, new_run.run_id}


def test_dashboard_artifact_integrity_states_render_without_false_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(tmp_path, monkeypatch)
    root = tmp_path / "artifact-root"
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-artifacts")
    _add_lineage_inputs(database, "qf-artifacts")
    _register_artifact(
        database,
        root,
        "qf-artifacts",
        artifact_type=ArtifactType.RUN_SUMMARY,
        name="valid-summary",
        content=b'{"ok":true}',
        write_content=b'{"ok":true}',
    )
    _register_artifact(
        database,
        root,
        "qf-artifacts",
        artifact_type=ArtifactType.METRICS,
        name="missing-metrics",
        content=b'{"missing":true}',
    )
    _register_artifact(
        database,
        root,
        "qf-artifacts",
        artifact_type=ArtifactType.EQUITY_CURVE,
        name="corrupt-equity",
        content=b'{"expected":0}',
        write_content=b'{"expected":1}',
    )
    _persist_manifest(database, "qf-artifacts")

    rendered = _render_selected(_app(service, adapter, tmp_path), "qf-artifacts")

    assert "valid-summary" in rendered
    assert "artifact-status-success" in rendered
    assert "missing-metrics" in rendered
    assert "artifact_missing" in rendered
    assert "artifact-status-warning" in rendered
    assert "corrupt-equity" in rendered
    assert "artifact_checksum_mismatch" in rendered
    assert "artifact-status-error" in rendered

    persistence = PersistenceService(database)
    try:
        persistence.connection.execute(
            """
            UPDATE artifact_references
            SET schema_version=schema_version + 1
            WHERE logical_name=?
            """,
            ("valid-summary",),
        )
        persistence.connection.commit()
    finally:
        persistence.close()

    invalid_schema = _render_selected(_app(service, adapter, tmp_path), "qf-artifacts")
    assert "stored run manifest artifacts do not match database records" in invalid_schema
    assert "valid-summary" in invalid_schema
    assert "artifact-status-error" in invalid_schema


def test_dashboard_missing_manifest_and_incomplete_lineage_are_neutral_not_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(tmp_path, monkeypatch)
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-no-manifest")

    missing_manifest = _render_selected(_app(service, adapter, tmp_path), "qf-no-manifest")
    assert "No persisted run manifest is available." in missing_manifest
    assert "No artifact inventory is available" in missing_manifest
    assert "artifact-status-success" not in missing_manifest

    persistence = PersistenceService(database)
    try:
        run = persistence.runs.get("qf-no-manifest")
        assert run is not None
        document = {
            "manifest_schema_version": 2,
            "run_id": run.run_id,
            "configuration_id": run.configuration_id,
            "strategy_id": run.strategy_id,
            "strategy_version": run.strategy_version,
            "artifacts": [],
        }
        checksum = __import__("hashlib").sha256(
            canonical_json(document).encode("utf-8")
        ).hexdigest()
        persistence.connection.execute(
            """
            INSERT INTO run_manifests
                (run_id, schema_version, manifest_json, content_checksum, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run.run_id, 2, canonical_json(document), checksum, utc_now()),
        )
        persistence.connection.commit()
    finally:
        persistence.close()

    incomplete_lineage = _render_selected(_app(service, adapter, tmp_path), "qf-no-manifest")
    assert "Schema version" in incomplete_lineage
    assert "Not recorded" in incomplete_lineage
    assert "artifact-status-success" not in incomplete_lineage


def test_dashboard_callback_refresh_integrity_with_real_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(tmp_path, monkeypatch)
    app = _app(service, adapter, tmp_path)

    output_keys = "\n".join(app.callback_map)
    assert output_keys.count("selected-run-selector.value") == 1
    assert output_keys.count("selected-run-selector.options") == 1
    assert output_keys.count("selected-run-detail.children") == 1

    service.launch_fixture(configuration_id=configuration_id, run_id="qf-refresh-old")
    new_launch = service.launch_fixture(configuration_id=configuration_id, run_id="qf-refresh-new")

    refresh_monitor = _callback_function(app, "recent-runs-monitor")
    runs_panel, events_panel = refresh_monitor(1, 0, 0, 0, 0, 0)
    assert "qf-refresh-old" in str(runs_panel)
    assert "qf-refresh-new" in str(runs_panel)
    assert "Run succeeded" in str(events_panel)

    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "refresh-runs",
    )
    options, selected_update = refresh_selectors(
        1,
        0,
        0,
        0,
        "qf-refresh-old",
        "qf-refresh-old",
        [],
    )
    selected = "qf-refresh-old" if selected_update is no_update else selected_update
    assert selected == "qf-refresh-old"

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "launch-message",
    )
    _, selected_after_launch = refresh_selectors(
        2,
        _run_launch_summary(new_launch.run),
        0,
        0,
        "qf-refresh-old",
        "qf-refresh-old",
        options,
    )
    assert selected_after_launch == "qf-refresh-new"
    assert service.get_run("qf-refresh-old") is not None
    assert service.get_run("qf-refresh-new") is not None
