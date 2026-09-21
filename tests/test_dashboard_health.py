"""Deterministic read-only health views for the M23 operator pages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from dashboard.health import (
    HomeHealthReading,
    inspect_artifact_storage,
    inspect_catalog,
    inspect_database,
    inspect_research_cache,
    local_home_health_readings,
    normalize_health_reading,
)
from dashboard.callbacks.health import health_presentations
from dashboard.application import create_layout
from dashboard.pages.market_data import layout as market_data_layout
from dashboard.pages.system_health import layout as system_health_layout
from dashboard.run_adapter import SavedConfigurationView
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


def _walk_components(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk_components(child)
    elif children is not None:
        yield from _walk_components(children)


def _component_text(component) -> str:
    return " ".join(
        str(item)
        for item in _walk_components(component)
        if isinstance(item, (str, int, float))
    )


@pytest.mark.parametrize(
    ("checked_at", "expected_status", "expected_checked_at", "expected_stale"),
    (
        (None, "Not checked", None, False),
        ("not-a-timestamp", "Not checked", None, False),
        ("2026-09-18T12:00:01Z", "Not checked", None, False),
        ("2026-09-18T11:59:00Z", "Available", "2026-09-18T11:59:00Z", False),
        (
            "2026-09-18T10:00:00Z",
            "Stale — Available",
            "2026-09-18T10:00:00Z",
            True,
        ),
    ),
    ids=("missing", "invalid", "future", "fresh", "stale"),
)
def test_normalize_health_reading_fails_closed_by_observation_time(
    checked_at: str | None,
    expected_status: str,
    expected_checked_at: str | None,
    expected_stale: bool,
) -> None:
    normalized, stale = normalize_health_reading(
        HomeHealthReading(
            "database",
            "Available",
            "A bounded local observation.",
            checked_at,
        ),
        observed_at=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
        stale_after=timedelta(minutes=30),
    )

    assert normalized.status == expected_status
    assert normalized.checked_at == expected_checked_at
    assert stale is expected_stale


@pytest.mark.parametrize(
    ("observed_at", "stale_after"),
    (
        (datetime(2026, 9, 18, 12, 0), timedelta(minutes=15)),
        (datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc), timedelta(0)),
    ),
    ids=("timezoneless-clock", "non-positive-threshold"),
)
def test_normalize_health_reading_rejects_ambiguous_freshness_contract(
    observed_at: datetime,
    stale_after: timedelta,
) -> None:
    with pytest.raises(ValueError):
        normalize_health_reading(
            HomeHealthReading(
                "database",
                "Available",
                "A bounded local observation.",
                "2026-09-18T11:59:00Z",
            ),
            observed_at=observed_at,
            stale_after=stale_after,
        )


def test_health_presentations_transition_fresh_snapshot_to_stale_without_probe() -> None:
    snapshot = {
        "readings": [
            {
                "area": "database",
                "status": "Available",
                "detail": "A read-only integrity check passed.",
                "checked_at": "2026-09-18T12:00:00Z",
            },
            {
                "area": "credential",
                "status": "Available: SENSITIVE_SENTINEL",
                "detail": "SENSITIVE_SENTINEL",
                "checked_at": "2026-09-18T12:00:00Z",
            },
        ],
        "stale_after_seconds": 60,
    }

    fresh_home, fresh_system = health_presentations(
        snapshot,
        observed_at=datetime(2026, 9, 18, 12, 0, 30, tzinfo=timezone.utc),
    )
    stale_home, stale_system = health_presentations(
        snapshot,
        observed_at=datetime(2026, 9, 18, 12, 1, 1, tzinfo=timezone.utc),
    )

    fresh_text = " ".join(
        _component_text(card) for card in (*fresh_home, *fresh_system)
    )
    stale_text = " ".join(
        _component_text(card) for card in (*stale_home, *stale_system)
    )
    assert "Research database Available" in fresh_text
    assert "Research database Stale — Available" in stale_text
    assert "SENSITIVE_SENTINEL" not in fresh_text
    assert "SENSITIVE_SENTINEL" not in stale_text


def test_health_presentations_fail_closed_for_non_positive_snapshot_threshold() -> None:
    home_cards, system_cards = health_presentations(
        {
            "readings": [
                {
                    "area": "database",
                    "status": "Available",
                    "detail": "Untrusted snapshot.",
                    "checked_at": "2026-09-18T12:00:00Z",
                }
            ],
            "stale_after_seconds": 0,
        },
        observed_at=datetime(2026, 9, 18, 12, 0, 1, tzinfo=timezone.utc),
    )

    rendered = " ".join(
        _component_text(card) for card in (*home_cards, *system_cards)
    )
    assert "Available" not in rendered
    assert "Not checked" in rendered


def test_catalog_inspection_verifies_matching_file_and_keeps_quarantine_visible(
    tmp_path: Path,
) -> None:
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


def test_catalog_respects_disabled_checksum_policy_without_claiming_verification(
    tmp_path: Path,
) -> None:
    root, manifests, config = _catalog(tmp_path)
    _manifest(manifests, dataset_id="spym", content=b"expected")
    target = root / "equities/spym.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"differs!")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "verify_sha256_before_use = true",
            "verify_sha256_before_use = false",
        ),
        encoding="utf-8",
    )

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
    assert "New candidate and edge research are paused until beta" in rendered
    assert (
        "Protected-data inspection, promotion, deployment, paper execution, and live "
        "trading remain blocked"
        in rendered
    )


def test_system_health_marks_old_supplied_observation_stale(tmp_path: Path) -> None:
    observed = "2026-09-18T10:00:00Z"

    rendered = _component_text(
        system_health_layout(
            tmp_path / "unused.sqlite3",
            tmp_path / "unused-artifacts",
            health_readings=(
                HomeHealthReading(
                    "database",
                    "Available",
                    "A read-only integrity check passed at the recorded time.",
                    observed,
                ),
            ),
            observed_at=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
            stale_after=timedelta(minutes=30),
        )
    )

    assert "Stale — Available" in rendered
    assert f"Last checked: {observed}" in rendered


def test_system_health_never_renders_supplied_credential_values(tmp_path: Path) -> None:
    rendered = _component_text(
        system_health_layout(
            tmp_path / "unused.sqlite3",
            tmp_path / "unused-artifacts",
            health_readings=(
                HomeHealthReading(
                    "credential",
                    "Available: SENSITIVE_SENTINEL",
                    "SENSITIVE_SENTINEL",
                    "2026-09-18T11:59:00Z",
                ),
            ),
            observed_at=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc),
        )
    )

    assert "SENSITIVE_SENTINEL" not in rendered
    assert "Credential values are never displayed." in rendered
    assert "Not checked" in rendered


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
    database = tmp_path / "wrong.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE unrelated (value TEXT)")
    connection.commit()
    connection.close()

    health = inspect_database(database)

    assert health.status == "Unavailable"
    assert "required table" in health.detail


def test_system_health_rejects_outdated_database_schema_without_writing(tmp_path: Path) -> None:
    database = tmp_path / "outdated.sqlite3"
    connection = initialize_database(database)
    connection.execute("UPDATE schema_metadata SET schema_version=0")
    connection.commit()
    connection.close()
    before = database.stat().st_mtime_ns

    health = inspect_database(database)

    assert health.status == "Unavailable"
    assert "schema is not current" in health.detail
    assert database.stat().st_mtime_ns == before


def test_artifact_health_reads_permission_metadata_without_opening_or_writing(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    sentinel = artifact_root / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    before = (
        sentinel.read_bytes(),
        sentinel.stat().st_mtime_ns,
        tuple(artifact_root.iterdir()),
    )

    health = inspect_artifact_storage(artifact_root)

    assert health.status == "Available"
    assert "No file was opened or written" in health.detail
    assert (
        sentinel.read_bytes(),
        sentinel.stat().st_mtime_ns,
        tuple(artifact_root.iterdir()),
    ) == before


def test_artifact_health_reports_a_file_as_unavailable(tmp_path: Path) -> None:
    artifact_file = tmp_path / "not-a-directory"
    artifact_file.write_text("unchanged", encoding="utf-8")
    before = (artifact_file.read_bytes(), artifact_file.stat().st_mtime_ns)

    health = inspect_artifact_storage(artifact_file)

    assert health.status == "Unavailable"
    assert "not a directory" in health.detail
    assert (artifact_file.read_bytes(), artifact_file.stat().st_mtime_ns) == before


def test_research_cache_uses_only_active_configuration_dataset_identities(
    tmp_path: Path,
) -> None:
    root, manifests, config = _catalog(tmp_path)
    active = b"active"
    _manifest(manifests, dataset_id="active", content=active)
    _manifest(manifests, dataset_id="unrelated", content=b"missing")
    target = root / "equities/active.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(active)
    snapshot = inspect_catalog(config_path=config, manifest_dir=manifests)

    health = inspect_research_cache(
        snapshot,
        required_dataset_ids=("active",),
    )

    assert health.status == "Available"
    assert health.detail.startswith("1 of 1")


def test_research_cache_fails_closed_for_missing_or_unverified_required_data(
    tmp_path: Path,
) -> None:
    root, manifests, config = _catalog(tmp_path)
    _manifest(manifests, dataset_id="missing", content=b"missing")
    available = b"available"
    _manifest(manifests, dataset_id="available", content=available)
    target = root / "equities/available.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(available)
    snapshot = inspect_catalog(config_path=config, manifest_dir=manifests)

    partial = inspect_research_cache(
        snapshot,
        required_dataset_ids=("available", "missing"),
    )
    unavailable = inspect_research_cache(
        snapshot,
        required_dataset_ids=("missing",),
    )

    assert partial.status == "Degraded"
    assert partial.detail.startswith("1 of 2")
    assert unavailable.status == "Unavailable"
    assert unavailable.detail.startswith("0 of 1")


def test_local_home_health_preserves_catalog_time_and_never_checks_remote_areas(
    tmp_path: Path,
) -> None:
    root, manifests, config = _catalog(tmp_path)
    content = b"verified"
    _manifest(manifests, dataset_id="active", content=content)
    target = root / "equities/active.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    catalog_snapshot = inspect_catalog(config_path=config, manifest_dir=manifests)
    database = tmp_path / "state.sqlite3"
    initialize_database(database).close()
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    catalog_time = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
    observed_at = datetime(2026, 9, 18, 10, 5, tzinfo=timezone.utc)

    readings = local_home_health_readings(
        database=database,
        artifact_root=artifact_root,
        catalog_snapshot=catalog_snapshot,
        catalog_checked_at=catalog_time,
        required_dataset_ids=("active",),
        observed_at=observed_at,
    )
    by_area = {reading.area: reading for reading in readings}

    assert by_area["database"].status == "Available"
    assert by_area["database"].checked_at == "2026-09-18T10:05:00Z"
    assert by_area["cache"].status == "Available"
    assert by_area["cache"].checked_at == "2026-09-18T10:00:00Z"
    assert by_area["artifact"].status == "Available"
    assert by_area["artifact"].checked_at == "2026-09-18T10:05:00Z"
    for area in ("worker", "provider", "credential"):
        assert by_area[area].status == "Not checked"
        assert by_area[area].checked_at is None


def test_registered_layout_mounts_one_truthful_local_snapshot_on_home_and_system(
    tmp_path: Path,
) -> None:
    root, manifests, config = _catalog(tmp_path)
    content = b"active configuration data"
    _manifest(manifests, dataset_id="active", content=content)
    target = root / "equities/active.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    snapshot = inspect_catalog(config_path=config, manifest_dir=manifests)
    database = tmp_path / "state.sqlite3"
    initialize_database(database).close()
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    catalog_checked_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    configuration = SavedConfigurationView(
        configuration_id="configuration-active",
        experiment_id="health-fixture",
        strategy_id="health_fixture_strategy",
        strategy_version="1.0.0",
        strategy_name="Health Fixture",
        lifecycle="infrastructure_fixture",
        active=True,
        parameters={"fixture": True},
        execution={"kind": "fixture"},
        market_data={"dataset_id": "active"},
        config_hash="health-fixture-hash",
    )

    mounted = create_layout(
        None,
        (configuration,),
        dashboard_database=database,
        artifact_root=artifact_root,
        catalog_snapshot=snapshot,
        catalog_checked_at=catalog_checked_at,
    )
    by_id = {
        component.id: component
        for component in _walk_components(mounted)
        if getattr(component, "id", None) is not None
    }

    home_database = by_id["home-health-database"]
    home_cache = by_id["home-health-cache"]
    home_artifact = by_id["home-health-artifact"]
    assert by_id["health-freshness-interval"].interval == 30_000
    snapshot = by_id["health-observation-snapshot"].data
    assert snapshot["stale_after_seconds"] == 900.0
    assert "SENSITIVE_SENTINEL" not in str(snapshot)
    assert "system-health-summary" in by_id
    assert "Available" in _component_text(home_database)
    assert "Available" in _component_text(home_cache)
    assert "Available" in _component_text(home_artifact)
    for area in ("worker", "provider", "credential"):
        text = _component_text(by_id[f"home-health-{area}"])
        assert "Not checked" in text
        assert "Last checked: Not checked" in text

    system_text = _component_text(by_id["route-system"])
    assert "Research database Available" in system_text
    assert "Artifact storage Available" in system_text
    assert "Local data Available" in system_text
    assert home_database.children[-1].children in system_text
    assert home_cache.children[-1].children in system_text
    assert home_artifact.children[-1].children in system_text
    assert catalog_checked_at.isoformat().replace("+00:00", "Z") in system_text


@pytest.mark.parametrize("field", ("catalog_checked_at", "observed_at"))
def test_local_home_health_fails_closed_for_timezoneless_observations(
    tmp_path: Path,
    field: str,
) -> None:
    database = tmp_path / "state.sqlite3"
    initialize_database(database).close()
    values = {
        "database": database,
        "artifact_root": tmp_path,
        "catalog_snapshot": (None, (), "not configured"),
        "catalog_checked_at": datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc),
        "required_dataset_ids": (),
        "observed_at": datetime(2026, 9, 18, 10, 5, tzinfo=timezone.utc),
    }
    values[field] = datetime(2026, 9, 18, 10, 0)

    readings = local_home_health_readings(**values)
    by_area = {reading.area: reading for reading in readings}

    if field == "catalog_checked_at":
        assert by_area["cache"].status == "Not checked"
        assert by_area["cache"].checked_at is None
    else:
        for area in ("database", "artifact"):
            assert by_area[area].status == "Not checked"
            assert by_area[area].checked_at is None


def test_local_home_health_fails_closed_for_future_catalog_observation(
    tmp_path: Path,
) -> None:
    observed_at = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)

    readings = local_home_health_readings(
        database=tmp_path / "missing.sqlite3",
        artifact_root=tmp_path,
        catalog_snapshot=(None, (), "not configured"),
        catalog_checked_at=observed_at + timedelta(seconds=1),
        required_dataset_ids=("active",),
        observed_at=observed_at,
    )
    cache = next(reading for reading in readings if reading.area == "cache")

    assert cache.status == "Not checked"
    assert cache.checked_at is None
    assert "invalid" in cache.detail
