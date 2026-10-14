from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from agent_gateway.auto_campaign import MAX_ATTEMPTS, AutoTestCampaign
from agent_gateway.store import GatewayStore
from market_data import DatasetUnavailableError
from orchestration.auto_campaign import (
    POLICY_ID,
    AutoTestOutcome,
    InstalledRuleStrategy,
    campaign_idempotency_key,
    dataset_profile,
    outcome_from_chain,
    run_auto_test,
)
from orchestration.auto_campaign_process import run_in_child
from orchestration import CandidatePipelineDefinition
from persistence import PersistenceService
from strategies.rule_spec_strategy import install_rule_strategy, rule_strategy_definition

ROOT = Path(__file__).resolve().parents[1]
RULES = {
    "language": "qf_rules_v1",
    "bar": "5m",
    "tick_size": 0.25,
    "session": {"timezone": "America/New_York", "open": "09:30", "close": "16:00"},
    "flat_at": "15:55",
    "signals": [{"when": {"crosses_above": [{"sma": "close", "length": 10}, {"sma": "close", "length": 30}]}, "side": "long"}],
    "max_trades_per_session": 1,
}


class FakeAdapter:
    """The real rule compiler, installing into a temporary folder and recording installs."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.installed: list[str] = []

    def definition(self, *, candidate_id, title, rule_spec, variables):
        return rule_strategy_definition(candidate_id=candidate_id, title=title, rule_spec=rule_spec, variables=variables)

    def install(self, definition):
        identity = install_rule_strategy(dict(definition), root=self.root).spec.identity
        self.installed.append(identity.strategy_id)
        return InstalledRuleStrategy(identity.strategy_id, identity.version, identity.name, identity.description)


def _chain(status="ready_for_protected_test", stopped_at=None, reasons=("Protected test remains locked.",)):
    return SimpleNamespace(status=status, stopped_at=stopped_at, reasons=reasons)


class Harness:
    def __init__(self, tmp_path: Path, chain=None) -> None:
        self.tmp_path = tmp_path
        self.database = tmp_path / "qf.sqlite3"
        self.gateway_database = tmp_path / "gateway.sqlite3"
        self.adapter = FakeAdapter(tmp_path / "rule_strategies")
        self.chain = chain or _chain()
        self.launches: list[tuple[str, str]] = []

    def launch(self, configuration_id, key):
        self.launches.append((configuration_id, key))
        return f"run_{len(self.launches):032d}", self.chain

    def executor(self, request):
        return run_auto_test(request, adapter=self.adapter, launch=self.launch, data_check=lambda *_: None)

    def campaign(self, executor=None) -> AutoTestCampaign:
        return AutoTestCampaign(
            database=self.database, gateway_database=self.gateway_database, artifact_root=self.tmp_path / "artifacts",
            adapter=self.adapter, executor=executor or self.executor,
            rule_spec_reader=lambda packet: packet.get("rule_spec"),
        )

    def draft(self, draft_id: str, *, rule_spec=RULES, symbol="MES", variables=None) -> str:
        packet = json.loads((ROOT / "research_intake" / "mes_sma_10_30_candidate.json").read_text())
        packet["market"]["instruments"]["preferred"] = [symbol]
        packet["variables"] = variables or {}
        if rule_spec is not None:
            packet["rule_spec"] = rule_spec
        service = PersistenceService(self.database)
        try:
            service.save_idea_draft(title=f"Idea {draft_id}", draft_id=draft_id)
            service.set_idea_candidate_packet(draft_id=draft_id, candidate_json=json.dumps(packet, sort_keys=True))
        finally:
            service.close()
        time.sleep(0.002)  # distinct created_at so oldest-first order is deterministic
        return draft_id

    def events(self, candidate_id=None):
        store = GatewayStore(self.gateway_database)
        try:
            rows = store.connection.execute("SELECT * FROM campaign_events ORDER BY event_id").fetchall()
        finally:
            store.close()
        return [dict(row) for row in rows if candidate_id in (None, row["candidate_id"])]

    def states(self, candidate_id):
        return [(row["state"], row["reason_code"]) for row in self.events(candidate_id)]


def test_rules_missing_and_invalid_are_blocked_with_plain_reasons(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_missing01", rule_spec=None)
    harness.draft("idea_invalid01", rule_spec={**RULES, "invalid": True})
    harness.campaign().run_once()
    assert harness.states("idea_missing01") == [("queued", "waiting"), ("implementation_blocked", "rules_missing")]
    assert harness.states("idea_invalid01") == [("queued", "waiting"), ("implementation_blocked", "rules_invalid")]
    assert "unknown key 'invalid'" in harness.events("idea_invalid01")[-1]["reason_detail"]
    assert all(row["policy_id"] == POLICY_ID and row["created_at"].endswith("+00:00") for row in harness.events())
    assert harness.launches == []


def test_unsupported_market_is_data_unavailable_and_unreadable_data_too(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_btc00001", symbol="BTC")
    harness.campaign().run_once()
    assert harness.states("idea_btc00001")[-1] == ("implementation_blocked", "data_unavailable")
    assert "BTC" in harness.events("idea_btc00001")[-1]["reason_detail"]

    def missing(*_):
        raise DatasetUnavailableError("/var/lib/quant-factory/market-data/futures/MES/5m/x.parquet is missing")

    harness.draft("idea_mesdata1")
    harness.campaign(lambda request: run_auto_test(
        request, adapter=harness.adapter, launch=harness.launch, data_check=missing
    )).run_once()
    last = harness.events("idea_mesdata1")[-1]
    assert (last["state"], last["reason_code"]) == ("implementation_blocked", "data_unavailable")
    assert "/var/lib" not in last["reason_detail"] and harness.launches == []


def test_success_links_setup_and_survives_awaiting_owner_review(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_success1")
    harness.campaign().run_once()
    assert harness.states("idea_success1") == [
        ("queued", "waiting"), ("running", "started"), ("survivor", "awaiting_owner_review")
    ]
    strategy_id = harness.adapter.installed[0]
    configuration_id, key = harness.launches[0]
    assert key == campaign_idempotency_key("idea_success1", strategy_id) == f"idea_success1-{strategy_id}"
    assert harness.events("idea_success1")[-1]["run_id"] == "run_" + "1".rjust(32, "0")
    service = PersistenceService(harness.database)
    try:
        draft = service.idea_drafts.get("idea_success1")
        configuration = service.configurations.get(configuration_id)
    finally:
        service.close()
    assert draft.configuration_id == configuration_id
    assert configuration.strategy_id == strategy_id
    assert "fixed_rule_cost_stress" in configuration.canonical_config_json  # no variables
    harness.campaign().run_once()
    assert len(harness.events("idea_success1")) == 3  # terminal: not re-run


def test_duplicate_rules_close_before_install(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_first001")
    harness.draft("idea_second01")
    harness.campaign().run_once()
    assert harness.states("idea_second01")[-1] == ("duplicate_closed", "same_rules")
    assert harness.events("idea_second01")[-1]["reason_detail"] == "idea_first001"
    assert len(harness.adapter.installed) == 1


def test_screened_out_uses_pipeline_stage_names():
    outcome = outcome_from_chain(_chain("stopped", "walk_forward", ("Walk-forward return was negative.",)), "run_x")
    assert (outcome.state, outcome.reason_code, outcome.reason_detail) == (
        "screened_out", "walk_forward", "Walk-forward return was negative."
    )
    screened = outcome_from_chain(_chain("screened_out", "screening", ()), "run_y")
    assert (screened.state, screened.reason_code) == ("screened_out", "screening")
    assert outcome_from_chain(_chain("invalid", None, ()), "run_z").reason_code == "run_error"


def test_variables_drop_fixed_rule_stress_and_expand_grid(tmp_path):
    harness = Harness(tmp_path, chain=_chain("screened_out", "screening", ("No result qualified.",)))
    grid_rules = {**RULES, "signals": [{"when": {"crosses_above": [
        {"sma": "close", "length": {"param": "fast"}}, {"sma": "close", "length": {"param": "slow"}}]}, "side": "long"}]}
    harness.draft("idea_grid0001", rule_spec=grid_rules,
                  variables={"fast": {"values": [5, 10]}, "slow": {"values": [30]}})
    harness.campaign().run_once()
    assert harness.states("idea_grid0001")[-1] == ("screened_out", "screening")
    service = PersistenceService(harness.database)
    try:
        document = json.loads(service.configurations.get(harness.launches[0][0]).canonical_config_json)
    finally:
        service.close()
    assert "fixed_rule_cost_stress" not in json.dumps(document)
    definition = CandidatePipelineDefinition.from_configuration_document(document)
    assert definition.experiment.parameter_combinations == ({"fast": 5, "slow": 30}, {"fast": 10, "slow": 30})


def _crash_target(_request):
    raise RuntimeError("boom at /home/someone/secret/path.py line 3\nTraceback (most recent call last)")


def _sleep_target(_request):
    time.sleep(30)


def _request():
    return SimpleNamespace(candidate_id="idea_child001")


def test_child_failure_and_timeout_are_one_plain_line():
    failed = run_in_child(_request(), target=_crash_target, timeout_seconds=60)
    assert (failed.state, failed.reason_code) == ("failed", "run_error")
    assert "/home" not in failed.reason_detail and "\n" not in failed.reason_detail
    timed_out = run_in_child(_request(), target=_sleep_target, timeout_seconds=1)
    assert (timed_out.state, timed_out.reason_code) == ("failed", "run_timeout")


def test_restart_requeues_open_candidates_with_the_same_key(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_restart1")
    store = GatewayStore(harness.gateway_database)
    try:
        packet = PersistenceService(harness.database).idea_drafts.get("idea_restart1").candidate_json
        digest = hashlib.sha256(packet.encode()).hexdigest()
        store.append_campaign_event(candidate_id="idea_restart1", policy_id=POLICY_ID, state="running",
                                    reason_code="started", packet_sha256=digest)
    finally:
        store.close()
    campaign = harness.campaign()
    assert campaign.requeue_after_restart() == ["idea_restart1"]
    campaign.run_once()
    assert harness.states("idea_restart1") == [
        ("running", "started"), ("queued", "requeued_after_restart"), ("running", "started"),
        ("survivor", "awaiting_owner_review"),
    ]
    assert harness.launches[0][1] == campaign_idempotency_key("idea_restart1", harness.adapter.installed[0], 1)
    assert harness.launches[0][1].endswith("-r1")


def test_idea_interrupted_max_times_is_reported_not_rerun(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_restart2")
    store = GatewayStore(harness.gateway_database)
    try:
        packet = PersistenceService(harness.database).idea_drafts.get("idea_restart2").candidate_json
        digest = hashlib.sha256(packet.encode()).hexdigest()
        for _ in range(MAX_ATTEMPTS):
            store.append_campaign_event(candidate_id="idea_restart2", policy_id=POLICY_ID, state="running",
                                        reason_code="started", packet_sha256=digest)
    finally:
        store.close()
    campaign = harness.campaign()
    campaign.requeue_after_restart()
    campaign.run_once()
    assert harness.states("idea_restart2")[-1] == ("failed", "run_error")
    assert harness.launches == []


def test_blocked_idea_is_re_evaluated_only_when_its_packet_changes(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_change01", rule_spec=None)
    campaign = harness.campaign()
    campaign.run_once()
    campaign.run_once()
    assert len(harness.events("idea_change01")) == 2
    service = PersistenceService(harness.database)
    try:
        packet = json.loads(service.idea_drafts.get("idea_change01").candidate_json)
        packet["rule_spec"] = RULES
        service.set_idea_candidate_packet(draft_id="idea_change01", candidate_json=json.dumps(packet))
    finally:
        service.close()
    campaign.run_once()
    assert harness.states("idea_change01")[-1] == ("survivor", "awaiting_owner_review")
    digests = {row["packet_sha256"] for row in harness.events("idea_change01")}
    assert len(digests) == 2


def test_hand_built_setups_are_skipped_without_writing(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_manual01")
    request = SimpleNamespace(
        candidate_id="idea_manual01", definition=harness.adapter.definition(
            candidate_id="idea_manual01", title="t", rule_spec=RULES, variables={}),
        profile=dataset_profile("MES", "5m"), database=str(harness.database), artifact_root=str(tmp_path), attempt=0,
    )
    assert harness.executor(request).state == "survivor"
    harness.launches.clear()
    harness.campaign().run_once()
    assert harness.events() == [] and harness.launches == []


def test_only_one_run_at_a_time(tmp_path):
    harness = Harness(tmp_path)
    for index in range(3):
        harness.draft(f"idea_serial{index:02d}", rule_spec={**RULES, "max_trades_per_session": index + 1})
    active, peak, lock = [0], [0], threading.Lock()

    def slow(request):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return AutoTestOutcome("screened_out", "screening", "No result qualified.", "run_a")

    campaign = harness.campaign(slow)
    threads = [threading.Thread(target=campaign.run_once) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak[0] == 1
    assert sum(1 for row in harness.events() if row["state"] == "screened_out") == 3


@pytest.mark.parametrize("operation", ["UPDATE campaign_events SET state='x'", "DELETE FROM campaign_events"])
def test_campaign_events_are_append_only(tmp_path, operation):
    store = GatewayStore(tmp_path / "gateway.sqlite3")
    try:
        store.append_campaign_event(candidate_id="idea_append01", policy_id=POLICY_ID, state="queued", reason_code="waiting")
        with pytest.raises(Exception, match="append-only"):
            store.connection.execute(operation)
    finally:
        store.close()
