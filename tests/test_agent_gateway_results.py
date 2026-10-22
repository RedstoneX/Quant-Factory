from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_gateway.contracts import GatewayIdentity, GatewayRequest
from agent_gateway.service import AgentResearchGateway
from agent_gateway.store import GatewayStore
from orchestration.auto_campaign import POLICY_ID
from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.models import normalized_configuration_document

READER = GatewayIdentity("reader-local", "local-provider", "reader", "local", 0, os.getuid())
DRAFTER = GatewayIdentity("claude-local", "anthropic", "claude-code", "local", 1, os.getuid())
_counter = iter(range(10_000))


def _gateway(tmp_path: Path) -> AgentResearchGateway:
    return AgentResearchGateway(
        database=tmp_path / "qf.sqlite3",
        gateway_database=tmp_path / "gateway.sqlite3",
        artifact_root=tmp_path / "artifacts",
    )


def _ask(gateway, operation, identity=READER, **arguments):
    request = GatewayRequest(
        request_id=f"req_results_{next(_counter):08d}", operation=operation, arguments=arguments, payload=None
    )
    return gateway.handle(request, identity)


def _run(tmp_path: Path, stage: RunStage, *, finish: bool, artifact: tuple[ArtifactType, str, dict] | None = None) -> str:
    service = PersistenceService(tmp_path / "qf.sqlite3")
    try:
        service.register_strategy(
            strategy_id="s1", strategy_version="1.0.0", display_name="S", description="",
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        config = service.upsert_configuration(normalized_configuration_document(
            experiment_id="e", strategy_id="s1", strategy_version="1.0.0",
            market_data={"symbol": "SPY", "provider": "fixture"}, parameters={"fixture": True},
            execution={"kind": "fixture"}, ranking={"columns": ("total_return",), "ascending": (False,)},
            screening={"kind": "none"},
        ))
        run = service.create_run(
            configuration_id=config.configuration_id, strategy_id="s1", strategy_version="1.0.0", stage=stage
        )
        if artifact is not None:
            kind, name, document = artifact
            location = f"{run.run_id}/{name.replace(':', '_')}.json"
            target = tmp_path / "artifacts" / location
            target.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(document).encode()
            target.write_bytes(content)
            service.register_artifact(
                run_id=run.run_id, artifact_type=kind, logical_name=name, media_type="application/json",
                format="json", location=location, content=content,
            )
            with transaction(service.connection):
                service.results.set_data_provenance(DataProvenanceRecord(
                    run_id=run.run_id, provider="fixture", provider_implementation="fixture-provider", symbol="SPY",
                    interval="1 day", timezone="UTC", requested_coverage="2020-01-01",
                    actual_coverage="2020-01-01..2020-02-09", adjusted=True, row_count=40, cache_action="fixture",
                    validation_summary_json=canonical_json({"valid": True}),
                    manifest_reference="data/manifests/fixture.json", checksum="dataset-checksum",
                ))
                service.results.set_execution_assumptions(ExecutionAssumptionsRecord(
                    run_id=run.run_id, assumptions_json=canonical_json({"kind": "fixture"}),
                ))
            service.persist_run_manifest(service.build_run_manifest(run.run_id))
        if finish:
            service.transition_run(run.run_id, RunStatus.RUNNING)
            service.transition_run(run.run_id, RunStatus.SUCCEEDED)
        return run.run_id
    finally:
        service.close()


_OOS_REPORT = {
    "test_status": "passed",
    "metrics": {"total_return": 0.12, "max_drawdown": -0.05, "win_rate": 0.55, "number_of_trades": 40, "sharpe_ratio": 1.3},
    "selected_parameters": {"lookback": 10},
}


def test_oos_metrics_returned_after_finish(tmp_path):
    run_id = _run(tmp_path, RunStage.OOS, finish=True,
                  artifact=(ArtifactType.VALIDATION_EVIDENCE, "source_lock_evidence:abc", _OOS_REPORT))
    gateway = _gateway(tmp_path)
    for operation in ("run.results", "run.evidence"):
        response = _ask(gateway, operation, run_id=run_id)
        assert response.ok, response.error
        oos = response.result["out_of_sample"]
        assert oos["total_return"] == 0.12 and oos["max_drawdown"] == -0.05
        assert oos["win_rate"] == 0.55 and oos["number_of_trades"] == 40 and oos["sharpe_ratio"] == 1.3


def test_oos_results_refused_while_running(tmp_path):
    run_id = _run(tmp_path, RunStage.OOS, finish=False,
                  artifact=(ArtifactType.VALIDATION_EVIDENCE, "source_lock_evidence:abc", _OOS_REPORT))
    gateway = _gateway(tmp_path)
    for operation in ("run.results", "run.evidence", "run.trades"):
        response = _ask(gateway, operation, run_id=run_id)
        assert not response.ok and response.error["code"] == "protected_result_denied"


def test_walk_forward_per_fold_sharpe(tmp_path):
    document = {"evidence": {"folds": [
        {"fold_id": "fold_001", "status": "ok", "test_metrics": {"sharpe_ratio": 0.9, "total_return": 0.01}},
        {"fold_id": "fold_002", "status": "ok", "test_metrics": {"sharpe_ratio": -0.2, "total_return": -0.01}},
    ]}}
    run_id = _run(tmp_path, RunStage.WALK_FORWARD, finish=True,
                  artifact=(ArtifactType.VALIDATION_EVIDENCE, "walk_forward_evidence", document))
    response = _ask(_gateway(tmp_path), "run.results", run_id=run_id)
    assert response.ok, response.error
    assert [fold["sharpe_ratio"] for fold in response.result["walk_forward"]] == [0.9, -0.2]


def test_trade_list_in_eastern_time(tmp_path):
    trades = {"price_unit": "index_points", "trades": [{
        "Entry Index": "2026-01-05T14:35:00+00:00", "Exit Index": "2026-01-05T15:05:00+00:00",
        "Direction": "Long", "Avg Entry Price": 100.0, "Avg Exit Price": 102.5, "Return": 0.025, "PnL": 12.5,
    }]}
    run_id = _run(tmp_path, RunStage.SCREENING, finish=True,
                  artifact=(ArtifactType.TRADES_OR_ORDERS, "trades_and_orders", trades))
    response = _ask(_gateway(tmp_path), "run.trades", run_id=run_id)
    assert response.ok, response.error
    trade = response.result["trades"][0]
    assert trade["entry_time_eastern"].startswith("2026-01-05T09:35:00-05:00")
    assert trade["exit_time_eastern"].startswith("2026-01-05T10:05:00-05:00")
    assert trade["side"] == "Long" and trade["pnl_points"] == 2.5 and trade["pnl_percent"] == pytest.approx(2.5)


def test_oos_trades_returned_after_finish(tmp_path):
    trades = {"price_unit": "index_points", "trades": [{
        "Entry Index": "2026-01-05T14:35:00+00:00", "Exit Index": "2026-01-05T15:05:00+00:00",
        "Direction": "Long", "Avg Entry Price": 100.0, "Avg Exit Price": 102.5, "Return": 0.025, "PnL": 12.5,
    }]}
    run_id = _run(tmp_path, RunStage.OOS, finish=True,
                  artifact=(ArtifactType.TRADES_OR_ORDERS, "trades_and_orders", trades))
    response = _ask(_gateway(tmp_path), "run.trades", run_id=run_id)
    assert response.ok, response.error
    assert response.result["trades"][0]["side"] == "Long"


def test_trade_list_says_not_saved(tmp_path):
    run_id = _run(tmp_path, RunStage.SCREENING, finish=True)
    response = _ask(_gateway(tmp_path), "run.trades", run_id=run_id)
    assert response.ok and response.result["trades"] is None and "not saved" in response.result["note"]


def _event(tmp_path, state, code, detail=None):
    store = GatewayStore(tmp_path / "gateway.sqlite3")
    try:
        store.append_campaign_event(candidate_id="idea_requeue1", policy_id=POLICY_ID, state=state,
                                    reason_code=code, reason_detail=detail, packet_sha256="abc")
    finally:
        store.close()


def _requeue(tmp_path):
    return _ask(_gateway(tmp_path), "campaign.requeue", DRAFTER, candidate_id="idea_requeue1")


def test_requeue_allowed_after_interruption_run_error(tmp_path):
    _event(tmp_path, "failed", "run_error", "An earlier attempt was interrupted before finishing and was not run a second time.")
    response = _requeue(tmp_path)
    assert response.ok, response.error
    assert response.result["latest_event"]["state"] == "queued"
    assert response.result["latest_event"]["reason_code"] == "requeued_by_agent"


@pytest.mark.parametrize("state,code,detail", [
    ("screened_out", "no_survivor", None),
    ("duplicate_closed", "same_rules", "idea_other"),
    ("failed", "run_error", "ValueError: bad rule"),
])
def test_requeue_refused_for_merit_duplicate_and_non_interruption(tmp_path, state, code, detail):
    _event(tmp_path, state, code, detail)
    response = _requeue(tmp_path)
    assert not response.ok and response.error["code"] == "requeue_not_allowed"


def _retest(tmp_path, **arguments):
    return _ask(_gateway(tmp_path), "campaign.retest", DRAFTER, reason="stage 1 screens in-sample only", **arguments)


@pytest.mark.parametrize("state,code", [("survivor", "passed"), ("screened_out", "no_survivor"), ("failed", "run_error")])
def test_retest_queues_a_settled_idea_with_the_reason(tmp_path, state, code):
    _event(tmp_path, state, code)
    response = _retest(tmp_path, candidate_id="idea_requeue1")
    assert response.ok, response.error
    assert response.result["count"] == 1
    latest = response.result["latest_event"]
    assert (latest["state"], latest["reason_code"], latest["reason_detail"], latest["packet_sha256"]) == (
        "queued", "requeued_after_fix", "stage 1 screens in-sample only", "abc")


@pytest.mark.parametrize("state,code", [("running", "started"), ("queued", "waiting")])
def test_retest_refuses_open_ideas_and_unknown_ideas(tmp_path, state, code):
    _event(tmp_path, state, code)
    assert _retest(tmp_path, candidate_id="idea_requeue1").error["code"] == "retest_not_allowed"
    assert _retest(tmp_path, candidate_id="idea_unknown").error["code"] == "retest_not_allowed"
    assert _ask(_gateway(tmp_path), "campaign.retest", DRAFTER, candidate_id="idea_requeue1").error["code"] == "retest_reason_required"
    assert _ask(_gateway(tmp_path), "campaign.retest", READER, candidate_id="idea_requeue1", reason="x").error["code"] == "authority_denied"


def test_retest_all_settled_is_idempotent_and_skips_open_ideas(tmp_path):
    store = GatewayStore(tmp_path / "gateway.sqlite3")
    try:
        for candidate, state, code in (("idea_a", "survivor", "passed"), ("idea_b", "screened_out", "no_survivor"),
                                       ("idea_c", "running", "started")):
            store.append_campaign_event(candidate_id=candidate, policy_id=POLICY_ID, state=state,
                                        reason_code=code, packet_sha256="abc")
    finally:
        store.close()
    first = _retest(tmp_path, all_settled=True)
    assert first.ok and first.result["count"] == 2 and first.result["queued"] == ["idea_a", "idea_b"]
    second = _retest(tmp_path, all_settled=True)
    assert second.ok and second.result["count"] == 0
    store = GatewayStore(tmp_path / "gateway.sqlite3")
    try:
        events = store.connection.execute(
            "SELECT candidate_id, state FROM campaign_events ORDER BY event_id").fetchall()
    finally:
        store.close()
    assert [tuple(row) for row in events] == [("idea_a", "survivor"), ("idea_b", "screened_out"), ("idea_c", "running"),
                                              ("idea_a", "queued"), ("idea_b", "queued")]


def test_requeue_needs_authority_and_does_not_reset_interruption_budget(tmp_path):
    _event(tmp_path, "failed", "run_error", "The test was interrupted 3 times before finishing and was not started again.")
    assert _ask(_gateway(tmp_path), "campaign.requeue", READER, candidate_id="idea_requeue1").error["code"] == "authority_denied"
    for _ in range(3):
        store = GatewayStore(tmp_path / "gateway.sqlite3")
        store.append_campaign_event(candidate_id="idea_requeue1", policy_id=POLICY_ID, state="running",
                                    reason_code="started", packet_sha256="abc")
        store.close()
    _event(tmp_path, "failed", "run_error", "The test was interrupted 3 times before finishing and was not started again.")
    assert _requeue(tmp_path).ok
    store = GatewayStore(tmp_path / "gateway.sqlite3")
    try:
        assert store.campaign_attempts_since_requeue("idea_requeue1", "abc") == 3
    finally:
        store.close()
