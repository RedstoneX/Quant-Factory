"""stop_loss {"signal_bar": true}: the stop is the signal bar's low (long) or high (short).

It is a ``level`` stop whose level follows the signal's side, translated the same way (VectorBT PRO from_signals
``sl_stop`` as a fraction of the entry open, ``stop_entry_price="Open"``, ``stop_exit_price="Stop"``).
"""

from __future__ import annotations

import numpy as np
import pytest

from rule_language import RuleSpecError, validate_rule_spec
from tests.test_rule_language_exits import LONG_AT_10, SHORT_AT_10, _fills
from tests.test_rule_spec_strategy import _frame, _run, _spec

SIGNAL_BAR = {"stop_loss": {"signal_bar": True}}
STOP_ROW = 8  # 5m row of the bar starting 10:10, after the 10:00 signal (row 5) and its 10:00 fill (row 6)


def test_signal_bar_stop_validates_only_as_true_in_stop_loss() -> None:
    assert validate_rule_spec(_spec(LONG_AT_10, exit=SIGNAL_BAR), variables={})["exit"]["stop_loss"] == {"signal_bar": True}
    with pytest.raises(RuleSpecError, match="must be true"):
        validate_rule_spec(_spec(LONG_AT_10, exit={"stop_loss": {"signal_bar": False}}), variables={})
    with pytest.raises(RuleSpecError, match="allowed only in stop_loss"):
        validate_rule_spec(_spec(LONG_AT_10, exit={"take_profit": {"signal_bar": True}}), variables={})


@pytest.mark.parametrize(("signals", "fraction"), [(LONG_AT_10, 0.005), (SHORT_AT_10, 0.005)])
def test_signal_bar_stop_is_the_fraction_from_the_entry_open_to_the_bar_extreme(signals: list, fraction: float) -> None:
    signals_out = _run(_spec(signals, exit=SIGNAL_BAR), _frame([np.full(78, 100.0)]))
    entries = signals_out.entries | signals_out.short_entries
    entry = entries[entries].index[0]
    # Signal bar 100 +/- 0.5: low 99.5 (long), high 100.5 (short); the entry fills at the next open, 100.
    assert signals_out.stop_loss[entry] == pytest.approx(fraction)
    assert signals_out.stop_loss.drop(entry).isna().all()


def test_entry_opening_through_the_signal_bar_low_is_skipped() -> None:
    closes = np.full(78, 100.0)
    closes[6] = 99.0  # the 10:00 fill bar opens at 99, below the 99.5 signal-bar low
    signals = _run(_spec(LONG_AT_10, exit=SIGNAL_BAR), _frame([closes]))
    assert not signals.entries.any()
    assert signals.metadata["entries_skipped_without_valid_stop_distance"] == 1


def _quiet_after_signal():
    """Flat 100 bars; after the 10:00 signal bar (range 99.5-100.5) every bar stays inside 99.75-100.25."""
    frame = _frame([np.full(78, 100.0)])
    frame.iloc[6:, frame.columns.get_loc("High")] = 100.25
    frame.iloc[6:, frame.columns.get_loc("Low")] = 99.75
    return frame


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize(
    ("signals", "bar", "fill"),
    [
        (LONG_AT_10, (99.8, 100.0, 99.0, 99.2), 99.5),  # trades through the 99.5 signal-bar low: fills at the low
        (SHORT_AT_10, (100.2, 101.0, 100.0, 100.8), 100.5),  # trades through the 100.5 high: fills at the high
    ],
)
def test_signal_bar_stop_fills_at_the_signal_bar_extreme_in_vectorbt(signals: list, bar: tuple, fill: float) -> None:
    frame = _quiet_after_signal()
    frame.iloc[STOP_ROW, :4] = bar
    prices, fills = _fills(frame, _run(_spec(signals, exit=SIGNAL_BAR), frame))
    assert prices == pytest.approx([100.0, fill])
    assert fills[1] == frame.index[STOP_ROW]


@pytest.mark.licensed_vectorbt
def test_signal_bar_stop_sets_r_for_the_target_in_vectorbt() -> None:
    frame = _quiet_after_signal()
    frame.iloc[STOP_ROW, :4] = (100.2, 101.2, 100.1, 101.0)  # reaches the 2R target: 100 + 2 x 0.5 = 101
    exit_rules = {**SIGNAL_BAR, "take_profit": {"r_multiple": 2}}
    prices, fills = _fills(frame, _run(_spec(LONG_AT_10, exit=exit_rules), frame))
    assert prices == pytest.approx([100.0, 101.0])
    assert fills[1] == frame.index[STOP_ROW]
