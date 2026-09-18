"""Focused tests for durable robustness evidence artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtesting.robustness import insufficient_result
from backtesting.robustness.models import (
    CandidateDerivation,
    DimensionStability,
    EvaluatedParameterPoint,
    NeighborhoodCandidate,
    NeighborhoodConstructionResult,
    NeighborhoodSummary,
    RegimeEvaluationResult,
    RegimeLabelMetadata,
    RobustnessResult,
    ThresholdResult,
)
from backtesting.validation.robustness_artifacts import (
    ROBUSTNESS_EVIDENCE_LOGICAL_NAME,
    build_robustness_evidence_document,
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


def _threshold(status: str = "passed") -> ThresholdResult:
    return ThresholdResult(
        rule_id="minimum_valid_neighbors",
        status=status,
        observed=3,
        threshold=3,
        message="minimum valid-neighbor evidence",
    )


def _derivation() -> CandidateDerivation:
    return CandidateDerivation(
        parameter_name="window",
        locked_value=14,
        method="integer_offsets",
        source_value=1,
        raw_value=15,
        normalized_value=15,
        status="accepted",
    )


def _construction() -> NeighborhoodConstructionResult:
    candidate = NeighborhoodCandidate(
        normalized_parameters={"window": 15},
        derivations=(_derivation(),),
        is_locked_point=False,
    )
    return NeighborhoodConstructionResult(
        requested_candidate_count=3,
        raw_derived_count=3,
        unique_normalized_count=3,
        accepted_count=3,
        rejected_count=0,
        duplicate_count=0,
        candidates=(candidate,),
        rejected_derivations=(),
    )


def _point(status: str = "passed") -> EvaluatedParameterPoint:
    return EvaluatedParameterPoint(
        normalized_parameters={"window": 15},
        derivations=(_derivation(),),
        is_locked_point=False,
        status=status,
        total_return=0.08,
        maximum_drawdown=-0.04,
        sharpe_ratio=1.2,
        trade_count=12,
        screening_status="passed",
        hygiene_status="passed",
        absolute_degradation=0.02,
        relative_degradation=0.10,
        degradation_unit="total_return",
        degradation_interpretation="lower_is_worse",
        threshold_results=(_threshold(status),),
        reasons=() if status == "passed" else ("neighbor failed",),
        warnings=(),
        source_run_identity="neighbor-run-1",
    )


def _summary(status: str = "passed") -> NeighborhoodSummary:
    return NeighborhoodSummary(
        requested_candidate_count=3,
        raw_derived_count=3,
        unique_normalized_count=3,
        rejected_count=0,
        duplicate_count=0,
        valid_count=3,
        evaluated_count=3,
        passing_count=3 if status == "passed" else 1,
        passing_proportion=1.0 if status == "passed" else 0.33,
        proportion_within_degradation_limit=1.0 if status == "passed" else 0.33,
        median_total_return=0.08,
        worst_total_return=0.05,
        median_maximum_drawdown=-0.04,
        worst_maximum_drawdown=-0.06,
        median_sharpe=1.1,
        locked_point_rank=1,
        locked_point_status="passed",
        dimension_stability=(
            DimensionStability(
                parameter_name="window",
                tested_values=(13, 14, 15),
                locked_value=14,
                pass_count=3 if status == "passed" else 1,
                return_range=0.03,
                drawdown_range=0.02,
                behavior="monotonic" if status == "passed" else "unstable",
            ),
        ),
        threshold_results=(_threshold(status),),
        status=status,
        reasons=() if status == "passed" else ("minimum valid-neighbor evidence",),
    )


def _regime(status: str = "passed") -> RegimeEvaluationResult:
    return RegimeEvaluationResult(
        regime_id="bullish_low_volatility",
        trend_component="bullish",
        volatility_component="low_volatility",
        first_timestamp="2020-01-01",
        last_timestamp="2020-03-31",
        observation_count=60,
        trade_count=4,
        total_return=0.04,
        maximum_drawdown=-0.02,
        sharpe_ratio=1.0,
        win_rate=0.75,
        minimum_observations=20,
        minimum_trades=None,
        threshold_results=(
            ThresholdResult(
                rule_id="minimum_observations",
                status=status,
                observed=60,
                threshold=20,
                message="minimum regime observations",
            ),
        ),
        status=status,
        reasons=() if status == "passed" else ("minimum regime observations",),
        warnings=("thin regime",) if status != "passed" else (),
    )


def _metadata() -> RegimeLabelMetadata:
    return RegimeLabelMetadata(
        first_usable_timestamp="2020-01-20",
        warmup_observation_count=20,
        trend_rule="close above rolling mean",
        volatility_rule="realized volatility threshold",
        annualization_factor=252.0,
        attribution_policy="entry timestamp",
    )


def _result(
    status: str = "passed",
    *,
    source_artifact_id: str = "source-lock-1",
    timestamp: str = "2026-01-01T00:00:00+00:00",
) -> RobustnessResult:
    reasons = () if status == "passed" else ("robustness fixture reason",)
    return RobustnessResult(
        schema_version=1,
        status=status,
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        experiment_id="robustness-artifact",
        source_artifact_id=source_artifact_id,
        locked_parameters={"window": 14},
        data_provenance={"provider": "fixture", "row_count": 120},
        execution_assumptions={"kind": "fixture", "fees": 0.0005},
        neighborhood_construction=_construction(),
        parameter_points=(_point(status),),
        neighborhood_summary=_summary(status),
        regime_metadata=_metadata(),
        regime_results=(_regime(status),),
        component_statuses={
            "parameter_neighborhood": status,
            "regimes": status,
        },
        reasons=reasons,
        warnings=("passing robustness is not promotion or production approval",),
        timestamp=timestamp,
    )


def _insufficient_result() -> RobustnessResult:
    return insufficient_result(
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        experiment_id="robustness-artifact",
        artifact_id="source-lock-1",
        reasons=("no usable regimes were available",),
    )


def _service_with_run(
    tmp_path: Path,
    *,
    run_id: str = "robust-run",
    stage: RunStage = RunStage.ROBUSTNESS,
) -> PersistenceService:
    service = PersistenceService(tmp_path / "state" / f"{run_id}.sqlite3")
    service.register_strategy(
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        display_name="Fixture Strategy",
        description="Synthetic robustness fixture",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    configuration = service.upsert_configuration(
        normalized_configuration_document(
            experiment_id="robustness-artifact",
            strategy_id="fixture_strategy",
            strategy_version="1.0.0",
            market_data={"symbol": "SPY", "provider": "fixture"},
            parameters={"window": 14},
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
                actual_coverage="2020-01-01..2020-04-30",
                adjusted=True,
                row_count=120,
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
    location = f"artifacts/{run_id}/{ROBUSTNESS_EVIDENCE_LOGICAL_NAME}.json"
    target = artifact_root / location
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    artifact = service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=ROBUSTNESS_EVIDENCE_LOGICAL_NAME,
        media_type="application/json",
        format="json",
        location=location,
        content=content,
    )
    service.persist_run_manifest(service.build_run_manifest(run_id))
    return artifact


def test_robustness_evidence_document_is_canonical_and_compact() -> None:
    document = build_robustness_evidence_document(
        run_id="robust-run",
        source={"run_id": "robust-run"},
        result=_result(),
    )

    assert json.loads(canonical_json(document)) == document
    native = document["evidence"]["robustness"]
    assert document["artifact"]["logical_name"] == ROBUSTNESS_EVIDENCE_LOGICAL_NAME
    assert native["configuration"]["locked_parameters"] == {"window": 14}
    assert native["source"]["source_artifact_id"] == "source-lock-1"
    assert native["parameter_points"][0]["normalized_parameters"] == {"window": 15}
    assert native["regime_results"][0]["regime_id"] == "bullish_low_volatility"
    assert "values" not in native["source"]
    assert "returns" not in native["source"]
    assert "trades" not in native
    assert document["evidence"]["normalized_evidence"]["status"] == "passed"


def test_robustness_evidence_identity_is_deterministic_and_changes() -> None:
    source = {"run_id": "robust-run"}
    first = build_robustness_evidence_document(
        run_id="robust-run",
        source=source,
        result=_result(),
    )
    second = build_robustness_evidence_document(
        run_id="robust-run",
        source=source,
        result=_result(timestamp="2026-01-02T00:00:00+00:00"),
    )
    changed = build_robustness_evidence_document(
        run_id="robust-run",
        source=source,
        result=_result(source_artifact_id="source-lock-2"),
    )

    assert first["artifact"]["evidence_identity"] == second["artifact"]["evidence_identity"]
    assert first["evidence"]["robustness"]["timestamp"] != (
        second["evidence"]["robustness"]["timestamp"]
    )
    assert first["evidence"]["robustness"]["source"]["source_identity"] != (
        changed["evidence"]["robustness"]["source"]["source_identity"]
    )
    assert first["artifact"]["evidence_identity"] != changed["artifact"]["evidence_identity"]


def test_robustness_pass_persists_retrieves_and_manifests(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        evidence = ValidationEvidenceArtifactService(service)
        persisted = evidence.persist_robustness(
            run_id="robust-run",
            result=_result(),
            artifact_root=root,
        )
        retrieved = evidence.retrieve_robustness("robust-run", artifact_root=root)

        assert retrieved.artifact == persisted.artifact
        native = retrieved.document["evidence"]["robustness"]
        normalized = retrieved.document["evidence"]["normalized_evidence"]
        assert native["status"] == "passed"
        assert native["configuration"]["strategy_id"] == "fixture_strategy"
        assert native["source"]["data_provenance"]["provider"] == "fixture"
        assert native["neighborhood_summary"]["threshold_results"][0]["rule_id"] == (
            "minimum_valid_neighbors"
        )
        assert native["regime_results"][0]["threshold_results"][0]["rule_id"] == (
            "minimum_observations"
        )
        assert native["timestamp"] == "2026-01-01T00:00:00+00:00"
        assert normalized["status"] == "passed"
        assert normalized["protected_data_state"] == "gated"
        assert normalized["eligible_to_progress"] is False

        persisted_manifest = service.read_persisted_run_manifest("robust-run")
        assert persisted_manifest is not None
        manifest = json.loads(persisted_manifest[0])
        assert [artifact["logical_name"] for artifact in manifest["artifacts"]] == [
            ROBUSTNESS_EVIDENCE_LOGICAL_NAME
        ]
    finally:
        service.close()


def test_robustness_failed_and_insufficient_statuses_survive_persistence(
    tmp_path: Path,
) -> None:
    failed_service = _service_with_run(tmp_path, run_id="robust-failed")
    root = tmp_path / "artifacts"
    try:
        persisted = ValidationEvidenceArtifactService(failed_service).persist_robustness(
            run_id="robust-failed",
            result=_result("failed"),
            artifact_root=root,
        )
        normalized = persisted.document["evidence"]["normalized_evidence"]
        assert normalized["status"] == "failed"
        assert normalized["reasons"] == ["robustness fixture reason"]
    finally:
        failed_service.close()

    insufficient_service = _service_with_run(tmp_path, run_id="robust-insufficient")
    try:
        persisted = ValidationEvidenceArtifactService(
            insufficient_service
        ).persist_robustness(
            run_id="robust-insufficient",
            result=_insufficient_result(),
            artifact_root=root,
        )
        normalized = persisted.document["evidence"]["normalized_evidence"]
        assert normalized["status"] == "insufficient_evidence"
        assert normalized["reasons"] == ["no usable regimes were available"]
    finally:
        insufficient_service.close()


def test_robustness_corruption_and_lineage_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        evidence = ValidationEvidenceArtifactService(service)
        persisted = evidence.persist_robustness(
            run_id="robust-run",
            result=_result(),
            artifact_root=root,
        )
        path = root / persisted.artifact.location
        path.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="artifact_.*mismatch"):
            evidence.retrieve_robustness("robust-run", artifact_root=root)
    finally:
        service.close()

    service = _service_with_run(tmp_path, run_id="robust-lineage")
    try:
        document = build_robustness_evidence_document(
            run_id="robust-lineage",
            source=ValidationEvidenceArtifactService(service).source_document(
                "robust-lineage"
            ),
            result=_result(),
        )
        document["source"]["configuration_hash"] = "different"
        _registered_document(
            service,
            run_id="robust-lineage",
            artifact_root=root,
            document=document,
        )
        with pytest.raises(ValueError, match="source lineage mismatch"):
            ValidationEvidenceArtifactService(service).retrieve_robustness(
                "robust-lineage",
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
def test_robustness_retrieval_rejects_progression_contract_mismatch(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_robustness_evidence_document(
            run_id="robust-run",
            source=ValidationEvidenceArtifactService(service).source_document("robust-run"),
            result=_result(),
        )
        normalized = document["evidence"]["normalized_evidence"]
        if value is None:
            normalized.pop(field)
        else:
            normalized[field] = value
        _registered_document(
            service,
            run_id="robust-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match=message):
            ValidationEvidenceArtifactService(service).retrieve_robustness(
                "robust-run",
                artifact_root=root,
            )
    finally:
        service.close()


def test_robustness_wrong_stage_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path, stage=RunStage.FIXTURE)
    try:
        with pytest.raises(ValueError, match="fixture runs"):
            ValidationEvidenceArtifactService(service).persist_robustness(
                run_id="robust-run",
                result=_result(),
                artifact_root=tmp_path / "artifacts",
            )
        assert service.list_run_artifacts("robust-run") == ()
    finally:
        service.close()


def test_robustness_invalid_native_result_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    try:
        invalid = insufficient_result(
            strategy_id="fixture_strategy",
            strategy_version="1.0.0",
            experiment_id="robustness-artifact",
            artifact_id="source-lock-1",
            reasons=("invalid lock",),
            invalid=True,
        )
        with pytest.raises(ValueError, match="does not satisfy evidence contract"):
            ValidationEvidenceArtifactService(service).persist_robustness(
                run_id="robust-run",
                result=invalid,
                artifact_root=tmp_path / "artifacts",
            )
        assert service.list_run_artifacts("robust-run") == ()
    finally:
        service.close()


def test_robustness_retrieval_rejects_wrong_identity_fields(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_robustness_evidence_document(
            run_id="robust-run",
            source=ValidationEvidenceArtifactService(service).source_document("robust-run"),
            result=_result(),
        )
        document["artifact_kind"] = "not_robustness"
        _registered_document(
            service,
            run_id="robust-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match="artifact kind"):
            ValidationEvidenceArtifactService(service).retrieve_robustness(
                "robust-run",
                artifact_root=root,
            )
    finally:
        service.close()


def test_robustness_retrieval_rejects_stale_source_identity(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_robustness_evidence_document(
            run_id="robust-run",
            source=ValidationEvidenceArtifactService(service).source_document("robust-run"),
            result=_result(),
        )
        document["evidence"]["robustness"]["source"]["data_provenance"][
            "provider"
        ] = "changed"
        _registered_document(
            service,
            run_id="robust-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match="source identity mismatch"):
            ValidationEvidenceArtifactService(service).retrieve_robustness(
                "robust-run",
                artifact_root=root,
            )
    finally:
        service.close()


def test_robustness_retrieval_rejects_stale_configuration_identity(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_robustness_evidence_document(
            run_id="robust-run",
            source=ValidationEvidenceArtifactService(service).source_document("robust-run"),
            result=_result(),
        )
        document["evidence"]["robustness"]["configuration"]["locked_parameters"][
            "window"
        ] = 21
        _registered_document(
            service,
            run_id="robust-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match="configuration identity mismatch"):
            ValidationEvidenceArtifactService(service).retrieve_robustness(
                "robust-run",
                artifact_root=root,
            )
    finally:
        service.close()
