from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from dashboard.overview_projection import (
    SURVIVOR_EVENT_MESSAGE,
    SURVIVOR_EVENT_SOURCE,
    load_candidate_detail,
    load_candidates_page,
    load_candidates_summary,
)


def _candidate_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE schema_metadata (schema_version INTEGER NOT NULL);
        INSERT INTO schema_metadata VALUES (7);
        CREATE TABLE strategies (strategy_id TEXT);
        CREATE TABLE idea_drafts (draft_id TEXT, title TEXT, description TEXT, candidate_json TEXT, configuration_id TEXT, updated_at TEXT);
        CREATE TABLE experiment_configurations (configuration_id TEXT, canonical_config_json TEXT);
        CREATE TABLE experiment_runs (run_id TEXT, configuration_id TEXT, stage TEXT, status TEXT, started_at TEXT, completed_at TEXT, error_summary TEXT, created_at TEXT);
        CREATE TABLE parameter_results (run_id TEXT, row_id TEXT, metrics_json TEXT, ranking_position INTEGER, screening_status TEXT);
        CREATE TABLE run_operator_events (run_id TEXT, source TEXT, message TEXT);
        """
    )
    now = "2026-10-09T00:00:00+00:00"
    candidates = [
        ("gold", "Gold edge", "Exact survivor", {"candidate": {"title": "Gold edge", "family": "Breakout", "status": "owner_approved"}}, "gold-cfg"),
        ("active", "Active edge", "In progress", {"candidate": {"title": "Active edge", "family": "Momentum", "status": "owner_approved"}}, "active-cfg"),
        ("closed", "Closed edge", "Evidence retained", {"candidate": {"title": "Closed edge", "family": "Reversion", "status": "rejected"}}, "closed-cfg"),
        ("exception", "Exception edge", "Meaning unresolved", {"candidate": {"title": "Exception edge", "family": "Reversion", "status": "exception_hold"}}, None),
    ]
    for candidate_id, title, description, packet, configuration_id in candidates:
        connection.execute("INSERT INTO idea_drafts VALUES (?,?,?,?,?,?)", (candidate_id, title, description, json.dumps(packet), configuration_id, now))
        if configuration_id:
            connection.execute("INSERT INTO experiment_configurations VALUES (?,?)", (configuration_id, json.dumps({"market_data": {"symbol": "MES", "asset_class": "futures"}})))
    connection.executemany("INSERT INTO experiment_runs VALUES (?,?,?,?,?,?,?,?)", [
        ("gold-oos", "gold-cfg", "oos", "succeeded", now, now, None, now),
        ("active-wf", "active-cfg", "walk_forward", "running", now, None, None, now),
        ("closed-oos", "closed-cfg", "oos", "succeeded", now, now, None, now),
    ])
    connection.executemany("INSERT INTO parameter_results VALUES (?,?,?,?,?)", [
        ("gold-oos", "gold-row", json.dumps({"sharpe_ratio": 1.8, "max_drawdown": -0.06, "total_return": 0.27}), 1, "passed"),
        ("closed-oos", "closed-row", json.dumps({"sharpe_ratio": 0.3, "max_drawdown": -0.12, "total_return": -0.04}), 1, "screened_out"),
    ])
    connection.execute("INSERT INTO run_operator_events VALUES (?,?,?)", ("gold-oos", SURVIVOR_EVENT_SOURCE, SURVIVOR_EVENT_MESSAGE))
    connection.commit(); connection.close()


def test_candidates_projection_is_bounded_sorted_filterable_and_exact(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"; _candidate_database(database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    summary = load_candidates_summary(database=database)
    assert summary["counts"] == {"survivor": 1, "advancing": 1, "needs_review": 1, "rejected": 1, "all": 4}
    assert summary["families"] == ["Breakout", "Momentum", "Reversion"]

    survivors = load_candidates_page(database=database, lifecycle="survivor", start=0, end=50)
    assert survivors["rowCount"] == 1
    assert survivors["rowData"][0]["candidate_id"] == "gold"
    assert survivors["rowData"][0]["sharpe"] == 1.8
    assert survivors["rowData"][0]["max_drawdown"] == 6.0
    assert survivors["rowData"][0]["net_return"] == 27.0

    filtered = load_candidates_page(database=database, lifecycle="all", market="futures", family="Reversion", search="closed", start=0, end=1, sort_model=[{"colId": "net_return", "sort": "asc"}])
    assert filtered["rowCount"] == 1 and filtered["rowData"][0]["candidate_id"] == "closed"

    detail = load_candidate_detail("gold", database=database)
    assert detail is not None and detail["candidate_id"] == "gold"
    assert detail["run_id"] == "gold-oos"
    assert detail["progression"] == [{"run_id": "gold-oos", "stage": "oos", "status": "succeeded", "created_at": "2026-10-09T00:00:00+00:00", "completed_at": "2026-10-09T00:00:00+00:00", "error_summary": None}]
    assert load_candidate_detail("missing", database=database) is None
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
