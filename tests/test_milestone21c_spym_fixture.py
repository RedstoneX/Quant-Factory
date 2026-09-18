"""Milestone 21C acceptance coverage for the SPYM VectorBT fixture."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestration import FixtureRunService
from persistence import PersistenceService, RunStatus
from prefect_spike.fixture_flow import (
    ControlledFixtureCancellation,
    deterministic_fixture_body,
)
from tests.test_prefect_spike import (
    deterministic_fixture_body as claimed_deterministic_fixture_body,
)
import prefect_spike.spym_vectorbt_fixture as spym_fixture
from prefect_spike.spym_vectorbt_fixture import (
    ensure_spym_21c_saved_configuration,
    load_spym_21c_fixture_inputs,
    spym_21c_execution_assumptions,
)


def _launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def _configured_service(tmp_path: Path) -> tuple[Path, str, FixtureRunService]:
    database = tmp_path / "state" / "milestone21c.sqlite3"
    persistence = PersistenceService(database)
    try:
        configuration_id = ensure_spym_21c_saved_configuration(persistence)
    finally:
        persistence.close()
    return database, configuration_id, FixtureRunService(
        database=database,
        fixture_launcher=_launcher,
    )


def _detail(database: Path, run_id: str) -> dict:
    persistence = PersistenceService(database)
    try:
        return persistence.run_detail(run_id)
    finally:
        persistence.close()


def test_spym_saved_configuration_launches_vectorbt_and_persists_lineage(
    tmp_path: Path,
) -> None:
    database, configuration_id, service = _configured_service(tmp_path)

    launched = service.launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-21c-spym",
    )

    assert launched.run.status == RunStatus.SUCCEEDED.value
    assert launched.prefect_result is not None
    assert launched.prefect_result.deterministic_value > 0

    persistence = PersistenceService(database)
    try:
        detail = persistence.run_detail("qf-21c-spym")
        provenance = detail["provenance"]
        assert provenance["provider"] == "Databento"
        assert provenance["symbol"] == "SPYM"
        assert provenance["manifest_reference"] == (
            "data/manifests/equities_SPYM_1m_databento_equs_mini.json"
        )
        assert provenance["checksum"] == (
            "0fac9de8cb97568c7ee5ae00532277d960c316989ccd65296c394f0dfa44a5ab"
        )
        execution = json.loads(detail["execution_assumptions"]["assumptions_json"])
        assert execution == spym_21c_execution_assumptions()
        assert execution["broker_orders"] == "disabled"
        assert detail["parameters"]
        assert json.loads(detail["parameters"][0]["metrics_json"])["number_of_trades"] > 0

        manifest = persistence.read_persisted_run_manifest_document("qf-21c-spym")
        assert manifest is not None
        assert manifest["lineage"]["data"]["dataset_manifest_reference"] == (
            "data/manifests/equities_SPYM_1m_databento_equs_mini.json"
        )
        retrieval = persistence.retrieve_run_artifacts(
            "qf-21c-spym",
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


def test_spym_fixture_rerun_keeps_deterministic_metrics_and_trades(
    tmp_path: Path,
) -> None:
    database, configuration_id, service = _configured_service(tmp_path)

    service.launch_fixture(configuration_id=configuration_id, run_id="qf-21c-a")
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-21c-b")

    first = _detail(database, "qf-21c-a")
    second = _detail(database, "qf-21c-b")
    assert first["parameters"][0]["normalized_parameters_json"] == (
        second["parameters"][0]["normalized_parameters_json"]
    )
    assert first["parameters"][0]["metrics_json"] == second["parameters"][0]["metrics_json"]

    trades_a = (tmp_path / "state" / "artifacts" / "qf-21c-a" / "trades_and_orders.json").read_text(
        encoding="utf-8"
    )
    trades_b = (tmp_path / "state" / "artifacts" / "qf-21c-b" / "trades_and_orders.json").read_text(
        encoding="utf-8"
    )
    assert trades_a == trades_b


def test_spym_fixture_cancellation_safe_point_discards_computed_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, configuration_id, service = _configured_service(tmp_path)
    run_id = "qf-21c-cancel-after-compute"

    def expensive_stub(*_args, **_kwargs):
        persistence = PersistenceService(database)
        try:
            persistence.request_run_cancellation(run_id)
        finally:
            persistence.close()
        return SimpleNamespace()

    monkeypatch.setattr(spym_fixture, "execute_experiment", expensive_stub)

    with pytest.raises(ControlledFixtureCancellation):
        claimed_deterministic_fixture_body(
            database_path=database,
            configuration_id=configuration_id,
            quant_factory_run_id=run_id,
            prefect_flow_run_id=f"prefect-{run_id}",
            prefect_api_url="http://127.0.0.1:4200/api",
            saved_parameters=spym_fixture.spym_21c_parameters(),
            saved_execution_assumptions=spym_fixture.spym_21c_execution_assumptions(),
        )

    assert service.get_run(run_id).status == RunStatus.CANCELLED.value
    persistence = PersistenceService(database)
    try:
        assert persistence.results.list_parameter_results(run_id) == ()
        assert persistence.results.list_artifacts(run_id) == ()
    finally:
        persistence.close()


def test_spym_fixture_fails_closed_on_mismatched_dataset_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, configuration_id, service = _configured_service(tmp_path)
    fixture = load_spym_21c_fixture_inputs(
        database_path=database,
        saved_execution_assumptions=spym_21c_execution_assumptions(),
    )
    bad_manifest = replace(
        fixture.manifest,
        metadata={**fixture.manifest.metadata, "dataset_id": "wrong_dataset"},
    )
    monkeypatch.setattr(
        "prefect_spike.spym_vectorbt_fixture.load_dataset_manifest",
        lambda dataset_id: bad_manifest,
    )

    launched = service.launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-21c-bad-dataset",
    )

    assert launched.run.status == RunStatus.FAILED.value
    assert "dataset_id must be" in (launched.run.error_summary or "")
    detail = _detail(database, "qf-21c-bad-dataset")
    assert detail["parameters"] == []
    assert detail["artifacts"] == []
