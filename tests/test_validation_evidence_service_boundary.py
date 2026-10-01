"""Independent contract proof for validation-evidence coordination."""

from __future__ import annotations

from types import SimpleNamespace

from backtesting.validation.evidence_service import ValidationEvidenceArtifactService


class _RunRepository:
    def get(self, run_id: str) -> object | None:
        if run_id != "run-1":
            return None
        return SimpleNamespace(stage=SimpleNamespace(value="walk_forward"))


class _ValidationPersistence:
    """Small contract fake; no database or application construction required."""

    runs = _RunRepository()
    configurations = SimpleNamespace()
    reviews = SimpleNamespace()

    def build_run_manifest(self, run_id: str) -> object:
        assert run_id == "run-1"
        lineage = SimpleNamespace(
            configuration=SimpleNamespace(
                configuration_id="config-1", config_hash="config-hash"
            ),
            strategy=SimpleNamespace(strategy_id="strategy-1", strategy_version="1"),
            data=SimpleNamespace(
                provenance_record_identity="provenance",
                provider_identity="provider",
                symbol="MES",
                timeframe="1m",
                requested_coverage="requested",
                actual_coverage="actual",
                dataset_identity="dataset",
                dataset_manifest_reference=None,
                dataset_checksum=None,
                calendar_identity="calendar",
                adjustment_mode="none",
                normalization_identity="normalization",
            ),
            normalization=SimpleNamespace(
                normalization_identity="normalization", contract_json="{}"
            ),
            execution_assumptions=SimpleNamespace(
                execution_assumptions_identity="execution", record_identity="record"
            ),
            runtime=SimpleNamespace(
                runtime_identity="runtime",
                git_commit_sha="sha",
                git_commit_available=True,
                git_dirty_state="clean",
                git_dirty_available=True,
                git_dirty_entry_count=0,
                git_dirty_fingerprint=None,
                python_implementation="CPython",
                python_version="3.12",
                python_cache_tag="cpython-312",
                vectorbtpro_version="fixture",
                vectorbtpro_available=True,
                package_fingerprint="packages",
                package_count=1,
                platform_system="Linux",
                platform_machine="x86_64",
            ),
        )
        return SimpleNamespace(
            schema_version=3,
            run_id=run_id,
            configuration_id="config-1",
            strategy_id="strategy-1",
            strategy_version="1",
            artifacts=(),
            lineage=lineage,
            created_at="2026-10-01T00:00:00+00:00",
        )


def test_validation_evidence_service_executes_against_its_storage_contract() -> None:
    source = ValidationEvidenceArtifactService(_ValidationPersistence()).source_document(
        "run-1"
    )

    assert source == {
        "run_id": "run-1",
        "configuration_id": "config-1",
        "strategy_id": "strategy-1",
        "strategy_version": "1",
        "stage": "walk_forward",
        "configuration_hash": "config-hash",
        "data_identity": "dataset",
        "execution_assumptions_identity": "execution",
        "runtime_identity": "runtime",
    }
