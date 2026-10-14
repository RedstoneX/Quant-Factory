"""qf_rules_v1 validation and Candidate intake of the optional rule_spec."""

from __future__ import annotations

import copy
import json

import pytest

from research_intake import candidate_rule_spec, validate_candidate_packet
from rule_language import MAX_RULE_DEPTH, RuleSpecError, canonical_rule_spec_json, validate_rule_spec
from tests.test_qf_candidate_v1 import _candidate_document

SESSION = {"timezone": "America/New_York", "open": "09:30", "close": "16:00"}


def _spec(**overrides) -> dict:
    spec = {
        "language": "qf_rules_v1",
        "bar": "5m",
        "tick_size": 0.25,
        "session": dict(SESSION),
        "flat_at": "15:55",
        "signals": [
            {
                "when": {"gt": ["close", {"range_high": {"from": "09:30", "to": "09:45"}}]},
                "side": "long",
            }
        ],
        "max_trades_per_session": 1,
    }
    spec.update(overrides)
    return spec


def _error(spec, variables=None) -> str:
    with pytest.raises(RuleSpecError) as caught:
        validate_rule_spec(spec, variables=variables or {})
    return str(caught.value)


def test_valid_spec_is_normalized_and_canonical() -> None:
    spec = _spec(signals=[{"when": {"gt": [{"sma": "close", "length": {"param": "fast"}}, "open"]}, "side": "short"}])
    normalized = validate_rule_spec(spec, variables={"fast": {"values": [5, 10], "rationale": "bounded"}})
    assert normalized["signals"][0]["when"]["gt"][0] == {"sma": "close", "length": {"param": "fast"}, "across_sessions": False}
    assert normalized["exit"] == {"on_opposite_signal": False}
    assert spec["signals"][0]["when"]["gt"][0] == {"sma": "close", "length": {"param": "fast"}}
    text = canonical_rule_spec_json(normalized)
    assert text == json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    assert validate_rule_spec(normalized, variables={"fast": {"values": [5, 10]}}) == normalized


@pytest.mark.parametrize(
    ("spec", "variables", "expected"),
    [
        (_spec(exit={"stop": {"ticks": 4}}), None, "rule_spec.exit: unknown key 'stop'"),
        (_spec(flat_at="9:30"), None, "rule_spec.flat_at: '9:30' is not a valid HH:MM time"),
        (_spec(flat_at="15:57"), None, "rule_spec.flat_at: 15:57 is not on the 5-minute bar grid"),
        (_spec(flat_at="16:00"), None, "rule_spec.flat_at: 16:00 must be between 09:40 and 15:55"),
        (
            _spec(signals=[{"when": {"time_between": ["10:00", "09:45"]}, "side": "long"}]),
            None,
            "rule_spec.signals[0].when.time_between: start 10:00 is after end 09:45",
        ),
        (
            _spec(signals=[{"when": {"gt": ["close", {"param": "level"}]}, "side": "long"}]),
            None,
            "rule_spec.signals[0].when.gt[1].param: 'level' is not a declared packet variable (declared: none)",
        ),
        (
            _spec(exit={"stop_loss": {"ticks": 8}}),
            None,
            "rule_spec.exit: stop_loss and take_profit must be given together",
        ),
        (
            _spec(signals=[{"when": {"gt": [{"sma": "close", "length": {"param": "n"}}, 1]}, "side": "long"}]),
            {"n": {"values": [10, 2.5]}},
            "variable 'n' value 2.5 cannot be used here",
        ),
        (_spec(), {"unused": {"values": [1, 2]}}, "variables.unused: is declared but rule_spec never uses it"),
        (_spec(session={**SESSION, "close": "13:00"}), None, "supports only the America/New_York 09:30-16:00"),
        (_spec(bar="2m"), None, 'rule_spec.bar: must be "1m" or "5m" in qf_rules_v1'),
        (
            _spec(signals=[{"when": {"gt": ["close", {"sma": "close", "length": 100}]}, "side": "long"}]),
            None,
            "rule_spec.signals[0].when.gt[1].length: must be a whole number from 1 to 78",
        ),
        (
            _spec(signals=[{"when": {"gt": ["close", True]}, "side": "long"}]),
            None,
            "true/false is not a number or series",
        ),
        (
            _spec(signals=[{"when": {"greater": ["close", 1]}, "side": "long"}]),
            None,
            "rule_spec.signals[0].when: unknown condition 'greater'",
        ),
    ],
)
def test_invalid_specs_fail_with_path_qualified_plain_messages(spec, variables, expected) -> None:
    assert expected in _error(spec, variables)


def test_depth_and_node_limits() -> None:
    deep: object = "close"
    for _ in range(MAX_RULE_DEPTH):
        deep = {"neg": deep}
    message = _error(_spec(signals=[{"when": {"gt": [deep, 0]}, "side": "long"}]))
    assert message == f"rule_spec: is nested more than {MAX_RULE_DEPTH} levels deep"
    wide = {"all": [{"gt": ["close", index]} for index in range(200)]}
    assert "rule_spec: has more than 500 elements" in _error(_spec(signals=[{"when": wide, "side": "long"}]))


def _packet_with(rule_spec) -> dict:
    packet = _candidate_document()
    packet["variables"] = {"opening_range_minutes": {"values": [5, 15, 30]}}
    if rule_spec is not None:
        packet["rule_spec"] = rule_spec
    return packet


def _range_spec() -> dict:
    return _spec(
        signals=[
            {
                "when": {"gt": ["close", {"max": "high", "length": {"param": "opening_range_minutes"}}]},
                "side": "long",
            }
        ]
    )


def test_packet_rule_spec_is_optional_validated_and_exposed() -> None:
    plain = _candidate_document()
    assert validate_candidate_packet(plain).valid
    assert candidate_rule_spec(plain) is None

    packet = _packet_with(_range_spec())
    validation = validate_candidate_packet(packet)
    assert validation.valid, validation.errors
    assert candidate_rule_spec(packet) == validate_rule_spec(_range_spec(), variables=packet["variables"])

    broken = _packet_with(_spec(flat_at="25:00"))
    errors = validate_candidate_packet(broken).errors
    assert [(issue.code, issue.path) for issue in errors] == [("rule_spec", "rule_spec.flat_at")]
    assert errors[0].message.startswith("rule_spec.flat_at: '25:00' is not a valid HH:MM time")
    with pytest.raises(RuleSpecError):
        candidate_rule_spec(broken)


def test_packet_rule_spec_bar_must_match_market_timeframe() -> None:
    packet = _packet_with(_range_spec())
    packet["market"] = copy.deepcopy(packet["market"]) | {"timeframe": "15m"}
    errors = validate_candidate_packet(packet).errors
    assert [issue.path for issue in errors] == ["rule_spec.bar"]
    assert "must equal market.timeframe ('15m')" in errors[0].message
