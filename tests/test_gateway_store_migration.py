from __future__ import annotations

import sqlite3

import pytest

from agent_gateway.store import GatewayStore


def test_an_older_campaign_events_layout_is_archived_not_lost(tmp_path):
    path = tmp_path / "gateway.sqlite3"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        """
        CREATE TABLE gateway_schema (version INTEGER NOT NULL);
        INSERT INTO gateway_schema VALUES (3);
        CREATE TABLE campaign_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, policy_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
            state TEXT NOT NULL, reason_code TEXT NOT NULL, reason_detail TEXT NOT NULL,
            parameter_combinations INTEGER NOT NULL, configuration_id TEXT, run_id TEXT,
            occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
        CREATE TRIGGER campaign_events_no_update BEFORE UPDATE ON campaign_events
            BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER campaign_events_no_delete BEFORE DELETE ON campaign_events
            BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        INSERT INTO campaign_events(policy_id, candidate_id, state, reason_code, reason_detail, parameter_combinations)
            VALUES ('r15-product-validation-v1', 'qfc_old', 'implementation_blocked', 'adapter_mapping_unavailable', 'x', 3);
        """
    )
    legacy.commit()
    legacy.close()

    store = GatewayStore(path)
    try:
        store.append_campaign_event(candidate_id="qfc_new", policy_id="auto_test_v1", state="queued", reason_code="waiting")
        archived = store.connection.execute("SELECT candidate_id FROM campaign_events_archive_r15").fetchall()
        current = store.connection.execute("SELECT candidate_id FROM campaign_events").fetchall()
        for table in ("campaign_events", "campaign_events_archive_r15"):
            with pytest.raises(sqlite3.DatabaseError):
                store.connection.execute(f"DELETE FROM {table}")
    finally:
        store.close()
    assert [row[0] for row in archived] == ["qfc_old"]
    assert [row[0] for row in current] == ["qfc_new"]
    GatewayStore(path).close()  # reopening an upgraded database is a no-op
