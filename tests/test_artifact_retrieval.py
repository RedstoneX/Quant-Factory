"""Focused regression coverage for Milestone 19D retrieval metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from persistence import (
    ArtifactAvailability,
    ArtifactType,
    canonical_json,
    PersistenceService,
)
from tests.test_artifact_contracts import _register, _service_with_run


def _persist_manifest(service: PersistenceService) -> tuple[str, str]:
    manifest = service.build_run_manifest(
        "artifact-run",
        created_at="2026-07-13T00:00:00Z",
    )
    service.persist_run_manifest(manifest)
    persisted = service.read_persisted_run_manifest("artifact-run")
    assert persisted is not None
    return persisted


def test_retrieval_returns_persisted_manifest_metadata_and_validation(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifact-root"
    target = root / "artifacts" / "metrics.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"value":1}')

    try:
        artifact = _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b'{"value":1}',
        )
        expected_manifest = _persist_manifest(service)

        result = service.retrieve_run_artifacts(
            "artifact-run",
            artifact_root=root,
        )

        assert result.run_id == "artifact-run"
        assert (result.manifest_json, result.manifest_checksum) == expected_manifest
        assert result.artifacts == (artifact,)
        assert len(result.validations) == 1
        assert result.validations[0].artifact_id == artifact.artifact_id
        assert result.validations[0].valid is True
        assert (
            result.validations[0].availability_state
            == ArtifactAvailability.AVAILABLE
        )
    finally:
        service.close()


def test_retrieval_reports_mixed_artifact_validation_states(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifact-root"

    available_path = root / "artifacts" / "available.json"
    available_path.parent.mkdir(parents=True)
    available_path.write_bytes(b"available")

    corrupt_path = root / "artifacts" / "corrupt.json"
    corrupt_path.write_bytes(b"changed")

    try:
        available = _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="available",
            content=b"available",
        )
        missing = _register(
            service,
            artifact_type=ArtifactType.RUN_SUMMARY,
            name="missing",
            content=b"missing",
        )
        corrupt = _register(
            service,
            artifact_type=ArtifactType.EQUITY_CURVE,
            name="corrupt",
            content=b"original",
        )
        _persist_manifest(service)

        result = service.retrieve_run_artifacts(
            "artifact-run",
            artifact_root=root,
        )

        validations = {
            validation.artifact_id: validation
            for validation in result.validations
        }

        assert validations[available.artifact_id].availability_state == (
            ArtifactAvailability.AVAILABLE
        )
        assert validations[missing.artifact_id].availability_state == (
            ArtifactAvailability.MISSING
        )
        assert validations[corrupt.artifact_id].availability_state == (
            ArtifactAvailability.CORRUPT
        )
    finally:
        service.close()


def test_retrieval_requires_known_run_and_persisted_manifest(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    try:
        with pytest.raises(KeyError, match="unknown run"):
            service.retrieve_run_artifacts(
                "unknown-run",
                artifact_root=tmp_path,
            )

        with pytest.raises(RuntimeError, match="has no persisted manifest"):
            service.retrieve_run_artifacts(
                "artifact-run",
                artifact_root=tmp_path,
            )
    finally:
        service.close()


def test_retrieval_is_stable_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "state" / "artifacts.sqlite3"
    root = tmp_path / "artifact-root"
    target = root / "artifacts" / "metrics.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"value":1}')

    service = _service_with_run(tmp_path)
    artifact = _register(
        service,
        artifact_type=ArtifactType.METRICS,
        name="metrics",
        content=b'{"value":1}',
    )
    expected_manifest = _persist_manifest(service)
    service.close()

    restarted = PersistenceService(database)
    try:
        result = restarted.retrieve_run_artifacts(
            "artifact-run",
            artifact_root=root,
        )

        assert result.run_id == "artifact-run"
        assert (result.manifest_json, result.manifest_checksum) == expected_manifest
        assert result.artifacts == (artifact,)
        assert result.validations[0].valid is True
    finally:
        restarted.close()


def test_retrieval_rejects_tampered_persisted_manifest_content(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    try:
        _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b"metrics",
        )
        _persist_manifest(service)

        row = service.connection.execute(
            "SELECT manifest_json FROM run_manifests WHERE run_id=?",
            ("artifact-run",),
        ).fetchone()
        assert row is not None
        tampered = row["manifest_json"].replace(
            '"strategy_version":"1.0.0"',
            '"strategy_version":"9.9.9"',
        )
        assert tampered != row["manifest_json"]

        service.connection.execute(
            "UPDATE run_manifests SET manifest_json=? WHERE run_id=?",
            (tampered, "artifact-run"),
        )
        service.connection.commit()

        with pytest.raises(
            ValueError,
            match="stored run manifest checksum mismatch",
        ):
            service.retrieve_run_artifacts(
                "artifact-run",
                artifact_root=tmp_path,
            )
    finally:
        service.close()


def test_retrieval_rejects_tampered_persisted_manifest_checksum(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    try:
        _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b"metrics",
        )
        _persist_manifest(service)

        service.connection.execute(
            "UPDATE run_manifests SET content_checksum=? WHERE run_id=?",
            ("0" * 64, "artifact-run"),
        )
        service.connection.commit()

        with pytest.raises(
            ValueError,
            match="stored run manifest checksum mismatch",
        ):
            service.retrieve_run_artifacts(
                "artifact-run",
                artifact_root=tmp_path,
            )
    finally:
        service.close()


def test_retrieval_rejects_invalid_persisted_manifest_json(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    try:
        _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b"metrics",
        )
        _persist_manifest(service)

        service.connection.execute(
            "UPDATE run_manifests SET manifest_json=? WHERE run_id=?",
            ("{not-json", "artifact-run"),
        )
        service.connection.commit()

        with pytest.raises(
            ValueError,
            match="stored canonical JSON is invalid",
        ):
            service.retrieve_run_artifacts(
                "artifact-run",
                artifact_root=tmp_path,
            )
    finally:
        service.close()


def test_retrieval_rejects_manifest_for_different_run(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    try:
        _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b"metrics",
        )
        _persist_manifest(service)

        row = service.connection.execute(
            "SELECT manifest_json FROM run_manifests WHERE run_id=?",
            ("artifact-run",),
        ).fetchone()
        assert row is not None
        import json

        document = json.loads(row["manifest_json"])
        document["run_id"] = "different-run"
        tampered = canonical_json(document)
        assert tampered != row["manifest_json"]

        service.connection.execute(
            "UPDATE run_manifests SET manifest_json=? WHERE run_id=?",
            (tampered, "artifact-run"),
        )
        service.connection.commit()

        with pytest.raises(
            ValueError,
            match="stored run manifest identity does not match requested run",
        ):
            service.retrieve_run_artifacts(
                "artifact-run",
                artifact_root=tmp_path,
            )
    finally:
        service.close()


def test_retrieval_rejects_artifact_added_after_manifest_persistence(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    try:
        _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b"metrics",
        )
        _persist_manifest(service)

        _register(
            service,
            artifact_type=ArtifactType.RUN_SUMMARY,
            name="late-summary",
            content=b"late",
        )

        with pytest.raises(
            ValueError,
            match="stored run manifest artifacts do not match database records",
        ):
            service.retrieve_run_artifacts(
                "artifact-run",
                artifact_root=tmp_path,
            )
    finally:
        service.close()


def test_retrieval_rejects_database_artifact_metadata_tampering(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    try:
        artifact = _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b"metrics",
        )
        _persist_manifest(service)

        service.connection.execute(
            """
            UPDATE artifact_references
            SET location=?
            WHERE artifact_id=?
            """,
            ("artifacts/tampered.json", artifact.artifact_id),
        )
        service.connection.commit()

        with pytest.raises(
            ValueError,
            match="stored run manifest artifacts do not match database records",
        ):
            service.retrieve_run_artifacts(
                "artifact-run",
                artifact_root=tmp_path,
            )
    finally:
        service.close()


def test_retrieval_allows_availability_state_to_change_after_manifest(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifact-root"

    try:
        artifact = _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b"metrics",
        )
        _persist_manifest(service)

        service.update_artifact_availability(
            artifact.artifact_id,
            ArtifactAvailability.MISSING,
        )

        result = service.retrieve_run_artifacts(
            "artifact-run",
            artifact_root=root,
        )

        assert result.artifacts[0].availability_state == (
            ArtifactAvailability.MISSING
        )
        assert result.validations[0].availability_state == (
            ArtifactAvailability.MISSING
        )
    finally:
        service.close()
