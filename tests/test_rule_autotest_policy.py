from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from execution.paper_handoff import PaperHandoffPackage
from rule_language import RuleSpecError, validate_rule_spec
from strategies.parameter_governance import (
    PROVISIONAL_GRID_WARNING_THRESHOLD,
    summarize_parameter_plan,
)
from strategies.rule_spec_strategy import (
    BACKTEST_APPROVAL_PROVENANCE,
    RuleSpecStrategy,
    install_rule_strategy,
    rule_strategy_definition,
)

SESSION = {"timezone": "America/New_York", "open": "09:30", "close": "16:00"}
REPO = Path(__file__).resolve().parents[1]


def _spec(when: dict) -> dict:
    return {
        "language": "qf_rules_v1",
        "bar": "5m",
        "tick_size": 0.25,
        "session": dict(SESSION),
        "flat_at": "15:55",
        "signals": [{"when": when, "side": "long"}],
        "max_trades_per_session": 1,
    }


def _two_variable_spec() -> dict:
    return _spec(
        {"gt": [{"sma": "close", "length": {"param": "a"}}, {"sma": "close", "length": {"param": "b"}}]}
    )


def _grid(a_count: int, b_count: int) -> dict:
    return {
        "a": {"values": list(range(2, 2 + a_count))},
        "b": {"values": list(range(2, 2 + b_count))},
    }


def test_rule_strategies_are_approved_for_backtests_with_exact_provenance() -> None:
    definition = rule_strategy_definition(
        candidate_id="c", title="t", rule_spec=_two_variable_spec(), variables=_grid(2, 3)
    )
    spec = RuleSpecStrategy(definition).spec
    assert BACKTEST_APPROVAL_PROVENANCE == (
        "Owner standing policy 2026-10-13: auto-test every valid idea; backtesting only; "
        "paper trading requires separate owner approval."
    )
    assert spec.approval_state == "approved" and spec.source == BACKTEST_APPROVAL_PROVENANCE
    assert spec.parameters and all(
        p.approval_state == "approved" and p.source == BACKTEST_APPROVAL_PROVENANCE for p in spec.parameters
    )
    assert summarize_parameter_plan(spec, require_approved=True).total_combinations == 6


def test_backtest_approval_does_not_make_a_rules_strategy_paper_eligible() -> None:
    # Paper handoff needs an eligibility decision and an owner-activated lane policy
    # that no strategy specification can supply.
    required = {
        field.name
        for field in dataclasses.fields(PaperHandoffPackage)
        if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING
    }
    assert {"eligibility_decision_id", "lane_policy_id", "paper_risk_policy_id", "eligibility_gate_ids"} <= required
    # Nothing in the paper boundary or the candidate paper column reads approval_state.
    for path in [*sorted((REPO / "execution").glob("*.py")), REPO / "dashboard" / "candidates_projection.py"]:
        assert "approval_state" not in path.read_text(encoding="utf-8"), path
    definition = rule_strategy_definition(rule_spec=_two_variable_spec(), variables=_grid(2, 2))
    spec = RuleSpecStrategy(definition).spec
    assert "paper" not in {spec.identity.family, spec.identity.strategy_id.split("_")[0]}
    assert "paper trading requires separate owner approval" in spec.source


def test_grid_cap_accepts_the_limit_and_rejects_one_over() -> None:
    assert PROVISIONAL_GRID_WARNING_THRESHOLD == 100
    at_limit = validate_rule_spec(_two_variable_spec(), variables=_grid(10, 10))
    assert at_limit["signals"]
    with pytest.raises(RuleSpecError) as caught:
        validate_rule_spec(_two_variable_spec(), variables=_grid(10, 11))
    assert caught.value.path == "variables" and "110" in str(caught.value)
    with pytest.raises(RuleSpecError):
        rule_strategy_definition(rule_spec=_two_variable_spec(), variables=_grid(11, 10))


def test_same_rules_different_titles_share_one_id_and_both_install(tmp_path) -> None:
    spec = _two_variable_spec()
    first = rule_strategy_definition(candidate_id="c1", title="First idea", rule_spec=spec, variables=_grid(2, 2))
    second = rule_strategy_definition(candidate_id="c2", title="Other title", rule_spec=spec, variables=_grid(2, 2))
    assert first == second and first["strategy_id"] == second["strategy_id"]
    assert set(first) == {"strategy_id", "version", "rule_spec", "variables"}
    one = install_rule_strategy(first, root=tmp_path)
    two = install_rule_strategy(second, root=tmp_path)
    assert one is two and len(list(tmp_path.glob("rules_*.json"))) == 1


def test_different_rules_or_variables_give_different_ids() -> None:
    base = rule_strategy_definition(rule_spec=_two_variable_spec(), variables=_grid(2, 2))
    other_values = rule_strategy_definition(rule_spec=_two_variable_spec(), variables=_grid(2, 3))
    other_rules = rule_strategy_definition(
        rule_spec=_spec({"gt": [{"sma": "close", "length": {"param": "a"}}, {"sma": "close", "length": {"param": "b"}}]}) | {"flat_at": "15:50"},
        variables=_grid(2, 2),
    )
    assert len({base["strategy_id"], other_values["strategy_id"], other_rules["strategy_id"]}) == 3
