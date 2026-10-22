"""Deterministic tests for local catalog resolution and verification."""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from market_data.catalog import (
    DataLocations,
    DatasetManifest,
    DatasetUnavailableError,
    load_data_locations,
    load_dataset_manifest,
    resolve_dataset_path,
    verify_dataset_file,
)


def _locations(root: Path) -> DataLocations:
    return DataLocations(
        root=root,
        manifests=root / "manifests",
        quarantine=root / "quarantine",
        backup_archive=None,
        extracted_root=None,
        verify_sha256_before_use=True,
    )


def _manifest(content: bytes, *, status: str = "validated") -> DatasetManifest:
    return DatasetManifest.from_dict(
        {
            "dataset_id": "futures_MES_5m_databento",
            "status": status,
            "asset_class": "futures",
            "symbol": "MES",
            "provider": "Databento",
            "timeframe": "5m",
            "format": "parquet",
            "canonical_relative_path": "futures/MES/5m/test.parquet",
            "sha256": sha256(content).hexdigest(),
            "size_bytes": len(content),
            "row_count": 2,
        }
    )


def test_load_local_configuration(tmp_path: Path) -> None:
    config = tmp_path / "locations.toml"
    root = tmp_path / "data"
    config.write_text(
        "\n".join(
            [
                "[data]",
                f'root = "{root}"',
                f'manifests = "{root / "manifests"}"',
                f'quarantine = "{root / "quarantine"}"',
                "[legacy]",
                'backup_archive = ""',
                'extracted_root = ""',
                "[policy]",
                "preserve_originals = true",
                "verify_sha256_before_use = true",
                "allow_raw_data_in_repository = false",
            ]
        ),
        encoding="utf-8",
    )
    locations = load_data_locations(config)
    assert locations.root == root
    assert locations.verify_sha256_before_use is True
    assert locations.backup_archive is None


def test_load_committed_manifest_and_resolve_path(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    values = _manifest(b"bars").metadata
    (manifest_dir / "futures_MES_5m_databento.json").write_text(
        json.dumps(values), encoding="utf-8"
    )
    manifest = load_dataset_manifest(
        "futures_MES_5m_databento", manifest_dir
    )
    assert manifest.symbol == "MES"
    assert resolve_dataset_path(manifest, _locations(tmp_path)) == (
        tmp_path / "futures/MES/5m/test.parquet"
    )


def test_verify_matching_file(tmp_path: Path) -> None:
    content = b"deterministic market data fixture"
    manifest = _manifest(content)
    path = tmp_path / manifest.canonical_relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    assert verify_dataset_file(manifest, _locations(tmp_path)) == path


@pytest.mark.parametrize("status", ["provisional", "quarantined", "superseded"])
def test_nonvalidated_status_fails_closed(tmp_path: Path, status: str) -> None:
    with pytest.raises(DatasetUnavailableError, match=f"is {status}"):
        verify_dataset_file(_manifest(b"bars", status=status), _locations(tmp_path))


def test_missing_and_mismatched_files_fail_clearly(tmp_path: Path) -> None:
    manifest = _manifest(b"expected")
    with pytest.raises(DatasetUnavailableError, match="is missing"):
        verify_dataset_file(manifest, _locations(tmp_path))

    path = tmp_path / manifest.canonical_relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"wrong-size")
    with pytest.raises(DatasetUnavailableError, match="size mismatch"):
        verify_dataset_file(manifest, _locations(tmp_path))

    path.write_bytes(b"different")
    same_size = replace(manifest, size_bytes=len(b"different"))
    with pytest.raises(DatasetUnavailableError, match="SHA-256 mismatch"):
        verify_dataset_file(same_size, _locations(tmp_path))


def test_manifest_paths_cannot_escape_data_root() -> None:
    values = dict(_manifest(b"bars").metadata)
    values["canonical_relative_path"] = "../outside.parquet"
    with pytest.raises(ValueError, match="stay within"):
        DatasetManifest.from_dict(values)


def test_committed_legacy_manifests_are_loadable_and_machine_independent() -> None:
    manifest_dir = Path(__file__).resolve().parents[1] / "data" / "manifests"
    paths = sorted(manifest_dir.glob("*.json"))
    assert len(paths) >= 15
    for path in paths:
        manifest = load_dataset_manifest(path.stem, manifest_dir)
        assert manifest.canonical_relative_path.is_absolute() is False
        assert manifest.status in {
            "validated",
            "provisional",
            "quarantined",
            "superseded",
        }


def test_mes_manifest_is_validated_and_locatable() -> None:
    manifest = load_dataset_manifest("futures_MES_5m_databento")
    assert manifest.status == "validated"
    assert manifest.row_count == 476_042
    assert manifest.canonical_relative_path == Path(
        "futures/MES/5m/MES_5m_databento.parquet"
    )
