"""Run manifest document serialization helpers."""

from __future__ import annotations

from typing import Any

from persistence.models import RunLineage, RunManifest, RuntimeLineage

PACKAGE_FINGERPRINT_ALGORITHM = "sha256:canonical-json:normalized-package-name-version-pairs:v1"


def _json_document(value: str) -> Any:
    import json

    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("stored canonical JSON is invalid") from exc


def run_manifest_document(
    manifest: RunManifest,
    *,
    include_mutable: bool,
) -> dict[str, Any]:
    artifacts = []
    for artifact in manifest.artifacts:
        entry = {
            "artifact_id": artifact.artifact_id,
            "run_id": artifact.run_id,
            "artifact_type": artifact.artifact_type.value,
            "logical_name": artifact.logical_name,
            "schema_version": artifact.schema_version,
            "media_type": artifact.media_type,
            "format": artifact.format,
            "checksum_algorithm": artifact.checksum_algorithm,
            "checksum": artifact.checksum,
            "size_bytes": artifact.size_bytes,
            "location": artifact.location,
            "created_at": artifact.created_at,
        }
        if include_mutable:
            entry["availability_state"] = artifact.availability_state.value
        artifacts.append(entry)
    document = {
        "manifest_schema_version": manifest.schema_version,
        "run_id": manifest.run_id,
        "configuration_id": manifest.configuration_id,
        "strategy_id": manifest.strategy_id,
        "strategy_version": manifest.strategy_version,
        "artifacts": artifacts,
    }
    if manifest.lineage is not None:
        document["lineage"] = run_lineage_document(manifest.lineage)
    if include_mutable:
        document["created_at"] = manifest.created_at
    return document


def run_lineage_document(lineage: RunLineage) -> dict[str, Any]:
    return {
        "configuration": {
            "configuration_id": lineage.configuration.configuration_id,
            "config_hash": lineage.configuration.config_hash,
        },
        "strategy": {
            "strategy_id": lineage.strategy.strategy_id,
            "strategy_version": lineage.strategy.strategy_version,
        },
        "data": {
            "provenance_record_identity": lineage.data.provenance_record_identity,
            "provider_identity": lineage.data.provider_identity,
            "symbol": lineage.data.symbol,
            "timeframe": lineage.data.timeframe,
            "requested_coverage": lineage.data.requested_coverage,
            "actual_coverage": lineage.data.actual_coverage,
            "dataset_identity": lineage.data.dataset_identity,
            "dataset_manifest_reference": lineage.data.dataset_manifest_reference,
            "dataset_checksum": lineage.data.dataset_checksum,
            "calendar_identity": lineage.data.calendar_identity,
            "adjustment_mode": lineage.data.adjustment_mode,
            "normalization_identity": lineage.data.normalization_identity,
        },
        "normalization": {
            "normalization_identity": lineage.normalization.normalization_identity,
            "contract": _json_document(lineage.normalization.contract_json),
        },
        "execution_assumptions": {
            "execution_assumptions_identity": (
                lineage.execution_assumptions.execution_assumptions_identity
            ),
            "record_identity": lineage.execution_assumptions.record_identity,
        },
        "runtime": runtime_lineage_document(lineage.runtime),
    }


def runtime_lineage_document(lineage: RuntimeLineage) -> dict[str, Any]:
    return {
        "runtime_identity": lineage.runtime_identity,
        "git": {
            "commit_sha": lineage.git_commit_sha,
            "commit_available": lineage.git_commit_available,
            "dirty_state": lineage.git_dirty_state,
            "dirty_available": lineage.git_dirty_available,
            "dirty_entry_count": lineage.git_dirty_entry_count,
            "dirty_fingerprint": lineage.git_dirty_fingerprint,
        },
        "python": {
            "implementation": lineage.python_implementation,
            "version": lineage.python_version,
            "cache_tag": lineage.python_cache_tag,
        },
        "vectorbtpro": {
            "version": lineage.vectorbtpro_version,
            "available": lineage.vectorbtpro_available,
        },
        "packages": {
            "fingerprint": lineage.package_fingerprint,
            "fingerprint_algorithm": PACKAGE_FINGERPRINT_ALGORITHM,
            "count": lineage.package_count,
        },
        "platform": {
            "system": lineage.platform_system,
            "machine": lineage.platform_machine,
        },
    }
