"""Source-lock comparison must treat 1 and 1.0 as the same grid value."""
from __future__ import annotations

import pytest

import strategies
from backtesting.validation.evidence_service import ValidationEvidenceArtifactService as Svc
from strategies.rule_spec_strategy import RuleSpecStrategy, rule_strategy_definition
from tests.test_rule_spec_strategy import _spec

GRID = [{"trail": 1}, {"trail": 1.5}, {"trail": 2}]


@pytest.fixture()
def strategy_id(monkeypatch):
    spec = _spec([{"when": {"gt": ["close", {"sma": "close", "length": {"param": "trail"}}]}, "side": "long"}])
    definition = rule_strategy_definition(
        candidate_id="c1", title="T", rule_spec=spec, variables={"trail": {"values": [1, 1.5, 2]}}
    )
    strategy = RuleSpecStrategy(definition)
    monkeypatch.setattr(strategies, "get_strategy", lambda _id: strategy)
    return definition["strategy_id"]


@pytest.mark.parametrize("winner", [1.0, 1.5, 2.0])
def test_normalised_lock_matches_raw_grid(strategy_id, winner):
    assert Svc._configuration_allows_locked_parameters(GRID, {"trail": winner}, strategy_id=strategy_id)


def test_different_locked_value_still_fails(strategy_id):
    assert not Svc._configuration_allows_locked_parameters(GRID, {"trail": 3.0}, strategy_id=strategy_id)


def test_single_configuration_form_matches(strategy_id):
    assert Svc._configuration_allows_locked_parameters({"trail": 1}, {"trail": 1.0}, strategy_id=strategy_id)
