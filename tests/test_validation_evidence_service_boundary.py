"""Independent contract proof for validation-evidence coordination, against a real research database."""

from __future__ import annotations

from pathlib import Path

from backtesting.validation.evidence_service import ValidationEvidenceArtifactService
from tests.test_artifact_contracts import _service_with_run


def test_validation_evidence_service_reads_its_source_identity_from_the_saved_run(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path, "run-1")
    try:
        run = service.runs.get("run-1")
        lineage = service.build_run_manifest("run-1").lineage
        source = ValidationEvidenceArtifactService(service).source_document("run-1")
    finally:
        service.close()

    assert source == {
        "run_id": "run-1",
        "configuration_id": run.configuration_id,
        "strategy_id": "fixture_strategy",
        "strategy_version": "1.0.0",
        "stage": "fixture",
        "configuration_hash": lineage.configuration.config_hash,
        "data_identity": lineage.data.dataset_identity,
        "execution_assumptions_identity": lineage.execution_assumptions.execution_assumptions_identity,
        "runtime_identity": lineage.runtime.runtime_identity,
    }
    assert all(isinstance(value, str) and value for value in source.values())
