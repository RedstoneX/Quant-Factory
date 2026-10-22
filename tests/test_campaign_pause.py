from __future__ import annotations

import os
import sqlite3

import pytest

from agent_gateway.authority import OPERATION_LEVELS
from agent_gateway.contracts import GatewayIdentity, GatewayRequest
from agent_gateway.service import AgentResearchGateway
from agent_gateway.store import SCHEMA_VERSION, GatewayStore
from orchestration.auto_campaign import AutoTestOutcome
from test_auto_campaign import RULES, Harness

READER = GatewayIdentity("reader-local", "local-provider", "reader", "local", 0, os.getuid())
OWNER = GatewayIdentity("claude-local", "anthropic", "claude-code", "local", 1, os.getuid())
_ids = iter(range(10_000))


def _gateway(tmp_path):
    return AgentResearchGateway(
        database=tmp_path / "qf.sqlite3", gateway_database=tmp_path / "gateway.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )


def _ask(gateway, operation, identity=OWNER, **arguments):
    request = GatewayRequest(request_id=f"req_pause_{next(_ids):08d}", operation=operation, arguments=arguments, payload=None)
    return gateway.handle(request, identity)


@pytest.mark.parametrize("sql", ["UPDATE campaign_control SET paused=0", "DELETE FROM campaign_control"])
def test_campaign_control_is_append_only(tmp_path, sql):
    store = GatewayStore(tmp_path / "gateway.sqlite3")
    try:
        store.append_campaign_control(True, "owner", "why")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            store.connection.execute(sql)
    finally:
        store.close()


def test_state_is_the_latest_row_and_defaults_to_not_paused(tmp_path):
    store = GatewayStore(tmp_path / "gateway.sqlite3")
    try:
        assert store.campaign_control_state()["paused"] is False
        store.append_campaign_control(True, "owner", "hold")
        assert store.campaign_control_state()["paused"] is True
        store.append_campaign_control(False, "owner2", None)
        state = store.campaign_control_state()
        assert state["paused"] is False and state["actor"] == "owner2" and state["created_at"]
    finally:
        store.close()


def test_migration_from_version_three_adds_the_table(tmp_path):
    path = tmp_path / "gateway.sqlite3"
    GatewayStore(path).close()
    raw = sqlite3.connect(path)
    raw.executescript(
        "DROP TRIGGER campaign_control_no_update; DROP TRIGGER campaign_control_no_delete;"
        "DROP TABLE campaign_control; UPDATE gateway_schema SET version=3;"
    )
    raw.commit()
    raw.close()
    store = GatewayStore(path)
    try:
        assert SCHEMA_VERSION == 4
        assert store.connection.execute("SELECT version FROM gateway_schema").fetchone()[0] == 4
        store.append_campaign_control(True, "owner")
        assert store.campaign_control_state()["paused"] is True
    finally:
        store.close()


def test_pause_resume_are_idempotent_and_audited(tmp_path):
    gateway = _gateway(tmp_path)
    first = _ask(gateway, "campaign.pause", reason="markets odd")
    assert first.ok and first.result["paused"] is True and first.result["reason"] == "markets odd"
    assert _ask(gateway, "campaign.pause").result["paused"] is True
    assert _ask(gateway, "campaign.control_status", READER).result["paused"] is True
    assert _ask(gateway, "campaign.resume").result["paused"] is False
    assert _ask(gateway, "campaign.resume").result["paused"] is False
    store = GatewayStore(tmp_path / "gateway.sqlite3")
    try:
        assert store.connection.execute("SELECT COUNT(*) FROM campaign_control").fetchone()[0] == 2
        ops = [r[0] for r in store.connection.execute("SELECT operation FROM gateway_audit ORDER BY rowid")]
        assert ops == ["campaign.pause", "campaign.pause", "campaign.resume", "campaign.resume"]
    finally:
        store.close()


def test_authority_levels_and_denial(tmp_path):
    assert OPERATION_LEVELS["campaign.pause"] == OPERATION_LEVELS["campaign.resume"] == OPERATION_LEVELS["campaign.requeue"]
    assert OPERATION_LEVELS["campaign.control_status"] == OPERATION_LEVELS["campaign.status"]
    gateway = _gateway(tmp_path)
    assert _ask(gateway, "campaign.pause", READER).error["code"] == "authority_denied"
    assert _ask(gateway, "campaign.control_status", READER).ok


def test_paused_campaign_starts_nothing_then_resumes(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_pause001")
    started = []

    def executor(request):
        started.append(request)
        return AutoTestOutcome("screened_out", "screening", "No result qualified.", "run_a")

    campaign = harness.campaign(executor)
    store = GatewayStore(harness.gateway_database)
    store.append_campaign_control(True, "owner", "hold")
    store.close()
    campaign.run_once()
    assert started == [] and harness.states("idea_pause001")[-1][0] == "queued"
    store = GatewayStore(harness.gateway_database)
    store.append_campaign_control(False, "owner")
    store.close()
    campaign.run_once()
    assert len(started) == 1 and harness.states("idea_pause001")[-1][0] == "screened_out"


def test_pause_during_a_running_test_does_not_interrupt_it_or_start_the_next(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_pause002")
    harness.draft("idea_pause003", rule_spec={**RULES, "max_trades_per_session": 7})
    started = []

    def executor(request):
        started.append(request)
        store = GatewayStore(harness.gateway_database)
        store.append_campaign_control(True, "owner")  # owner pauses mid-test
        store.close()
        return AutoTestOutcome("screened_out", "screening", "No result qualified.", "run_a")

    harness.campaign(executor).run_once()
    assert len(started) == 1
    states = {c: harness.states(c)[-1][0] for c in ("idea_pause002", "idea_pause003")}
    assert sorted(states.values()) == ["queued", "screened_out"]
