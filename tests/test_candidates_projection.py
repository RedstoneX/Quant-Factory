from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from dashboard.candidates_projection import (
    load_candidate_detail,
    load_candidates_page,
    load_candidates_summary,
)
from dashboard.overview_projection import SURVIVOR_EVENT_MESSAGE, SURVIVOR_EVENT_SOURCE


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
        CREATE TABLE parameter_results (run_id TEXT, row_id TEXT, normalized_parameters_json TEXT, metrics_json TEXT, ranking_position INTEGER, screening_status TEXT, rejection_reasons TEXT);
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
        ("active-wf", "active-cfg", "walk_forward", "created", now, None, None, now),
        ("closed-oos", "closed-cfg", "oos", "succeeded", now, now, None, now),
    ])
    connection.executemany("INSERT INTO parameter_results VALUES (?,?,?,?,?,?,?)", [
        ("gold-oos", "gold-row", "{}", json.dumps({"sharpe_ratio": 1.8, "max_drawdown": -0.06, "total_return": 0.27}), 1, "passed", ""),
        ("closed-oos", "closed-row", "{}", json.dumps({"sharpe_ratio": 0.3, "max_drawdown": -0.12, "total_return": -0.04}), 1, "screened_out", "Sharpe below gate"),
    ])
    connection.execute("INSERT INTO run_operator_events VALUES (?,?,?)", ("gold-oos", SURVIVOR_EVENT_SOURCE, SURVIVOR_EVENT_MESSAGE))
    connection.commit(); connection.close()


def test_candidates_projection_is_bounded_sorted_filterable_and_exact(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"; _candidate_database(database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    summary = load_candidates_summary(database=database)
    assert summary["counts"] == {"survivor": 1, "advancing": 1, "needs_review": 1, "rejected": 1, "blocked": 0, "duplicate": 0, "crashed": 0, "all": 4}
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
    assert detail["progression"] == [{"run_id": "gold-oos", "stage": "oos", "status": "succeeded", "created_at": "2026-10-09T00:00:00+00:00", "completed_at": "2026-10-09T00:00:00+00:00", "error_summary": None, "passed_count": 1, "result_count": 1}]
    assert load_candidate_detail("missing", database=database) is None
    closed_detail = load_candidate_detail("closed", database=database)
    assert closed_detail is not None
    assert closed_detail["screening_count"] == 1
    assert closed_detail["screened_out_count"] == 1
    assert closed_detail["screening_sharpe"] == 0.3
    assert closed_detail["screening_reasons"] == "Sharpe below gate"
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_home_and_ideas_share_one_count_definition(tmp_path: Path) -> None:
    from dashboard.overview_projection import load_dashboard_snapshot

    database = tmp_path / "state.sqlite3"; _candidate_database(database)
    connection = sqlite3.connect(database)
    connection.execute("INSERT INTO idea_drafts VALUES (?,?,?,?,?,?)", ("probe", "Connection test 7", "", json.dumps({"candidate": {"title": "Connection test 7"}}), None, "2026-10-09T00:00:00+00:00"))
    for statement in (  # the home page also reads run-level columns the Ideas fixture leaves out
        "ALTER TABLE strategies ADD COLUMN strategy_version TEXT", "ALTER TABLE strategies ADD COLUMN display_name TEXT",
        "ALTER TABLE experiment_runs ADD COLUMN strategy_id TEXT", "ALTER TABLE experiment_runs ADD COLUMN strategy_version TEXT",
        "ALTER TABLE experiment_configurations ADD COLUMN experiment_id TEXT",
    ):
        connection.execute(statement)
    connection.commit(); connection.close()

    ideas = load_candidates_summary(database=database)["counts"]
    home = load_dashboard_snapshot(window="ytd", database=database)
    assert home["population_count"] == ideas["all"] == 4  # the throwaway entry is in neither
    assert home["counts"]["advancing"] == ideas["advancing"] == 1


def test_tile_notes_and_stress_note_explain_themselves() -> None:
    from dashboard.ui.layout import stat_card
    from dashboard.ui.scores import score_cards

    assert "after trading costs" in str(stat_card("Net return", "1.62%")).lower()
    failed = {"stress_status": "failed", "stress_failed": ["the shuffled-trades check"]}
    stress = str(score_cards(failed)[2])
    assert "not a pass mark" in stress and "shuffled-trades" in stress
    assert "not a pass mark" not in str(score_cards({"stress_status": "passed"})[2])
