from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from dashboard.factory_projection import load_factory_summary
from tests.test_dashboard_overview_projection import _legacy_runtime_database


def _database(tmp_path: Path, gateway_states: list[str]) -> Path:
    database = tmp_path / "state.sqlite3"
    _legacy_runtime_database(database)
    connection = sqlite3.connect(database)
    connection.execute("INSERT INTO idea_drafts VALUES ('idea-1','T','D','{\"candidate\":{}}','cfg','2026-09-01')")
    connection.execute("INSERT INTO experiment_runs VALUES ('run-orphan','cfg','legacy','1','screening','running','2026-10-14T21:08:00Z',NULL,NULL,'2026-10-14T21:08:00Z')")
    connection.commit()
    connection.close()
    gateway = tmp_path / "gateway.sqlite3"
    conn = sqlite3.connect(gateway)
    conn.execute("CREATE TABLE campaign_events (event_id INTEGER PRIMARY KEY, candidate_id TEXT, policy_id TEXT, state TEXT, reason_code TEXT, reason_detail TEXT)")
    for state in gateway_states:
        conn.execute("INSERT INTO campaign_events (candidate_id,policy_id,state,reason_code,reason_detail) VALUES ('idea-1','p',?,'x','')", (state,))
    conn.commit()
    conn.close()
    return database


def test_run_left_running_by_restart_is_not_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database(tmp_path, ["running", "queued"])
    monkeypatch.setenv("QF_GATEWAY_DB_PATH", str(tmp_path / "gateway.sqlite3"))
    assert load_factory_summary(database=database)["counts"]["running"] == 0


def test_run_whose_idea_is_running_is_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database(tmp_path, ["queued", "running"])
    monkeypatch.setenv("QF_GATEWAY_DB_PATH", str(tmp_path / "gateway.sqlite3"))
    assert load_factory_summary(database=database)["counts"]["running"] == 1
