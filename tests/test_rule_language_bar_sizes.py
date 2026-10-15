"""1-minute and 5-minute bar sizes in qf_rules_v1: limits, evaluation timing and data-frequency refusal."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from rule_language import RuleSpecError, bars_per_session, canonical_rule_spec_json, validate_rule_spec
from strategies.rule_spec_evaluation import bar_position
from strategies.models import SignalResult
from strategies.rule_spec_strategy import RuleSpecStrategy, rule_strategy_definition
from tests.rule_trades import trades

SESSION = {"timezone": "America/New_York", "open": "09:30", "close": "16:00"}
DAYS = pd.bdate_range("2026-10-05", periods=6)  # NYSE full sessions, no holidays
VARIABLES = {"fast": {"values": [4, 6]}}

# Pinned from origin/main (da5cf8c), computed on the code before bar sizes existed, from golden_spec("5m")
# and golden_frame(5) with fast=4.
MAIN_DEFINITION_SHA256 = "39ba9b145bacce42cdf7f745034a50c005a55f67d7a57aa78efcfff7bee68167"
MAIN_SIGNAL_POSITIONS = {
    "entries": [17, 146, 286, 328, 378, 426, 442, 454],
    "exits": [26, 149, 295, 337, 387, 435, 451, 455],
    "short_entries": [138, 179, 213, 308],
    "short_exits": [143, 188, 221, 310],
}
MAIN_STOP_SHA256 = "30075faf694760a98bb82ccf9471b9f0e7073d82fda0fed5cbc6d1eadd60533e"


def golden_spec(bar: str = "5m") -> dict:
    return {
        "language": "qf_rules_v1", "bar": bar, "tick_size": 0.25, "session": dict(SESSION), "flat_at": "15:55",
        "signals": [
            {"when": {"all": [
                {"crosses_above": [{"sma": "close", "length": {"param": "fast"}}, {"sma": "close", "length": 12}]},
                {"time_between": ["10:00", "15:30"]},
                {"gt": ["close", {"value_at": "open", "time": "09:35"}]}]}, "side": "long"},
            {"when": {"all": [
                {"crosses_below": [{"ema": "close", "length": 5}, {"sma": "close", "length": 12}]},
                {"lt": ["close", {"range_low": {"from": "09:30", "to": "10:00"}}]}]}, "side": "short"},
        ],
        "exit": {"after_bars": 9, "at_time": "15:00", "on_opposite_signal": True,
                 "stop_loss": {"atr": {"length": 6, "multiple": 2.0}}, "take_profit": {"ticks": 40}},
        "max_trades_per_session": 3,
    }


def golden_frame(minutes: int = 5) -> pd.DataFrame:
    frames = []
    per = 390 // minutes
    for number, day in enumerate(DAYS):
        t = np.arange(per, dtype=float)
        closes = 5000 + 8 * np.sin(t / (per / 9.0) + number) + 3 * np.sin(t / (per / 30.0)) + 0.3 * number
        closes = np.round(closes * 4) / 4
        start = pd.Timestamp(f"{day.date()} 09:30", tz="America/New_York").tz_convert("UTC")
        index = pd.date_range(start, periods=per, freq=f"{minutes}min")
        frames.append(pd.DataFrame({"Open": closes, "High": closes + 0.5, "Low": closes - 0.5, "Close": closes,
                                    "Volume": 10.0 + t % 7}, index=index))
    return pd.concat(frames)


def _simple(bar: str, when: dict, **extra) -> dict:
    spec = {
        "language": "qf_rules_v1", "bar": bar, "tick_size": 0.25, "session": dict(SESSION), "flat_at": "15:55",
        "signals": [{"when": when, "side": "long"}], "max_trades_per_session": 1,
    }
    spec.update(extra)
    return spec


def _check(spec: dict) -> dict:
    return validate_rule_spec(spec, variables={})


def _run(spec: dict, minutes: int):
    return RuleSpecStrategy(rule_strategy_definition(rule_spec=spec, variables={})).generate_signals(
        golden_frame(minutes), {}
    )


def test_one_minute_spec_validates_and_keeps_its_bar() -> None:
    assert validate_rule_spec(golden_spec("1m"), variables=VARIABLES)["bar"] == "1m"
    assert validate_rule_spec(golden_spec("5m"), variables=VARIABLES)["bar"] == "5m"


@pytest.mark.parametrize("bar", ["2m", "15m", "1h", "5M", 5, None, ["1m"]])
def test_other_bar_sizes_are_rejected_with_the_allowed_list(bar) -> None:
    spec = golden_spec()
    spec["bar"] = bar
    with pytest.raises(RuleSpecError, match=r'"1m" or "5m"'):
        validate_rule_spec(spec, variables=VARIABLES)


def test_bars_per_session_is_derived_from_the_bar() -> None:
    assert bars_per_session("1m") == 390
    assert bars_per_session("5m") == 78


def test_one_minute_limits_are_390_based_and_five_minute_limits_stay_78_based() -> None:
    always = {"gt": ["close", "open"]}
    _check(_simple("1m", always, max_trades_per_session=390))
    with pytest.raises(RuleSpecError, match="1 to 390"):
        _check(_simple("1m", always, max_trades_per_session=391))
    _check(_simple("5m", always, max_trades_per_session=78))
    with pytest.raises(RuleSpecError, match="1 to 78"):
        _check(_simple("5m", always, max_trades_per_session=79))
    _check(_simple("1m", always, exit={"after_bars": 389}))
    with pytest.raises(RuleSpecError, match="1 to 389"):
        _check(_simple("1m", always, exit={"after_bars": 390}))
    with pytest.raises(RuleSpecError, match="1 to 77"):
        _check(_simple("5m", always, exit={"after_bars": 78}))
    _check(_simple("1m", {"gt": [{"sma": "close", "length": 390}, "open"]}))
    with pytest.raises(RuleSpecError, match="1 to 390"):
        _check(_simple("1m", {"gt": [{"sma": "close", "length": 391}, "open"]}))
    with pytest.raises(RuleSpecError, match="1 to 78"):
        _check(_simple("5m", {"gt": [{"sma": "close", "length": 79}, "open"]}))
    _check(_simple("1m", {"gt": [{"atr": {"length": 390}}, 1]}))
    _check(_simple("1m", {"gt": [{"prev": "close", "bars": 389}, 1]}))
    with pytest.raises(RuleSpecError, match="1 to 77"):
        _check(_simple("5m", {"gt": [{"prev": "close", "bars": 78}, 1]}))


def test_clock_grid_follows_the_bar_size() -> None:
    _check(_simple("1m", {"time_is": "09:31"}, flat_at="15:59"))
    _check(_simple("1m", {"time_is": "09:36"}))
    with pytest.raises(RuleSpecError, match="between 09:31"):
        _check(_simple("1m", {"time_is": "09:30"}))
    with pytest.raises(RuleSpecError, match="5-minute bar grid"):
        _check(_simple("5m", {"time_is": "09:36"}))
    with pytest.raises(RuleSpecError, match="5-minute bar grid"):
        _check(_simple("5m", {"time_is": "09:35"}, flat_at="15:56"))
    with pytest.raises(RuleSpecError, match="1-minute bar END times"):
        _check(_simple("1m", {"time_is": "09:35"}, flat_at="16:00"))


def test_bar_position_uses_the_bar_size() -> None:
    assert bar_position("09:35") == 0 and bar_position("09:35", "5m") == 0
    assert bar_position("10:00", "5m") == 5
    assert bar_position("09:31", "1m") == 0 and bar_position("10:00", "1m") == 29
    assert bar_position("16:00", "1m") == 389 and bar_position("16:00", "5m") == 77


@pytest.mark.licensed_vectorbt
def test_five_minute_spec_is_identical_to_main() -> None:
    definition = rule_strategy_definition(rule_spec=golden_spec("5m"), variables=VARIABLES)
    assert hashlib.sha256(canonical_rule_spec_json(definition).encode()).hexdigest() == MAIN_DEFINITION_SHA256
    frame = golden_frame(5)
    signals = RuleSpecStrategy(definition).generate_signals(frame, {"fast": 4})
    # main's compiled flags (its own per-session walk) simulate to exactly the same trades as today's signals.
    flags = {}
    for name, positions in MAIN_SIGNAL_POSITIONS.items():
        flags[name] = pd.Series(False, index=frame.index)
        flags[name].iloc[positions] = True
    main = SignalResult(parameters={"fast": 4}, stop_loss=signals.stop_loss, **flags)
    assert trades(signals, frame) == trades(main, frame) != []
    on_main_entries = signals.stop_loss.where(flags["entries"] | flags["short_entries"])
    assert hashlib.sha256(np.nan_to_num(on_main_entries.to_numpy()).tobytes()).hexdigest() == MAIN_STOP_SHA256


def test_one_minute_spec_runs_on_one_minute_data() -> None:
    strategy = RuleSpecStrategy(rule_strategy_definition(rule_spec=golden_spec("1m"), variables=VARIABLES))
    assert strategy.spec.data.supported_intervals == ("1m",)
    assert strategy.spec.data.minimum_history_bars == 390
    signals = strategy.generate_signals(golden_frame(1), {"fast": 4})
    assert signals.metadata["sessions_traded"] == len(DAYS)
    assert signals.entries.sum() > 0 and signals.exits.sum() > 0


@pytest.mark.parametrize(("spec_bar", "data_minutes"), [("1m", 5), ("5m", 1)])
def test_spec_bar_and_data_frequency_mismatch_raises(spec_bar: str, data_minutes: int) -> None:
    definition = rule_strategy_definition(rule_spec=golden_spec(spec_bar), variables=VARIABLES)
    with pytest.raises(ValueError, match=rf"bar is '{spec_bar}' but the data has {data_minutes}-minute bars"):
        RuleSpecStrategy(definition).generate_signals(golden_frame(data_minutes), {"fast": 4})


def _stamps(series: pd.Series) -> list[str]:
    return [stamp.tz_convert("America/New_York").strftime("%d %H:%M") for stamp in series[series].index]


@pytest.mark.licensed_vectorbt
def test_one_minute_entry_and_at_time_exit_fire_on_the_right_minute() -> None:
    held = trades(_run(_simple("1m", {"time_is": "10:00"}, exit={"at_time": "11:30"}), 1), golden_frame(1))
    # Fills are at the open after the signal bar: the bar ending 10:00 fills at 10:00, the at_time exit at 11:30.
    assert held[0] == ("long", "05 10:00", "05 11:30")
    assert len(held) == len(DAYS)


@pytest.mark.licensed_vectorbt
def test_one_minute_after_bars_and_flat_at_count_minutes() -> None:
    frame = golden_frame(1)
    assert trades(_run(_simple("1m", {"time_is": "10:00"}, exit={"after_bars": 45}), 1), frame)[0] == ("long", "05 10:00", "05 10:45")
    assert trades(_run(_simple("1m", {"time_is": "15:57"}, flat_at="15:59"), 1), frame)[0] == ("long", "05 15:57", "05 15:59")
