"""Deterministic tests for database bootstrap, schema versioning and migrations."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from persistence import LATEST_SCHEMA_VERSION, SchemaVersionError, initialize_database
import persistence.database as database
from tests.test_persistence import _db_path


def test_fresh_database_initialization_schema_version_and_restart(tmp_path):
    path = _db_path(tmp_path)
    connection = initialize_database(path)
    version = connection.execute(
        "SELECT schema_version FROM schema_metadata"
    ).fetchone()["schema_version"]
    assert version == LATEST_SCHEMA_VERSION
    connection.close()

    restarted = initialize_database(path)
    assert restarted.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    restarted.close()


def test_default_database_path_is_anchored_to_repository_root(tmp_path, monkeypatch):
    monkeypatch.delenv(database.ENV_DATABASE_PATH, raising=False)
    monkeypatch.chdir(tmp_path)
    assert database.database_path() == (
        Path(database.__file__).resolve().parents[1]
        / "state"
        / "quant_factory.sqlite3"
    )

    explicit = tmp_path / "explicit.sqlite3"
    assert database.database_path(explicit) == explicit

    override = tmp_path / "override.sqlite3"
    monkeypatch.setenv(database.ENV_DATABASE_PATH, str(override))
    assert database.database_path() == override


def test_migration_failure_leaves_no_partial_schema(tmp_path, monkeypatch):
    path = _db_path(tmp_path)
    monkeypatch.setattr(
        database,
        "MIGRATION_001_STATEMENTS",
        database.MIGRATION_001_STATEMENTS[:2]
        + ("INSERT INTO missing_table VALUES (1)",)
        + database.MIGRATION_001_STATEMENTS[2:],
    )
    with pytest.raises(sqlite3.Error):
        database.initialize_database(path)

    connection = sqlite3.connect(path)
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    connection.close()
    assert tables == []


def test_initialize_database_closes_connection_on_schema_error(tmp_path, monkeypatch):
    class TrackingConnection(sqlite3.Connection):
        closed = False

        def close(self):
            type(self).closed = True
            super().close()

    path = tmp_path / "newer.sqlite3"
    setup = sqlite3.connect(path)
    setup.execute(
        "CREATE TABLE schema_metadata (schema_version INTEGER PRIMARY KEY, migration_id TEXT, applied_at TEXT)"
    )
    setup.execute(
        "INSERT INTO schema_metadata VALUES (?, ?, ?)",
        (LATEST_SCHEMA_VERSION + 1, "future", "2026-01-01T00:00:00Z"),
    )
    setup.commit()
    setup.close()

    def tracking_connect(path_arg=None):
        connection = sqlite3.connect(path, factory=TrackingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    monkeypatch.setattr(database, "connect", tracking_connect)
    with pytest.raises(SchemaVersionError):
        database.initialize_database(path)
    assert TrackingConnection.closed is True



def test_corrupt_and_newer_schema_fail_clearly(tmp_path):
    corrupt = tmp_path / "corrupt.sqlite3"
    connection = sqlite3.connect(corrupt)
    connection.execute("CREATE TABLE orphan (id INTEGER)")
    connection.commit()
    connection.close()
    with pytest.raises(SchemaVersionError, match="no schema metadata"):
        initialize_database(corrupt)

    newer = tmp_path / "newer.sqlite3"
    connection = sqlite3.connect(newer)
    connection.execute(
        "CREATE TABLE schema_metadata (schema_version INTEGER PRIMARY KEY, migration_id TEXT, applied_at TEXT)"
    )
    connection.execute(
        "INSERT INTO schema_metadata VALUES (?, ?, ?)",
        (LATEST_SCHEMA_VERSION + 1, "future", "2026-01-01T00:00:00Z"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(SchemaVersionError, match="newer than supported"):
        initialize_database(newer)


def test_database_and_sidecar_files_are_git_ignored():
    import subprocess

    paths = [
        "state/quant_factory.sqlite3",
        "state/quant_factory.sqlite3-wal",
        "state/quant_factory.sqlite3-shm",
    ]
    completed = subprocess.run(
        ["git", "check-ignore", *paths],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.splitlines() == paths
