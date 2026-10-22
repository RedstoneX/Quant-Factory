from __future__ import annotations

import dataclasses

from orchestration.auto_campaign import AutoTestRequest, dataset_profile, run_auto_test
from agent_gateway.results import retest_settled
from agent_gateway.store import GatewayStore
from persistence import PersistenceService
from tests.test_auto_campaign import RULES, FakeAdapter, Harness, _chain


def _run(tmp_path, adapter, rules, profile, launches, rebuild=False):
    definition = adapter.definition(candidate_id="idea_relink01", title="Relink", rule_spec=rules, variables={})
    request = AutoTestRequest(
        candidate_id="idea_relink01", definition=definition, profile=profile,
        database=str(tmp_path / "qf.sqlite3"), artifact_root=str(tmp_path / "artifacts"), rebuild=rebuild,
    )

    def launch(configuration_id, key):
        launches.append(configuration_id)
        return "run_" + "0" * 32, _chain()

    return run_auto_test(request, adapter=adapter, launch=launch, data_check=lambda *_: None)


def _draft(tmp_path):
    service = PersistenceService(tmp_path / "qf.sqlite3")
    try:
        service.save_idea_draft(title="Relink", draft_id="idea_relink01")
    finally:
        service.close()


def test_rerun_with_later_data_cutoff_reuses_linked_configuration(tmp_path):
    adapter = FakeAdapter(tmp_path / "rule_strategies")
    profile = dataset_profile("MES", "5m")
    _draft(tmp_path)
    launches: list[str] = []
    assert _run(tmp_path, adapter, RULES, profile, launches).state == "survivor"
    later = dataclasses.replace(profile, dataset_end="2026-10-14T17:20:00Z")
    assert _run(tmp_path, adapter, RULES, later, launches).state == "survivor"
    assert len(launches) == 2 and launches[0] == launches[1]


def test_rerun_with_changed_rules_fails_in_plain_english(tmp_path):
    adapter = FakeAdapter(tmp_path / "rule_strategies")
    profile = dataset_profile("MES", "5m")
    _draft(tmp_path)
    launches: list[str] = []
    _run(tmp_path, adapter, RULES, profile, launches)
    outcome = _run(tmp_path, adapter, {**RULES, "max_trades_per_session": 2}, profile, launches)
    assert (outcome.state, outcome.reason_code) == ("failed", "rules_changed")
    assert "different rules" in outcome.reason_detail and len(launches) == 1


def test_operator_retest_builds_a_new_setup_and_keeps_the_old_one(tmp_path):
    adapter = FakeAdapter(tmp_path / "rule_strategies")
    profile = dataset_profile("MES", "5m")
    _draft(tmp_path)
    launches: list[str] = []
    _run(tmp_path, adapter, RULES, profile, launches)
    corrected = dataclasses.replace(profile, requested_start="2021-05-03")
    assert _run(tmp_path, adapter, RULES, corrected, launches, rebuild=True).state == "survivor"
    assert len(launches) == 2 and launches[0] != launches[1]
    service = PersistenceService(tmp_path / "qf.sqlite3")
    try:
        assert service.idea_drafts.get("idea_relink01").configuration_id == launches[1]
        assert service.configurations.get(launches[0]) is not None  # the old setup is kept
        assert "2021-05-03" in service.configurations.get(launches[1]).canonical_config_json
    finally:
        service.close()


def test_operator_retest_still_refuses_changed_rules(tmp_path):
    adapter = FakeAdapter(tmp_path / "rule_strategies")
    profile = dataset_profile("MES", "5m")
    _draft(tmp_path)
    launches: list[str] = []
    _run(tmp_path, adapter, RULES, profile, launches)
    outcome = _run(tmp_path, adapter, {**RULES, "max_trades_per_session": 2}, profile, launches, rebuild=True)
    assert (outcome.state, outcome.reason_code) == ("failed", "rules_changed") and len(launches) == 1


def test_only_an_operator_retest_asks_for_a_fresh_setup(tmp_path):
    harness = Harness(tmp_path)
    harness.draft("idea_rebuild1")
    seen = []
    campaign = harness.campaign(executor=lambda request: seen.append(request.rebuild) or harness.executor(request))
    campaign.run_once()
    store = GatewayStore(harness.gateway_database)
    try:
        retest_settled(store, "idea_rebuild1", "stage 1 screens in-sample only")
    finally:
        store.close()
    campaign.run_once()
    assert seen == [False, True]
