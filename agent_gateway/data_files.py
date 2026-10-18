"""Read-only listing and opening of committed price files for the research gateway.

Every path comes from a manifest through the market-data catalog; the caller only
ever supplies a dataset ID, which must match a listed ID exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, BinaryIO

from agent_gateway.contracts import GatewayError
from market_data.catalog import (
    DataLocations,
    DatasetUnavailableError,
    load_dataset_manifest,
    manifest_dir_for,
    resolve_dataset_path,
)


@dataclass(frozen=True)
class Download:
    """A download answer: the JSON document plus the opened committed file."""

    document: dict[str, Any]
    stream: BinaryIO


def _committed(locations: DataLocations) -> dict[str, tuple[dict[str, Any], Path]]:
    folders = {locations.manifests.resolve(), locations.downloaded_manifest_dir.resolve()}
    dataset_ids = sorted({path.stem for folder in folders if folder.is_dir() for path in folder.glob("*.json")})
    committed: dict[str, tuple[dict[str, Any], Path]] = {}
    for dataset_id in dataset_ids:
        try:
            manifest = load_dataset_manifest(dataset_id, manifest_dir_for(dataset_id, locations))
            path = resolve_dataset_path(manifest, locations)
        except (DatasetUnavailableError, OSError, ValueError, json.JSONDecodeError):
            continue
        slot = manifest.metadata.get("local_canonical_path", manifest.canonical_relative_path.as_posix())
        if slot != manifest.canonical_relative_path.as_posix() or not path.is_file():
            continue
        coverage = manifest.metadata.get("full_stored_coverage") or {}
        committed[dataset_id] = (
            {
                "dataset_id": dataset_id,
                "symbol": manifest.symbol,
                "asset_class": manifest.asset_class,
                "provider": manifest.provider,
                "timeframe": manifest.timeframe,
                "format": manifest.format,
                "status": manifest.status,
                "session_policy": manifest.metadata.get("session_policy"),
                "first_bar": coverage.get("first_timestamp", manifest.metadata.get("earliest_timestamp")),
                "last_bar": coverage.get("last_timestamp", manifest.metadata.get("latest_timestamp")),
                "row_count": manifest.row_count,
                "sha256": manifest.sha256,
                "size_bytes": manifest.size_bytes,
            },
            path,
        )
    return committed


def list_datasets(locations: DataLocations) -> dict[str, Any]:
    return {"datasets": [entry for entry, _path in _committed(locations).values()]}


def open_dataset(locations: DataLocations, dataset_id: object) -> Download:
    committed = _committed(locations)
    if not isinstance(dataset_id, str) or dataset_id not in committed:
        raise GatewayError("unknown_dataset", "dataset is not in the data_files listing")
    entry, path = committed[dataset_id]
    stream = path.open("rb")
    if os.fstat(stream.fileno()).st_size != entry["size_bytes"]:
        stream.close()
        raise GatewayError("dataset_changing", "dataset is being refreshed; list again and retry")
    return Download(document={"dataset": entry}, stream=stream)
