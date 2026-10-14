"""Resolve and verify cataloged local market-data files."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tomllib
from typing import Any

import pandas as pd

from market_data.bar_outliers import METHOD as SUSPECT_BAR_METHOD, flag_suspect_bars

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "data_locations.local.toml"
DEFAULT_MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
ALLOWED_STATUSES = frozenset(
    {"validated", "provisional", "quarantined", "superseded"}
)


class DatasetUnavailableError(RuntimeError):
    """Raised when a cataloged dataset is not approved and locally verified."""


@dataclass(frozen=True)
class DataLocations:
    root: Path
    manifests: Path
    quarantine: Path
    backup_archive: Path | None
    extracted_root: Path | None
    verify_sha256_before_use: bool
    # Manifests written by downloaders at run time (persistent, inside the data mount).
    downloaded_manifests: Path | None = None

    @property
    def downloaded_manifest_dir(self) -> Path:
        return self.downloaded_manifests or self.root / "manifests"


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    status: str
    asset_class: str
    symbol: str
    provider: str
    timeframe: str
    format: str
    canonical_relative_path: Path
    sha256: str
    size_bytes: int
    row_count: int
    metadata: dict[str, Any]

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "DatasetManifest":
        required = {
            "dataset_id",
            "status",
            "asset_class",
            "symbol",
            "provider",
            "timeframe",
            "format",
            "canonical_relative_path",
            "sha256",
            "size_bytes",
            "row_count",
        }
        missing = sorted(required - values.keys())
        if missing:
            raise ValueError(f"Manifest missing required field(s): {missing}")
        if values["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"Unsupported manifest status: {values['status']!r}")
        relative_path = Path(values["canonical_relative_path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("canonical_relative_path must stay within the data root")
        digest = str(values["sha256"])
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("Manifest sha256 must be 64 lowercase hexadecimal characters")
        return cls(
            dataset_id=str(values["dataset_id"]),
            status=str(values["status"]),
            asset_class=str(values["asset_class"]),
            symbol=str(values["symbol"]),
            provider=str(values["provider"]),
            timeframe=str(values["timeframe"]),
            format=str(values["format"]),
            canonical_relative_path=relative_path,
            sha256=digest,
            size_bytes=int(values["size_bytes"]),
            row_count=int(values["row_count"]),
            metadata=dict(values),
        )


def _optional_path(value: str) -> Path | None:
    return Path(value).expanduser() if value else None


def load_data_locations(path: Path = DEFAULT_CONFIG_PATH) -> DataLocations:
    """Load the machine-local data-root configuration."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Local data configuration is missing: {path}. "
            "Copy config/data_locations.example.toml and configure this machine."
        )
    with path.open("rb") as stream:
        values = tomllib.load(stream)
    try:
        data = values["data"]
        legacy = values.get("legacy", {})
        policy = values["policy"]
        root = Path(data["root"]).expanduser()
        manifests = Path(data["manifests"]).expanduser()
        quarantine = Path(data["quarantine"]).expanduser()
        downloaded = _optional_path(str(data.get("downloaded_manifests", "")))
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid data-location configuration: {exc}") from exc
    if not root.is_absolute() or not manifests.is_absolute() or not quarantine.is_absolute():
        raise ValueError("Configured data locations must be absolute paths")
    if downloaded is not None and not downloaded.is_absolute():
        raise ValueError("Configured data locations must be absolute paths")
    if policy.get("allow_raw_data_in_repository") is not False:
        raise ValueError("Local policy must prohibit raw data in the repository")
    return DataLocations(
        root=root,
        manifests=manifests,
        quarantine=quarantine,
        backup_archive=_optional_path(str(legacy.get("backup_archive", ""))),
        extracted_root=_optional_path(str(legacy.get("extracted_root", ""))),
        verify_sha256_before_use=bool(policy.get("verify_sha256_before_use", True)),
        downloaded_manifests=downloaded,
    )


