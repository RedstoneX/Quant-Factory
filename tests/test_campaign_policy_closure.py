from __future__ import annotations

import json

from agent_gateway.campaign_policy import R15_POLICY_ID
from agent_gateway.contracts import GatewayIdentity, GatewayRequest
from agent_gateway.service import AgentResearchGateway
from persistence import PersistenceService


def _candidate(index: int) -> dict:
    return {
        "schema": "qf_candidate_v1",
        "candidate": {"title": f"MES bounded hypothesis {index}", "family": f"family_{index}", "status": "draft"},
        "hypothesis": {"behavior": "A bounded intraday effect may persist.", "failure_theory": ["The effect may be noise."]},
        "market": {"holding_style": "intraday", "overnight_positions": False, "instruments": {"preferred": ["MES"]}},
        "rules": {"entry": ["Enter after a completed bar."], "exit": ["Exit in-session."]},
        "sources": [{"type": "owner_observation", "title": "Bounded test", "claim": "A testable behavior may exist."}],
        "fixed": {"flat_by_close": True, "dataset_id": "futures_MES_5m_databento"},
        "variables": {"lookback": {"values": [5]}},
        "variants": [], "open_questions": [],
        "implementation": {"strategy_id": f"unmapped_{index}"},
    }


def test_r15_ceiling_rejects_new_candidate_before_canonical_persistence(tmp_path):
    gateway = AgentResearchGateway(
        database=tmp_path / "qf.sqlite3",
        gateway_database=tmp_path / "gateway.sqlite3",
        artifact_root=tmp_path / "artifacts",
        run_launcher=lambda *_: "unused",
        campaign_policy_id=R15_POLICY_ID,
    )
    identity = GatewayIdentity("codex-local", "openai", "codex", "local", 2)
    for index in range(12):
        response = gateway.handle(
            GatewayRequest(f"req_r15_cap_{index:08d}", "candidate.submit", {}, json.dumps(_candidate(index))),
            identity,
        )
        assert response.ok

    denied = gateway.handle(
        GatewayRequest("req_r15_cap_00000012", "candidate.submit", {}, json.dumps(_candidate(12))),
        identity,
    )
    assert denied.ok is False
    assert denied.error["code"] == "campaign_closed"
    service = PersistenceService(tmp_path / "qf.sqlite3")
    try:
        assert len(service.idea_drafts.list()) == 12
    finally:
        service.close()
    status = gateway.handle(GatewayRequest("req_bootstrap_closed", "bootstrap", {}), identity)
    assert status.result["campaign"]["state"] == "closed"
    assert status.result["campaign"]["accepted_candidates"] == 12
