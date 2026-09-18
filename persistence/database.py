"""SQLite connection setup and deterministic schema migrations."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
from typing import Iterator

LATEST_SCHEMA_VERSION = 4
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = Path("state") / "quant_factory.sqlite3"
ENV_DATABASE_PATH = "QUANT_FACTORY_DB_PATH"
MIGRATION_001_STATEMENTS = (
    """
    CREATE TABLE schema_metadata (
        schema_version INTEGER NOT NULL PRIMARY KEY,
        migration_id TEXT NOT NULL,
        applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )
    """,
    """
    CREATE TABLE strategies (
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        display_name TEXT NOT NULL,
        description TEXT NOT NULL,
        lifecycle TEXT NOT NULL,
        active INTEGER NOT NULL CHECK (active IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (strategy_id, strategy_version)
    )
    """,
    """
    CREATE TABLE experiment_configurations (
        configuration_id TEXT NOT NULL PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        canonical_config_json TEXT NOT NULL,
        config_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (strategy_id, strategy_version)
            REFERENCES strategies(strategy_id, strategy_version)
            ON DELETE RESTRICT,
        UNIQUE (config_hash)
    )
    """,
    """
    CREATE TABLE experiment_runs (
        run_id TEXT NOT NULL PRIMARY KEY,
        configuration_id TEXT NOT NULL,
        strategy_id TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        stage TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        error_summary TEXT,
        environment_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (configuration_id)
            REFERENCES experiment_configurations(configuration_id)
            ON DELETE RESTRICT,
        FOREIGN KEY (strategy_id, strategy_version)
            REFERENCES strategies(strategy_id, strategy_version)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE parameter_results (
        run_id TEXT NOT NULL,
        row_id TEXT NOT NULL,
        normalized_parameters_json TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        ranking_position INTEGER NOT NULL,
        screening_status TEXT NOT NULL,
        rejection_reasons TEXT NOT NULL,
        PRIMARY KEY (run_id, row_id),
        FOREIGN KEY (run_id)
            REFERENCES experiment_runs(run_id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE data_provenance (
        run_id TEXT NOT NULL PRIMARY KEY,
        provider TEXT NOT NULL,
        provider_implementation TEXT NOT NULL,
        symbol TEXT NOT NULL,
        interval TEXT NOT NULL,
        timezone TEXT NOT NULL,
        requested_coverage TEXT NOT NULL,
        actual_coverage TEXT NOT NULL,
        adjusted INTEGER NOT NULL CHECK (adjusted IN (0, 1)),
        row_count INTEGER NOT NULL,
        cache_action TEXT NOT NULL,
        validation_summary_json TEXT NOT NULL,
        manifest_reference TEXT,
        checksum TEXT,
        FOREIGN KEY (run_id)
            REFERENCES experiment_runs(run_id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE execution_assumptions (
        run_id TEXT NOT NULL PRIMARY KEY,
        assumptions_json TEXT NOT NULL,
        FOREIGN KEY (run_id)
            REFERENCES experiment_runs(run_id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE artifact_references (
        artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        path TEXT NOT NULL,
        validation_status TEXT NOT NULL,
        checksum TEXT,
        availability TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (run_id)
            REFERENCES experiment_runs(run_id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE review_current_state (
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        state TEXT NOT NULL,
        note TEXT NOT NULL,
        operator TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (target_type, target_id)
    )
    """,
    """
    CREATE TABLE review_audit_history (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        prior_state TEXT,
        new_state TEXT NOT NULL,
        note TEXT NOT NULL,
        operator TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX idx_runs_strategy ON experiment_runs(strategy_id, strategy_version)",
    "CREATE INDEX idx_runs_status_stage ON experiment_runs(status, stage, created_at)",
    "CREATE INDEX idx_parameter_results_run_rank ON parameter_results(run_id, ranking_position)",
    "CREATE INDEX idx_artifacts_run ON artifact_references(run_id, artifact_type)",
    "CREATE INDEX idx_review_state ON review_current_state(state, target_type)",
)

MIGRATION_002_STATEMENTS = (
    """
    CREATE TABLE run_operator_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        severity TEXT NOT NULL,
        source TEXT NOT NULL,
        message TEXT NOT NULL,
        FOREIGN KEY (run_id)
            REFERENCES experiment_runs(run_id)
            ON DELETE RESTRICT
    )
    """,
    "CREATE INDEX idx_run_operator_events_run ON run_operator_events(run_id, occurred_at, event_id)",
    "CREATE INDEX idx_run_operator_events_recent ON run_operator_events(occurred_at DESC, event_id DESC)",
    """
    CREATE TRIGGER run_operator_events_no_update
    BEFORE UPDATE ON run_operator_events
    BEGIN
        SELECT RAISE(ABORT, 'run operator events are append-only');
    END
    """,
    """
    CREATE TRIGGER run_operator_events_no_delete
    BEFORE DELETE ON run_operator_events
    BEGIN
        SELECT RAISE(ABORT, 'run operator events are append-only');
    END
    """,
)

MIGRATION_003_STATEMENTS = (
    "ALTER TABLE experiment_runs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
)

MIGRATION_004_STATEMENTS = (
    "ALTER TABLE artifact_references ADD COLUMN logical_name TEXT",
    "ALTER TABLE artifact_references ADD COLUMN media_type TEXT",
    "ALTER TABLE artifact_references ADD COLUMN format TEXT",
    "ALTER TABLE artifact_references ADD COLUMN checksum_algorithm TEXT",
    "ALTER TABLE artifact_references ADD COLUMN size_bytes INTEGER",
    "ALTER TABLE artifact_references ADD COLUMN location TEXT",
    "ALTER TABLE artifact_references ADD COLUMN identity_key TEXT",
    "UPDATE artifact_references SET logical_name=path, media_type='application/octet-stream', format='unknown', checksum_algorithm='sha256', size_bytes=0, location=path, identity_key='legacy:' || artifact_id WHERE logical_name IS NULL",
    "CREATE UNIQUE INDEX idx_artifacts_identity_key ON artifact_references(identity_key)",
    "CREATE INDEX idx_artifacts_contract_order ON artifact_references(run_id, artifact_type, logical_name, artifact_id)",
    """
    CREATE TABLE run_manifests (
        run_id TEXT NOT NULL PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        manifest_json TEXT NOT NULL,
        content_checksum TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES experiment_runs(run_id) ON DELETE RESTRICT
    )
    """,
)


class DatabaseError(RuntimeError):
    """Raised when the local experiment database is unusable."""


class SchemaVersionError(DatabaseError):
    """Raised when schema metadata is missing, corrupt, or unsupported."""


def database_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    if ENV_DATABASE_PATH in os.environ:
        return Path(os.environ[ENV_DATABASE_PATH])
    return REPOSITORY_ROOT / DEFAULT_DATABASE_PATH


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    resolved = database_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        connection.execute("BEGIN")
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _schema_version(connection: sqlite3.Connection) -> int | None:
    if not _table_exists(connection, "schema_metadata"):
        return None
    rows = connection.execute(
        "SELECT schema_version FROM schema_metadata ORDER BY schema_version"
    ).fetchall()
    if len(rows) != 1:
        raise SchemaVersionError("schema metadata is corrupt")
    return int(rows[0]["schema_version"])


def initialize_database(path: str | Path | None = None) -> sqlite3.Connection:
    """Open the database and migrate an empty file to the latest schema."""
    connection = connect(path)
    try:
        current = _schema_version(connection)
        if current is None:
            if connection.execute(
                "SELECT COUNT(*) AS count FROM sqlite_master WHERE type='table'"
            ).fetchone()["count"]:
                raise SchemaVersionError("database has tables but no schema metadata")
            _migrate_empty_to_v1(connection)
            current = 1
        if current > LATEST_SCHEMA_VERSION:
            raise SchemaVersionError(
                f"database schema {current} is newer than supported {LATEST_SCHEMA_VERSION}"
            )
        while current < LATEST_SCHEMA_VERSION:
            if current == 1:
                _migrate_v1_to_v2(connection)
                current = 2
            elif current == 2:
                _migrate_v2_to_v3(connection)
                current = 3
            elif current == 3:
                _migrate_v3_to_v4(connection)
                current = 4
            else:
                raise SchemaVersionError(
                    f"database schema {current} cannot be migrated by this version"
                )
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except Exception:
        connection.close()
        raise


def _migrate_empty_to_v1(connection: sqlite3.Connection) -> None:
    with transaction(connection):
        for statement in MIGRATION_001_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            """
            INSERT INTO schema_metadata (schema_version, migration_id)
            VALUES (?, ?)
            """,
            (1, "001_initial_experiment_database"),
        )


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    with transaction(connection):
        for statement in MIGRATION_002_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            """
            UPDATE schema_metadata
            SET schema_version=?, migration_id=?
            """,
            (2, "002_run_operator_events"),
        )


def _migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
    with transaction(connection):
        for statement in MIGRATION_003_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            """
            UPDATE schema_metadata
            SET schema_version=?, migration_id=?
            """,
            (3, "003_run_attempt_tracking"),
        )


def _migrate_v3_to_v4(connection: sqlite3.Connection) -> None:
    with transaction(connection):
        for statement in MIGRATION_004_STATEMENTS:
            connection.execute(statement)
        connection.execute(
            "UPDATE schema_metadata SET schema_version=?, migration_id=?",
            (4, "004_artifact_identity_and_run_manifests"),
        )
