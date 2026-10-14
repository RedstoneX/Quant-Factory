"""Library indicators in qf_rules_v1: the whole VectorBT PRO / TA-Lib catalogue through one adapter."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from research_intake.starter_kit import starter_kit
from rule_language import RuleSpecError
from rule_language.indicators import INDICATORS, library_indicator, library_indicators
from strategies.rule_spec_evaluation import RuleEvaluator
from tests.test_rule_language_indicators import _bars, _evaluate, _normalized


def test_unknown_library_indicator_is_rejected_with_a_clear_message() -> None:
    with pytest.raises(RuleSpecError, match=r'indicator: .*not a usable library indicator \(names look like "talib:RSI"'):
        _normalized({"indicator": "talib:NOT_A_THING", "params": {}})


@pytest.mark.licensed_vectorbt
def test_catalogue_comes_from_the_library_metadata() -> None:
    names = {spec.name for spec in library_indicators()}
    assert len(names) >= 200
    assert {"talib:CCI", "talib:CDLDOJI", "vbt:SUPERTREND", "vbt:RSI"} <= names
    # WorldQuant alphas rank across sessions; label generators look ahead; signal generators are not indicators.
    assert not {name for name in names if name.startswith("wqa101:")}
    assert not names & {"vbt:FMEAN", "vbt:FIXLB", "vbt:RAND", "vbt:STX", "vbt:VWAP", "talib:MAVP"}
    assert library_indicator("talib:CDLDOJI").inputs == ("open", "high", "low", "close")
    assert library_indicator("talib:MA").params == (("timeperiod", "count"), ("matype", "count"))
    assert library_indicator("talib:BBANDS").params[1] == ("nbdevup", "number")


@pytest.mark.licensed_vectorbt
def test_every_named_operator_is_an_alias_of_a_usable_library_indicator() -> None:
    for name, spec in INDICATORS.items():
        if not spec.library:
            assert name in ("keltner", "donchian")
            continue
        library = library_indicator(spec.library)
        assert library is not None, name
        assert set(spec.library_params) <= {key for key, _ in library.params}, name
        assert len(spec.library_outputs) == max(len(spec.outputs), 1), name


@pytest.mark.licensed_vectorbt
def test_library_node_equals_the_named_operator() -> None:
    bars = _bars(rows=40, sessions=2)
    pairs = [
        ({"indicator": "talib:CCI", "params": {"timeperiod": 5}}, {"cci": {}, "length": 5}),
        ({"indicator": "vbt:RSI", "params": {"window": 6}}, {"rsi": "close", "length": 6}),
        (
            {"indicator": "vbt:STOCH", "params": {"fast_k_window": 5, "slow_k_window": 3, "slow_d_window": 3}, "output": "slow_d"},
            {"stochastic": {}, "k_length": 5, "k_smooth": 3, "d_length": 3, "output": "d"},
        ),
    ]
    for library, named in pairs:
        np.testing.assert_allclose(_evaluate(library, bars), _evaluate(named, bars), equal_nan=True)


@pytest.mark.licensed_vectorbt
def test_library_node_restarts_each_session_and_is_causal() -> None:
    node = {"indicator": "talib:CDLENGULFING", "params": {}}
    rsi = {"indicator": "talib:RSI", "params": {"timeperiod": 5}, "inputs": {"close": {"sma": "close", "length": 2}}}
    both = _bars(rows=40, sessions=2)
    fields = ("open", "high", "low", "close", "volume")
    first_30 = replace(both, **{key: getattr(both, key)[:30, :1] for key in fields})
    second_only = replace(both, **{key: getattr(both, key)[:, 1:] for key in fields})
    for item in (node, rsi):
        full = _evaluate(item, both)
        np.testing.assert_allclose(full[:30, :1], RuleEvaluator(first_30).series(_normalized(item)), equal_nan=True)
        np.testing.assert_allclose(full[:, 1:], RuleEvaluator(second_only).series(_normalized(item)), equal_nan=True)
    assert np.isnan(_evaluate(rsi, both)[:5, 1]).all()
    across = _evaluate({**rsi, "across_sessions": True}, both)
    assert not np.isnan(across[:5, 1]).any()


@pytest.mark.licensed_vectorbt
def test_library_node_parameters_accept_variables() -> None:
    variables = {"n": {"values": [5, 8]}}
    literal = _evaluate({"indicator": "talib:CCI", "params": {"timeperiod": 8}}, _bars(rows=40, parameters={"n": 8}))
    variable = _evaluate(
        {"indicator": "talib:CCI", "params": {"timeperiod": {"param": "n"}}}, _bars(rows=40, parameters={"n": 8}), variables
    )
    np.testing.assert_allclose(literal, variable, equal_nan=True)


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize(
    ("node", "message"),
    [
        ({"indicator": "wqa101:1", "params": {}}, "not a usable library indicator"),
        ({"indicator": "vbt:FMEAN", "params": {"window": 5, "wait": 1}}, "not a usable library indicator"),
        ({"indicator": "talib:CCI", "params": {}}, "missing required key 'timeperiod'"),
        ({"indicator": "talib:CCI", "params": {"timeperiod": 5, "timeframe": 2}}, "unknown key 'timeframe'"),
        ({"indicator": "talib:CCI", "params": {"timeperiod": "5"}}, "must be a whole number"),
        ({"indicator": "talib:BBANDS", "params": {"timeperiod": 5, "nbdevup": 2, "nbdevdn": 2, "matype": 0}}, "needs one of: upperband"),
        ({"indicator": "talib:CCI", "params": {"timeperiod": 5}, "inputs": {"open": "close"}}, "unknown key 'open'"),
    ],
)
def test_library_node_rejects_bad_names_params_and_outputs(node: dict[str, Any], message: str) -> None:
    with pytest.raises(RuleSpecError, match=message):
        _normalized(node)


@pytest.mark.licensed_vectorbt
def test_starter_kit_lists_the_library_catalogue() -> None:
    guide = starter_kit()["guide"]
    assert '{"indicator":"talib:CCI","params":{"timeperiod":20},"output":"real"}' in guide
    assert "talib:CCI(timeperiod)->real" in guide
    assert "talib:CDLDOJI()->integer" in guide
