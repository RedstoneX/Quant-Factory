"""All settings in one pass: the batch compiler must equal a per-setting reference bit for bit.

The reference below is the per-setting compiler as it stood before the batch path (one session loop, one
fresh evaluator and one Python state machine per setting); it is the oracle, not production code.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from rule_language.validation import STOP_KEYS
from strategies.mes_opening_range_breakout import _schedule
from strategies.models import SignalResult
from tests.rule_trades import trades
from strategies.rule_spec_evaluation import RuleEvaluator, SessionBars, bar_position
from strategies.rule_spec_strategy import RuleSpecStrategy, rule_strategy_definition
from tests.test_rule_spec_strategy import _frame, _spec

FIELDS = ("entries", "exits", "short_entries", "short_exits", "stop_loss", "take_profit", "trailing_stop")
EVENT_FIELD = {"entry": "entries", "exit": "exits", "short_entry": "short_entries", "short_exit": "short_exits"}


def _reference(definition: dict, data: pd.DataFrame, parameters: dict) -> dict[str, pd.Series | None]:
    spec, frame = definition["rule_spec"], data.copy()
    frame.index = frame.index.tz_convert("UTC")
    sessions = []
    for _, row in _schedule(frame.index).iterrows():
        start, end = pd.Timestamp(row["market_open"]).tz_convert("UTC"), pd.Timestamp(row["market_close"]).tz_convert("UTC")
        expected = pd.date_range(start, end, freq="5min", inclusive="left")
        positions = frame.index.get_indexer(expected)
        if end - start != pd.Timedelta(hours=6, minutes=30) or (positions < 0).any():
            continue
        day = frame.iloc[positions][["Open", "High", "Low", "Close", "Volume"]]
        if np.isfinite(day.to_numpy(float)).all() and (day.to_numpy(float) > 0).all():
            sessions.append((expected, day))
    out = {name: pd.Series(False, index=frame.index, dtype=bool) for name in EVENT_FIELD.values()}
    exit_rules = spec["exit"]
    present = [key for key in STOP_KEYS if key in exit_rules]
    levels = {key: pd.Series(np.nan, index=frame.index, dtype=float) for key in present}
    evaluator = RuleEvaluator(SessionBars.from_sessions([d for _, d in sessions], tick_size=spec["tick_size"], parameters=parameters))
    sides = np.zeros(evaluator.shape)
    undecided = np.ones(evaluator.shape, dtype=bool)
    for signal in spec["signals"]:
        side = evaluator.side(signal["side"])
        fired = evaluator.condition(signal["when"]) & (side != 0)
        sides[undecided & fired] = side[undecided & fired]
        undecided &= ~fired
    fractions = {key: evaluator.distance_fraction(exit_rules[key]) for key in present}
    with np.errstate(invalid="ignore"):
        valid = np.logical_and.reduce([np.isfinite(f) & (f > 0) for f in fractions.values()] + [np.ones(evaluator.shape, bool)])
    flat = bar_position(spec["flat_at"])
    at_time = bar_position(exit_rules["at_time"]) if "at_time" in exit_rules else None
    after = evaluator.count(exit_rules["after_bars"]) if "after_bars" in exit_rules else None
    skipped = 0
    for session in range(evaluator.shape[1]):
        state, entry_row, taken = 0.0, -1, 0
        for row in range(evaluator.shape[0]):
            side, stamp = sides[row, session], sessions[session][0][row]
            if state:
                if row in (flat, at_time) or (after is not None and row - entry_row >= after) or (
                    exit_rules["on_opposite_signal"] and side == -state
                ):
                    out["exits" if state > 0 else "short_exits"].at[stamp] = True
                    state = 0.0
                continue
            if taken >= spec["max_trades_per_session"] or row >= flat or side == 0:
                continue
            if not valid[row, session]:
                skipped += 1
                continue
            out["entries" if side > 0 else "short_entries"].at[stamp] = True
            for key, level in levels.items():
                level.at[stamp] = float(fractions[key][row, session])
            state, entry_row, taken = side, row, taken + 1
    return out | {key: levels.get(key) for key in STOP_KEYS} | {"skipped": skipped, "sessions": len(sessions)}


def _data(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = [100 + np.cumsum(rng.normal(0, 0.6, 78)) for _ in range(10)]
    frame = _frame(days)
    frame["High"] = frame[["Open", "Close"]].max(axis=1) + rng.uniform(0, 0.5, len(frame))
    frame["Low"] = frame[["Open", "Close"]].min(axis=1) - rng.uniform(0, 0.5, len(frame))
    frame["Open"] = frame["Close"].shift(1).fillna(frame["Close"].iloc[0])
    frame["Volume"] = rng.integers(1, 500, len(frame)).astype(float)
    frame.iloc[200, frame.columns.get_loc("Close")] = np.nan  # one session dropped for an unusable bar
    return frame.drop(frame.index[500])  # and one for a missing bar


P = {"param": "n"}
CORE_SIGNALS = [
    {"when": {"all": [{"crosses_above": ["close", {"sma": "close", "length": P}]}, {"time_between": ["09:45", "15:00"]}]}, "side": "long"},
    {"when": {"crosses_below": ["close", {"ema": "close", "length": {"param": "m"}, "across_sessions": True}]}, "side": "short"},
    {"when": {"any": [
        {"lt": [{"pct_change": "close"}, {"neg": {"param": "th"}}]},
        {"not": {"gte": ["close", {"prev": "close", "bars": {"param": "lag"}}]}},
        {"gt": [{"abs": {"div": [{"sub": ["close", "open"]}, {"std": "close", "length": P}]}}, {"mul": [{"param": "th"}, 40]}]},
    ]}, "side": {"opposite_sign_of": {"change": "close"}}},
    {"when": {"all": [{"gt": [{"same_sign_run": {"change": "close"}}, {"param": "lag"}]}, {"lte": [{"bar_index": {}}, 70]}]},
     "side": {"sign_of": {"sub": [{"vwap": {}}, {"session_open": {}}]}}},
    {"when": {"any": [{"gt": ["close", {"range_high": {"from": "09:30", "to": "10:00"}}]},
                      {"lt": ["close", {"range_low": {"from": "09:30", "to": "10:00"}}]},
                      {"eq": [{"max": "high", "length": 3}, "high"]}, {"lt": ["close", {"min": "low", "length": 4}]},
                      {"gt": [{"median": "close", "length": 5}, {"value_at": "close", "time": "10:30"}]},
                      {"gt": [{"ticks": {"change": "close"}}, {"add": [{"sum": {"change": "close"}, "length": 3}, 4]}]}]},
     "side": {"sign_of": {"change": "close"}}},
]
CORE_EXIT = {
    "after_bars": {"param": "hold"}, "at_time": "15:30", "on_opposite_signal": True,
    "stop_loss": {"atr": {"length": {"param": "lag"}, "multiple": {"param": "mult"}}},
    "take_profit": {"points": {"param": "tp"}}, "trailing_stop": {"ticks": {"param": "trail"}},
}
CORE_VARIABLES = {  # 96 combinations; the language caps a grid at 100
    "n": {"values": [3, 8]}, "m": {"values": [9]}, "th": {"values": [0.001, 0.004]}, "lag": {"values": [1, 2, 3]},
    "hold": {"values": [3, 40]}, "mult": {"values": [0.5, 2.0]}, "tp": {"values": [1]}, "trail": {"values": [2, 8]},
}
LIBRARY_SIGNALS = [
    {"when": {"lt": [{"rsi": "close", "length": P}, {"param": "lo"}]}, "side": "long"},
    {"when": {"gt": [{"rsi": "close", "length": P, "across_sessions": True}, {"sub": [100, {"param": "lo"}]}]}, "side": "short"},
]
LIBRARY_VARIABLES = {"n": {"values": [3, 6, 10]}, "lo": {"values": [30, 45]}, "stop": {"values": [0.2, 0.5, 1]}}
LIBRARY_EXIT = {"stop_loss": {"percent": {"param": "stop"}}, "on_opposite_signal": False}


def _settings(variables: dict, count: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    return [{name: v["values"][rng.integers(len(v["values"]))] for name, v in variables.items()} for _ in range(count)]


def _assert_batch_matches_reference(signals, variables, exit_rules, seed: int, *, max_trades: int = 2) -> None:
    spec = _spec(signals, exit=exit_rules, max_trades_per_session=max_trades)
    definition = rule_strategy_definition(rule_spec=spec, variables=variables)
    strategy = RuleSpecStrategy(definition)
    data = _data(seed)
    settings = _settings(variables, 24, seed)
    batch = strategy.generate_signals_batch(data, settings)
    entries = 0
    for supplied, result in zip(settings, batch):
        parameters = strategy.validate_parameters(supplied)
        single = strategy.generate_signals(data, parameters)
        reference = _reference(strategy.definition, data, parameters)
        assert isinstance(result, SignalResult) and result.parameters == single.parameters == parameters
        assert result.metadata == single.metadata
        # Every entry the reference skips for an unusable stop is an entry signal the compiler skips too.
        assert result.metadata["entries_skipped_without_valid_stop_distance"] >= reference["skipped"]
        assert result.metadata["sessions_traded"] == reference["sessions"] == 8
        for name in FIELDS:
            got, alone = getattr(result, name), getattr(single, name)
            if reference[name] is None:
                assert got is None and alone is None, name
                continue
            assert got.dtype == alone.dtype and got.index.equals(alone.index), name
            assert np.array_equal(got.to_numpy(), alone.to_numpy(), equal_nan=True), (name, parameters)
        # The reference walk's flags, simulated by plain VectorBT, give exactly the trades the compiled signals give.
        walked = SignalResult(parameters=parameters, **{name: reference[name] for name in FIELDS})
        expected = trades(walked, data)
        assert trades(result, data) == expected, parameters
        entries += len(expected)
    assert entries > 0


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_core_features_batch_equals_per_setting_reference(seed: int) -> None:
    _assert_batch_matches_reference(CORE_SIGNALS, CORE_VARIABLES, CORE_EXIT, seed)


@pytest.mark.licensed_vectorbt
def test_single_trade_and_no_exit_rules_batch_equals_reference() -> None:
    _assert_batch_matches_reference(CORE_SIGNALS[:2], {"n": {"values": [3, 5]}, "m": {"values": [4, 9]}}, {}, 4, max_trades=1)


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize("seed", [5, 6])
def test_library_indicators_batch_equals_per_setting_reference(seed: int) -> None:
    _assert_batch_matches_reference(LIBRARY_SIGNALS, LIBRARY_VARIABLES, LIBRARY_EXIT, seed)


def test_empty_settings_and_no_sessions() -> None:
    definition = rule_strategy_definition(rule_spec=_spec(CORE_SIGNALS[:1]), variables={"n": {"values": [3, 5]}})
    strategy = RuleSpecStrategy(definition)
    data = _data(7)
    assert strategy.generate_signals_batch(data, []) == []
    partial = data.iloc[:40]  # no complete session
    results = strategy.generate_signals_batch(partial, [{"n": 3}, {"n": 5}])
    assert [r.metadata["sessions_traded"] for r in results] == [0, 0]
    assert not any(r.entries.any() for r in results)
