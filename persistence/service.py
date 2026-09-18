"""Transactional facade and experiment-result adapter for persistence."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from importlib import metadata
import json
import math
import hashlib
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys
from typing import Any
from uuid import uuid4

import pandas as pd

from backtesting.experiments.models import ExperimentConfig, ExperimentResult
from backtesting.validation.evidence_decision_artifacts import (
    EVIDENCE_DECISION_LOGICAL_NAME,
)
from backtesting.validation.review_context_artifacts import REVIEW_CONTEXT_LOGICAL_NAME
from persistence.database import initialize_database, transaction
from persistence.manifest import (
    PACKAGE_FINGERPRINT_ALGORITHM,
    run_manifest_document,
    runtime_lineage_document,
)
from persistence.models import (
    ArtifactAvailability,
    ArtifactContractRecord,
    ArtifactType,
    ArtifactValidationResult,
    ConfigurationLineage,
    ConfigurationRecord,
    DataLineage,
    DataProvenanceRecord,
    ExecutionAssumptionLineage,
    ExecutionAssumptionsRecord,
    EventSeverity,
    ExperimentRunRecord,
    NormalizationLineage,
    ReviewRecord,
    ReviewState,
    RunStage,
    RunEventRecord,
    RunEventType,
    RunLineage,
    RunStatus,
    RunManifest,
    RunArtifactRetrieval,
    RuntimeLineage,
    StrategyLifecycle,
    StrategyLineage,
    StrategyRecord,
    normalized_configuration_document,
)
from persistence.repositories import (
    ConfigurationRepository,
    ResultRepository,
    RunEventRepository,
    ReviewRepository,
    RunRepository,
    StrategyRepository,
    record_to_dict,
    utc_now,
)
from persistence.serialization import canonical_json, configuration_hash

METRIC_COLUMNS = (
    "total_return",
    "annualized_return",
    "sharpe_ratio",
    "max_drawdown",
    "number_of_trades",
    "win_rate",
)
NORMALIZATION_CONTRACT_VERSION = "data_provenance.normalization.v1"
NORMALIZATION_CONTRACT_RULES = {
    "timestamp_convention": "source_timestamp_recorded_in_provenance",
    "timezone_handling": "timezone_recorded_in_provenance",
    "column_schema_version": "ohlcv.v1",
    "adjustment_handling": "adjustment_mode_recorded_in_provenance",
    "session_filtering": "coverage_recorded_in_provenance",
    "duplicate_handling": "duplicate_count_recorded_in_provenance",
    "missing_bar_policy": "missing_bar_counts_recorded_in_provenance",
    "resampling_rule": "timeframe_recorded_in_provenance",
}
RUN_MANIFEST_SCHEMA_VERSION = 3
DIRTY_WORKTREE_FINGERPRINT_ALGORITHM = "sha256:git-dirty-worktree:v1"
RUNTIME_LINEAGE_ENVIRONMENT_KEY = "runtime_lineage"


class RunCompletionRejectedError(RuntimeError):
    """Raised when a terminal run attempts to write completion output."""


def _parse_utc_timestamp(value: str, *, label: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{label} must be an ISO-8601 UTC timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{label} must include a UTC offset")
    return timestamp.astimezone(timezone.utc)


def _artifact_contract_document(
    artifact: ArtifactContractRecord,
) -> dict[str, Any]:
    return {
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


def _persisted_manifest_checksum(manifest_json: str) -> str:
    document = _json_document(manifest_json)
    if not isinstance(document, dict):
        raise ValueError("stored run manifest is not a JSON object")

    immutable_document = dict(document)
    immutable_document.pop("created_at", None)

    artifacts = immutable_document.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("stored run manifest artifacts are not a JSON array")

    immutable_artifacts = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("stored run manifest artifact is not a JSON object")
        immutable_artifact = dict(artifact)
        immutable_artifact.pop("availability_state", None)
        immutable_artifacts.append(immutable_artifact)

    immutable_document["artifacts"] = immutable_artifacts
    return hashlib.sha256(
        canonical_json(immutable_document).encode("utf-8")
    ).hexdigest()


def _identity(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _json_document(value: str) -> Any:
    import json

    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("stored canonical JSON is invalid") from exc


def _normalization_contract() -> dict[str, Any]:
    return {
        "schema_version": NORMALIZATION_CONTRACT_VERSION,
        **NORMALIZATION_CONTRACT_RULES,
    }


def _normalize_package_name(name: str) -> str:
    import re

    return re.sub(r"[-_.]+", "-", name).lower()


def installed_package_fingerprint(
    packages: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> tuple[str, int]:
    pairs = sorted(
        {
            (
                _normalize_package_name(str(name).strip()),
                str(version).strip(),
            )
            for name, version in packages
        }
    )
    document = {
        "algorithm": PACKAGE_FINGERPRINT_ALGORITHM,
        "packages": [{"name": name, "version": version} for name, version in pairs],
    }
    return _identity(document), len(pairs)


def _installed_packages() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name or not version:
            raise RuntimeError("installed package metadata missing name or version")
        pairs.append((name, version))
    return tuple(pairs)


def _git_output(args: list[str], *, cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _git_output_bytes(args: list[str], *, cwd: Path) -> bytes | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _dirty_worktree_fingerprint(repository_root: Path, *, status: str) -> str | None:
    staged_diff = _git_output_bytes(
        ["diff", "--cached", "--binary", "--no-ext-diff"],
        cwd=repository_root,
    )
    unstaged_diff = _git_output_bytes(
        ["diff", "--binary", "--no-ext-diff"],
        cwd=repository_root,
    )
    untracked_output = _git_output_bytes(
        ["ls-files", "--others", "--exclude-standard", "-z"],
        cwd=repository_root,
    )
    if staged_diff is None or unstaged_diff is None or untracked_output is None:
        return None
    untracked_files = []
    for raw_path in sorted(path for path in untracked_output.split(b"\0") if path):
        relative_path = raw_path.decode("utf-8")
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RuntimeError("git returned an unsafe untracked repository path")
        full_path = repository_root / candidate
        if not full_path.is_file():
            continue
        content = full_path.read_bytes()
        untracked_files.append(
            {
                "path": relative_path,
                "content_sha256": _sha256_bytes(content),
                "size_bytes": len(content),
            }
        )
    document = {
        "algorithm": DIRTY_WORKTREE_FINGERPRINT_ALGORITHM,
        "state": "dirty" if status else "clean",
        "staged_tracked_diff_sha256": _sha256_bytes(staged_diff),
        "unstaged_tracked_diff_sha256": _sha256_bytes(unstaged_diff),
        "untracked_files": untracked_files,
    }
    return _identity(document)


def _git_lineage(repository_root: Path) -> dict[str, Any]:
    commit = _git_output(["rev-parse", "--verify", "HEAD"], cwd=repository_root)
    status = _git_output(
        ["status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repository_root,
    )
    commit_sha = commit.strip() if commit is not None else None
    if commit_sha is None:
        # Container images may omit .git. This file is build metadata only; it
        # is not signed provenance and is never sourced from an environment var.
        revision_file = repository_root / ".qf-build-revision"
        try:
            candidate = revision_file.read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError):
            candidate = None
        if candidate is not None and re.fullmatch(r"[0-9a-f]{40}", candidate):
            commit_sha = candidate
    status_lines = [] if status is None else [line for line in status.splitlines() if line]
    dirty_fingerprint = (
        None if status is None else _dirty_worktree_fingerprint(repository_root, status=status)
    )
    if status is not None and dirty_fingerprint is None:
        raise RuntimeError("git dirty-worktree fingerprint could not be determined")
    return {
        "commit_sha": commit_sha or None,
        "commit_available": bool(commit_sha),
        "dirty_state": (
            "unavailable"
            if status is None
            else ("dirty" if status_lines else "clean")
        ),
        "dirty_available": status is not None,
        "dirty_entry_count": None if status is None else len(status_lines),
        "dirty_fingerprint": dirty_fingerprint,
    }


def _vectorbtpro_lineage() -> dict[str, Any]:
    try:
        version = metadata.version("vectorbtpro")
    except metadata.PackageNotFoundError:
        version = None
    return {
        "version": version,
        "available": version is not None,
    }


def capture_runtime_lineage(repository_root: Path | None = None) -> RuntimeLineage:
    root = repository_root or Path(__file__).resolve().parents[1]
    package_fingerprint, package_count = installed_package_fingerprint(_installed_packages())
    git = _git_lineage(root)
    vectorbtpro = _vectorbtpro_lineage()
    contract = {
        "git": git,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "cache_tag": sys.implementation.cache_tag,
        },
        "vectorbtpro": vectorbtpro,
        "packages": {
            "fingerprint": package_fingerprint,
            "fingerprint_algorithm": PACKAGE_FINGERPRINT_ALGORITHM,
            "count": package_count,
        },
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
        },
    }
    return RuntimeLineage(
        runtime_identity=_identity(contract),
        git_commit_sha=git["commit_sha"],
        git_commit_available=git["commit_available"],
        git_dirty_state=git["dirty_state"],
        git_dirty_available=git["dirty_available"],
        git_dirty_entry_count=git["dirty_entry_count"],
        git_dirty_fingerprint=git["dirty_fingerprint"],
        python_implementation=contract["python"]["implementation"],
        python_version=contract["python"]["version"],
        python_cache_tag=contract["python"]["cache_tag"],
        vectorbtpro_version=vectorbtpro["version"],
        vectorbtpro_available=vectorbtpro["available"],
        package_fingerprint=package_fingerprint,
        package_count=package_count,
        platform_system=contract["platform"]["system"],
        platform_machine=contract["platform"]["machine"],
    )


def _runtime_lineage_from_document(document: dict[str, Any]) -> RuntimeLineage:
    try:
        git = document["git"]
        python_doc = document["python"]
        vectorbtpro = document["vectorbtpro"]
        packages = document["packages"]
        platform_doc = document["platform"]
        declared_identity = document["runtime_identity"]

        identity_contract = {
            key: value
            for key, value in document.items()
            if key != "runtime_identity"
        }
        computed_identity = _identity(identity_contract)
        if declared_identity != computed_identity:
            raise ValueError(
                "stored runtime lineage identity does not match canonical content"
            )

        return RuntimeLineage(
            runtime_identity=declared_identity,
            git_commit_sha=git["commit_sha"],
            git_commit_available=git["commit_available"],
            git_dirty_state=git["dirty_state"],
            git_dirty_available=git["dirty_available"],
            git_dirty_entry_count=git["dirty_entry_count"],
            git_dirty_fingerprint=git.get("dirty_fingerprint"),
            python_implementation=python_doc["implementation"],
            python_version=python_doc["version"],
            python_cache_tag=python_doc["cache_tag"],
            vectorbtpro_version=vectorbtpro["version"],
            vectorbtpro_available=vectorbtpro["available"],
            package_fingerprint=packages["fingerprint"],
            package_count=packages["count"],
            platform_system=platform_doc["system"],
            platform_machine=platform_doc["machine"],
        )
    except KeyError as exc:
        raise ValueError("stored runtime lineage document is incomplete") from exc


def _environment_with_runtime_lineage(
    environment: dict[str, Any] | None,
    runtime_lineage: RuntimeLineage,
) -> dict[str, Any]:
    values = dict(environment or {})
    if RUNTIME_LINEAGE_ENVIRONMENT_KEY in values:
        existing = values[RUNTIME_LINEAGE_ENVIRONMENT_KEY]
        if canonical_json(existing) != canonical_json(runtime_lineage_document(runtime_lineage)):
            raise ValueError("environment runtime lineage conflicts with captured runtime lineage")
        return values
    values[RUNTIME_LINEAGE_ENVIRONMENT_KEY] = runtime_lineage_document(runtime_lineage)
    return values


def capture_runtime_lineage_document() -> dict[str, Any]:
    return runtime_lineage_document(capture_runtime_lineage())


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if hasattr(value, "item"):
        return _jsonable(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("experiment configuration cannot contain non-finite floats")
    return value


def configuration_document_from_experiment_config(
    config: ExperimentConfig,
    *,
    strategy_version: str,
) -> dict[str, Any]:
    return normalized_configuration_document(
        experiment_id=config.experiment_id,
        strategy_id=config.strategy_id,
        strategy_version=strategy_version,
        market_data=_jsonable(config.market_data),
        parameters=_jsonable(config.parameter_combinations),
        execution=_jsonable(config.execution),
        ranking={
            "columns": config.ranking_columns,
            "ascending": config.ranking_ascending,
            "parameter_output_names": config.parameter_output_names,
        },
        screening=_jsonable(config.screening),
    )


class PersistenceService:
    """Small dashboard-facing facade over transactional repository operations."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        runtime_lineage_provider=None,
    ) -> None:
        self.connection = initialize_database(path)
        self.strategies = StrategyRepository(self.connection)
        self.configurations = ConfigurationRepository(self.connection)
        self.runs = RunRepository(self.connection)
        self.events = RunEventRepository(self.connection)
        self.results = ResultRepository(self.connection)
        self.reviews = ReviewRepository(self.connection)
        self._runtime_lineage_provider = runtime_lineage_provider or capture_runtime_lineage

    def close(self) -> None:
        self.connection.close()

    def _freeze_environment(
        self,
        environment: dict[str, Any] | None,
    ) -> dict[str, Any]:
        values = dict(environment or {})
        if RUNTIME_LINEAGE_ENVIRONMENT_KEY in values:
            runtime_document = values[RUNTIME_LINEAGE_ENVIRONMENT_KEY]
            if not isinstance(runtime_document, dict):
                raise ValueError("stored runtime lineage is not a JSON object")
            _runtime_lineage_from_document(runtime_document)
            return values
        return _environment_with_runtime_lineage(values, self._runtime_lineage_provider())

    def _runtime_lineage_for_run(self, run: ExperimentRunRecord) -> RuntimeLineage:
        environment = _json_document(run.environment_json)
        if not isinstance(environment, dict):
            raise ValueError("stored run environment is not a JSON object")
        runtime_document = environment.get(RUNTIME_LINEAGE_ENVIRONMENT_KEY)
        if runtime_document is None:
            raise RuntimeError(
                f"run {run.run_id} has no frozen runtime lineage in its execution environment"
            )
        if not isinstance(runtime_document, dict):
            raise ValueError("stored runtime lineage is not a JSON object")
        return _runtime_lineage_from_document(runtime_document)

    def register_artifact(
        self,
        *,
        run_id: str,
        artifact_type: ArtifactType,
        logical_name: str,
        media_type: str,
        format: str,
        location: str,
        content: bytes | Any,
        schema_version: int = 1,
        availability_state: ArtifactAvailability = ArtifactAvailability.AVAILABLE,
    ) -> ArtifactContractRecord:
        data = content if isinstance(content, bytes) else content.read()
        if not isinstance(data, bytes):
            raise TypeError("artifact content must be bytes or a byte stream")
        if not logical_name or not media_type or not format or not location or schema_version < 1:
            raise ValueError("artifact metadata must be non-empty and schema_version positive")
        checksum = hashlib.sha256(data).hexdigest()
        identity_key = hashlib.sha256(
            canonical_json({
                "run_id": run_id,
                "artifact_type": ArtifactType(artifact_type).value,
                "logical_name": logical_name,
                "schema_version": schema_version,
            }).encode("utf-8")
        ).hexdigest()
        with transaction(self.connection):
            return self.results.register_artifact_contract(
                run_id=run_id,
                artifact_type=artifact_type,
                logical_name=logical_name,
                schema_version=schema_version,
                media_type=media_type,
                format=format,
                checksum=checksum,
                size_bytes=len(data),
                location=location,
                availability_state=availability_state,
                identity_key=identity_key,
            )

    def get_artifact_metadata(self, artifact_id: int) -> ArtifactContractRecord:
        return self.results.get_artifact_contract(artifact_id)

    def validate_artifact(
        self,
        artifact_id: int,
        *,
        artifact_root: str | Path,
    ) -> ArtifactValidationResult:
        artifact = self.get_artifact_metadata(artifact_id)
        root = Path(artifact_root).resolve()
        relative = Path(artifact.location)

        if relative.is_absolute() or ".." in relative.parts:
            return ArtifactValidationResult(
                artifact_id=artifact.artifact_id,
                availability_state=ArtifactAvailability.CORRUPT,
                valid=False,
                reason="unsafe_artifact_location",
                expected_checksum=artifact.checksum,
                actual_checksum=None,
                expected_size_bytes=artifact.size_bytes,
                actual_size_bytes=None,
                resolved_path=None,
            )

        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return ArtifactValidationResult(
                artifact_id=artifact.artifact_id,
                availability_state=ArtifactAvailability.CORRUPT,
                valid=False,
                reason="artifact_location_escapes_root",
                expected_checksum=artifact.checksum,
                actual_checksum=None,
                expected_size_bytes=artifact.size_bytes,
                actual_size_bytes=None,
                resolved_path=None,
            )

        resolved_path = str(candidate)

        if not candidate.exists():
            return ArtifactValidationResult(
                artifact_id=artifact.artifact_id,
                availability_state=ArtifactAvailability.MISSING,
                valid=False,
                reason="artifact_missing",
                expected_checksum=artifact.checksum,
                actual_checksum=None,
                expected_size_bytes=artifact.size_bytes,
                actual_size_bytes=None,
                resolved_path=resolved_path,
            )

        if not candidate.is_file():
            return ArtifactValidationResult(
                artifact_id=artifact.artifact_id,
                availability_state=ArtifactAvailability.CORRUPT,
                valid=False,
                reason="artifact_not_regular_file",
                expected_checksum=artifact.checksum,
                actual_checksum=None,
                expected_size_bytes=artifact.size_bytes,
                actual_size_bytes=None,
                resolved_path=resolved_path,
            )

        content = candidate.read_bytes()
        actual_checksum = hashlib.sha256(content).hexdigest()
        actual_size = len(content)

        if actual_size != artifact.size_bytes:
            return ArtifactValidationResult(
                artifact_id=artifact.artifact_id,
                availability_state=ArtifactAvailability.CORRUPT,
                valid=False,
                reason="artifact_size_mismatch",
                expected_checksum=artifact.checksum,
                actual_checksum=actual_checksum,
                expected_size_bytes=artifact.size_bytes,
                actual_size_bytes=actual_size,
                resolved_path=resolved_path,
            )

        if actual_checksum != artifact.checksum:
            return ArtifactValidationResult(
                artifact_id=artifact.artifact_id,
                availability_state=ArtifactAvailability.CORRUPT,
                valid=False,
                reason="artifact_checksum_mismatch",
                expected_checksum=artifact.checksum,
                actual_checksum=actual_checksum,
                expected_size_bytes=artifact.size_bytes,
                actual_size_bytes=actual_size,
                resolved_path=resolved_path,
            )

        return ArtifactValidationResult(
            artifact_id=artifact.artifact_id,
            availability_state=ArtifactAvailability.AVAILABLE,
            valid=True,
            reason="validated",
            expected_checksum=artifact.checksum,
            actual_checksum=actual_checksum,
            expected_size_bytes=artifact.size_bytes,
            actual_size_bytes=actual_size,
            resolved_path=resolved_path,
        )

    def list_run_artifacts(self, run_id: str) -> tuple[ArtifactContractRecord, ...]:
        return self.results.list_artifact_contracts(run_id)

    def retrieve_run_artifacts(
        self,
        run_id: str,
        *,
        artifact_root: str | Path,
    ) -> RunArtifactRetrieval:
        run = self.runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id}")

        persisted = self.read_persisted_run_manifest(run_id)
        if persisted is None:
            raise RuntimeError(f"run {run_id} has no persisted manifest")

        manifest_json, manifest_checksum = persisted
        manifest_document = _json_document(manifest_json)
        if not isinstance(manifest_document, dict):
            raise ValueError("stored run manifest is not a JSON object")
        if manifest_document.get("run_id") != run_id:
            raise ValueError(
                f"stored run manifest identity does not match requested run {run_id}"
            )

        computed_manifest_checksum = _persisted_manifest_checksum(manifest_json)
        if computed_manifest_checksum != manifest_checksum:
            raise ValueError(
                f"stored run manifest checksum mismatch for run {run_id}"
            )

        artifacts = self.list_run_artifacts(run_id)

        manifest_artifacts = manifest_document.get("artifacts")
        if not isinstance(manifest_artifacts, list):
            raise ValueError("stored run manifest artifacts are not a JSON array")

        immutable_manifest_artifacts = []
        for artifact_document in manifest_artifacts:
            if not isinstance(artifact_document, dict):
                raise ValueError(
                    "stored run manifest artifact is not a JSON object"
                )
            immutable_artifact = dict(artifact_document)
            immutable_artifact.pop("availability_state", None)
            immutable_manifest_artifacts.append(immutable_artifact)

        database_artifacts = [
            _artifact_contract_document(artifact)
            for artifact in artifacts
            if artifact.logical_name
            not in {EVIDENCE_DECISION_LOGICAL_NAME, REVIEW_CONTEXT_LOGICAL_NAME}
        ]

        if canonical_json(immutable_manifest_artifacts) != canonical_json(
            database_artifacts
        ):
            raise ValueError(
                f"stored run manifest artifacts do not match database records "
                f"for run {run_id}"
            )

        validations = tuple(
            self.validate_artifact(
                artifact.artifact_id,
                artifact_root=artifact_root,
            )
            for artifact in artifacts
        )

        return RunArtifactRetrieval(
            run_id=run_id,
            manifest_json=manifest_json,
            manifest_checksum=manifest_checksum,
            artifacts=artifacts,
            validations=validations,
        )

    def walk_forward_evidence_source_document(self, run_id: str) -> dict[str, Any]:
        from persistence.evidence_service import ValidationEvidenceArtifactService

        return ValidationEvidenceArtifactService(self).source_document(run_id)

    def persist_walk_forward_evidence(
        self,
        *,
        run_id: str,
        result: Any,
        rules: Any,
        artifact_root: str | Path,
    ) -> Any:
        from persistence.evidence_service import ValidationEvidenceArtifactService

        return ValidationEvidenceArtifactService(self).persist_walk_forward(
            run_id=run_id,
            result=result,
            rules=rules,
            artifact_root=artifact_root,
        )

    def retrieve_walk_forward_evidence(
        self,
        run_id: str,
        *,
        artifact_root: str | Path,
    ) -> Any:
        from persistence.evidence_service import ValidationEvidenceArtifactService

        return ValidationEvidenceArtifactService(self).retrieve_walk_forward(
            run_id=run_id,
            artifact_root=artifact_root,
        )

    def update_artifact_availability(
        self, artifact_id: int, availability_state: ArtifactAvailability
    ) -> ArtifactContractRecord:
        with transaction(self.connection):
            return self.results.update_artifact_availability(artifact_id, availability_state)

    def build_run_manifest(self, run_id: str, *, created_at: str | None = None) -> RunManifest:
        run = self.runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id}")
        return RunManifest(
            schema_version=RUN_MANIFEST_SCHEMA_VERSION,
            run_id=run.run_id,
            configuration_id=run.configuration_id,
            strategy_id=run.strategy_id,
            strategy_version=run.strategy_version,
            lineage=self.get_run_lineage(run_id),
            artifacts=self.list_run_artifacts(run_id),
            created_at=created_at or utc_now(),
        )

    def get_run_lineage(self, run_id: str) -> RunLineage:
        run = self.runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id}")
        configuration = self.configurations.get(run.configuration_id)
        if configuration is None:
            raise RuntimeError(f"run {run_id} references missing configuration")
        strategy = self.strategies.get(run.strategy_id, run.strategy_version)
        if strategy is None:
            raise RuntimeError(
                f"run {run_id} references missing strategy {run.strategy_id}@{run.strategy_version}"
            )
        if (
            configuration.strategy_id != run.strategy_id
            or configuration.strategy_version != run.strategy_version
        ):
            raise ValueError("run and saved configuration disagree on strategy identity")
        configuration_document = _json_document(configuration.canonical_config_json)
        if (
            configuration_document.get("strategy_id") != run.strategy_id
            or configuration_document.get("strategy_version") != run.strategy_version
        ):
            raise ValueError("saved configuration canonical strategy identity is mismatched")
        if configuration.config_hash != configuration_hash(configuration_document):
            raise ValueError("saved configuration hash does not match canonical content")
        provenance = self.results.get_data_provenance(run_id)
        if provenance is None:
            raise RuntimeError(f"run {run_id} has no data provenance record")
        execution = self.results.get_execution_assumptions(run_id)
        if execution is None:
            raise RuntimeError(f"run {run_id} has no execution assumptions record")
        return RunLineage(
            configuration=ConfigurationLineage(
                configuration_id=configuration.configuration_id,
                config_hash=configuration.config_hash,
            ),
            strategy=StrategyLineage(
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
            ),
            data=self._data_lineage(provenance),
            normalization=self._normalization_lineage(provenance),
            execution_assumptions=self._execution_assumption_lineage(
                execution,
                configuration_document=configuration_document,
            ),
            runtime=self._runtime_lineage_for_run(run),
        )

    def _normalization_lineage(
        self, provenance: DataProvenanceRecord
    ) -> NormalizationLineage:
        _ = provenance
        contract = _normalization_contract()
        contract_json = canonical_json(contract)
        return NormalizationLineage(
            normalization_identity=_identity(contract),
            contract_json=contract_json,
        )

    def _data_lineage(self, provenance: DataProvenanceRecord) -> DataLineage:
        normalization = self._normalization_lineage(provenance)
        provider_doc = {
            "provider": provenance.provider,
            "provider_implementation": provenance.provider_implementation,
        }
        dataset_doc = {
            **provider_doc,
            "symbol": provenance.symbol,
            "timeframe": provenance.interval,
            "requested_coverage": provenance.requested_coverage,
            "actual_coverage": provenance.actual_coverage,
            "adjustment_mode": "adjusted" if provenance.adjusted else "raw",
            "row_count": provenance.row_count,
            "dataset_manifest_reference": provenance.manifest_reference,
            "dataset_checksum": provenance.checksum,
            "normalization_identity": normalization.normalization_identity,
        }
        return DataLineage(
            provenance_record_identity=_identity(record_to_dict(provenance)),
            provider_identity=_identity(provider_doc),
            symbol=provenance.symbol,
            timeframe=provenance.interval,
            requested_coverage=provenance.requested_coverage,
            actual_coverage=provenance.actual_coverage,
            dataset_identity=_identity(dataset_doc),
            dataset_manifest_reference=provenance.manifest_reference,
            dataset_checksum=provenance.checksum,
            calendar_identity=provenance.timezone,
            adjustment_mode="adjusted" if provenance.adjusted else "raw",
            normalization_identity=normalization.normalization_identity,
        )

    def _execution_assumption_lineage(
        self,
        execution: ExecutionAssumptionsRecord,
        *,
        configuration_document: dict[str, Any],
    ) -> ExecutionAssumptionLineage:
        assumptions = _json_document(execution.assumptions_json)
        expected = configuration_document.get("execution")
        if expected is None:
            raise ValueError("saved configuration lacks execution assumptions")
        if canonical_json(assumptions) != canonical_json(expected):
            raise ValueError("run execution assumptions disagree with saved configuration")
        assumptions_identity = _identity(assumptions)
        return ExecutionAssumptionLineage(
            execution_assumptions_identity=assumptions_identity,
            record_identity=_identity(
                {
                    "run_id": execution.run_id,
                    "execution_assumptions_identity": assumptions_identity,
                }
            ),
        )

    def serialize_run_manifest(self, manifest: RunManifest) -> str:
        return canonical_json(run_manifest_document(manifest, include_mutable=True))

    def run_manifest_checksum(self, manifest: RunManifest) -> str:
        return hashlib.sha256(
            canonical_json(run_manifest_document(manifest, include_mutable=False)).encode("utf-8")
        ).hexdigest()

    def persist_run_manifest(self, manifest: RunManifest) -> None:
        serialized = self.serialize_run_manifest(manifest)
        checksum = self.run_manifest_checksum(manifest)
        with transaction(self.connection):
            existing = self.connection.execute(
                "SELECT content_checksum FROM run_manifests WHERE run_id=?",
                (manifest.run_id,),
            ).fetchone()
            if existing is not None and existing["content_checksum"] != checksum:
                raise ValueError("persisted run manifest conflicts with proposed immutable lineage")
            self.connection.execute(
                """
                INSERT INTO run_manifests (run_id, schema_version, manifest_json, content_checksum, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    schema_version=excluded.schema_version, manifest_json=excluded.manifest_json,
                    content_checksum=excluded.content_checksum, created_at=excluded.created_at
                """,
                (
                    manifest.run_id, manifest.schema_version, serialized,
                    checksum, manifest.created_at,
                ),
            )

    def read_persisted_run_manifest(self, run_id: str) -> tuple[str, str] | None:
        row = self.connection.execute(
            "SELECT manifest_json, content_checksum FROM run_manifests WHERE run_id=?", (run_id,)
        ).fetchone()
        return None if row is None else (row["manifest_json"], row["content_checksum"])

    def read_persisted_run_manifest_document(self, run_id: str) -> dict[str, Any] | None:
        persisted = self.read_persisted_run_manifest(run_id)
        if persisted is None:
            return None
        return _json_document(persisted[0])

    def register_strategy(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        display_name: str,
        description: str,
        lifecycle: StrategyLifecycle,
        active: bool = True,
    ) -> StrategyRecord:
        with transaction(self.connection):
            return self.strategies.upsert(
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                display_name=display_name,
                description=description,
                lifecycle=lifecycle,
                active=active,
            )

    def update_strategy_lifecycle(
        self,
        strategy_id: str,
        strategy_version: str,
        *,
        lifecycle: StrategyLifecycle,
        active: bool,
    ) -> StrategyRecord:
        with transaction(self.connection):
            return self.strategies.update_lifecycle(
                strategy_id,
                strategy_version,
                lifecycle=lifecycle,
                active=active,
            )

    def upsert_configuration(self, document: dict[str, Any]) -> ConfigurationRecord:
        with transaction(self.connection):
            return self.configurations.upsert(document)

    def create_run(
        self,
        *,
        configuration_id: str,
        strategy_id: str,
        strategy_version: str,
        stage: RunStage,
        run_id: str | None = None,
        status: RunStatus = RunStatus.CREATED,
        environment: dict[str, Any] | None = None,
    ) -> ExperimentRunRecord:
        with transaction(self.connection):
            return self.runs.create(
                run_id=run_id or f"run_{uuid4().hex}",
                configuration_id=configuration_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                stage=stage,
                status=status,
                environment=self._freeze_environment(environment),
            )

    def create_run_with_operator_event(
        self,
        *,
        configuration_id: str,
        strategy_id: str,
        strategy_version: str,
        stage: RunStage,
        run_id: str,
        status: RunStatus,
        environment: dict[str, Any] | None,
        event_type: RunEventType,
        severity: EventSeverity,
        message: str,
        source: str = "quant_factory",
    ) -> ExperimentRunRecord:
        """Atomically create a run and its initial concise operator event."""
        with transaction(self.connection):
            run = self.runs.create(
                run_id=run_id,
                configuration_id=configuration_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                stage=stage,
                status=status,
                environment=self._freeze_environment(environment),
            )
            self.events.append(
                run_id=run.run_id,
                event_type=event_type,
                severity=severity,
                message=message,
                source=source,
                occurred_at=run.created_at,
            )
            return run

    def transition_run(
        self,
        run_id: str,
        status: RunStatus,
        *,
        error_summary: str | None = None,
    ) -> ExperimentRunRecord:
        with transaction(self.connection):
            return self.runs.transition(run_id, status, error_summary=error_summary)

    def increment_run_attempt(self, run_id: str) -> ExperimentRunRecord:
        """Persist the next authoritative fixture-attempt count."""
        with transaction(self.connection):
            return self.runs.increment_attempt(run_id)

    def require_active_run_for_completion(self, run_id: str) -> ExperimentRunRecord:
        """Fail closed before a worker writes successful completion output."""
        run = self.runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id}")
        if run.status != RunStatus.RUNNING:
            raise RunCompletionRejectedError(
                f"run {run_id} is {run.status.value} and cannot accept completion output"
            )
        return run

    def request_run_cancellation(self, run_id: str) -> ExperimentRunRecord:
        """Durably request cooperative cancellation of one active fixture run."""
        with transaction(self.connection):
            run = self.runs.get(run_id)
            if run is None:
                raise KeyError(f"unknown run {run_id}")
            if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return run
            if run.status != RunStatus.RUNNING:
                raise ValueError(f"run {run_id} is not active and cannot be cancelled")
            if not any(
                event.event_type == RunEventType.RUN_CANCELLATION_REQUESTED
                for event in self.events.list_for_run(run_id)
            ):
                self.events.append(
                    run_id=run_id,
                    event_type=RunEventType.RUN_CANCELLATION_REQUESTED,
                    severity=EventSeverity.INFO,
                    message="Cancellation requested; waiting for fixture acknowledgement.",
                )
            return run

    def cancellation_requested(self, run_id: str) -> bool:
        """Return whether an active run has a durable cancellation request."""
        if self.runs.get(run_id) is None:
            raise KeyError(f"unknown run {run_id}")
        return any(
            event.event_type == RunEventType.RUN_CANCELLATION_REQUESTED
            for event in self.events.list_for_run(run_id)
        )

    def acknowledge_run_cancellation(self, run_id: str) -> ExperimentRunRecord:
        """Apply the terminal cancellation transition once a fixture cooperates."""
        with transaction(self.connection):
            run = self.runs.get(run_id)
            if run is None:
                raise KeyError(f"unknown run {run_id}")
            if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return run
            if run.status != RunStatus.RUNNING:
                raise ValueError(f"run {run_id} is not active and cannot acknowledge cancellation")
            if not any(
                event.event_type == RunEventType.RUN_CANCELLATION_REQUESTED
                for event in self.events.list_for_run(run_id)
            ):
                raise ValueError(f"run {run_id} has no cancellation request")
            run = self.runs.transition(run_id, RunStatus.CANCELLED)
            self.events.append(
                run_id=run_id,
                event_type=RunEventType.RUN_CANCELLED,
                severity=EventSeverity.INFO,
                message="Run cancelled after fixture acknowledgement.",
                occurred_at=run.completed_at,
            )
            return run

    def transition_run_with_operator_event(
        self,
        *,
        run_id: str,
        status: RunStatus,
        event_type: RunEventType,
        severity: EventSeverity,
        message: str,
        error_summary: str | None = None,
        source: str = "quant_factory",
    ) -> ExperimentRunRecord:
        """Atomically apply one lifecycle transition and its operator event."""
        with transaction(self.connection):
            run = self.runs.transition(run_id, status, error_summary=error_summary)
            timestamp = run.completed_at or run.started_at or run.created_at
            self.events.append(
                run_id=run.run_id,
                event_type=event_type,
                severity=severity,
                message=message,
                source=source,
                occurred_at=timestamp,
            )
            return run

    def append_run_event(
        self,
        *,
        run_id: str,
        event_type: RunEventType,
        severity: EventSeverity,
        message: str,
        source: str = "quant_factory",
        occurred_at: str | None = None,
    ) -> RunEventRecord:
        with transaction(self.connection):
            return self.events.append(
                run_id=run_id,
                event_type=event_type,
                severity=severity,
                message=message,
                source=source,
                occurred_at=occurred_at,
            )

    def fail_run_for_timeout(
        self,
        *,
        run_id: str,
        timeout_message: str,
        error_summary: str,
    ) -> ExperimentRunRecord:
        """Record one timeout notice, then the normal failed terminal event.

        This is deliberately idempotent for an already-terminal run so a late
        fixture completion cannot create duplicate terminal lifecycle events.
        """
        with transaction(self.connection):
            run = self.runs.get(run_id)
            if run is None:
                raise KeyError(f"unknown run {run_id}")
            if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return run
            if run.status == RunStatus.CREATED:
                run = self.runs.transition(run_id, RunStatus.RUNNING)
                self.events.append(
                    run_id=run.run_id,
                    event_type=RunEventType.RUN_STARTED,
                    severity=EventSeverity.INFO,
                    message="Run started through Prefect fixture execution.",
                    occurred_at=run.started_at,
                )
            self.events.append(
                run_id=run.run_id,
                event_type=RunEventType.RUN_TIMED_OUT,
                severity=EventSeverity.ERROR,
                message=timeout_message,
            )
            run = self.runs.transition(run_id, RunStatus.FAILED, error_summary=error_summary)
            self.events.append(
                run_id=run.run_id,
                event_type=RunEventType.RUN_FAILED,
                severity=EventSeverity.ERROR,
                message="Run failed; see the Prefect reference for technical details.",
                occurred_at=run.completed_at,
            )
            return run

    def recover_stale_fixture_runs(
        self,
        *,
        stale_before: str,
    ) -> tuple[ExperimentRunRecord, ...]:
        """Fail stale fixture runs with explicit, caller-controlled time semantics."""
        cutoff = _parse_utc_timestamp(stale_before, label="stale_before")
        recovered: list[ExperimentRunRecord] = []
        with transaction(self.connection):
            for run in self.runs.list(stage=RunStage.FIXTURE):
                if run.status not in {RunStatus.CREATED, RunStatus.RUNNING}:
                    continue
                reference_timestamp = run.created_at if run.status == RunStatus.CREATED else run.started_at
                if reference_timestamp is None:
                    raise RuntimeError(f"running run {run.run_id} has no started_at timestamp")
                if _parse_utc_timestamp(reference_timestamp, label="run timestamp") >= cutoff:
                    continue
                state = run.status.value
                self.events.append(
                    run_id=run.run_id,
                    event_type=RunEventType.RUN_STALE_RECOVERED,
                    severity=EventSeverity.ERROR,
                    message=f"Stale {state} fixture run recovered to failed.",
                )
                recovered_run = self.runs.transition(
                    run.run_id,
                    RunStatus.FAILED,
                    error_summary=(
                        f"Fixture run remained {state} beyond the stale recovery cutoff."
                    ),
                )
                self.events.append(
                    run_id=recovered_run.run_id,
                    event_type=RunEventType.RUN_FAILED,
                    severity=EventSeverity.ERROR,
                    message="Run failed after stale recovery.",
                    occurred_at=recovered_run.completed_at,
                )
                recovered.append(recovered_run)
        return tuple(recovered)

    def update_review(
        self,
        *,
        target_type: str,
        target_id: str,
        state: ReviewState,
        note: str,
        operator: str = "local-user",
    ) -> ReviewRecord:
        with transaction(self.connection):
            return self.reviews.update(
                target_type=target_type,
                target_id=target_id,
                state=state,
                note=note,
                operator=operator,
            )

    def persist_experiment_result(
        self,
        *,
        config: ExperimentConfig,
        result: ExperimentResult,
        stage: RunStage,
        artifact_path: str,
        artifact_type: str = "experiment_result",
        artifact_schema_version: int = 1,
        artifact_validation_status: str = "validated",
        artifact_availability: ArtifactAvailability = ArtifactAvailability.AVAILABLE,
        review_state: ReviewState = ReviewState.INFRASTRUCTURE_FIXTURE,
        review_note: str = "stored deterministic fixture result",
        run_id: str | None = None,
    ) -> ExperimentRunRecord:
        """Persist a complete completed experiment-result fixture atomically."""
        document = configuration_document_from_experiment_config(
            config,
            strategy_version=result.strategy_version,
        )
        environment = {
            "python": platform.python_version(),
            "platform": platform.platform(),
        }
        frozen_environment = self._freeze_environment(environment)
        with transaction(self.connection):
            self.strategies.upsert(
                strategy_id=result.strategy_id,
                strategy_version=result.strategy_version,
                display_name=result.strategy_name,
                description="Persisted deterministic infrastructure fixture",
                lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
                active=True,
            )
            configuration = self.configurations.upsert(document)
            run = self.runs.create(
                run_id=run_id or f"run_{uuid4().hex}",
                configuration_id=configuration.configuration_id,
                strategy_id=result.strategy_id,
                strategy_version=result.strategy_version,
                stage=stage,
                status=RunStatus.CREATED,
                environment=frozen_environment,
            )
            self.runs.transition(run.run_id, RunStatus.RUNNING)
            self._persist_rows(run.run_id, result)
            self.results.set_data_provenance(_provenance_from_result(run.run_id, result))
            self.results.set_execution_assumptions(
                ExecutionAssumptionsRecord(
                    run_id=run.run_id,
                    assumptions_json=canonical_json(result.execution_assumptions),
                )
            )
            self.results.add_artifact(
                run_id=run.run_id,
                artifact_type=artifact_type,
                schema_version=artifact_schema_version,
                path=artifact_path,
                validation_status=artifact_validation_status,
                availability=artifact_availability,
            )
            self.reviews.update(
                target_type="run",
                target_id=run.run_id,
                state=review_state,
                note=review_note,
                operator="local-user",
            )
            return self.runs.transition(run.run_id, RunStatus.SUCCEEDED)

    def _persist_rows(self, run_id: str, result: ExperimentResult) -> None:
        screening_by_id = {
            item.parameter_row_id: item for item in result.screening_results
        }
        for position, (_, row) in enumerate(result.ranked_results.iterrows(), start=1):
            row_dict = row.to_dict()
            row_id = str(row_dict.get("parameter_row_id") or _row_identity(run_id, row_dict))
            screening = screening_by_id.get(row_id)
            if screening is not None:
                parameters = dict(screening.normalized_parameters)
            else:
                parameters = {
                    key: value
                    for key, value in row_dict.items()
                    if key not in METRIC_COLUMNS
                    and not key.endswith("_status")
                    and key != "parameter_row_id"
                }
            metrics = {
                key: row_dict[key]
                for key in METRIC_COLUMNS
                if key in row_dict and pd.notna(row_dict[key])
            }
            self.results.add_parameter_result(
                run_id=run_id,
                row_id=row_id,
                normalized_parameters=parameters,
                metrics=metrics,
                ranking_position=position,
                screening_status=str(row_dict.get("screening_status", "")),
                rejection_reasons=str(row_dict.get("screening_rejection_reasons", "")),
            )

    def run_detail(self, run_id: str) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if run is None:
            raise KeyError(f"unknown run {run_id}")
        return {
            "run": record_to_dict(run),
            "configuration": _maybe_record_to_dict(
                self.configurations.get(run.configuration_id)
            ),
            "strategy": _maybe_record_to_dict(
                self.strategies.get(run.strategy_id, run.strategy_version)
            ),
            "parameters": [
                record_to_dict(row) for row in self.results.list_parameter_results(run_id)
            ],
            "provenance": _maybe_record_to_dict(self.results.get_data_provenance(run_id)),
            "execution_assumptions": _maybe_record_to_dict(
                self.results.get_execution_assumptions(run_id)
            ),
            "artifacts": [
                record_to_dict(row) for row in self.results.list_artifacts(run_id)
            ],
            "manifest": self.read_persisted_run_manifest_document(run_id),
            "review": _maybe_record_to_dict(self.reviews.get_current("run", run_id)),
        }

    def compare_runs(self, run_ids: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
        if len(run_ids) < 2:
            raise ValueError("at least two runs are required for comparison")
        details: list[dict[str, Any]] = []
        for run_id in run_ids:
            run = self.runs.get(run_id)
            if run is None:
                raise KeyError(f"unknown run {run_id}")
            details.append(self.run_detail(run_id))
        comparison_fields = _comparison_fields(details)
        return tuple(
            {
                "run_id": detail["run"]["run_id"],
                "run": detail["run"],
                "parameter_count": len(detail["parameters"]),
                "review": detail["review"],
                "fields": tuple(
                    field["values"][detail["run"]["run_id"]]
                    for field in comparison_fields
                ),
            }
            for detail in details
        )


def _maybe_record_to_dict(record: Any | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return record_to_dict(record)


def _comparison_json_document(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    document = json.loads(value)
    if not isinstance(document, dict):
        raise ValueError("stored JSON document is not an object")
    return document


def _first_parameter_row(detail: dict[str, Any]) -> dict[str, Any] | None:
    rows = detail.get("parameters") or ()
    return rows[0] if rows else None


def _first_parameter_document(detail: dict[str, Any]) -> dict[str, Any] | None:
    row = _first_parameter_row(detail)
    return _comparison_json_document(row.get("normalized_parameters_json")) if row else None


def _first_metric_document(detail: dict[str, Any]) -> dict[str, Any] | None:
    row = _first_parameter_row(detail)
    return _comparison_json_document(row.get("metrics_json")) if row else None


def _comparison_value(detail: dict[str, Any], key: str) -> Any:
    run = detail["run"]
    configuration = detail.get("configuration") or {}
    config_doc = _comparison_json_document(configuration.get("canonical_config_json"))
    provenance = detail.get("provenance") or {}
    execution = detail.get("execution_assumptions") or {}
    execution_doc = _comparison_json_document(execution.get("assumptions_json"))
    parameters = _first_parameter_document(detail)
    metrics = _first_metric_document(detail)
    artifacts = detail.get("artifacts") or ()
    manifest = detail.get("manifest") or {}
    lineage = manifest.get("lineage") if isinstance(manifest.get("lineage"), dict) else {}
    data_lineage = lineage.get("data") if isinstance(lineage.get("data"), dict) else {}
    runtime_lineage = (
        lineage.get("runtime") if isinstance(lineage.get("runtime"), dict) else {}
    )
    execution_lineage = (
        lineage.get("execution_assumptions")
        if isinstance(lineage.get("execution_assumptions"), dict)
        else {}
    )
    environment = _comparison_json_document(run.get("environment_json"))
    reproduction = (
        environment.get("reproduction")
        if isinstance(environment.get("reproduction"), dict)
        else None
    )
    if key == "run_id":
        return run.get("run_id")
    if key == "run_status":
        return run.get("status")
    if key == "stage":
        return run.get("stage")
    if key == "configuration_id":
        return run.get("configuration_id")
    if key == "configuration_hash":
        return configuration.get("config_hash")
    if key == "strategy":
        return f"{run.get('strategy_id')}@{run.get('strategy_version')}"
    if key == "parameters":
        return parameters
    if key == "execution_assumptions":
        return execution_doc
    if key == "dataset_identity":
        return data_lineage.get("dataset_identity") or provenance.get("checksum")
    if key == "dataset":
        return {
            name: provenance.get(name)
            for name in ("provider", "symbol", "interval", "actual_coverage")
        }
    if key == "lineage_identity":
        return (config_doc or {}).get("lineage_identity")
    if key == "runtime_identity":
        return runtime_lineage.get("runtime_identity")
    if key == "execution_assumptions_identity":
        return execution_lineage.get("execution_assumptions_identity")
    if key == "reproduction_source":
        return reproduction
    if key == "metrics":
        return {
            name: (metrics or {}).get(name)
            for name in (
                "total_return",
                "annualized_return",
                "sharpe_ratio",
                "max_drawdown",
                "number_of_trades",
                "win_rate",
                "deterministic_value",
            )
            if metrics and name in metrics
        }
    if key == "validation_evidence":
        validation_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.get("artifact_type") == ArtifactType.VALIDATION_EVIDENCE.value
        ]
        if not validation_artifacts:
            return None
        return {
            artifact["path"]: artifact["availability"]
            for artifact in validation_artifacts
        }
    raise KeyError(key)


def _comparison_state(values: tuple[Any, ...]) -> str:
    if any(value in (None, {}, ()) for value in values):
        return "missing"
    return "equal" if len({canonical_json(value) for value in values}) == 1 else "changed"


def _comparison_fields(details: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    definitions = (
        ("run_id", "Run ID"),
        ("run_status", "Run status"),
        ("stage", "Stage"),
        ("configuration_id", "Configuration ID"),
        ("configuration_hash", "Configuration hash"),
        ("strategy", "Strategy"),
        ("parameters", "Parameters"),
        ("execution_assumptions", "Execution assumptions"),
        ("dataset_identity", "Dataset identity"),
        ("dataset", "Dataset"),
        ("lineage_identity", "Lineage identity"),
        ("runtime_identity", "Runtime identity"),
        ("execution_assumptions_identity", "Execution assumptions identity"),
        ("metrics", "Key metrics"),
        ("validation_evidence", "Validation evidence"),
        ("reproduction_source", "Reproduction source"),
    )
    fields = []
    for key, label in definitions:
        values = tuple(_comparison_value(detail, key) for detail in details)
        state = _comparison_state(values)
        fields.append(
            {
                "key": key,
                "label": label,
                "state": state,
                "values": {
                    detail["run"]["run_id"]: {
                        "label": label,
                        "value": value,
                        "state": state,
                    }
                    for detail, value in zip(details, values, strict=True)
                },
            }
        )
    return tuple(fields)


def _row_identity(run_id: str, row: dict[str, Any]) -> str:
    return configuration_hash({"run_id": run_id, "row": row})


def _provenance_from_result(
    run_id: str, result: ExperimentResult
) -> DataProvenanceRecord:
    audit = result.market_data_audit
    validation_summary = {
        "duplicate_timestamp_count": audit.duplicate_timestamp_count,
        "missing_open_count": audit.missing_open_count,
        "missing_high_count": audit.missing_high_count,
        "missing_low_count": audit.missing_low_count,
        "missing_close_count": audit.missing_close_count,
        "missing_volume_count": audit.missing_volume_count,
        "expected_session_gap_count": audit.expected_session_gap_count,
        "unexpected_session_gaps": audit.unexpected_session_gaps,
        "provider_warnings": audit.provider_warnings,
    }
    return DataProvenanceRecord(
        run_id=run_id,
        provider=audit.provider,
        provider_implementation=audit.provider_implementation,
        symbol=audit.symbol,
        interval=audit.interval,
        timezone=audit.download_timezone,
        requested_coverage=audit.requested_start,
        actual_coverage=f"{audit.actual_first_row_date}..{audit.actual_last_row_date}",
        adjusted=audit.prices_adjusted,
        row_count=audit.row_count,
        cache_action=audit.cache_action,
        validation_summary_json=canonical_json(validation_summary),
        manifest_reference=None,
        checksum=None,
    )