def manifest_dir_for(dataset_id: str, locations: DataLocations) -> Path:
    """Return the one manifest folder holding ``dataset_id``: repo or downloaded.

    Fails closed when both hold it, so a stale copy can never shadow the live one.
    """
    if not dataset_id or Path(dataset_id).name != dataset_id:
        raise ValueError("dataset_id must be a plain stable identifier")
    folders = [locations.manifests, locations.downloaded_manifest_dir]
    hits = [folder for folder in folders if (folder / f"{dataset_id}.json").is_file()]
    if len(hits) == 2 and hits[0].resolve() != hits[1].resolve():
        raise DatasetUnavailableError(
            f"Dataset {dataset_id} has manifests in both {hits[0]} and {hits[1]}; remove one"
        )
    return hits[0] if hits else locations.manifests


def load_dataset_manifest(
    dataset_id: str, manifest_dir: Path = DEFAULT_MANIFEST_DIR
) -> DatasetManifest:
    """Load one committed manifest by stable dataset ID."""
    if not dataset_id or Path(dataset_id).name != dataset_id:
        raise ValueError("dataset_id must be a plain stable identifier")
    path = manifest_dir / f"{dataset_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Dataset manifest is missing: {path}")
    with path.open("r", encoding="utf-8") as stream:
        values = json.load(stream)
    manifest = DatasetManifest.from_dict(values)
    if manifest.dataset_id != dataset_id:
        raise ValueError(
            f"Manifest ID {manifest.dataset_id!r} does not match {dataset_id!r}"
        )
    return manifest


def resolve_dataset_path(
    manifest: DatasetManifest, locations: DataLocations
) -> Path:
    """Resolve a manifest path beneath the configured canonical root."""
    candidate = (locations.root / manifest.canonical_relative_path).resolve()
    root = locations.root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Resolved dataset path escapes the configured data root")
    return candidate


def calculate_sha256(path: Path) -> str:
    """Hash one file incrementally without loading it into memory."""
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_verified_bytes(manifest: DatasetManifest, path: Path) -> bytes:
    """Read a dataset once and prove those exact bytes are the ones the manifest names.

    Parsing from the returned bytes (not by reopening the path) makes the read atomic
    with respect to any later writer.
    """
    payload = path.read_bytes()
    if len(payload) != manifest.size_bytes or sha256(payload).hexdigest() != manifest.sha256:
        raise DatasetUnavailableError(
            f"Dataset {manifest.dataset_id} bytes read do not match its manifest size and SHA-256"
        )
    return payload


def verify_dataset_file(
    manifest: DatasetManifest,
    locations: DataLocations,
    *,
    require_validated: bool = True,
) -> Path:
    """Fail unless a dataset is approved, present, sized, and hash-matched."""
    if require_validated and manifest.status != "validated":
        raise DatasetUnavailableError(
            f"Dataset {manifest.dataset_id} is {manifest.status}, not validated"
        )
    path = resolve_dataset_path(manifest, locations)
    if not path.is_file():
        raise DatasetUnavailableError(
            f"Dataset {manifest.dataset_id} is missing at {path}"
        )
    actual_size = path.stat().st_size
    if actual_size != manifest.size_bytes:
        raise DatasetUnavailableError(
            f"Dataset {manifest.dataset_id} size mismatch: "
            f"expected {manifest.size_bytes}, got {actual_size}"
        )
    if locations.verify_sha256_before_use:
        actual_hash = calculate_sha256(path)
        if actual_hash != manifest.sha256:
            raise DatasetUnavailableError(
                f"Dataset {manifest.dataset_id} SHA-256 mismatch: "
                f"expected {manifest.sha256}, got {actual_hash}"
            )
    return path


def suspect_bar_timestamps(
    manifest: DatasetManifest, payload: bytes
) -> tuple[pd.DatetimeIndex, dict[str, int]] | None:
    """Timestamps of suspect bars in an Alpaca SIP file, flagged from the verified bytes.

    Computed on the whole file (all sessions, per New York date) so a later session filter
    cannot change a flag. Returns None for datasets this check does not apply to.
    """
    if manifest.provider != "alpaca" or manifest.metadata.get("feed") != "sip":
        return None
    time_column = str(manifest.metadata.get("timestamp_column", "timestamp"))
    bars = pd.read_parquet(BytesIO(payload), engine="pyarrow", columns=[time_column, "high", "low", "close"])
    bars = bars.rename(columns={time_column: "timestamp"})
    flags, counts = flag_suspect_bars(bars)
    stamps = pd.DatetimeIndex(pd.to_datetime(bars["timestamp"], utc=True))
    return stamps[flags.to_numpy()], counts
