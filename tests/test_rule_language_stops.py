"""Built-in stops in qf_rules_v1: stop_loss, take_profit and trailing_stop, each optional and independent."""

from __future__ import annotations

import hashlib
import itertools
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from rule_language import canonical_rule_spec_json, validate_rule_spec
from strategies.models import SignalResult
from strategies.rule_spec_strategy import RuleSpecStrategy, rule_strategy_definition
from tests.test_rule_spec_strategy import _frame, _run, _spec

LONG_AT_10 = [{"when": {"time_is": "10:00"}, "side": "long"}]
BOTH_SIDES = LONG_AT_10 + [{"when": {"time_is": "13:00"}, "side": "short"}]

# sha256 of _fingerprint(...) computed on origin/main (e1bdcec) before this change.
MAIN_FINGERPRINTS = {
    "both_ticks_percent": "31bff4880710da172b280ee550f43ae0b28f5747644cc80077763ddd6b20fe6b",
    "both_atr_points": "f23afc426af0e0d955225ad88033393091cbfc2f5c31c0f4926ea317fd7d597c",
    "neither": "70018a94c27d530247e3b683ae79350da5cc46fb83f327e3221f1afc64a4a5e6",
}
LEGACY_EXITS = {
    "both_ticks_percent": {"stop_loss": {"ticks": 8}, "take_profit": {"percent": 1}, "after_bars": 20},
    "both_atr_points": {"stop_loss": {"atr": {"length": 6, "multiple": 2.0}}, "take_profit": {"points": 3}},
    "neither": {"after_bars": 12, "on_opposite_signal": True},
}


def _legacy_frame() -> pd.DataFrame:
    rng = np.random.default_rng(20261014)
    bars = np.arange(78)
    days = [5000 + 8 * np.sin(2 * np.pi * bars / 50 + day) + np.cumsum(rng.normal(0, 1.5, 78)) for day in range(4)]
    return _frame(days)


def _fingerprint(exit_rules: dict) -> str:
    """Hash every observable output of validation and compilation for one spec."""
    spec = _spec(BOTH_SIDES, exit=exit_rules, max_trades_per_session=2)
    normalized = canonical_rule_spec_json(validate_rule_spec(spec, variables={}))
    definition = rule_strategy_definition(candidate_id="cand-test", title="Test rules", rule_spec=spec, variables={})
    strategy = RuleSpecStrategy(definition)
    signals = strategy.generate_signals(_legacy_frame(), {})
    parts = [normalized, repr(strategy.spec.assumptions), json.dumps(signals.parameters)]
    for name in ("entries", "exits", "short_entries", "short_exits", "stop_loss", "take_profit"):
        series = getattr(signals, name)
        parts.append("None" if series is None else repr(list(zip(series.index.astype(str), series.tolist()))))
    parts.append(json.dumps(signals.metadata, default=str))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


@pytest.mark.parametrize("name", sorted(LEGACY_EXITS))
def test_legacy_both_or_neither_specs_are_byte_identical_to_main(name: str) -> None:
    assert _fingerprint(LEGACY_EXITS[name]) == MAIN_FINGERPRINTS[name]
    spec = _spec(BOTH_SIDES, exit=LEGACY_EXITS[name], max_trades_per_session=2)
    assert _run(spec, _legacy_frame()).trailing_stop is None


@pytest.mark.parametrize("key", ["stop_loss", "take_profit", "trailing_stop"])
@pytest.mark.parametrize("distance", [{"percent": 0.5}, {"points": 2}, {"ticks": 8}, {"atr": {"length": 6, "multiple": 2}}])
def test_each_stop_alone_validates_and_compiles(key: str, distance: dict) -> None:
    spec = _spec(LONG_AT_10, exit={key: distance})
    exit_rules = validate_rule_spec(spec, variables={})["exit"]
    assert [name for name in ("stop_loss", "take_profit", "trailing_stop") if name in exit_rules] == [key]
    signals = _run(spec, _frame([np.full(78, 100.0)]))
    for name in ("stop_loss", "take_profit", "trailing_stop"):
        level = getattr(signals, name)
        assert (level is not None) == (name == key)
    level = getattr(signals, key)
    entry = signals.entries[signals.entries].index[0]
    assert level[entry] > 0 and level.drop(entry).isna().all()


def test_trailing_stop_is_described_and_explained() -> None:
    spec = _spec(LONG_AT_10, exit={"stop_loss": {"ticks": 8}, "trailing_stop": {"percent": 1}})
    definition = rule_strategy_definition(candidate_id="cand-test", title="Test rules", rule_spec=spec, variables={})
    strategy = RuleSpecStrategy(definition)
    assert strategy.spec.assumptions.stop_loss == '{"ticks":8}; trailing {"percent":1}'
    assert strategy.spec.assumptions.profit_target is None
    signals = strategy.generate_signals(_frame([np.full(78, 100.0)]), {})
    assert "best price since entry" in signals.metadata["trailing_stop_distance"]


