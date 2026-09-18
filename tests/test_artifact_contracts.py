"""Focused regression coverage for the Milestone 19A artifact contract."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import hashlib

import pytest

from persistence import (
    LATEST_SCHEMA_VERSION,
    ArtifactAvailability,
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    initialize_database,
    canonical_json,
)
from persistence.database import transaction
import persistence.database as database_module
from persistence.models import normalized_configuration_document
from tests.test_persistence import _register_strategy


def _service_with_run(tmp_path: Path, run_id: str = "artifact-run") -> PersistenceService:
    service = PersistenceService(tmp_path / "state" / "artifacts.sqlite3")
    _register_strategy(service)
    configuration = service.upsert_configuration(
        normalized_configuration_document(
            experiment_id="artifact-contract",
            strategy_id="fixture_strategy",
            strategy_version="1.0.0",
            market_data={"kind": "none"},
            parameters={"fixture": True},
            execution={"kind": "fixture"},
            ranking={"columns": ("value",), "ascending": (False,)},
            screening={"kind": "none"},
        )
    )
    service.create_run(
        configuration_id=configuration.configuration_id,
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        stage=RunStage.FIXTURE,
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
                timezone="America/New_York",
                requested_coverage="2020-01-01",
                actual_coverage="2020-01-02..2020-01-10",
                adjusted=True,
                row_count=7,
                cache_action="reused",
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


def _register(service: PersistenceService, *, artifact_type: ArtifactType, name: str, content: bytes, location: str | None = None):
    return service.register_artifact(
        run_id="artifact-run",
        artifact_type=artifact_type,
        logical_name=name,
        media_type="application/json",
        format="json",
        location=location or f"artifacts/{name}.json",
        content=BytesIO(content),
    )


def test_artifact_identity_checksum_and_duplicate_registration_are_stable(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    try:
        first = _register(
            service, artifact_type=ArtifactType.PARAMETER_RESULTS, name="parameters", content=b'{"alpha":1}'
        )
        duplicate = _register(
            service, artifact_type=ArtifactType.PARAMETER_RESULTS, name="parameters", content=b'{"alpha":1}'
        )
        distinct_name = _register(
            service, artifact_type=ArtifactType.PARAMETER_RESULTS, name="parameters-copy", content=b'{"alpha":1}'
        )

        assert first.artifact_id == duplicate.artifact_id
        assert first.checksum == hashlib.sha256(b'{"alpha":1}').hexdigest()
        assert first.checksum_algorithm == "sha256"
        assert first.checksum == first.checksum.lower()
        assert distinct_name.artifact_id != first.artifact_id
        assert distinct_name.checksum == first.checksum

        with pytest.raises(ValueError, match="immutable artifact identity conflicts"):
            _register(
                service, artifact_type=ArtifactType.PARAMETER_RESULTS, name="parameters", content=b'{"alpha":2}'
            )
    finally:
        service.close()


def test_artifacts_are_ordered_and_availability_is_the_only_mutable_contract_field(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    try:
        later = _register(service, artifact_type=ArtifactType.RUN_SUMMARY, name="z-summary", content=b"summary")
        first = _register(service, artifact_type=ArtifactType.EQUITY_CURVE, name="a-equity", content=b"curve")
        ordered = service.list_run_artifacts("artifact-run")
        assert [artifact.artifact_id for artifact in ordered] == [first.artifact_id, later.artifact_id]

        unavailable = service.update_artifact_availability(first.artifact_id, ArtifactAvailability.UNAVAILABLE)
        assert unavailable.artifact_id == first.artifact_id
        assert unavailable.checksum == first.checksum
        assert unavailable.availability_state == ArtifactAvailability.UNAVAILABLE
    finally:
        service.close()


def test_manifest_is_canonical_and_its_checksum_excludes_time_and_availability(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    try:
        _register(service, artifact_type=ArtifactType.METRICS, name="metrics", content=b"metrics")
        manifest = service.build_run_manifest("artifact-run", created_at="2026-07-13T00:00:00Z")
        later_manifest = service.build_run_manifest("artifact-run", created_at="2026-07-14T00:00:00Z")
        serialized = service.serialize_run_manifest(manifest)
        assert serialized == service.serialize_run_manifest(manifest)
        assert service.run_manifest_checksum(manifest) == service.run_manifest_checksum(later_manifest)

        service.update_artifact_availability(manifest.artifacts[0].artifact_id, ArtifactAvailability.MISSING)
        changed_availability = service.build_run_manifest("artifact-run", created_at="2026-07-15T00:00:00Z")
        assert service.run_manifest_checksum(manifest) == service.run_manifest_checksum(changed_availability)

        service.persist_run_manifest(changed_availability)
        expected = (service.serialize_run_manifest(changed_availability), service.run_manifest_checksum(changed_availability))
    finally:
        service.close()

    restarted = PersistenceService(tmp_path / "state" / "artifacts.sqlite3")
    try:
        assert restarted.get_artifact_metadata(manifest.artifacts[0].artifact_id).checksum == manifest.artifacts[0].checksum
        assert restarted.read_persisted_run_manifest("artifact-run") == expected
        reconstructed = restarted.build_run_manifest("artifact-run", created_at="2026-07-15T00:00:00Z")
        assert restarted.serialize_run_manifest(reconstructed) == expected[0]
        assert reconstructed.schema_version == 3
        assert reconstructed.lineage is not None
    finally:
        restarted.close()


def test_v3_artifact_rows_migrate_forward_and_remain_readable(tmp_path: Path) -> None:
    path = tmp_path / "state" / "v3.sqlite3"
    connection = database_module.connect(path)
    try:
        database_module._migrate_empty_to_v1(connection)
        database_module._migrate_v1_to_v2(connection)
        database_module._migrate_v2_to_v3(connection)
        connection.execute(
            "INSERT INTO strategies VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy", "1", "Legacy", "legacy", "infrastructure_fixture", 1, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO experiment_configurations VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("legacy-config", "legacy", "legacy", "1", "{}", "legacy-hash", "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO experiment_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-run", "legacy-config", "legacy", "1", "fixture", "created", None, None, None, "{}", "2026-01-01T00:00:00Z", 0),
        )
        connection.execute(
            "INSERT INTO artifact_references (run_id, artifact_type, schema_version, path, validation_status, checksum, availability, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-run", "fixture_json", 1, "legacy.json", "validated", "abc", "available", "2026-01-01T00:00:00Z"),
        )
        connection.commit()
    finally:
        connection.close()

    migrated = initialize_database(path)
    try:
        assert migrated.execute("SELECT schema_version FROM schema_metadata").fetchone()["schema_version"] == LATEST_SCHEMA_VERSION == 5
        assert migrated.execute(
            "SELECT run_id FROM experiment_runs WHERE run_id='legacy-run'"
        ).fetchone()["run_id"] == "legacy-run"
        assert migrated.execute(
            "SELECT COUNT(*) FROM research_run_submissions"
        ).fetchone()[0] == 0
    finally:
        migrated.close()
    service = PersistenceService(path)
    try:
        legacy = service.results.list_artifacts("legacy-run")
        assert len(legacy) == 1
        assert legacy[0].path == "legacy.json"
    finally:
        service.close()
