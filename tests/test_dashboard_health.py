"""Deterministic read-only health views for the M23 operator pages."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from dashboard.health import inspect_catalog, inspect_database
from dashboard.pages.market_data import layout as market_data_layout
from dashboard.pages.system_health import layout as system_health_layout
from persistence.database import initialize_database


def _catalog(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "market-data"
    manifests = tmp_path / "manifests"
    config = tmp_path / "locations.toml"
    manifests.mkdir()
    config.write_text(
        "\n".join(
            (
                "[data]",
                f'root = "{root}"',
                f'manifests = "{root / "manifests"}"',
                f'quarantine = "{root / "quarantine"}"',
                "[policy]",
                "allow_raw_data_in_repository = false",
                "verify_sha256_before_use = true",
            )
        ),
        encoding="utf-8",
    )
    return root, manifests, config


def _manifest(
    manifests: Path,
    *,
    dataset_id: str,
    content: bytes,
    status: str = "validated",
) -> Path:
    document = {
        "dataset_id": dataset_id,
        "status": status,
        "asset_class": "equity",
        "symbol": "SPYM" if dataset_id == "spym" else "OLD",
        "provider": "Databento",
        "timeframe": "1m",
        "format": "parquet",
        "canonical_relative_path": f"equities/{dataset_id}.parquet",
        "sha256": sha256(content).hexdigest(),
        "size_bytes": len(content),
        "row_count": 2,
        "coverage_start": "2025-01-01",
        "latest_completed_session": "2025-01-02",
        "adjustment": "raw",
        "missing_session_count": 0,
    }
    target = manifests / f"{dataset_id}.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def test_catalog_inspection_verifies_matching_file_and_keeps_quarantine_visible(tmp_path: Path) -> None:
    root, manifests, config = _catalog(tmp_path)
    content = b"verified data"
    _manifest(manifests, dataset_id="spym", content=content)
    _manifest(manifests, dataset_id="legacy", content=b"old", status="quarantined")
    target = root / "equities/spym.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(content)

    locations, datasets, error = inspect_catalog(config_path=config, manifest_dir=manifests)

    assert locations is not None
    assert error is None
    by_id = {item.manifest.dataset_id: item for item in datasets}
    assert by_id["spym"].availability == "Available locally"
    assert by_id["spym"].checksum == "Verified"
    assert by_id["legacy"].manifest.status == "quarantined"
    assert by_id["legacy"].availability == "Missing locally"
    rendered = str(market_data_layout(config_path=config, manifest_dir=manifests))
    assert "SPYM" in rendered
    assert "Quarantined — not approved" in rendered
    assert "Fixture evidence does not authorize" in rendered


def test_catalog_inspection_reports_checksum_mismatch_without_mutating_file(tmp_path: Path) -> None:
    root, manifests, config = _catalog(tmp_path)
    _manifest(manifests, dataset_id="spym", content=b"expected")
    target = root / "equities/spym.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"different")
    before = target.read_bytes()

    _, datasets, error = inspect_catalog(config_path=config, manifest_dir=manifests)

    assert error is None
    assert datasets[0].availability == "Available locally"
    assert datasets[0].checksum == "Mismatch"
    assert target.read_bytes() == before


def test_catalog_respects_disabled_checksum_policy_without_claiming_verification(tmp_path: Path) -> None:
    root, manifests, config = _catalog(tmp_path)
    _manifest(manifests, dataset_id="spym", content=b"expected")
    target = root / "equities/spym.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"differs!")
    config.write_text(config.read_text(encoding="utf-8").replace("verify_sha256_before_use = true", "verify_sha256_before_use = false"), encoding="utf-8")

    _, datasets, error = inspect_catalog(config_path=config, manifest_dir=manifests)

    assert error is None
    assert datasets[0].availability == "Available locally"
    assert datasets[0].checksum == "Not checked"
    assert "disabled by local policy" in datasets[0].detail


def test_catalog_missing_configuration_is_a_readable_not_inspected_state(tmp_path: Path) -> None:
    _, manifests, _ = _catalog(tmp_path)
    _manifest(manifests, dataset_id="spym", content=b"expected")

    locations, datasets, error = inspect_catalog(
        config_path=tmp_path / "missing.toml", manifest_dir=manifests
    )

    assert locations is None
    assert "Local data configuration is missing" in str(error)
    assert datasets[0].availability == "Not inspected"
    rendered = str(
        market_data_layout(config_path=tmp_path / "missing.toml", manifest_dir=manifests)
    )
    assert "Local data verification is unavailable." in rendered


def test_catalog_surfaces_malformed_manifest_instead_of_dropping_it(tmp_path: Path) -> None:
    _, manifests, config = _catalog(tmp_path)
    (manifests / "broken.json").write_text("{\"dataset_id\":", encoding="utf-8")

    _, datasets, error = inspect_catalog(config_path=config, manifest_dir=manifests)

    assert datasets == ()
    assert error is not None
    assert "broken.json" in error


def test_system_health_uses_read_only_database_and_artifact_checks(tmp_path: Path) -> None:
    root, manifests, config = _catalog(tmp_path)
    _manifest(manifests, dataset_id="spym", content=b"expected")
    database = tmp_path / "missing.sqlite3"
    artifact_root = tmp_path / "missing-artifacts"

    assert inspect_database(database).status == "Unavailable"
    rendered = str(
        system_health_layout(
            database,
            artifact_root,
            config_path=config,
            manifest_dir=manifests,
        )
    )
    assert not database.exists()
    assert "research state database does not exist" in rendered
    assert "configured artifact location does not exist" in rendered
    assert "Orchestrator" in rendered and "Not checked" in rendered
    assert "paper execution, and live trading are blocked" in rendered


def test_system_health_reports_unreadable_database_as_unavailable(tmp_path: Path) -> None:
    database = tmp_path / "broken.sqlite3"
    database.write_text("not sqlite", encoding="utf-8")

    health = inspect_database(database)

    assert health.status == "Unavailable"
    assert "could not be read" in health.detail


def test_system_health_accepts_initialized_database_without_writing(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    connection = initialize_database(database)
    connection.close()
    before = database.stat().st_mtime_ns

    health = inspect_database(database)

    assert health.status == "Available"
    assert "integrity and schema check" in health.detail
    assert database.stat().st_mtime_ns == before


def test_system_health_rejects_sqlite_file_without_quant_factory_schema(tmp_path: Path) -> None:
    import sqlite3

    database = tmp_path / "wrong.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE unrelated (value TEXT)")
    connection.commit()
    connection.close()

    health = inspect_database(database)

    assert health.status == "Unavailable"
    assert "required table" in health.detail
