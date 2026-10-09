from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from dashboard.overview_projection import load_dashboard_snapshot


def _legacy_runtime_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE schema_metadata (schema_version INTEGER NOT NULL);
        INSERT INTO schema_metadata VALUES (7);
        CREATE TABLE strategies (
          strategy_id TEXT, strategy_version TEXT, display_name TEXT,
          lifecycle TEXT, active INTEGER, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE idea_drafts (
          draft_id TEXT, title TEXT, description TEXT, candidate_json TEXT,
          configuration_id TEXT, updated_at TEXT
        );
        CREATE TABLE experiment_configurations (
          configuration_id TEXT, experiment_id TEXT, strategy_id TEXT,
          strategy_version TEXT, canonical_config_json TEXT, created_at TEXT
        );
        CREATE TABLE experiment_runs (
          run_id TEXT, configuration_id TEXT, strategy_id TEXT,
          strategy_version TEXT, stage TEXT, status TEXT, started_at TEXT,
          completed_at TEXT, error_summary TEXT, created_at TEXT
        );
        CREATE TABLE parameter_results (
          run_id TEXT, row_id TEXT, metrics_json TEXT, ranking_position INTEGER,
          screening_status TEXT
        );
        CREATE TABLE run_operator_events (run_id TEXT, source TEXT, message TEXT);
        """
    )
    configuration = json.dumps(
        {"market_data": {"asset_class": "futures", "symbol": "MES"}}
    )
    connection.execute(
        "INSERT INTO strategies VALUES (?,?,?,?,?,?,?)",
        ("legacy", "1", "Retained legacy study", "rejected", 0, "2026-01-01", "2026-01-01"),
    )
    connection.execute(
        "INSERT INTO experiment_configurations VALUES (?,?,?,?,?,?)",
        ("cfg", "experiment", "legacy", "1", configuration, "2026-09-01T00:00:00Z"),
    )
    connection.execute(
        "INSERT INTO experiment_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("run-ok", "cfg", "legacy", "1", "screening", "succeeded", "2026-09-01T00:00:00Z", "2026-09-01T00:10:00Z", None, "2026-09-01T00:00:00Z"),
    )
    connection.execute(
        "INSERT INTO parameter_results VALUES (?,?,?,?,?)",
        ("run-ok", "best", json.dumps({"sharpe_ratio": -1.0, "max_drawdown": -0.05}), 1, "screened_out"),
    )
    connection.commit()
    connection.close()


def test_legacy_persisted_run_remains_visible_without_candidate_draft(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    _legacy_runtime_database(database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    snapshot = load_dashboard_snapshot(database=database, window="all", market="all")

    assert snapshot["available"] is True
    assert snapshot["population_count"] == 0
    assert snapshot["operation"]["terminal"] == 1
    assert snapshot["latest_finding"]["record_type"] == "factory_study"
    assert snapshot["latest_finding"]["candidate_id"] is None
    assert snapshot["latest_finding"]["run_id"] == "run-ok"
    assert snapshot["latest_finding"]["outcome"] == "screened_out"
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
