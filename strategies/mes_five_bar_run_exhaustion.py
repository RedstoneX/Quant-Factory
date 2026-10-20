"""Exact adapter for the retained MES five-bar-run exhaustion Candidate."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from strategies.mes_opening_range_breakout import MES_TICK_SIZE, _schedule
from strategies.models import (
    DataRequirements,
    ParameterDefinition,
    SignalResult,
    StrategyIdentity,
    StrategySpecification,
    TradingAssumptions,
)

CANDIDATE_ID = "qfc_d21077c94c96d40b205628d2ef90fee3"
CANDIDATE_VERSION = "d21077c94c96d40b205628d2ef90fee339caaf1b2425d97e46d6ec10942e8776"
STRATEGY_ID = "mes_five_bar_run_exhaustion"
STRATEGY_VERSION = "1.0.0"
FIVE_MINUTES = pd.Timedelta(minutes=5)


MES_FIVE_BAR_RUN_EXHAUSTION_SPEC = StrategySpecification(
    identity=StrategyIdentity(
        strategy_id=STRATEGY_ID,
        name="MES five-bar run exhaustion",
        family="mean_reversion",
        version=STRATEGY_VERSION,
        description=(
            "Reverse a qualifying 4/5/6-bar same-direction MES run between "
            "10:00 and 14:00 ET, then exit after two completed bars."
        ),
        direction="both",
    ),
    data=DataRequirements(
        required_fields=("Open", "High", "Low", "Close", "Volume"),
        supported_intervals=("5m",),
        asset_classes=("futures",),
        minimum_history_bars=78,
        adjusted_prices=False,
    ),
    parameters=(
        ParameterDefinition(
            name="run_length", value_type=int, default=5,
            description="Number of consecutive completed same-sign bars.",
            optimizable=True, allowed_values=(4, 5, 6),
            classification="bounded_discrete", reference_value=5,
            source=f"QF Candidate {CANDIDATE_ID}",
            rationale="Exact precommitted Candidate grid.", approval_state="approved",
            expected_grid_contribution=3,
        ),
        ParameterDefinition(
            name="minimum_ticks_per_bar", value_type=int, default=1,
            description="Minimum absolute open-to-close body of every run bar.",
            optimizable=True, allowed_values=(1, 2),
            classification="bounded_discrete", reference_value=1,
            source=f"QF Candidate {CANDIDATE_ID}",
            rationale="Exact precommitted Candidate grid.", approval_state="approved",
            expected_grid_contribution=2,
        ),
    ),
    assumptions=TradingAssumptions(
        signal_timing="Completed five-minute bar; bar sign is Close minus Open",
        execution_timing="Next five-minute bar open; exit after two completed bars",
        position_sizing="One MES contract; at most one trade per session",
        fee_rate=0.0,
        slippage_rate=0.0,
        stop_loss=None,
        profit_target=None,
        maximum_holding_period=2,
        pyramiding=False,
        same_bar_limitation="Signals use completed bars only; no same-bar fill.",
    ),
    hypothesis=(
        "A 4/5/6-bar same-direction MES run whose every bar moves at least "
        "1/2 ticks may exhaust and reverse over the next two completed bars."
    ),
    source=f"Retained QF Candidate {CANDIDATE_ID} version {CANDIDATE_VERSION}",
    approval_state="approved",
)


def _validate_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    definitions = MES_FIVE_BAR_RUN_EXHAUSTION_SPEC.parameter_map
    if set(parameters) != set(definitions):
        raise ValueError("run_length and minimum_ticks_per_bar are both required")
    normalized = dict(parameters)
    for name, definition in definitions.items():
        definition.validate(normalized[name])
    return normalized


def generate_signals(
    data: pd.DataFrame,
    parameters: Mapping[str, Any],
    *,
    schedule: pd.DataFrame | None = None,
) -> SignalResult:
    """Generate the exact one-trade-per-session Candidate signals."""
    normalized = _validate_parameters(parameters)
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"MES run-exhaustion data is missing columns: {missing}")
    if not isinstance(data.index, pd.DatetimeIndex) or data.index.tz is None:
        raise ValueError("MES run-exhaustion data requires a timezone-aware DatetimeIndex")
    if not data.index.is_unique or not data.index.is_monotonic_increasing:
        raise ValueError("MES run-exhaustion timestamps must be unique and chronological")

    frame = data.copy()
    frame.index = frame.index.tz_convert("UTC")
    schedule = _schedule(frame.index) if schedule is None else schedule
    entries = pd.Series(False, index=frame.index, dtype=bool)
    exits = entries.copy()
    short_entries = entries.copy()
    short_exits = entries.copy()
    eligible_sessions = 0
    excluded_sessions = 0
    run_length = normalized["run_length"]
    minimum_points = normalized["minimum_ticks_per_bar"] * MES_TICK_SIZE

    for _, row in schedule.iterrows():
        session_open = pd.Timestamp(row["market_open"]).tz_convert("UTC")
        session_close = pd.Timestamp(row["market_close"]).tz_convert("UTC")
        if session_close - session_open != pd.Timedelta(hours=6, minutes=30):
            excluded_sessions += 1
            continue
        expected = pd.date_range(session_open, session_close, freq=FIVE_MINUTES, inclusive="left")
        if not expected.isin(frame.index).all():
            excluded_sessions += 1
            continue
        day = frame.loc[expected]
        if (
            not np.isfinite(day[list(required)].to_numpy(dtype=float)).all()
            or (day["Volume"] <= 0).any()
            or (day[["Open", "High", "Low", "Close"]] <= 0).any().any()
        ):
            excluded_sessions += 1
            continue

        bodies = day["Close"].astype(float) - day["Open"].astype(float)
        # A bar counts when its body is at least the minimum size; a run is ``run_length`` consecutive counting
        # bars of one sign, completed (bar end) between 10:00 and 14:00 New York time inclusive.
        counting = (bodies.abs() >= minimum_points) & (bodies != 0)
        in_window = pd.Series(False, index=day.index)
        completed_at = (day.index + FIVE_MINUTES).tz_convert("America/New_York")
        in_window.iloc[completed_at.indexer_between_time("10:00", "14:00")] = True
        rising = ((bodies > 0) & counting).rolling(run_length).sum() == run_length
        falling = ((bodies < 0) & counting).rolling(run_length).sum() == run_length
        exhausted = (rising | falling) & in_window
        if not exhausted.any():
            eligible_sessions += 1
            continue
        signal_time = exhausted.idxmax()
        direction = "short" if rising.at[signal_time] else "long"
        entry_time = signal_time + FIVE_MINUTES
        # The generic next-bar-open adapter shifts this raw exit signal once,
        # producing an exit after exactly two completed bars.
        exit_signal_time = entry_time + FIVE_MINUTES
        forced_exit_signal_time = session_close - pd.Timedelta(minutes=15)
        exit_signal_time = min(exit_signal_time, forced_exit_signal_time)
        if entry_time not in frame.index or exit_signal_time not in frame.index:
            excluded_sessions += 1
            continue
        if direction == "long":
            entries.at[signal_time] = True
            exits.at[exit_signal_time] = True
        else:
            short_entries.at[signal_time] = True
            short_exits.at[exit_signal_time] = True
        eligible_sessions += 1

    return SignalResult(
        entries=entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=short_exits,
        parameters=normalized,
        metadata={
            "candidate_id": CANDIDATE_ID,
            "candidate_version": CANDIDATE_VERSION,
            "calendar_session_count": len(schedule),
            "eligible_session_count": eligible_sessions,
            "excluded_session_count": excluded_sessions,
            "bar_sign_basis": "Close minus Open",
            "entry": "next five-minute bar open",
            "holding_period": "two completed five-minute bars",
            "forced_flat": "15:50 America/New_York",
        },
    )


class MESFiveBarRunExhaustionStrategy:
    spec = MES_FIVE_BAR_RUN_EXHAUSTION_SPEC

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        return _validate_parameters(parameters)

    def generate_signals(
        self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]
    ) -> SignalResult:
        if not isinstance(data, pd.DataFrame):
            raise TypeError("MES run-exhaustion requires OHLCV market data")
        return generate_signals(data, parameters)


MES_FIVE_BAR_RUN_EXHAUSTION_STRATEGY = MESFiveBarRunExhaustionStrategy()
