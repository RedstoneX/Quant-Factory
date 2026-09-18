"""Focused regression coverage for Milestone 19D artifact validation primitives."""

from __future__ import annotations

from pathlib import Path

from persistence import (
    ArtifactAvailability,
    ArtifactType,
)
from tests.test_artifact_contracts import _register, _service_with_run


def test_valid_artifact_matches_registered_checksum_and_size(tmp_path: Path) -> None:
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

        result = service.validate_artifact(
            artifact.artifact_id,
            artifact_root=root,
        )

        assert result.valid is True
        assert result.availability_state == ArtifactAvailability.AVAILABLE
        assert result.reason == "validated"
        assert result.actual_checksum == artifact.checksum
        assert result.actual_size_bytes == artifact.size_bytes
        assert result.resolved_path == str(target.resolve())
    finally:
        service.close()


def test_missing_artifact_is_reported_without_mutating_metadata(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifact-root"

    try:
        artifact = _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b'{"value":1}',
        )

        result = service.validate_artifact(
            artifact.artifact_id,
            artifact_root=root,
        )

        assert result.valid is False
        assert result.availability_state == ArtifactAvailability.MISSING
        assert result.reason == "artifact_missing"
        assert result.actual_checksum is None
        assert result.actual_size_bytes is None

        persisted = service.get_artifact_metadata(artifact.artifact_id)
        assert persisted.availability_state == ArtifactAvailability.AVAILABLE
    finally:
        service.close()


def test_changed_artifact_content_is_reported_as_corrupt(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifact-root"
    target = root / "artifacts" / "metrics.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b'{"value":2}')

    try:
        artifact = _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=b'{"value":1}',
        )

        result = service.validate_artifact(
            artifact.artifact_id,
            artifact_root=root,
        )

        assert result.valid is False
        assert result.availability_state == ArtifactAvailability.CORRUPT
        assert result.reason in {
            "artifact_size_mismatch",
            "artifact_checksum_mismatch",
        }
        assert result.actual_checksum != artifact.checksum
    finally:
        service.close()


def test_unsafe_artifact_location_is_rejected(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)

    try:
        artifact = _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="unsafe",
            content=b"unsafe",
            location="../outside.json",
        )

        result = service.validate_artifact(
            artifact.artifact_id,
            artifact_root=tmp_path / "artifact-root",
        )

        assert result.valid is False
        assert result.availability_state == ArtifactAvailability.CORRUPT
        assert result.reason == "unsafe_artifact_location"
        assert result.resolved_path is None
    finally:
        service.close()


def test_validation_result_is_stable_across_restart(tmp_path: Path) -> None:
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
    first = service.validate_artifact(
        artifact.artifact_id,
        artifact_root=root,
    )
    service.close()

    from persistence import PersistenceService

    restarted = PersistenceService(database)
    try:
        second = restarted.validate_artifact(
            artifact.artifact_id,
            artifact_root=root,
        )
        assert second == first
    finally:
        restarted.close()
