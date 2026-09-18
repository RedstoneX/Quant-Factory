"""Automated Milestone 23 full-system acceptance coverage."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import threading
import time

import pandas as pd
import pytest

from dashboard.app import DashboardContext, create_app
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService
from persistence import (
    ArtifactType,
    PersistenceService,
    ReviewState,
    RunStage,
    RunStatus,
)
from persistence.database import transaction
from persistence.evidence_service import ValidationEvidenceArtifactService
from prefect_spike.fixture_flow import (
    ControlledFixtureCancellation,
    PrefectFixtureResult,
    PrefectRunReference,
    _create_or_reference_run,
    _persist_fixture_result,
    acknowledge_fixture_cancellation,
    deterministic_fixture_body,
    reconcile_quant_factory_run_status,
)
from prefect_spike.spym_vectorbt_fixture import ensure_spym_21c_saved_configuration
from tests.test_dashboard import _audit, _callback_function, _data, _ranked_row
from tests.test_milestone22e_acceptance import (
    _dashboard_fields,
    _database_path as _m22_database_path,
    _persist_passed_monte_carlo_case,
    _run_summary as _m22_run_summary,
)
from tests.test_milestone_20_acceptance import (
    _add_lineage_inputs,
    _failure_launcher,
    _persist_manifest,
    _register_artifact,
    _render_selected,
    _seed_dashboard,
)
from tests.test_run_stale_recovery import _create_run
from tests.test_lockbox_gate import (
    _monte_carlo_result,
    _robustness_result,
    _rules,
    _walk_forward_result,
    _service as _m22_service,
)
from tests.test_review_context_artifacts import _source_lock_artifact


def _render_selected(app, run_id: str) -> str:
    inspect = _callback_function(app, "selected-run-detail")
    return str(inspect(run_id, run_id, 1, 0, 0, 0))


def _context() -> DashboardContext:
    data = _data()
    return DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))


def _spym_launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def _spym_stack(tmp_path: Path) -> tuple[Path, str, FixtureRunService, RunDetailDashboardAdapter]:
    database = tmp_path / "state" / "milestone23.sqlite3"
    persistence = PersistenceService(database)
    try:
        configuration_id = ensure_spym_21c_saved_configuration(persistence)
    finally:
        persistence.close()
    service = FixtureRunService(database=database, fixture_launcher=_spym_launcher)
    adapter = RunDetailDashboardAdapter(database=database, artifact_root=tmp_path)
    return database, configuration_id, service, adapter


def _app(
    database: Path,
    service: FixtureRunService,
    adapter: RunDetailDashboardAdapter,
):
    return create_app(
        _context(),
        database,
        run_service=service,
        run_detail_adapter=adapter,
    )


def _persist_spym_review_prerequisites(
    database: Path,
    artifact_root: Path,
    *,
    target_run_id: str,
) -> tuple[object, tuple[str, str]]:
    """Persist explicit deterministic validation evidence compatible with one SPYM run."""
    persistence = PersistenceService(database)
    try:
        target = persistence.runs.get(target_run_id)
        assert target is not None
        configuration = persistence.configurations.get(target.configuration_id)
        assert configuration is not None
        configuration_document = json.loads(configuration.canonical_config_json)
        target_provenance = persistence.results.get_data_provenance(target_run_id)
        target_execution = persistence.results.get_execution_assumptions(target_run_id)
        assert target_provenance is not None
        assert target_execution is not None
        environment = json.loads(target.environment_json)

        stage_runs = (
            ("m23-spym-review-source-lock", RunStage.OOS),
            ("m23-spym-review-walk-forward", RunStage.WALK_FORWARD),
            ("m23-spym-review-monte-carlo", RunStage.MONTE_CARLO),
            ("m23-spym-review-robustness", RunStage.ROBUSTNESS),
        )
        for run_id, stage in stage_runs:
            persistence.create_run(
                configuration_id=target.configuration_id,
                strategy_id=target.strategy_id,
                strategy_version=target.strategy_version,
                stage=stage,
                run_id=run_id,
                status=RunStatus.SUCCEEDED,
                environment=environment,
            )
            with transaction(persistence.connection):
                persistence.results.set_data_provenance(
                    replace(target_provenance, run_id=run_id)
                )
                persistence.results.set_execution_assumptions(
                    replace(target_execution, run_id=run_id)
                )

        envelope = configuration_document["parameters"]
        assert set(envelope) == {"fixture", "strategy_parameters"}
        parameters = envelope["strategy_parameters"]
        assert isinstance(parameters, dict) and parameters
        experiment_id = configuration_document["experiment_id"]
        evidence = ValidationEvidenceArtifactService(persistence)
        evidence.persist_walk_forward(
            run_id="m23-spym-review-walk-forward",
            result=_walk_forward_result(
                experiment_id=experiment_id,
                strategy_id=target.strategy_id,
                strategy_version=target.strategy_version,
                parameters=parameters,
            ),
            rules=_rules(),
            artifact_root=artifact_root,
        )
        evidence.persist_monte_carlo(
            run_id="m23-spym-review-monte-carlo",
            result=_monte_carlo_result(
                experiment_id=experiment_id,
                strategy_id=target.strategy_id,
                strategy_version=target.strategy_version,
            ),
            artifact_root=artifact_root,
        )
        target_source = evidence.source_document(target_run_id)
        source_lock_id = _source_lock_artifact(
            persistence,
            artifact_root,
            run_id="m23-spym-review-source-lock",
            artifact_id="m23-spym-source-lock",
            locked_parameters=parameters,
            strategy_id=target.strategy_id,
            strategy_version=target.strategy_version,
            experiment_id=experiment_id,
            data_provenance={
                "dataset_identity": target_source["data_identity"],
                "provider": target_provenance.provider,
            },
            execution_assumptions=json.loads(target_execution.assumptions_json),
            source_start="2025-10-31",
            source_end="2025-10-31",
        )
        robustness = _robustness_result(
            locked_parameters=parameters,
            source_artifact_id="m23-spym-source-lock",
            experiment_id=experiment_id,
            strategy_id=target.strategy_id,
            strategy_version=target.strategy_version,
        )
        evidence.persist_robustness(
            run_id="m23-spym-review-robustness",
            result=replace(
                robustness,
                data_provenance={
                    "dataset_identity": target_source["data_identity"],
                    "provider": target_provenance.provider,
                },
                execution_assumptions=json.loads(target_execution.assumptions_json),
            ),
            artifact_root=artifact_root,
        )
        manifest_before = persistence.read_persisted_run_manifest(target_run_id)
        assert manifest_before is not None
        context = evidence.persist_review_context(
            target_run_id=target_run_id,
            source_lock_run_id="m23-spym-review-source-lock",
            source_lock_artifact_id=source_lock_id,
            walk_forward_run_id="m23-spym-review-walk-forward",
            monte_carlo_run_id="m23-spym-review-monte-carlo",
            robustness_run_id="m23-spym-review-robustness",
            protected_data_state="gated",
            artifact_root=artifact_root,
            created_at="2026-07-17T00:00:00+00:00",
        )
        return context, manifest_before
    finally:
        persistence.close()


def test_milestone23_successful_spym_workflow_compare_reproduce_and_review(
    tmp_path: Path,
) -> None:
    database, configuration_id, service, adapter = _spym_stack(tmp_path)

    persistence = PersistenceService(database)
    try:
        configuration = persistence.configurations.get(configuration_id)
        assert configuration is not None
        immutable_config_json = configuration.canonical_config_json
    finally:
        persistence.close()

    launched = service.launch_fixture(
        configuration_id=configuration_id,
        run_id="m23-spym-success",
    )

    assert launched.run.status == RunStatus.SUCCEEDED.value
    assert launched.run.prefect_flow_run_id == "prefect-m23-spym-success"
    assert launched.prefect_result is not None
    assert launched.prefect_result.deterministic_value == 366

    persistence = PersistenceService(database)
    try:
        configuration = persistence.configurations.get(configuration_id)
        assert configuration is not None
        assert configuration.canonical_config_json == immutable_config_json
        detail = persistence.run_detail("m23-spym-success")
        metrics = detail["parameters"][0]["metrics_json"]
        assert '"number_of_trades":366' in metrics
        assert detail["provenance"]["provider"] == "Databento"
        assert detail["provenance"]["symbol"] == "SPYM"
        manifest = persistence.read_persisted_run_manifest_document("m23-spym-success")
        assert manifest is not None
        lineage = manifest["lineage"]
        assert lineage["configuration"]["configuration_id"] == configuration_id
        assert lineage["data"]["dataset_manifest_reference"] == (
            "data/manifests/equities_SPYM_1m_databento_equs_mini.json"
        )
        assert lineage["execution_assumptions"]["execution_assumptions_identity"]
        assert lineage["runtime"]["runtime_identity"]
        retrieval = persistence.retrieve_run_artifacts(
            "m23-spym-success",
            artifact_root=tmp_path,
        )
        assert all(validation.valid for validation in retrieval.validations)
        assert {
            artifact.logical_name for artifact in retrieval.artifacts
        } == {
            "dataset_manifest",
            "equity_curve",
            "metrics",
            "parameter_results",
            "run_summary",
            "trades_and_orders",
            "validation_evidence",
        }
    finally:
        persistence.close()

    selected = adapter.selected_run_detail("m23-spym-success")
    assert not selected.warnings
    assert any(field.label == "Number Of Trades" and field.value == "366" for field in selected.evidence.metrics)
    assert len(selected.evidence.trades) == 366
    assert len(selected.evidence.orders) == 732
    assert selected.evidence.equity_curve
    assert any(field.value == "Databento" for field in selected.evidence.provenance)
    assert any(field.label == "Result Validation Gate Count" for field in selected.evidence.validation)
    assert any("not profitability evidence" in notice for notice in selected.evidence.notices)
    assert any("not selected as the final paper or micro-live instrument" in notice for notice in selected.evidence.notices)

    app = _app(database, service, adapter)
    reproduce = _callback_function(app, "reproduction-message")
    (
        message,
        class_name,
        reproduction_comparison,
        comparison_class,
        comparison_value,
    ) = reproduce(1, "m23-spym-success")
    assert class_name == "reproduction-message reproduction-message-success"
    assert comparison_class == "run-comparison-output"
    assert comparison_value[0] == "m23-spym-success"
    assert "Allowed differences" in str(message)
    assert "m23-spym-success" in str(reproduction_comparison)

    persistence = PersistenceService(database)
    try:
        reproduced = next(
            run for run in persistence.runs.list() if run.run_id != "m23-spym-success"
        )
        source = persistence.runs.get("m23-spym-success")
        assert source is not None
        assert source.configuration_id == reproduced.configuration_id == configuration_id
        assert comparison_value[1] == reproduced.run_id
        compare = persistence.compare_runs(("m23-spym-success", reproduced.run_id))
        source_environment = compare[0]["run"]["environment_json"]
        reproduced_environment = compare[1]["run"]["environment_json"]
        assert "reproduction" not in source_environment
        assert "m23-spym-success" in reproduced_environment
    finally:
        persistence.close()

    comparison_panel, comparison_class = _callback_function(app, "run-comparison-output")(
        1,
        ["m23-spym-success", reproduced.run_id],
    )
    assert comparison_class == "run-comparison-output"
    rendered_comparison = str(comparison_panel)
    assert "Configuration hash" in rendered_comparison
    assert "Dataset identity" in rendered_comparison
    assert "Runtime identity" in rendered_comparison
    assert "Number Of Trades" not in rendered_comparison
    assert "Number of trades: 366" in rendered_comparison

    review_context, sealed_manifest_before_review = _persist_spym_review_prerequisites(
        database,
        tmp_path,
        target_run_id="m23-spym-success",
    )
    assert review_context.context_identity

    load_review = _callback_function(app, "review-status")
    refresh_review_context = _callback_function(app, "save-review")
    save_review = _callback_function(app, "review-message")
    review_target = "m23-spym-success"
    status, note, history = load_review(review_target)
    assert status == ReviewState.UNREVIEWED.value
    assert note == ""
    assert "No durable decision" in str(history)
    save_disabled, save_title, availability = refresh_review_context(review_target)
    assert save_disabled is False
    assert "durable evidence decision" in save_title
    assert availability == ""
    persistence = PersistenceService(database)
    try:
        review_history_before = persistence.reviews.history("run", review_target)
    finally:
        persistence.close()
    review_message, review_history = save_review(
        1,
        review_target,
        ReviewState.WATCHLIST.value,
        "Milestone 23 durable review",
    )
    assert "Evidence decision artifact validated." in str(review_message)
    assert "dashboard-operator" in str(review_history)
    persistence = PersistenceService(database)
    try:
        current_review = persistence.reviews.get_current("run", review_target)
        review_history = persistence.reviews.history("run", review_target)
        assert current_review is not None
        assert current_review.state == ReviewState.WATCHLIST.value
        assert current_review.note == "Milestone 23 durable review"
        assert current_review.operator == "dashboard-operator"
        assert len(review_history) == len(review_history_before) + 1
        assert persistence.read_persisted_run_manifest(review_target) == sealed_manifest_before_review
        decision_artifacts = tuple(
            artifact
            for artifact in persistence.list_run_artifacts(review_target)
            if artifact.logical_name == "evidence_decision_record"
        )
        assert len(decision_artifacts) == 1
        validation = persistence.validate_artifact(
            decision_artifacts[0].artifact_id,
            artifact_root=tmp_path,
        )
        assert validation.valid
    finally:
        persistence.close()

    retry_message = save_review(
        2,
        review_target,
        parameters,
        ReviewState.WATCHLIST.value,
        "Milestone 23 durable review",
    )
    assert "Evidence decision artifact validated." in str(retry_message)
    persistence = PersistenceService(database)
    try:
        assert persistence.reviews.history("run", review_target) == review_history
        assert len(
            [
                artifact
                for artifact in persistence.list_run_artifacts(review_target)
                if artifact.logical_name == "evidence_decision_record"
            ]
        ) == 1
        assert persistence.read_persisted_run_manifest(review_target) == sealed_manifest_before_review
    finally:
        persistence.close()

    restarted = _app(
        database,
        FixtureRunService(database=database, fixture_launcher=_spym_launcher),
        RunDetailDashboardAdapter(database=database, artifact_root=tmp_path),
    )
    restarted_status, restarted_note = _callback_function(restarted, "review-status")(
        review_target
    )
    assert restarted_status == ReviewState.WATCHLIST.value
    assert restarted_note == "Milestone 23 durable review"
    restarted_disabled, _, restarted_availability = _callback_function(
        restarted, "save-review"
    )(review_target)
    assert restarted_disabled is False
    assert restarted_availability == ""
    reopened = _callback_function(restarted, "selected-run-detail")(
        "m23-spym-success",
        "m23-spym-success",
        1,
        0,
        0,
        0,
    )
    assert "Research history" in str(reopened)
    assert "artifact-status-success" in str(reopened)


def test_milestone23_normalized_validation_outcome_reuses_milestone22_path(
    tmp_path: Path,
) -> None:
    service = _m22_service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_passed_monte_carlo_case(service, root)
        outcome = ValidationEvidenceArtifactService(service).stage_outcome(
            "mc-run",
            artifact_root=root,
        )
        detail = RunDetailDashboardAdapter(
            database=_m22_database_path(tmp_path),
            artifact_root=root,
        ).selected_run_detail("mc-run")
        fields = _dashboard_fields(detail)
        rendered = str(_render_validation_panel(service, detail))

        assert outcome.status == "passed"
        assert fields["Normalized status"] == "passed"
        assert fields["Reasons"] == "Not recorded"
        assert "No strategy progression occurred." in rendered
    finally:
        service.close()


def _render_validation_panel(service, detail) -> object:
    from dashboard.app import _run_detail_panel

    return _run_detail_panel(_m22_run_summary(service), detail=detail)


def test_milestone23_controlled_failure_is_diagnosable_without_false_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(
        tmp_path,
        monkeypatch,
        fixture_launcher=_failure_launcher,
    )
    app = _app(database, service, adapter)

    content, class_name, context, context_class = _callback_function(
        app, "launch-message"
    )(
        1,
        configuration_id,
    )
    run_id = service.recent_runs(limit=1)[0].run_id
    rendered = _render_selected(app, run_id)

    assert class_name == "save-message"
    assert "failed" in str(content)
    assert context_class == "operator-context"
    assert "Review failure" in str(context)
    assert "controlled Prefect fixture failure" in rendered
    assert "No artifact inventory is available" in rendered
    assert "No persisted parameter result summary is available" in rendered

    persistence = PersistenceService(database)
    try:
        run = persistence.runs.get(run_id)
        assert run is not None and run.status == RunStatus.FAILED
        assert persistence.results.list_parameter_results(run_id) == ()
        assert persistence.results.list_artifacts(run_id) == ()
        assert persistence.read_persisted_run_manifest(run_id) is None
    finally:
        persistence.close()


def test_milestone23_recovery_and_integrity_fail_closed_dashboard_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, configuration_id, service, adapter = _seed_dashboard(tmp_path, monkeypatch)

    timeout_finished = threading.Event()

    def timeout_launcher(**kwargs):
        persistence = PersistenceService(kwargs["database_path"])
        try:
            _create_or_reference_run(
                persistence,
                configuration_id=kwargs["configuration_id"],
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_reference=PrefectRunReference(flow_run_id="prefect-timeout"),
                reference_source="milestone23_timeout",
                frozen_runtime_lineage=kwargs["frozen_runtime_lineage"],
            )
            persistence.increment_run_attempt(kwargs["quant_factory_run_id"])
            reconcile_quant_factory_run_status(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_state="Running",
            )
            time.sleep(0.1)
            _persist_fixture_result(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                configuration_id=kwargs["configuration_id"],
                prefect_flow_run_id="prefect-timeout",
                deterministic_value=1729,
                attempt_count=1,
            )
            reconcile_quant_factory_run_status(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_state="Completed",
            )
            return PrefectFixtureResult(
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_flow_run_id="prefect-timeout",
                configuration_id=kwargs["configuration_id"],
                deterministic_value=1729,
                attempt_count=1,
            )
        finally:
            persistence.close()
            timeout_finished.set()

    timeout_service = FixtureRunService(
        database=database,
        fixture_launcher=timeout_launcher,
    )
    timeout = timeout_service.launch_fixture(
        configuration_id=configuration_id,
        run_id="m23-timeout",
        timeout_seconds=0.01,
    )
    assert timeout.run.status == RunStatus.FAILED.value
    assert "timed out" in (timeout.run.error_summary or "")
    assert timeout_finished.wait(timeout=5)
    timeout_render = _render_selected(_app(database, timeout_service, adapter), "m23-timeout")
    assert "failed" in timeout_render
    assert "timed out" in timeout_render
    assert "artifact-status-success" not in timeout_render

    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def cancellable_launcher(**kwargs):
        persistence = PersistenceService(kwargs["database_path"])
        try:
            _create_or_reference_run(
                persistence,
                configuration_id=kwargs["configuration_id"],
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_reference=PrefectRunReference(flow_run_id="prefect-cancel"),
                reference_source="milestone23_cancel",
                frozen_runtime_lineage=kwargs["frozen_runtime_lineage"],
            )
            persistence.increment_run_attempt(kwargs["quant_factory_run_id"])
            reconcile_quant_factory_run_status(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_state="Running",
            )
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

    cancel_service = FixtureRunService(
        database=database,
        fixture_launcher=cancellable_launcher,
    )
    cancel_app = _app(database, cancel_service, adapter)
    errors: list[BaseException] = []
    outcomes = []

    def launch_cancellable() -> None:
        try:
            outcomes.append(
                cancel_service.launch_fixture(
                    configuration_id=configuration_id,
                    run_id="m23-cancel",
                )
            )
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(
        target=launch_cancellable,
    )
    worker.start()
    assert started.wait(timeout=5)
    cancel_message, cancel_class = _callback_function(cancel_app, "cancellation-message")(
        1,
        "m23-cancel",
    )
    assert cancel_class == "cancellation-message cancellation-message-pending"
    assert "waiting for fixture acknowledgement" in cancel_message
    release.set()
    assert finished.wait(timeout=5)
    worker.join(timeout=5)
    assert errors == []
    assert outcomes and outcomes[0].run.status == RunStatus.CANCELLED.value
    assert service.get_run("m23-cancel").status == RunStatus.CANCELLED.value
    assert "Run cancelled after fixture acknowledgement." in _render_selected(
        cancel_app,
        "m23-cancel",
    )

    _create_run(
        database,
        configuration_id,
        run_id="m23-stale-created",
        status=RunStatus.CREATED,
        old=True,
    )
    _create_run(
        database,
        configuration_id,
        run_id="m23-stale-running",
        status=RunStatus.RUNNING,
        old=True,
    )
    _create_run(
        database,
        configuration_id,
        run_id="m23-fresh-running",
        status=RunStatus.RUNNING,
        old=False,
    )
    stale_app = _app(database, service, adapter)
    stale_message, stale_class = _callback_function(stale_app, "stale-recovery-message")(
        1,
        "2025-01-01T00:00:00Z",
    )
    assert stale_class == "stale-recovery-message stale-recovery-message-success"
    assert "Recovered 2 stale fixture runs" in str(stale_message)
    assert "Fixture run remained running beyond the stale recovery cutoff." in _render_selected(
        stale_app,
        "m23-stale-running",
    )
    no_recovery_message, no_recovery_class = _callback_function(
        stale_app,
        "stale-recovery-message",
    )(2, "2025-01-01T00:00:00Z")
    assert no_recovery_class == "stale-recovery-message"
    assert "No stale fixture runs" in str(no_recovery_message)

    service.launch_fixture(configuration_id=configuration_id, run_id="m23-artifact")
    root = tmp_path / "artifact-root"
    _add_lineage_inputs(database, "m23-artifact")
    _register_artifact(
        database,
        root,
        "m23-artifact",
        artifact_type=ArtifactType.RUN_SUMMARY,
        name="valid-summary",
        content=b'{"ok":true}',
        write_content=b'{"ok":true}',
    )
    _register_artifact(
        database,
        root,
        "m23-artifact",
        artifact_type=ArtifactType.METRICS,
        name="missing-metrics",
        content=b'{"missing":true}',
    )
    _register_artifact(
        database,
        root,
        "m23-artifact",
        artifact_type=ArtifactType.EQUITY_CURVE,
        name="corrupt-equity",
        content=b'{"expected":0}',
        write_content=b'{"expected":1}',
    )
    _persist_manifest(database, "m23-artifact")
    artifact_render = _render_selected(_app(database, service, adapter), "m23-artifact")
    assert "valid-summary" in artifact_render
    assert "artifact-status-success" in artifact_render
    assert "artifact_missing" in artifact_render
    assert "artifact_checksum_mismatch" in artifact_render

    persistence = PersistenceService(database)
    try:
        artifact_status = persistence.runs.get("m23-artifact").status
    finally:
        persistence.close()

    service.launch_fixture(configuration_id=configuration_id, run_id="m23-corrupt-lineage")
    _add_lineage_inputs(database, "m23-corrupt-lineage")
    _register_artifact(
        database,
        root,
        "m23-corrupt-lineage",
        artifact_type=ArtifactType.RUN_SUMMARY,
        name="lineage-summary",
        content=b'{"ok":true}',
        write_content=b'{"ok":true}',
    )
    _persist_manifest(database, "m23-corrupt-lineage")
    persistence = PersistenceService(database)
    try:
        corrupt_lineage_status = persistence.runs.get("m23-corrupt-lineage").status
        persistence.connection.execute(
            "UPDATE run_manifests SET manifest_json=? WHERE run_id=?",
            ("{not-json", "m23-corrupt-lineage"),
        )
        persistence.connection.commit()
    finally:
        persistence.close()

    corrupt_lineage = _render_selected(
        _app(database, service, adapter),
        "m23-corrupt-lineage",
    )
    assert "The persisted run manifest is invalid" in corrupt_lineage
    assert "artifact-status-success" not in corrupt_lineage
    persistence = PersistenceService(database)
    try:
        assert persistence.runs.get("m23-artifact").status == artifact_status
        assert (
            persistence.runs.get("m23-corrupt-lineage").status
            == corrupt_lineage_status
        )
    finally:
        persistence.close()

    restarted_service = FixtureRunService(database=database, fixture_launcher=_spym_launcher)
    restarted_adapter = RunDetailDashboardAdapter(
        database=database,
        artifact_root=tmp_path / "artifact-root",
    )
    restarted_app = _app(database, restarted_service, restarted_adapter)
    persistence = PersistenceService(database)
    try:
        statuses = {
            run_id: persistence.runs.get(run_id).status
            for run_id in (
                "m23-timeout",
                "m23-cancel",
                "m23-stale-created",
                "m23-stale-running",
                "m23-fresh-running",
                "m23-artifact",
                "m23-corrupt-lineage",
            )
        }
        identities = {
            run_id: persistence.runs.get(run_id).configuration_id
            for run_id in statuses
        }
    finally:
        persistence.close()
    assert statuses == {
        "m23-timeout": RunStatus.FAILED,
        "m23-cancel": RunStatus.CANCELLED,
        "m23-stale-created": RunStatus.FAILED,
        "m23-stale-running": RunStatus.FAILED,
        "m23-fresh-running": RunStatus.RUNNING,
        "m23-artifact": artifact_status,
        "m23-corrupt-lineage": corrupt_lineage_status,
    }
    assert set(identities.values()) == {configuration_id}
    assert "timed out" in _render_selected(restarted_app, "m23-timeout")
    assert "Run cancelled after fixture acknowledgement." in _render_selected(
        restarted_app,
        "m23-cancel",
    )
    assert "Fixture run remained running beyond the stale recovery cutoff." in _render_selected(
        restarted_app,
        "m23-stale-running",
    )
    restarted_artifact = _render_selected(restarted_app, "m23-artifact")
    assert "artifact_missing" in restarted_artifact
    assert "artifact_checksum_mismatch" in restarted_artifact
    assert "artifact-status-success" in restarted_artifact
    restarted_corrupt_lineage = _render_selected(
        restarted_app,
        "m23-corrupt-lineage",
    )
    assert "The persisted run manifest is invalid" in restarted_corrupt_lineage
    assert "artifact-status-success" not in restarted_corrupt_lineage
    repeat_message, repeat_class = _callback_function(
        restarted_app,
        "stale-recovery-message",
    )(3, "2025-01-01T00:00:00Z")
    assert repeat_class == "stale-recovery-message"
    assert "No stale fixture runs" in str(repeat_message)