def test_atr_trailing_distance_is_fixed_at_the_entry_signal_bar() -> None:
    closes = np.full(78, 100.0)
    closes[7:] = 100.0 + 10.0 * (np.arange(71) % 2)  # volatility explodes right after the 10:00 signal bar
    signals = _run(_spec(LONG_AT_10, exit={"trailing_stop": {"atr": {"length": 3, "multiple": 2}}}), _frame([closes]))
    entry = signals.entries[signals.entries].index[0]
    # Bars up to the 10:00 signal bar are flat with a 1.0 high-low range: ATR 1.0, distance 2.0 on a 100 close.
    assert signals.trailing_stop[entry] == pytest.approx(0.02)
    assert signals.trailing_stop.drop(entry).isna().all()


def test_entry_skipped_when_any_present_stop_distance_is_unusable() -> None:
    closes = np.full(78, 100.0)
    signals = _run(_spec(LONG_AT_10, exit={"trailing_stop": {"atr": {"length": 30, "multiple": 2}}}), _frame([closes]))
    assert not signals.entries.any()
    assert signals.metadata["entries_skipped_without_valid_stop_distance"] == 1


def _execution(mode: str = "next_bar_open") -> SimpleNamespace:
    return SimpleNamespace(
        mode=mode, price_multiplier=5.0, direction="both", execution_price_field="Open", absolute_slippage_points=0.0,
        order_size=1.0, accumulate=False, leverage=1.0, initial_cash=10_000.0, fees=0.0, slippage=0.0,
        fixed_fee_per_order=0.0, position_sizing="fixed_units",
    )


def _capture(monkeypatch, aligned: SignalResult, mode: str = "next_bar_open") -> dict:
    import backtesting.experiments.runner as runner

    captured: dict = {}

    class Portfolio:
        @staticmethod
        def from_signals(**kwargs):
            captured.update(kwargs)
            return "portfolio"

    monkeypatch.setattr(runner, "require_vectorbtpro", lambda: SimpleNamespace(Portfolio=Portfolio))
    assert runner._construct_portfolio(_frame([np.full(78, 100.0)]), aligned, SimpleNamespace(execution=_execution(mode))) == "portfolio"
    return captured


def _signals(**levels) -> SignalResult:
    index = _frame([np.full(78, 100.0)]).index
    flags = pd.Series(False, index=index)
    return SignalResult(entries=flags, exits=flags, short_entries=flags, short_exits=flags, parameters={}, **levels)


@pytest.mark.parametrize("present", [combo for size in range(4) for combo in itertools.combinations(("sl", "tp", "tsl"), size)])
def test_runner_passes_only_the_stops_present(monkeypatch, present: tuple[str, ...]) -> None:
    index = _frame([np.full(78, 100.0)]).index
    fields = {"sl": "stop_loss", "tp": "take_profit", "tsl": "trailing_stop"}
    levels = {fields[short]: pd.Series(0.01 * (i + 1), index=index) for i, short in enumerate(present)}
    captured = _capture(monkeypatch, _signals(**levels))
    stop_keys = [key for key in ("sl_stop", "tp_stop", "tsl_stop") if key in captured]
    assert stop_keys == [f"{short}_stop" for short in present]
    for short in present:
        assert captured[f"{short}_stop"] is levels[fields[short]]
    if present:
        assert (captured["delta_format"], captured["stop_entry_price"], captured["stop_exit_price"]) == ("Percent", "Open", "Stop")
        assert captured["use_stops"] is True and captured["open"].equals(_frame([np.full(78, 100.0)])["Open"] * 5.0)
    else:
        assert not {"open", "high", "low", "delta_format", "use_stops"} & captured.keys()


def test_runner_legacy_both_kwargs_keep_their_exact_order(monkeypatch) -> None:
    index = _frame([np.full(78, 100.0)]).index
    captured = _capture(monkeypatch, _signals(stop_loss=pd.Series(0.01, index=index), take_profit=pd.Series(0.02, index=index)))
    keys = list(captured)
    start = keys.index("open")
    assert keys[start:] == ["open", "high", "low", "sl_stop", "tp_stop", "delta_format", "stop_entry_price", "stop_exit_price", "use_stops"]


def test_trailing_stop_requires_next_bar_open_and_is_shifted_with_signals(monkeypatch) -> None:
    from backtesting.experiments.runner import align_signals_for_execution

    index = _frame([np.full(78, 100.0)]).index
    trailing = pd.Series(np.nan, index=index)
    trailing.iloc[5] = 0.02
    with pytest.raises(ValueError, match="next-bar-open"):
        _capture(monkeypatch, _signals(trailing_stop=trailing), mode="same_bar_close")
    aligned = align_signals_for_execution(_signals(trailing_stop=trailing), _execution())
    assert aligned.trailing_stop.iloc[6] == 0.02 and aligned.trailing_stop.isna().sum() == len(index) - 1

