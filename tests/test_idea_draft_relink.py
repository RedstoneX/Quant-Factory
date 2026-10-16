from __future__ import annotations

import dataclasses

from orchestration.auto_campaign import AutoTestRequest, dataset_profile, run_auto_test
from persistence import PersistenceService
from tests.test_auto_campaign import RULES, FakeAdapter, _chain


def _run(tmp_path, adapter, rules, profile, launches):
    definition = adapter.definition(candidate_id="idea_relink01", title="Relink", rule_spec=rules, variables={})
    request = AutoTestRequest(
        candidate_id="idea_relink01", definition=definition, profile=profile,
        database=str(tmp_path / "qf.sqlite3"), artifact_root=str(tmp_path / "artifacts"),
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
