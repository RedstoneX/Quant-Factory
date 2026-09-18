"""Read-only local health summaries for the dashboard.

These helpers inspect committed manifests and local state only.  They do not
create databases, download data, contact providers, or change dataset status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
from typing import Iterable

from market_data.catalog import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_MANIFEST_DIR,
    DataLocations,
    DatasetManifest,
    load_data_locations,
    load_dataset_manifest,
    verify_dataset_file,
)
from persistence.database import LATEST_SCHEMA_VERSION


@dataclass(frozen=True)
class DatasetHealth:
    manifest: DatasetManifest
    availability: str
    checksum: str
    detail: str


@dataclass(frozen=True)
class DatabaseHealth:
    status: str
    detail: str


@dataclass(frozen=True)
class ArtifactStorageHealth:
    status: str
    detail: str


@dataclass(frozen=True)
class CacheHealth:
    status: str
    detail: str


@dataclass(frozen=True)
class HomeHealthReading:
    """One redacted observation supplied to the side-effect-free Home view."""

    area: str
    status: str
    detail: str
    checked_at: str | None = None


def normalize_health_reading(
    reading: HomeHealthReading,
    *,
    observed_at: datetime,
    stale_after: timedelta,
) -> tuple[HomeHealthReading, bool]:
    """Fail closed when an observation is missing, invalid, future, or stale."""

    status = reading.status.strip() or "Not checked"
    if reading.checked_at is None:
        return (
            HomeHealthReading(
                reading.area,
                "Not checked",
                reading.detail,
            ),
            False,
        )
    try:
        checked_at = datetime.fromisoformat(reading.checked_at.replace("Z", "+00:00"))
    except ValueError:
        checked_at = None
    if checked_at is None or checked_at.tzinfo is None:
        return (
            HomeHealthReading(
                reading.area,
                "Not checked",
                "The recorded check time is invalid; current health is not assumed.",
            ),
            False,
        )
    checked_at = checked_at.astimezone(timezone.utc)
    as_of = observed_at.astimezone(timezone.utc)
    if checked_at > as_of:
        return (
            HomeHealthReading(
                reading.area,
                "Not checked",
                "The recorded check time is in the future; current health is not assumed.",
            ),
            False,
        )
    stale = as_of - checked_at > stale_after
    return (
        HomeHealthReading(
            reading.area,
            f"Stale — {status}" if stale else status,
            reading.detail,
            reading.checked_at,
        ),
        stale,
    )


def redact_credential_health_reading(
    reading: HomeHealthReading,
) -> HomeHealthReading:
    """Keep only an allow-listed availability state and its observation time."""

    credential_states = {
        "available": "Available",
        "unavailable": "Unavailable",
        "degraded": "Degraded",
        "not checked": "Not checked",
    }
    status = credential_states.get(reading.status.strip().lower(), "Not checked")
    return HomeHealthReading(
        reading.area,
        status,
        "Availability only. Credential values are never displayed.",
        reading.checked_at,
    )


def inspect_catalog(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    manifest_dir: Path = DEFAULT_MANIFEST_DIR,
) -> tuple[DataLocations | None, tuple[DatasetHealth, ...], str | None]:
    """Inspect every committed manifest and its configured local file."""

    manifests, manifest_errors = _load_manifests(manifest_dir)
    try:
        locations = load_data_locations(config_path)
    except (OSError, ValueError) as exc:
        detail = _join_errors((str(exc), *manifest_errors))
        return (
            None,
            tuple(
                _unconfigured_health(item, detail or str(exc))
                for item in manifests
            ),
            detail,
        )

    health: list[DatasetHealth] = []
    for manifest in manifests:
        try:
            verify_dataset_file(manifest, locations, require_validated=False)
        except Exception as exc:  # catalog exceptions are presented to the operator
            availability, checksum = _verification_failure(str(exc))
            health.append(DatasetHealth(manifest, availability, checksum, str(exc)))
        else:
            checksum = "Verified" if locations.verify_sha256_before_use else "Not checked"
            detail = (
                "Local file size and SHA-256 match the committed manifest."
                if checksum == "Verified"
                else "Local file size matches; SHA-256 verification is disabled by local policy."
            )
            health.append(
                DatasetHealth(
                    manifest,
                    "Available locally",
                    checksum,
                    detail,
                )
            )
    return locations, tuple(health), _join_errors(manifest_errors)


def inspect_database(database: Path) -> DatabaseHealth:
    """Perform a bounded read-only SQLite check without creating a database."""

    if not database.is_file():
        return DatabaseHealth("Unavailable", "The research state database does not exist.")
    try:
        uri = f"{database.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if quick_check != ("ok",):
                return DatabaseHealth(
                    "Unavailable",
                    f"The research state database failed SQLite integrity check: {quick_check!r}",
                )
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            missing = sorted({"schema_metadata", "experiment_runs"} - tables)
            if missing:
                return DatabaseHealth(
                    "Unavailable",
                    (
                        "The research state database is missing required table(s): "
                        f"{', '.join(missing)}"
                    ),
                )
            schema_version = connection.execute(
                "SELECT schema_version FROM schema_metadata"
            ).fetchone()
            if schema_version != (LATEST_SCHEMA_VERSION,):
                recorded = schema_version[0] if schema_version else "missing"
                return DatabaseHealth(
                    "Unavailable",
                    (
                        "The research state database schema is not current "
                        f"(recorded {recorded}; required {LATEST_SCHEMA_VERSION})."
                    ),
                )
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        return DatabaseHealth(
            "Unavailable",
            f"The research state database could not be read: {exc}",
        )
    return DatabaseHealth(
        "Available",
        "The research state database passed a read-only integrity and schema check.",
    )


def inspect_artifact_storage(root: Path) -> ArtifactStorageHealth:
    """Inspect directory identity and read permissions without opening or writing files."""

    if not root.exists():
        return ArtifactStorageHealth(
            "Unavailable",
            "The configured artifact location does not exist.",
        )
    if not root.is_dir():
        return ArtifactStorageHealth(
            "Unavailable",
            "The configured artifact location is not a directory.",
        )
    if not os.access(root, os.R_OK | os.X_OK):
        return ArtifactStorageHealth(
            "Unavailable",
            "The configured artifact directory does not report read access.",
        )
    return ArtifactStorageHealth(
        "Available",
        (
            "The configured artifact directory reports read access. "
            "No file was opened or written by this check."
        ),
    )


def inspect_research_cache(
    catalog_snapshot: tuple[
        DataLocations | None,
        tuple[DatasetHealth, ...],
        str | None,
    ],
    *,
    required_dataset_ids: Iterable[str],
) -> CacheHealth:
    """Summarize only datasets required by active launchable configurations."""

    required = tuple(
        sorted(
            {
                dataset_id.strip()
                for dataset_id in required_dataset_ids
                if isinstance(dataset_id, str) and dataset_id.strip()
            }
        )
    )
    if not required:
        return CacheHealth(
            "Not checked",
            "No active launchable saved setup requires a cataloged dataset.",
        )

    locations, datasets, configuration_error = catalog_snapshot
    if locations is None or configuration_error is not None:
        return CacheHealth(
            "Not checked",
            "The active-setup research cache could not be verified from the local catalog.",
        )

    by_id = {item.manifest.dataset_id: item for item in datasets}
    verified = tuple(
        dataset_id
        for dataset_id in required
        if (
            (item := by_id.get(dataset_id)) is not None
            and item.manifest.status == "validated"
            and item.availability == "Available locally"
            and item.checksum == "Verified"
        )
    )
    if len(verified) == len(required):
        status = "Available"
    elif verified:
        status = "Degraded"
    else:
        status = "Unavailable"
    return CacheHealth(
        status,
        (
            f"{len(verified)} of {len(required)} active-setup dataset(s) are "
            "available locally with validated manifests and verified checksums."
        ),
    )


def local_home_health_readings(
    *,
    database: Path,
    artifact_root: Path,
    catalog_snapshot: tuple[
        DataLocations | None,
        tuple[DatasetHealth, ...],
        str | None,
    ],
    catalog_checked_at: datetime | None,
    required_dataset_ids: Iterable[str],
    observed_at: datetime | None = None,
) -> tuple[HomeHealthReading, ...]:
    """Capture local health only; never probe services, providers, or credentials."""

    checked_at = observed_at or datetime.now(timezone.utc)
    local_timestamp = _utc_timestamp(checked_at)
    if local_timestamp is None:
        database_health = DatabaseHealth(
            "Not checked",
            "The local observation time is not timezone-aware; database health was not checked.",
        )
        artifact_health = ArtifactStorageHealth(
            "Not checked",
            "The local observation time is not timezone-aware; artifact health was not checked.",
        )
    else:
        database_health = inspect_database(database)
        artifact_health = inspect_artifact_storage(artifact_root)

    catalog_timestamp = _utc_timestamp(catalog_checked_at)
    catalog_time_is_future = (
        catalog_checked_at is not None
        and local_timestamp is not None
        and catalog_timestamp is not None
        and catalog_checked_at.astimezone(timezone.utc)
        > checked_at.astimezone(timezone.utc)
    )
    if catalog_timestamp is None or catalog_time_is_future:
        cache_health = CacheHealth(
            "Not checked",
            (
                "The catalog observation time is unavailable or invalid; "
                "research-cache health is not assumed."
            ),
        )
        catalog_timestamp = None
    else:
        cache_health = inspect_research_cache(
            catalog_snapshot,
            required_dataset_ids=required_dataset_ids,
        )
    return (
        HomeHealthReading(
            "database",
            database_health.status,
            database_health.detail,
            local_timestamp,
        ),
        HomeHealthReading(
            "worker",
            "Not checked",
            "No timestamped worker or orchestrator health snapshot was supplied.",
        ),
        HomeHealthReading(
            "provider",
            "Not checked",
            "Recorded provider provenance does not prove live provider connectivity.",
        ),
        HomeHealthReading(
            "cache",
            cache_health.status,
            cache_health.detail,
            catalog_timestamp,
        ),
        HomeHealthReading(
            "artifact",
            artifact_health.status,
            artifact_health.detail,
            local_timestamp,
        ),
        HomeHealthReading(
            "credential",
            "Not checked",
            "Availability only. Credential values are never displayed.",
        ),
    )


def _utc_timestamp(value: datetime | None) -> str | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_manifests(manifest_dir: Path) -> tuple[tuple[DatasetManifest, ...], tuple[str, ...]]:
    if not manifest_dir.is_dir():
        return (), (f"Dataset manifest directory is missing: {manifest_dir}",)
    manifests: list[DatasetManifest] = []
    errors: list[str] = []
    for path in sorted(manifest_dir.glob("*.json")):
        try:
            manifests.append(load_dataset_manifest(path.stem, manifest_dir))
        except (OSError, ValueError) as exc:
            errors.append(f"Dataset manifest {path.name} could not be read: {exc}")
    return tuple(manifests), tuple(errors)


def _join_errors(errors: Iterable[str]) -> str | None:
    values = tuple(error for error in errors if error)
    return "; ".join(values) if values else None


def _unconfigured_health(manifest: DatasetManifest, detail: str) -> DatasetHealth:
    return DatasetHealth(manifest, "Not inspected", "Not inspected", detail)


def _verification_failure(detail: str) -> tuple[str, str]:
    lowered = detail.lower()
    if "sha-256 mismatch" in lowered:
        return "Available locally", "Mismatch"
    if "size mismatch" in lowered:
        return "Available locally", "Mismatch"
    if "is missing" in lowered:
        return "Missing locally", "Not checked"
    return "Not available", "Not checked"
