"""Read-only local health summaries for the dashboard.

These helpers inspect committed manifests and local state only.  They do not
create databases, download data, contact providers, or change dataset status.
"""

from __future__ import annotations

from dataclasses import dataclass
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
        return None, tuple(_unconfigured_health(item, detail or str(exc)) for item in manifests), detail

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
                    f"The research state database is missing required table(s): {', '.join(missing)}",
                )
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        return DatabaseHealth("Unavailable", f"The research state database could not be read: {exc}")
    return DatabaseHealth("Available", "The research state database passed a read-only integrity and schema check.")


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
