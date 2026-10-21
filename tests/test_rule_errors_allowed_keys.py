"""RuleSpecError messages for unknown keys and names list the allowed ones (sorted) plus an example form."""

from __future__ import annotations

import copy

from rule_language.validation import CONDITION_OPERATORS, PRICE_FIELDS, SERIES_OPERATORS, _EXIT_KEYS
from tests.test_rule_language import _error, _spec


def _with_when(when) -> dict:
    spec = copy.deepcopy(_spec())
    spec["signals"][0]["when"] = when
    return spec


def test_unknown_top_level_key_lists_sorted_allowed_keys() -> None:
    message = _error(_spec(stop={"ticks": 4}))
    assert "rule_spec: unknown key 'stop'" in message
    assert "(allowed: bar, exit, flat_at, language, max_trades_per_session, session, signals, skip_days, tick_size)" in message


def test_unknown_exit_key_lists_sorted_allowed_keys() -> None:
    message = _error(_spec(exit={"stop": {"ticks": 4}}))
    assert "rule_spec.exit: unknown key 'stop'" in message
    assert f"(allowed: {', '.join(sorted(_EXIT_KEYS))})" in message


def test_unknown_condition_lists_sorted_operators_and_example() -> None:
    message = _error(_with_when({"greater": ["close", 1]}))
    assert "rule_spec.signals[0].when: unknown condition 'greater'" in message
    assert f"(allowed: {', '.join(sorted(CONDITION_OPERATORS))})" in message
    assert '; e.g. {"gt": ["close", "open"]}' in message


def test_unknown_series_lists_sorted_operators_and_example() -> None:
    message = _error(_with_when({"gt": [{"average": "close"}, 1]}))
    assert "rule_spec.signals[0].when.gt[0]: unknown series 'average'" in message
    assert f"(allowed: {', '.join(sorted(SERIES_OPERATORS))})" in message
    assert '; e.g. {"sma": "close", "length": 20}' in message


def test_unknown_price_field_lists_sorted_fields() -> None:
    message = _error(_with_when({"gt": ["price", 1]}))
    assert "unknown price field 'price'" in message
    assert f"(allowed: {', '.join(sorted(PRICE_FIELDS))})" in message


def test_unknown_distance_kind_lists_sorted_kinds_and_example() -> None:
    message = _error(_spec(exit={"stop_loss": {"pips": 4}}))
    assert "rule_spec.exit.stop_loss: unknown distance 'pips'" in message
    assert "(allowed: atr, level, percent, points, r_multiple, signal_bar, ticks)" in message
    assert '; e.g. {"ticks": 4}' in message
