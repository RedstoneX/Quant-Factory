"""Flat at a time of day: rule_spec "flat_at" closes any open trade at HH:MM New York and blocks later entries;
exit "at_time" closes at HH:MM without blocking. Hand-checked against VectorBT PRO fills."""

from __future__ import annotations

import numpy as np
import pytest

from tests.rule_trades import trades
from tests.test_rule_language_exits import LONG_AT_10, _fills
from tests.test_rule_spec_strategy import _frame, _run, _spec

FILL_ROW_15_00 = 66  # 5m row of the bar starting 15:00 (signal bar ending 15:00 is row 65)


@pytest.mark.licensed_vectorbt
def test_flat_at_closes_the_trade_at_that_time_at_the_open_in_vectorbt() -> None:
    closes = 100.0 + np.arange(78) * 0.25  # every bar's open differs, so the fill price names the bar
    frame = _frame([closes])
    prices, fills = _fills(frame, _run(_spec(LONG_AT_10, flat_at="15:00"), frame))
    assert fills[1] == frame.index[FILL_ROW_15_00]
    assert fills[1].tz_convert("America/New_York").strftime("%H:%M") == "15:00"
    assert prices == pytest.approx([closes[6], closes[FILL_ROW_15_00]])  # 10:00 open in, 15:00 open out


@pytest.mark.licensed_vectorbt
def test_flat_at_blocks_entries_from_that_time_but_at_time_does_not() -> None:
    late = [{"when": {"time_is": "15:30"}, "side": "long"}]
    frame = _frame([np.full(78, 100.0)])
    assert trades(_run(_spec(late, flat_at="15:00"), frame), frame) == []
    spec = _spec(late, exit={"at_time": "15:00"})
    spec.pop("flat_at")
    assert trades(_run(spec, frame), frame) == [("long", "05 15:30", "open")]  # held overnight: no flat_at
