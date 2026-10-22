from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from orchestration.auto_campaign import AutoTestOutcome, run_auto_test
from persistence import PersistenceService
from research_intake import starter_kit
from tests.test_auto_campaign import FakeAdapter, _chain
from tools import local_run


def _frame(rows):
    return pd.DataFrame(rows, columns=["stage", "parameters", "metric", "value"])


def test_exactly_one_mode_is_required():
    parser = local_run.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--run-id", "a", "--rerun", "b"])
    assert parser.parse_args(["--rerun", "run_1"]).rerun == "run_1"


def test_storage_requires_all_three_environment_variables():
    with pytest.raises(SystemExit, match="QUANT_FACTORY_DATA_LOCATIONS"):
        local_run.storage_from_environment({"QUANT_FACTORY_DB_PATH": "/db", "QUANT_FACTORY_ARTIFACT_ROOT": "/a"})
    database, artifacts = local_run.storage_from_environment(
        {"QUANT_FACTORY_DB_PATH": "/db", "QUANT_FACTORY_ARTIFACT_ROOT": "/a", "QUANT_FACTORY_DATA_LOCATIONS": "/d"}
    )
    assert (str(database), str(artifacts)) == ("/db", "/a")


def test_local_launcher_calls_the_runtime_without_prefect():
    calls = []
    runtime = SimpleNamespace(execute_flow=lambda **kwargs: calls.append(kwargs) or "chain")
    submission = SimpleNamespace(run_id="run_abc")
    assert local_run.local_pipeline_launcher(runtime=runtime, submission=submission) == "chain"
    assert calls == [{"submission": submission, "prefect_flow_run_id": "local-run_abc"}]


def test_packet_goes_through_run_auto_test_and_the_saved_idea(tmp_path, monkeypatch):
    database = tmp_path / "qf.sqlite3"
    packet = tmp_path / "idea.json"
    packet.write_text(json.dumps(starter_kit()["example"]), encoding="utf-8")
    seen = []
    monkeypatch.setattr(
        local_run, "run_auto_test",
        lambda request, **kwargs: seen.append(request) or run_auto_test(request, **kwargs, data_check=lambda *_: None),
    )
    launches = []

    def launch(configuration_id, key):
        launches.append((configuration_id, key))
        return "run_" + "1" * 32, _chain()

    outcome = local_run.run_packet(
        packet, database=database, artifact_root=tmp_path / "artifacts",
        adapter=FakeAdapter(tmp_path / "rule_strategies"), launch=launch,
    )
    assert (outcome.state, outcome.run_id) == ("survivor", "run_" + "1" * 32)
    assert len(seen) == 1 and len(launches) == 1
    service = PersistenceService(database)
    try:
        draft = service.idea_drafts.get(seen[0].candidate_id)
    finally:
        service.close()
    assert draft is not None and draft.configuration_id == launches[0][0]


def test_packet_without_rules_is_reported_not_run(tmp_path):
    example = starter_kit()["example"]
    example.pop("rule_spec")
    packet = tmp_path / "idea.json"
    packet.write_text(json.dumps(example), encoding="utf-8")
    outcome = local_run.run_packet(
        packet, database=tmp_path / "qf.sqlite3", artifact_root=tmp_path / "artifacts",
        adapter=FakeAdapter(tmp_path / "rule_strategies"), launch=lambda *_: pytest.fail("must not launch"),
    )
    assert (outcome.state, outcome.reason_code) == ("implementation_blocked", "rules_missing")


def test_identical_metrics_within_float_tolerance_match():
    old = _frame([("screening", "{}", "sharpe", 1.0), ("oos", "", "status", "passed"), ("oos", "", "eligible_to_progress", True)])
    new = _frame([("screening", "{}", "sharpe", 1.0 + 1e-13), ("oos", "", "status", "passed"), ("oos", "", "eligible_to_progress", True)])
    assert local_run.metric_differences(old, new).empty


def test_changed_and_one_sided_metrics_are_all_reported():
    old = _frame([("screening", "{}", "sharpe", 1.0), ("screening", "", "data_checksum", "aaa"), ("oos", "", "status", "passed")])
    new = _frame([("screening", "{}", "sharpe", 1.2), ("screening", "", "data_checksum", "bbb"), ("monte_carlo", "", "status", "passed")])
    differences = local_run.metric_differences(old, new)
    assert set(zip(differences["stage"], differences["metric"])) == {
        ("screening", "sharpe"), ("screening", "data_checksum"), ("oos", "status"), ("monte_carlo", "status"),
    }


def test_rerun_exit_code_reports_differences(monkeypatch, capsys):
    environment = {"QUANT_FACTORY_DB_PATH": "/db", "QUANT_FACTORY_ARTIFACT_ROOT": "/a", "QUANT_FACTORY_DATA_LOCATIONS": "/d"}
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    outcome = AutoTestOutcome("survivor", "awaiting_owner_review", None, "run_new")
    monkeypatch.setattr(local_run, "rerun", lambda *_args, **_kwargs: (outcome, _frame([])))
    assert local_run.main(["--rerun", "run_old"]) == 0
    assert "no metric differences" in capsys.readouterr().out
    changed = pd.DataFrame([{"stage": "screening", "parameters": "{}", "metric": "sharpe", "value_old": 1.0, "value_new": 1.2}])
    monkeypatch.setattr(local_run, "rerun", lambda *_args, **_kwargs: (outcome, changed))
    assert local_run.main(["--rerun", "run_old"]) == 3
    assert "sharpe" in capsys.readouterr().out
