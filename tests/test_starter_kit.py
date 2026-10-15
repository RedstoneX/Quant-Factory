from __future__ import annotations

import pytest

from research_intake import candidate_rule_spec, starter_kit, validate_candidate_packet
from rule_language import RuleSpecError, validate_rule_spec
from strategies.parameter_governance import PROVISIONAL_GRID_WARNING_THRESHOLD
from strategies.rule_spec_strategy import RuleSpecStrategy, rule_strategy_definition


def test_kit_has_four_parts_and_a_short_guide() -> None:
    kit = starter_kit()
    assert set(kit) == {"schema", "example", "guide", "indicators"}
    assert kit["schema"]["schema"] == "qf_candidate_v1"
    lines = kit["guide"].strip().splitlines()
    assert len(lines) <= 66  # 60 + six lines for exit_when, level stops, R-multiples, trail_after, every_minutes
    text = kit["guide"]
    for needed in ("5-minute", "MES", "2026-02-13", "Options", "String variables", str(PROVISIONAL_GRID_WARNING_THRESHOLD)):
        assert needed in text


def test_example_passes_intake_rule_validation_and_compiles() -> None:
    packet = starter_kit()["example"]
    result = validate_candidate_packet(packet)
    assert result.valid, [(issue.path, issue.message) for issue in result.issues if issue.severity == "error"]
    spec = candidate_rule_spec(packet)
    assert spec is not None
    assert validate_rule_spec(packet["rule_spec"], variables=packet["variables"]) == spec
    definition = rule_strategy_definition(
        candidate_id="starter-kit", title=packet["candidate"]["title"], rule_spec=packet["rule_spec"], variables=packet["variables"]
    )
    strategy = RuleSpecStrategy(definition)
    assert [p.allowed_values for p in strategy.spec.parameters] == [(5, 10, 15, 20)]


def test_kit_returns_independent_copies() -> None:
    first = starter_kit()
    first["example"]["variables"].clear()
    assert starter_kit()["example"]["variables"]


def test_example_grid_is_far_below_the_limit() -> None:
    values = starter_kit()["example"]["variables"]["fast_bars"]["values"]
    assert len(values) <= PROVISIONAL_GRID_WARNING_THRESHOLD
    with pytest.raises(RuleSpecError):
        validate_rule_spec(starter_kit()["example"]["rule_spec"], variables={})
