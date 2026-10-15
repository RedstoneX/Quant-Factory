"""Drilling into a survivor: unseen-data numbers, the Open Results target and luck scores.

The pipeline saves unseen-data metrics only in its OOS report (no parameter rows) and
saves luck scores flat in the rolling-test evidence; the dashboard must read both.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from dashboard import score_projection
from dashboard.candidates_projection import load_candidate_detail, load_candidates_page
from dashboard.overview_projection import SURVIVOR_EVENT_MESSAGE, SURVIVOR_EVENT_SOURCE
from dashboard.results_projection import _oos_metric_fields, oos_report_metrics
from dashboard.score_projection import load_shortlist

NOW = "2026-10-15T00:00:00+00:00"


def _write_artifact(connection: sqlite3.Connection, root: Path, run_id: str, name: str, document: dict) -> None:
    content = (json.dumps(document) + "\n").encode()
    location = f"{run_id}/{name.replace(':', '_').replace('/', '_')}.json"
    (root / run_id).mkdir(parents=True, exist_ok=True)
    (root / location).write_bytes(content)
    connection.execute(
        "INSERT INTO artifact_references VALUES (?,?,?,?,?,?,?)",
        (run_id, name, location, hashlib.sha256(content).hexdigest(), len(content), "available", "json"),
    )


def _database(tmp_path: Path, *, test_status: str = "passed") -> Path:
    path = tmp_path / "quant_factory.sqlite3"
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
        CREATE TABLE artifact_references (run_id TEXT, logical_name TEXT, location TEXT, checksum TEXT, size_bytes INTEGER, availability TEXT, format TEXT);
        """
    )
    packet = {"candidate": {"title": "MES edge", "family": "Breakout", "status": "owner_approved"}}
    connection.execute("INSERT INTO idea_drafts VALUES (?,?,?,?,?,?)", ("mes", "MES edge", "d", json.dumps(packet), "cfg", NOW))
    connection.execute("INSERT INTO experiment_configurations VALUES (?,?)", ("cfg", json.dumps({"market_data": {"symbol": "MES"}})))
    runs = [("run-screen", "screening", "2026-10-15T01:00:00+00:00"), ("run-oos", "oos", "2026-10-15T02:00:00+00:00"),
            ("run-wf", "walk_forward", "2026-10-15T03:00:00+00:00"), ("run-mc", "monte_carlo", "2026-10-15T04:00:00+00:00")]
    connection.executemany("INSERT INTO experiment_runs VALUES (?,?,?,?,?,?,?,?)", [(r, "cfg", s, "succeeded", c, c, None, c) for r, s, c in runs])
    # the pipeline saves screening rows, but none for the OOS run
    connection.execute("INSERT INTO parameter_results VALUES (?,?,?,?,?,?,?)", ("run-screen", "row", "{}", json.dumps({"sharpe_ratio": 2.0}), 1, "passed", ""))
    connection.execute("INSERT INTO run_operator_events VALUES (?,?,?)", ("run-oos", SURVIVOR_EVENT_SOURCE, SURVIVOR_EVENT_MESSAGE))
    _write_artifact(connection, tmp_path, "run-oos", "source_lock_evidence:out_of_sample", {
        "artifact_kind": "out_of_sample", "test_status": test_status,
        "metrics": {"sharpe_ratio": 1.4, "max_drawdown": -0.05, "total_return": 0.12, "number_of_trades": 30},
    })
    _write_artifact(connection, tmp_path, "run-wf", "walk_forward_evidence", {"evidence": {
        "folds": [{"test_metrics": {"total_return": 0.01, "sharpe_ratio": 1.0}}],
        "idea_overfitting": {"deflated_sharpe_probability": 0.83, "trial_count": 6, "pbo": 0.4, "pbo_split_count": 70},
    }})
    connection.commit()
    connection.close()
    return path


def test_ideas_row_shows_unseen_data_numbers_from_the_oos_report(tmp_path: Path) -> None:
    database = _database(tmp_path)
    row = load_candidates_page(database=database, lifecycle="all", start=0, end=10)["rowData"][0]
    assert (row["sharpe"], row["max_drawdown"], row["net_return"]) == (1.4, 5.0, 12.0)
    assert load_candidate_detail("mes", database=database)["sharpe"] == 1.4


def test_shortlist_includes_passed_idea_with_luck_scores(tmp_path: Path) -> None:
    rows = load_shortlist(database=_database(tmp_path))
    assert [r["candidate_id"] for r in rows] == ["mes"] and rows[0]["sharpe"] == 1.4
    assert rows[0]["luck"] == 0.83 and rows[0]["overfitting"] == 0.4


def test_shortlist_leaves_out_idea_that_failed_unseen_data(tmp_path: Path) -> None:
    assert load_shortlist(database=_database(tmp_path, test_status="screened_out")) == []


def test_open_results_targets_unseen_data_run_not_the_last_run(tmp_path: Path) -> None:
    detail = load_candidate_detail("mes", database=_database(tmp_path))
    assert detail["run_id"] == "run-mc" and detail["results_run_id"] == "run-oos"


def test_open_results_falls_back_to_screening_run(tmp_path: Path) -> None:
    database = _database(tmp_path)
    connection = sqlite3.connect(database)
    connection.execute("UPDATE experiment_runs SET status='failed' WHERE stage='oos'")
    connection.commit()
    connection.close()
    assert load_candidate_detail("mes", database=database)["results_run_id"] == "run-screen"


def test_unseen_data_run_page_gets_metric_fields(tmp_path: Path) -> None:
    database = _database(tmp_path)
    assert oos_report_metrics(database=database, run_id="run-wf") is None
    fields = {f["label"]: f["value"] for f in _oos_metric_fields(database, {"run_id": "run-oos", "stage": "oos"})}
    assert {"Total Return", "Sharpe Ratio", "Max Drawdown", "Number Of Trades"} <= set(fields)
    assert _oos_metric_fields(database, {"run_id": "run-wf", "stage": "walk_forward"}) == []


def test_run_scores_read_the_flat_keys_the_pipeline_writes(tmp_path: Path) -> None:
    scores = score_projection.load_run_scores("run-wf", database=_database(tmp_path))
    assert scores["luck"] == 0.83 and scores["overfitting"] == 0.4
