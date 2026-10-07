"""Owner-approved, fixed intraday MES 10/30 SMA crossover."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from strategies.mes_opening_range_breakout import _schedule
from strategies.models import DataRequirements, SignalResult, StrategyIdentity, StrategySpecification, TradingAssumptions

STRATEGY_ID = "mes_intraday_sma_10_30_candidate"
STRATEGY_VERSION = "1.0.0"
FIVE_MINUTES = pd.Timedelta(minutes=5)

MES_SMA_SPEC = StrategySpecification(
    identity=StrategyIdentity(
        strategy_id=STRATEGY_ID,
        name="MES intraday 10/30 SMA crossover",
        family="trend_following",
        version=STRATEGY_VERSION,
        description="First same-session 10/30 close-SMA cross; one MES contract, flat by 15:55 ET.",
        direction="both",
    ),
    data=DataRequirements(
        required_fields=("Open", "High", "Low", "Close", "Volume"),
        supported_intervals=("5m",),
        asset_classes=("futures",),
        minimum_history_bars=78,
        adjusted_prices=False,
    ),
    parameters=(),
    assumptions=TradingAssumptions(
        signal_timing="First completed-bar 10/30 SMA cross after both and prior values exist",
        execution_timing="Next contiguous five-minute bar open",
        position_sizing="One MES contract; at most one trade per session",
        fee_rate=0.0,
        slippage_rate=0.0,
        stop_loss=None,
        profit_target=None,
        maximum_holding_period=None,
        pyramiding=False,
        same_bar_limitation="No same-bar fill; completed close signals fill at the next open.",
    ),
    hypothesis="A fresh intraday 10/30 SMA cross may predict MES continuation before the cash close.",
    source="Terry's fixed Candidate approval, 2026-10-06",
    approval_state="approved",
)


def generate_candidate_signals(data: pd.DataFrame, *, schedule: pd.DataFrame | None = None) -> SignalResult:
    if not isinstance(data.index, pd.DatetimeIndex) or data.index.tz is None:
        raise ValueError("MES SMA requires a timezone-aware DatetimeIndex")
    if not data.index.is_unique or not data.index.is_monotonic_increasing:
        raise ValueError("MES SMA timestamps must be unique and chronological")
    required = {"Open", "High", "Low", "Close", "Volume"}
    if required - set(data.columns):
        raise ValueError(f"MES SMA data is missing columns: {sorted(required - set(data.columns))}")
    frame = data.copy()
    frame.index = frame.index.tz_convert("UTC")
    schedule = _schedule(frame.index) if schedule is None else schedule
    entries = pd.Series(False, index=frame.index, dtype=bool)
    exits = entries.copy()
    short_entries = entries.copy()
    short_exits = entries.copy()

    for _, row in schedule.iterrows():
        session_open = pd.Timestamp(row["market_open"]).tz_convert("UTC")
        session_close = pd.Timestamp(row["market_close"]).tz_convert("UTC")
        # A full regular session is required: no early close, roll gap, or partial session.
        if session_close - session_open != pd.Timedelta(hours=6, minutes=30):
            continue
        expected = pd.date_range(session_open, session_close, freq=FIVE_MINUTES, inclusive="left")
        if not expected.isin(frame.index).all():
            continue
        day = frame.loc[expected]
        if not np.isfinite(day[list(required)].to_numpy(dtype=float)).all():
            continue
        if (day["Volume"] <= 0).any() or (day[["Open", "High", "Low", "Close"]] <= 0).any().any():
            continue
        fast = day["Close"].rolling(10, min_periods=10).mean()
        slow = day["Close"].rolling(30, min_periods=30).mean()
        exit_signal = session_close - pd.Timedelta(minutes=10)
        # The prior pair is defined first on bar 30; bar 31 is the first eligible cross.
        for position in range(30, len(day) - 2):
            timestamp = expected[position]
            if timestamp >= exit_signal:
                break
            previous_fast, previous_slow = fast.iloc[position - 1], slow.iloc[position - 1]
            current_fast, current_slow = fast.iloc[position], slow.iloc[position]
            if previous_fast <= previous_slow and current_fast > current_slow:
                entries.at[timestamp] = True
                exits.at[exit_signal] = True
                break
            if previous_fast >= previous_slow and current_fast < current_slow:
                short_entries.at[timestamp] = True
                short_exits.at[exit_signal] = True
                break
    return SignalResult(entries=entries, exits=exits, short_entries=short_entries, short_exits=short_exits, parameters={})


class MESSMACrossoverCandidateStrategy:
    spec = MES_SMA_SPEC

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        if parameters:
            raise ValueError("The accepted MES SMA Candidate has no tunable parameters")
        return {}

    def generate_signals(self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]) -> SignalResult:
        if not isinstance(data, pd.DataFrame):
            raise TypeError("MES SMA requires OHLCV market data")
        self.validate_parameters(parameters)
        return generate_candidate_signals(data)


MES_SMA_CANDIDATE_STRATEGY = MESSMACrossoverCandidateStrategy()
