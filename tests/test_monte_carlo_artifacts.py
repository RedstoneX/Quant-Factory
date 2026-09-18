"""Focused tests for durable Monte Carlo evidence artifacts."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from backtesting.monte_carlo import (
    ExecutionCostScenario,
    MonteCarloConfig,
    SourceSeries,
    run_monte_carlo,
)
from backtesting.validation.monte_carlo_artifacts import (
    MONTE_CARLO_EVIDENCE_LOGICAL_NAME,
    build_monte_carlo_evidence_document,
)
from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.evidence_service import ValidationEvidenceArtifactService
from persistence.models import normalized_configuration_document


def _source(values=(0.10, 0.08, 0.06, 0.04)) -> SourceSeries:
    return SourceSeries(
        source_id="fixture_returns",
        source_kind="period_returns",
        experiment_id="monte-carlo-artifact",
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        values=tuple(values),
        provenance={"provider": "fixture", "verified": True},
        execution_assumptions={"kind": "fixture"},
        period_frequency="daily",
    )


def _config(**overrides) -> MonteCarloConfig:
    return replace(
        MonteCarloConfig(
            simulation_count=20,
            minimum_observations=3,
            percentiles=(5, 25, 50, 75, 95),
            maximum_loss_probability=1.0,
            maximum_drawdown_breach_probability=1.0,
            minimum_lower_percentile_return=-1.0,
            execution_cost_scenarios=(
                ExecutionCostScenario("fee-stress", fee_increase=0.001),
            ),
        ),
        **overrides,
    )


def _result(
    *,
    values=(0.10, 0.08, 0.06, 0.04),
    config: MonteCarloConfig | None = None,
    timestamp: str = "2026-01-01T00:00:00+00:00",
) -> object:
    result = run_monte_carlo(_source(values), config or _config())
    return replace(result, timestamp=timestamp)


def _service_with_run(
    tmp_path: Path,
    *,
    run_id: str = "mc-run",
    stage: RunStage = RunStage.MONTE_CARLO,
) -> PersistenceService:
    service = PersistenceService(tmp_path / "state" / f"{run_id}.sqlite3")
    service.register_strategy(
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        display_name="Fixture Strategy",
        description="Synthetic Monte Carlo fixture",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    configuration = service.upsert_configuration(
        normalized_configuration_document(
            experiment_id="monte-carlo-artifact",
            strategy_id="fixture_strategy",
            strategy_version="1.0.0",
            market_data={"symbol": "SPY", "provider": "fixture"},
            parameters={"fixture": True},
            execution={"kind": "fixture"},
            ranking={"columns": ("total_return",), "ascending": (False,)},
            screening={"kind": "none"},
        )
    )
    service.create_run(
        configuration_id=configuration.configuration_id,
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        stage=stage,
        run_id=run_id,
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
                actual_coverage="2020-01-01..2020-01-10",
                adjusted=True,
                row_count=4,
                cache_action="fixture",
                validation_summary_json=canonical_json({"valid": True}),
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
    return service


def _registered_document(
    service: PersistenceService,
    *,
    run_id: str,
    artifact_root: Path,
    document: dict,
):
    content = canonical_json(document).encode("utf-8")
    location = f"artifacts/{run_id}/{MONTE_CARLO_EVIDENCE_LOGICAL_NAME}.json"
    target = artifact_root / location
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    artifact = service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=MONTE_CARLO_EVIDENCE_LOGICAL_NAME,
        media_type="application/json",
        format="json",
        location=location,
        content=content,
    )
    service.persist_run_manifest(service.build_run_manifest(run_id))
    return artifact


def test_monte_carlo_evidence_document_is_canonical() -> None:
    document = build_monte_carlo_evidence_document(
        run_id="mc-run",
        source={"run_id": "mc-run"},
        result=_result(),
    )

    assert json.loads(canonical_json(document)) == document
    assert document["artifact"]["logical_name"] == MONTE_CARLO_EVIDENCE_LOGICAL_NAME
    assert document["evidence"]["monte_carlo"]["config"]["seed"] == 42
    assert "values" not in document["evidence"]["monte_carlo"]["source"]
    assert document["evidence"]["monte_carlo"]["paths"]["embedded"] is False
    assert document["evidence"]["normalized_evidence"]["status"] == "passed"


def test_monte_carlo_evidence_identity_is_deterministic_and_changes() -> None:
    source = {"run_id": "mc-run"}
    first = build_monte_carlo_evidence_document(
        run_id="mc-run",
        source=source,
        result=_result(),
    )
    second = build_monte_carlo_evidence_document(
        run_id="mc-run",
        source=source,
        result=_result(timestamp="2026-01-02T00:00:00+00:00"),
    )
    changed = build_monte_carlo_evidence_document(
        run_id="mc-run",
        source=source,
        result=_result(values=(0.10, 0.08, 0.06, 0.01)),
    )

    assert first["artifact"]["evidence_identity"] == second["artifact"]["evidence_identity"]
    assert first["evidence"]["monte_carlo"]["timestamp"] != (
        second["evidence"]["monte_carlo"]["timestamp"]
    )
    assert first["evidence"]["monte_carlo"]["source"]["source_values_identity"] != (
        changed["evidence"]["monte_carlo"]["source"]["source_values_identity"]
    )
    assert first["artifact"]["evidence_identity"] != changed["artifact"]["evidence_identity"]


def test_monte_carlo_paths_are_not_embedded_when_requested() -> None:
    document = build_monte_carlo_evidence_document(
        run_id="mc-run",
        source={"run_id": "mc-run"},
        result=_result(config=_config(persist_paths=True)),
    )

    native = document["evidence"]["monte_carlo"]
    assert "values" not in native["source"]
    assert "paths" not in native["paths"]
    assert native["paths"] == {
        "availability": "available_in_native_result_not_embedded",
        "embedded": False,
        "path_count": 20,
        "requested": True,
    }


def test_monte_carlo_pass_persists_retrieves_and_manifests(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        evidence = ValidationEvidenceArtifactService(service)
        persisted = evidence.persist_monte_carlo(
            run_id="mc-run",
            result=_result(),
            artifact_root=root,
        )
        retrieved = evidence.retrieve_monte_carlo("mc-run", artifact_root=root)

        assert retrieved.artifact == persisted.artifact
        native = retrieved.document["evidence"]["monte_carlo"]
        normalized = retrieved.document["evidence"]["normalized_evidence"]
        assert native["status"] == "passed"
        assert native["config"]["seed"] == 42
        assert native["config"]["simulation_count"] == 20
        assert native["source"]["source_id"] == "fixture_returns"
        assert native["source"]["observation_count"] == 4
        assert "source_values_identity" in native["source"]
        assert "values" not in native["source"]
        assert native["paths"]["embedded"] is False
        assert native["threshold_results"][0]["rule_id"] == "loss_probability"
        assert native["execution_stress"][0]["status"] == "insufficient_evidence"
        assert native["timestamp"] == "2026-01-01T00:00:00+00:00"
        assert normalized["status"] == "passed"
        assert normalized["protected_data_state"] == "gated"
        assert normalized["eligible_to_progress"] is False

        persisted_manifest = service.read_persisted_run_manifest("mc-run")
        assert persisted_manifest is not None
        manifest = json.loads(persisted_manifest[0])
        assert [artifact["logical_name"] for artifact in manifest["artifacts"]] == [
            MONTE_CARLO_EVIDENCE_LOGICAL_NAME
        ]
    finally:
        service.close()


def test_monte_carlo_failed_status_and_reasons_survive_persistence(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        result = _result(
            values=(-0.20, -0.10, -0.05),
            config=_config(
                maximum_loss_probability=0.0,
                maximum_drawdown_breach_probability=0.0,
                minimum_lower_percentile_return=0.0,
            ),
        )
        persisted = ValidationEvidenceArtifactService(service).persist_monte_carlo(
            run_id="mc-run",
            result=result,
            artifact_root=root,
        )

        normalized = persisted.document["evidence"]["normalized_evidence"]
        assert normalized["status"] == "failed"
        assert normalized["reasons"] == list(result.reasons)
    finally:
        service.close()


def test_monte_carlo_insufficient_evidence_survives_persistence(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        result = _result(
            values=(0.01, 0.02, 0.03),
            config=replace(MonteCarloConfig(), simulation_count=5),
        )
        persisted = ValidationEvidenceArtifactService(service).persist_monte_carlo(
            run_id="mc-run",
            result=result,
            artifact_root=root,
        )

        native = persisted.document["evidence"]["monte_carlo"]
        normalized = persisted.document["evidence"]["normalized_evidence"]
        assert native["config"]["minimum_observations"] == 20
        assert native["status"] == "insufficient_evidence"
        assert normalized["status"] == "insufficient_evidence"
        assert "requires at least 20 observations" in normalized["reasons"][0]
    finally:
        service.close()


def test_monte_carlo_corruption_and_lineage_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        evidence = ValidationEvidenceArtifactService(service)
        persisted = evidence.persist_monte_carlo(
            run_id="mc-run",
            result=_result(),
            artifact_root=root,
        )
        path = root / persisted.artifact.location
        path.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="artifact_.*mismatch"):
            evidence.retrieve_monte_carlo("mc-run", artifact_root=root)
    finally:
        service.close()

    service = _service_with_run(tmp_path, run_id="mc-lineage")
    try:
        document = build_monte_carlo_evidence_document(
            run_id="mc-lineage",
            source=ValidationEvidenceArtifactService(service).source_document("mc-lineage"),
            result=_result(),
        )
        document["source"]["configuration_hash"] = "different"
        _registered_document(
            service,
            run_id="mc-lineage",
            artifact_root=root,
            document=document,
        )
        with pytest.raises(ValueError, match="source lineage mismatch"):
            ValidationEvidenceArtifactService(service).retrieve_monte_carlo(
                "mc-lineage",
                artifact_root=root,
            )
    finally:
        service.close()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("eligible_to_progress", True, "cannot automatically progress"),
        ("protected_data_state", None, "protected-data state"),
        ("protected_data_state", "ready", "protected-data state"),
    ),
)
def test_monte_carlo_retrieval_rejects_progression_contract_mismatch(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_monte_carlo_evidence_document(
            run_id="mc-run",
            source=ValidationEvidenceArtifactService(service).source_document("mc-run"),
            result=_result(),
        )
        normalized = document["evidence"]["normalized_evidence"]
        if value is None:
            normalized.pop(field)
        else:
            normalized[field] = value
        _registered_document(
            service,
            run_id="mc-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match=message):
            ValidationEvidenceArtifactService(service).retrieve_monte_carlo(
                "mc-run",
                artifact_root=root,
            )
    finally:
        service.close()


def test_monte_carlo_wrong_stage_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path, stage=RunStage.FIXTURE)
    try:
        with pytest.raises(ValueError, match="fixture runs"):
            ValidationEvidenceArtifactService(service).persist_monte_carlo(
                run_id="mc-run",
                result=_result(),
                artifact_root=tmp_path / "artifacts",
            )
        assert service.list_run_artifacts("mc-run") == ()
    finally:
        service.close()


def test_monte_carlo_invalid_native_result_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    try:
        result = _result(values=(0.01, float("nan"), 0.03), config=_config())
        with pytest.raises(ValueError, match="does not satisfy evidence contract"):
            ValidationEvidenceArtifactService(service).persist_monte_carlo(
                run_id="mc-run",
                result=result,
                artifact_root=tmp_path / "artifacts",
            )
        assert service.list_run_artifacts("mc-run") == ()
    finally:
        service.close()
