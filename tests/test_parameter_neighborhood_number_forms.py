"""Stress-test neighbourhood must treat grid value 1 and locked 1.0 as the same setting."""
from __future__ import annotations

import pytest

from backtesting.robustness import NeighborhoodConfig, ParameterNeighborhoodDefinition, build_neighborhood
from strategies.rule_spec_strategy import RuleSpecStrategy, rule_strategy_definition
from tests.test_rule_spec_strategy import _spec


@pytest.fixture()
def strategy():
    spec = _spec([{"when": {"gt": ["close", {"mul": [{"param": "trail"}, 40]}]}, "side": "long"}])
    return RuleSpecStrategy(rule_strategy_definition(
        candidate_id="c1", title="T", rule_spec=spec, variables={"trail": {"values": [1, 1.5, 2]}}
    ))


def _config(values):
    return NeighborhoodConfig(
        definitions=(ParameterNeighborhoodDefinition("trail", "explicit_values", explicit_values=tuple(values)),),
    )


@pytest.mark.parametrize("locked", [1.0, 1.5, 2.0])
def test_mixed_grid_includes_whole_number_lock(strategy, locked):
    result = build_neighborhood(strategy, {"trail": locked}, _config([1, 1.5, 2]))
    assert [c.normalized_parameters["trail"] for c in result.candidates] == [1.0, 1.5, 2.0]
    assert sum(c.is_locked_point for c in result.candidates) == 1
    assert result.rejected_count == 0


def test_string_number_form_is_rejected_not_matched(strategy):
    result = build_neighborhood(strategy, {"trail": 1.5}, _config(["1.0", 1.5, 2]))
    assert [c.normalized_parameters["trail"] for c in result.candidates] == [1.5, 2.0]
    assert result.rejected_count == 1


def test_lock_outside_grid_still_fails(strategy):
    with pytest.raises(ValueError, match="must include locked value"):
        build_neighborhood(strategy, {"trail": 1.5}, _config([1, 2]))
