"""Test helper: simulate compiled rule signals with the experiment runner's VectorBT call and list the trades."""

from __future__ import annotations

from types import SimpleNamespace

from backtesting.experiments.models import ExecutionConfig
from backtesting.experiments.runner import _construct_portfolio, align_signals_for_execution

ZERO_COST = ExecutionConfig(
    mode="next_bar_open", signal_timing="completed_bar_close", execution_price_field="Open", initial_cash=1_000_000.0,
    fees=0.0, slippage=0.0, position_sizing="fixed_units", direction="both", leverage=1.0, accumulate=False, order_size=1.0,
)


def _clock(stamp) -> str:
    return stamp.tz_convert("America/New_York").strftime("%d %H:%M")


def trades(signals, frame, execution: ExecutionConfig = ZERO_COST) -> list[tuple[str, str, str]]:
    """(side, entry, exit) per trade; times are the New York fill-bar starts, i.e. the signal-bar END times,
    with exit "open" while the position is still held at the end of the data."""
    portfolio = _construct_portfolio(frame, align_signals_for_execution(signals, execution), SimpleNamespace(execution=execution))
    records = portfolio.trades.records_readable
    return [
        (row["Direction"].lower(), _clock(row["Entry Index"]), "open" if row["Status"] == "Open" else _clock(row["Exit Index"]))
        for _, row in records.iterrows()
    ]
