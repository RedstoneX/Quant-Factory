"""qf_rules_v1 exits added for the research agent, each a translation into Portfolio.from_signals inputs.

- ``exit.exit_when`` -> ``exits`` / ``short_exits``;
- ``stop_loss.level`` -> ``sl_stop`` (Percent of the entry open) and ``take_profit.r_multiple`` -> ``tp_stop``;
- the ``every_minutes`` condition (N-minute bar closes on finer bars).
Hand-checked cases on tiny sessions; the gap and target cases run the real VectorBT PRO simulation.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments.runner import _construct_portfolio, align_signals_for_execution
from rule_language import RuleSpecError, validate_rule_spec
from strategies.rule_spec_evaluation import RuleEvaluator, SessionBars
from tests.test_rule_language_stops import _execution
from tests.rule_trades import trades
from tests.test_rule_spec_strategy import _frame, _run, _spec

LONG_AT_10 = [{"when": {"time_is": "10:00"}, "side": "long"}]
SHORT_AT_10 = [{"when": {"time_is": "10:00"}, "side": "short"}]
OPENING_RANGE_LOW = {"range_low": {"from": "09:30", "to": "10:00"}}
SIGNAL_ROW, FLAT_ROW = 5, 76  # 5m rows of the bars ending 10:00 and 15:55


def _rows(series: pd.Series) -> list[int]:
    return [int(position) for position in np.flatnonzero(series.to_numpy())]


def test_exit_when_closes_the_trade_for_its_side_only() -> None:
    closes = np.full(78, 100.0)
    closes[10:] = 106.0  # close first exceeds 105 on row 10 (bar ending 10:25)
    exit_rules = {"exit_when": {"long": {"crosses_above": ["close", 105]}}}
    frame = _frame([closes])
    signals = _run(_spec(LONG_AT_10, exit=exit_rules), frame)
    assert trades(signals, frame) == [("long", "05 10:00", "05 10:25")]  # closed on row 10, before flat_at
    assert not signals.short_exits.any()
    assert "rule exit" in signals.metadata["exit_when"]


def test_exit_when_never_fires_on_the_entry_bar_and_ignores_the_other_side() -> None:
    exit_rules = {"exit_when": {"long": {"time_between": ["10:00", "10:05"]}, "short": {"time_is": "10:05"}}}
    frame = _frame([np.full(78, 100.0)])
    # exit_when is true on the entry bar too, but only a held trade exits; the short rule never touches a long.
    assert trades(_run(_spec(LONG_AT_10, exit=exit_rules), frame), frame) == [("long", "05 10:00", "05 10:05")]


def test_exit_when_exit_allows_a_new_entry() -> None:
    closes = np.full(78, 100.0)
    closes[5:] = 103.0
    closes[10] = 99.0  # exit_when (close < 100) on row 10; the signal (close > 102) fires again on row 11
    spec = _spec([{"when": {"gt": ["close", 102]}, "side": "long"}], exit={"exit_when": {"long": {"lt": ["close", 100]}}})
    frame = _frame([closes])
    assert trades(_run({**spec, "max_trades_per_session": 2}, frame), frame) == [
        ("long", "05 10:00", "05 10:25"), ("long", "05 10:30", "05 15:55"),
    ]


def _level_closes() -> np.ndarray:
    closes = np.full(78, 100.0)
    closes[2] = 98.0  # low 97.5: the 09:30-10:00 opening-range low
    return closes


def test_level_stop_and_r_multiple_target_are_fractions_of_the_entry_open() -> None:
    exit_rules = {"stop_loss": {"level": OPENING_RANGE_LOW}, "take_profit": {"r_multiple": 2}}
    signals = _run(_spec(LONG_AT_10, exit=exit_rules), _frame([_level_closes()]))
    entry = signals.entries[signals.entries].index[0]
    # Entry fills at the next open, 100; stop 97.5 is 2.5 below = 0.025; 2R target = 0.05 (105).
    assert signals.stop_loss[entry] == pytest.approx(0.025)
    assert signals.take_profit[entry] == pytest.approx(0.05)
    assert signals.stop_loss.drop(entry).isna().all() and signals.take_profit.drop(entry).isna().all()
    assert signals.metadata["entries_dropped_level_stop_on_wrong_side"] == 0


def test_level_on_the_wrong_side_of_the_entry_open_drops_the_entry() -> None:
    signals = _run(_spec(SHORT_AT_10, exit={"stop_loss": {"level": OPENING_RANGE_LOW}}), _frame([_level_closes()]))
    assert not signals.short_entries.any()  # a short's stop at 97.5 would sit below its 100 entry
    assert signals.stop_loss.isna().all()
    assert signals.metadata["entries_dropped_level_stop_on_wrong_side"] == 1


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize(
    ("row", "bar", "fill"),
    [
        (8, (95.0, 95.5, 94.5, 95.0), 95.0),  # opens 95, through the 97.5 stop: fills at the open, not 97.5
        (8, (99.0, 99.5, 97.0, 98.0), 97.5),  # trades through 97.5 intrabar: fills at the stop
        (8, (101.0, 105.5, 100.5, 105.0), 105.0),  # reaches the 2R target 105: fills at the target
    ],
)
def test_level_stop_and_target_fill_in_vectorbt(row: int, bar: tuple, fill: float) -> None:
    frame = _frame([_level_closes()])
    frame.iloc[row, :4] = bar
    exit_rules = {"stop_loss": {"level": OPENING_RANGE_LOW}, "take_profit": {"r_multiple": 2}}
    signals = _run(_spec(LONG_AT_10, exit=exit_rules), frame)
    prices, fills = _fills(frame, signals)
    assert prices == pytest.approx([100.0, fill])
    assert fills[1] == frame.index[row]


def _fills(frame: pd.DataFrame, signals) -> tuple[list[float], list]:
    execution = _execution()
    portfolio = _construct_portfolio(frame, align_signals_for_execution(signals, execution), SimpleNamespace(execution=execution))
    orders = portfolio.orders.readable
    return (orders["Price"].to_numpy() / execution.price_multiplier).tolist(), orders["Fill Index"].to_list()


def test_trail_after_r_multiple_is_r_times_the_stop_fraction() -> None:
    exit_rules = {"stop_loss": {"level": OPENING_RANGE_LOW}, "trailing_stop": {"percent": 1}, "trail_after": {"r_multiple": 1}}
    signals = _run(_spec(LONG_AT_10, exit=exit_rules), _frame([_level_closes()]))
    entry = signals.entries[signals.entries].index[0]
    assert signals.trailing_threshold[entry] == pytest.approx(0.025)  # 1R = 100 - 97.5 on a 100 entry
    assert signals.trailing_stop[entry] == pytest.approx(0.01)


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize(
    ("high_row_7", "fills"),
    [
        # +3 only: the trail never switches on, so the 98 low on row 8 does not exit; flat_at exits at the open.
        ((102.5, 103.0, 102.0, 102.5), [100.0, 100.0]),
        # +5 (high 105): trail on at +4, stop 105 x 0.96 = 100.8, hit on row 8 (low 100.5), above the 100 entry.
        ((104.5, 105.0, 104.0, 104.5), [100.0, 100.8]),
    ],
)
def test_breakeven_then_trail_in_vectorbt(high_row_7: tuple, fills: list) -> None:
    frame = _frame([np.full(78, 100.0)])
    frame.iloc[7, :4] = high_row_7
    frame.iloc[8, :4] = (101.0, 101.5, 98.0, 100.0) if high_row_7[1] < 104 else (103.0, 103.5, 100.5, 101.0)
    exit_rules = {"trailing_stop": {"points": 4}, "trail_after": {"points": 4}}
    prices, _ = _fills(frame, _run(_spec(LONG_AT_10, exit=exit_rules), frame))
    assert prices == pytest.approx(fills)


def test_every_minutes_marks_five_minute_closes_on_one_minute_bars() -> None:
    closes = np.full((390, 1), 100.0)
    bars = SessionBars(open=closes, high=closes, low=closes, close=closes, volume=closes, tick_size=0.25, parameters={}, bar="1m")
    condition = {"all": [{"every_minutes": 5}, {"time_between": ["09:50", "15:50"]}]}
    rows = np.flatnonzero(RuleEvaluator(bars).condition(condition)[:, 0])
    # Row p ends at 09:31 + p minutes: 09:50 is row 19, 15:50 is row 379, every fifth row between.
    assert rows.tolist() == list(range(19, 380, 5))


def test_every_minutes_validates_on_one_minute_specs() -> None:
    spec = _spec([{"when": {"all": [{"every_minutes": 5}, {"time_between": ["09:50", "15:50"]}]}, "side": "long"}], bar="1m")
    assert validate_rule_spec(spec, variables={})["signals"][0]["when"]["all"][0] == {"every_minutes": 5}


def test_legacy_exit_normalization_has_no_new_keys() -> None:
    exit_rules = validate_rule_spec(_spec(LONG_AT_10, exit={"stop_loss": {"ticks": 8}}), variables={})["exit"]
    assert exit_rules == {"on_opposite_signal": False, "stop_loss": {"ticks": 8}}


@pytest.mark.parametrize(
    ("signals", "exit_rules", "message"),
    [
        (LONG_AT_10, {"take_profit": {"level": "low"}}, "take_profit.level: is allowed only in stop_loss"),
        (LONG_AT_10, {"stop_loss": {"r_multiple": 2}}, "stop_loss.r_multiple: is allowed only in take_profit or trail_after"),
        (LONG_AT_10, {"trailing_stop": {"level": "low"}}, "trailing_stop.level: is allowed only in stop_loss"),
        (LONG_AT_10, {"take_profit": {"r_multiple": 2}}, "take_profit.r_multiple: needs a stop_loss"),
        (LONG_AT_10, {"stop_loss": {"points": 1}, "take_profit": {"r_multiple": 0}}, "r_multiple: must be a number greater than zero"),
        (LONG_AT_10, {"stop_loss": {"level": "price"}}, "unknown price field 'price'"),
        (LONG_AT_10, {"trail_after": {"points": 4}}, "trail_after: needs a trailing_stop"),
        (LONG_AT_10, {"trailing_stop": {"points": 4}, "trail_after": {"level": "low"}}, "trail_after.level: is allowed only in stop_loss"),
        (LONG_AT_10, {"trailing_stop": {"points": 4}, "trail_after": {"r_multiple": 1}}, "trail_after.r_multiple: needs a stop_loss"),
        (LONG_AT_10, {"exit_when": {}}, 'exit_when: needs "long", "short" or both'),
        (LONG_AT_10, {"exit_when": {"both": {"time_is": "10:00"}}}, "exit_when: unknown key 'both'"),
        (LONG_AT_10, {"exit_when": {"long": {"gt": ["close"]}}}, "exit_when.long.gt: must be a list of exactly two items"),
        ([{"when": {"every_minutes": 7}, "side": "long"}], {}, "every_minutes: must be a whole number of minutes, a multiple of the 5-minute bar"),
        ([{"when": {"every_minutes": 0}, "side": "long"}], {}, "every_minutes: must be a whole number"),
        ([{"when": {"every_minutes": True}, "side": "long"}], {}, "every_minutes: must be a whole number"),
    ],
)
def test_malformed_new_fields_are_rejected_clearly(signals: list, exit_rules: dict, message: str) -> None:
    with pytest.raises(RuleSpecError) as raised:
        validate_rule_spec(_spec(signals, exit=exit_rules), variables={})
    assert message in str(raised.value)
