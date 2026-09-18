"""End-to-end acceptance coverage for Milestone 19."""

from __future__ import annotations

from pathlib import Path

import pytest

from persistence import (
    ArtifactAvailability,
    ArtifactType,
    PersistenceService,
)
from tests.test_artifact_contracts import _register, _service_with_run


_CREATED_AT = "2026-07-13T00:00:00Z"


def _build_persisted_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, tuple[int, ...], tuple[str, str]]:
    database = tmp_path / "state" / "artifacts.sqlite3"
    artifact_root = tmp_path / "artifact-root"

    metrics_content = b'{"return":0.12,"trades":7}'
    summary_content = b'{"status":"complete"}'

    metrics_path = artifact_root / "artifacts" / "metrics.json"
    summary_path = artifact_root / "artifacts" / "summary.json"
    metrics_path.parent.mkdir(parents=True)
    metrics_path.write_bytes(metrics_content)
    summary_path.write_bytes(summary_content)

    service = _service_with_run(tmp_path)
    try:
        metrics = _register(
            service,
            artifact_type=ArtifactType.METRICS,
            name="metrics",
            content=metrics_content,
        )
        summary = _register(
            service,
            artifact_type=ArtifactType.RUN_SUMMARY,
            name="summary",
            content=summary_content,
        )

        manifest = service.build_run_manifest(
            "artifact-run",
            created_at=_CREATED_AT,
        )
        service.persist_run_manifest(manifest)

        persisted = service.read_persisted_run_manifest("artifact-run")
        assert persisted is not None

        artifact_ids = tuple(
            artifact.artifact_id
            for artifact in service.list_run_artifacts("artifact-run")
        )
        assert artifact_ids == (
            metrics.artifact_id,
            summary.artifact_id,
        )

        return database, artifact_root, artifact_ids, persisted
    finally:
        service.close()


def test_milestone19_fixture_reproduces_from_saved_manifest_after_restart(
    tmp_path: Path,
) -> None:
    database, artifact_root, artifact_ids, persisted = (
        _build_persisted_fixture(tmp_path)
    )

    restarted = PersistenceService(database)
    try:
        retrieval = restarted.retrieve_run_artifacts(
            "artifact-run",
            artifact_root=artifact_root,
        )

        assert retrieval.run_id == "artifact-run"
        assert (
            retrieval.manifest_json,
            retrieval.manifest_checksum,
        ) == persisted
        assert tuple(
            artifact.artifact_id
            for artifact in retrieval.artifacts
        ) == artifact_ids
        assert all(validation.valid for validation in retrieval.validations)
        assert all(
            validation.availability_state
            == ArtifactAvailability.AVAILABLE
            for validation in retrieval.validations
        )

        reconstructed = restarted.build_run_manifest(
            "artifact-run",
            created_at=_CREATED_AT,
        )
        assert (
            restarted.run_manifest_checksum(reconstructed)
            == retrieval.manifest_checksum
        )
        assert (
            restarted.serialize_run_manifest(reconstructed)
            == retrieval.manifest_json
        )
    finally:
        restarted.close()


def test_milestone19_detects_missing_and_corrupt_artifacts_after_restart(
    tmp_path: Path,
) -> None:
    database, artifact_root, artifact_ids, _ = (
        _build_persisted_fixture(tmp_path)
    )

    (artifact_root / "artifacts" / "metrics.json").unlink()
    (artifact_root / "artifacts" / "summary.json").write_bytes(
        b'{"status":"tampered"}'
    )

    restarted = PersistenceService(database)
    try:
        retrieval = restarted.retrieve_run_artifacts(
            "artifact-run",
            artifact_root=artifact_root,
        )
        validations = {
            validation.artifact_id: validation
            for validation in retrieval.validations
        }

        assert validations[artifact_ids[0]].availability_state == (
            ArtifactAvailability.MISSING
        )
        assert validations[artifact_ids[0]].valid is False

        assert validations[artifact_ids[1]].availability_state == (
            ArtifactAvailability.CORRUPT
        )
        assert validations[artifact_ids[1]].valid is False
    finally:
        restarted.close()


def test_milestone19_rejects_altered_saved_manifest_after_restart(
    tmp_path: Path,
) -> None:
    database, artifact_root, _, _ = _build_persisted_fixture(tmp_path)

    service = PersistenceService(database)
    try:
        row = service.connection.execute(
            """
            SELECT manifest_json
            FROM run_manifests
            WHERE run_id=?
            """,
            ("artifact-run",),
        ).fetchone()
        assert row is not None

        altered = row["manifest_json"].replace(
            '"strategy_version":"1.0.0"',
            '"strategy_version":"9.9.9"',
        )
        assert altered != row["manifest_json"]

        service.connection.execute(
            """
            UPDATE run_manifests
            SET manifest_json=?
            WHERE run_id=?
            """,
            (altered, "artifact-run"),
        )
        service.connection.commit()
    finally:
        service.close()

    restarted = PersistenceService(database)
    try:
        with pytest.raises(
            ValueError,
            match="stored run manifest checksum mismatch",
        ):
            restarted.retrieve_run_artifacts(
                "artifact-run",
                artifact_root=artifact_root,
            )
    finally:
        restarted.close()


def test_milestone19_rejects_mismatched_artifact_metadata_after_restart(
    tmp_path: Path,
) -> None:
    database, artifact_root, artifact_ids, _ = (
        _build_persisted_fixture(tmp_path)
    )

    service = PersistenceService(database)
    try:
        service.connection.execute(
            """
            UPDATE artifact_references
            SET location=?
            WHERE artifact_id=?
            """,
            (
                "artifacts/mismatched.json",
                artifact_ids[0],
            ),
        )
        service.connection.commit()
    finally:
        service.close()

    restarted = PersistenceService(database)
    try:
        with pytest.raises(
            ValueError,
            match=(
                "stored run manifest artifacts "
                "do not match database records"
            ),
        ):
            restarted.retrieve_run_artifacts(
                "artifact-run",
                artifact_root=artifact_root,
            )
    finally:
        restarted.close()
