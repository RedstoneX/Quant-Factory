"""Trader-facing Dashboard and Factory runs: one count, a true funnel, plain words, no junk rows."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from dashboard.factory_projection import load_factory_page, load_factory_summary, plain_error
from dashboard.overview_projection import load_dashboard_snapshot
from dashboard.ui.theme import AG_GRID_THEME, MANTINE_THEME
from tests.test_dashboard_overview_projection import _legacy_runtime_database

CONFIG = json.dumps({"market_data": {"asset_class": "futures", "symbol": "MES"}})


def _database(tmp_path: Path, runs: list[tuple], titles: dict[str, str] | None = None) -> Path:
    """runs: (run_id, config, stage, status, error). Each config gets one idea; one extra result per succeeded run."""
    path = tmp_path / "state.sqlite3"
    _legacy_runtime_database(path)
    connection = sqlite3.connect(path)
    connection.execute("DELETE FROM experiment_runs"); connection.execute("DELETE FROM parameter_results")
    connection.execute("DELETE FROM experiment_configurations")
    for config in sorted({run[1] for run in runs}):
        connection.execute("INSERT INTO experiment_configurations VALUES (?,?,?,?,?,?)",
                           (config, (titles or {}).get(config, config), "legacy", "1", CONFIG, "2026-10-01T00:00:00Z"))
        connection.execute("INSERT INTO idea_drafts VALUES (?,?,?,?,?,?)",
                           (f"idea-{config}", (titles or {}).get(config, config), "", json.dumps({"candidate": {"title": (titles or {}).get(config, config)}}), config, "2026-10-01T00:00:00Z"))
    for index, (run_id, config, stage, status, error) in enumerate(runs):
        stamp = f"2026-10-01T00:{index:02d}:00Z"
        connection.execute("INSERT INTO experiment_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (run_id, config, "legacy", "1", stage, status, stamp, stamp if status != "running" else None, error, stamp))
        if status == "succeeded" and not run_id.startswith("empty"):
            connection.execute("INSERT INTO parameter_results VALUES (?,?,?,?,?)",
                               (run_id, f"{run_id}-r", json.dumps({"sharpe_ratio": 1.0}), 1, "passed"))
    connection.commit(); connection.close()
    return path


def test_dashboard_and_factory_count_running_from_one_rule(tmp_path: Path) -> None:
    path = _database(tmp_path, [("r1", "c1", "screening", "running", None), ("r2", "c2", "oos", "created", None)])
    snapshot = load_dashboard_snapshot(database=path, window="all")["counts"]
    factory = load_factory_summary(database=path)["counts"]
    # Both runs belong to ideas with no live campaign event, so the leftover "running" row is not running.
    assert snapshot["running"] == factory["running"] == 0
    assert snapshot["queued"] == factory["queued"] == 1
    assert snapshot["failed"] == factory["failed"] == 1
    assert factory["open"] == 1


def test_funnel_never_grows_going_down(tmp_path: Path) -> None:
    path = _database(tmp_path, [
        ("a", "c1", "screening", "succeeded", None), ("b", "c2", "oos", "succeeded", None),
        ("c", "c3", "walk_forward", "succeeded", None), ("d", "c4", "screening", "failed", "x"),
    ])
    stages = load_dashboard_snapshot(database=path, window="all")["stages"]
    order = [stages[key] for key in ("submitted", "costs", "oos", "walk_forward", "robustness", "survivors")]
    assert order == sorted(order, reverse=True)
    assert order[:4] == [4, 3, 2, 1]


def test_winner_open_targets_the_unseen_data_run(tmp_path: Path) -> None:
    path = _database(tmp_path, [("shot", "c1", "screening", "succeeded", None), ("oos-run", "c1", "oos", "succeeded", None),
                                ("later", "c1", "screening", "succeeded", None)])
    chart = load_dashboard_snapshot(database=path, window="all")["chart"]
    assert [item["run_id"] for item in chart] == ["oos-run"]


def test_developer_wording_is_translated() -> None:
    assert plain_error("Test process lost; Prefect run marked Crashed by operator") == \
        "Stopped by the operator after a server restart. Safe to run again."
    assert "Prefect" not in plain_error("Prefect said no")


def test_test_junk_and_empty_runs_hidden_by_default_but_kept(tmp_path: Path) -> None:
    path = _database(tmp_path, [("good", "c1", "oos", "succeeded", None), ("empty-1", "c2", "screening", "succeeded", None),
                                ("junk", "c3", "screening", "failed", "boom")],
                     titles={"c3": "Connection test: ping"})
    shown = [row["run_id"] for row in load_factory_page(cohort="completed", database=path)["rowData"]]
    assert shown == ["good"]
    assert load_factory_page(cohort="failed", database=path)["rowCount"] == 0
    everything = load_factory_page(cohort="completed", show_hidden=True, database=path)["rowData"]
    empty = next(row for row in everything if row["run_id"] == "empty-1")
    assert empty["results_note"] == "Finished with no settings to test" and empty["hidden"]
    assert load_factory_summary(database=path)["counts"]["completed"] == 1


def test_text_is_phone_readable() -> None:
    sizes = {key: int(value.removesuffix("px")) for key, value in MANTINE_THEME["fontSizes"].items()}
    assert sizes["md"] >= 15 and sizes["sm"] >= 14 and sizes["xs"] >= 13
    assert '"fontSize": 14' in AG_GRID_THEME["function"]
