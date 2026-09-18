"""Milestone 21B SPYM Databento EQUS.MINI dataset acquisition."""

from __future__ import annotations

import os
from pathlib import Path

import databento as db

from market_data.catalog import (
    DataLocations,
    DatasetManifest,
    DatasetUnavailableError,
    load_data_locations,
    verify_dataset_file,
)
from market_data.equity_contract import (
    spym_databento_request,
    validate_spym_manifest,
)
from market_data.providers.databento import DatabentoDataError, DatabentoOhlcvProvider

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
MAX_DATABENTO_COST_USD = 1.0


def _databento_client_from_environment() -> db.Historical:
    if not os.environ.get("DATABENTO_API_KEY"):
        raise DatabentoDataError(
            "Missing non-empty Databento credential variable(s): DATABENTO_API_KEY"
        )
    return db.Historical(os.environ["DATABENTO_API_KEY"])


def _ensure_external_data_root(locations: DataLocations) -> None:
    root = locations.root.resolve()
    if root == PROJECT_ROOT or PROJECT_ROOT in root.parents:
        raise DatabentoDataError(
            "Configured market-data root is inside the repository; refusing raw-data write"
        )


def acquire_spym_dataset() -> dict[str, object]:
    """Acquire and validate the bounded SPYM Databento dataset."""
    locations = load_data_locations()
    _ensure_external_data_root(locations)
    provider = DatabentoOhlcvProvider(
        client=_databento_client_from_environment(),
        locations=locations,
    )
    result = provider.acquire_from_start(
        spym_databento_request(),
        repo_manifest_dir=REPO_MANIFEST_DIR,
        max_cost_usd=MAX_DATABENTO_COST_USD,
    )
    validate_spym_manifest(result.manifest)
    manifest = DatasetManifest.from_dict(result.manifest)
    verified_path = verify_dataset_file(manifest, locations)
    return {
        "dataset_id": result.manifest["dataset_id"],
        "status": result.manifest["status"],
        "row_count": result.manifest["row_count"],
        "earliest_timestamp": result.manifest["earliest_timestamp"],
        "latest_timestamp": result.manifest["latest_timestamp"],
        "latest_completed_session": result.manifest["latest_completed_session"],
        "estimated_cost_usd": result.manifest["estimated_cost_usd"],
        "actual_cost_usd": result.manifest["actual_cost_usd"],
        "sha256": result.manifest["sha256"],
        "size_bytes": result.manifest["size_bytes"],
        "parquet_path": verified_path.as_posix(),
        "manifest_path": result.manifest_path.as_posix(),
        "cache_status": result.manifest["cache_status"],
    }


def main() -> int:
    try:
        summary = acquire_spym_dataset()
    except (DatabentoDataError, DatasetUnavailableError, ValueError) as exc:
        print(f"SPYM acquisition failed closed: {exc}")
        return 1
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
