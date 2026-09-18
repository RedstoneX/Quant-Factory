"""Approved MES five-minute cash-session opening-range breakout."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from itertools import product
from typing import Any, Literal, Mapping

import pandas as pd
import pandas_market_calendars as mcal

from strategies.models import (
    DataRequirements,
    ParameterDefinition,
    SignalResult,
    StrategyIdentity,
    StrategySpecification,
    TradingAssumptions,
)

ORB_RANGE_MINUTES = (5, 15, 30, 45, 60)
ORB_OFFSET_TICKS = (0, 1, 2)
MES_TICK_SIZE = 0.25
MES_POINT_VALUE = 5.0
SESSION_TIMEZONE = "America/New_York"
SESSION_CALENDAR = "NYSE"
DirectionVariant = Literal["long", "short"]


@dataclass(frozen=True)
class ORBSessionIssue:
    session_date: str
    reason: str


@dataclass(frozen=True)
class ORBSignalBundle:
    signals: SignalResult
    opening_ranges: pd.DataFrame
    issues: tuple[ORBSessionIssue, ...]
    calendar_session_count: int
    eligible_session_count: int


PARAMETER_DEFINITIONS = (
    ParameterDefinition(
        name="range_minutes",
        value_type=int,
        default=30,
        description="Cash-session opening-range length in minutes.",
        optimizable=True,
        allowed_values=ORB_RANGE_MINUTES,
        minimum=5,
        maximum=60,
        classification="bounded_discrete",
        reference_value=30,
        source="User-approved MES ORB specification",
        rationale="Compare only the five explicitly approved opening-range windows.",
        expected_grid_contribution=len(ORB_RANGE_MINUTES),
        approval_state="approved",
    ),
    ParameterDefinition(
        name="breakout_offset_ticks",
        value_type=int,
        default=0,
        description="Ticks added above or below the completed opening range.",
        optimizable=True,
        allowed_values=ORB_OFFSET_TICKS,
        minimum=0,
        maximum=2,
        classification="bounded_discrete",
        reference_value=0,
        source="User-approved MES ORB specification",
        rationale="Test only the approved zero-, one-, and two-tick confirmations.",
        expected_grid_contribution=len(ORB_OFFSET_TICKS),
        approval_state="approved",
    ),
)


def _spec(direction: DirectionVariant) -> StrategySpecification:
    label = "Long" if direction == "long" else "Short"
    return StrategySpecification(
        identity=StrategyIdentity(
            strategy_id=f"mes_opening_range_breakout_{direction}",
            name=f"MES Opening Range Breakout — {label}",
            family="range_breakout",
            version="1.0.0",
            description=(
                f"{label}-only breakout from the completed MES 09:30 New York "
                "cash-session opening range."
            ),
            direction=direction,
        ),
        data=DataRequirements(
            required_fields=("Open", "High", "Low", "Close"),
            supported_intervals=("5m",),
            asset_classes=("futures",),
            minimum_history_bars=13,
            adjusted_prices=False,
        ),
        parameters=PARAMETER_DEFINITIONS,
        assumptions=TradingAssumptions(
            signal_timing="Completed five-minute close after the opening range",
            execution_timing="Next five-minute bar open",
            position_sizing="One MES contract using the $5 point value",
            fee_rate=0.0,
            slippage_rate=0.0,
            stop_loss=None,
            profit_target=None,
            maximum_holding_period=None,
            pyramiding=False,
            same_bar_limitation=None,
        ),
        hypothesis=(
            f"MES may continue in the {direction} direction after a completed "
            "five-minute close breaks the 09:30 New York opening range."
        ),
        source="Explicit user-approved MES opening-range breakout specification",
        approval_state="approved",
    )


MES_ORB_LONG_SPEC = _spec("long")
MES_ORB_SHORT_SPEC = _spec("short")


def build_parameter_grid() -> tuple[dict[str, int], ...]:
    """Return the exact approved 5 × 3 grid for one direction variant."""
    return tuple(
        {"range_minutes": minutes, "breakout_offset_ticks": offset}
        for minutes, offset in product(ORB_RANGE_MINUTES, ORB_OFFSET_TICKS)
    )


def _validate_parameters(
    spec: StrategySpecification, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    definitions = spec.parameter_map
    unsupported = set(parameters) - set(definitions)
    if unsupported:
        raise ValueError(
            f"Unsupported parameter(s): {', '.join(sorted(unsupported))}"
        )
    normalized = {
        name: parameters.get(name, definition.default)
        for name, definition in definitions.items()
    }
    for name, value in normalized.items():
        definitions[name].validate(value)
    return normalized


def _validate_data(data: pd.DataFrame) -> None:
    required = {"Open", "High", "Low", "Close"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"MES ORB data is missing columns: {missing}")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("MES ORB requires a DatetimeIndex")
    if data.index.tz is None:
        raise ValueError("MES ORB timestamps must be timezone-aware UTC values")
    if not data.index.is_monotonic_increasing or not data.index.is_unique:
        raise ValueError("MES ORB timestamps must be unique and chronological")


def _schedule(index: pd.DatetimeIndex) -> pd.DataFrame:
    local = index.tz_convert(SESSION_TIMEZONE)
    return mcal.get_calendar(SESSION_CALENDAR).schedule(
        start_date=local[0].date(), end_date=local[-1].date()
    )


def generate_orb_signal_bundle(
    data: pd.DataFrame,
    parameters: Mapping[str, Any],
    *,
    direction: DirectionVariant,
    schedule: pd.DataFrame | None = None,
) -> ORBSignalBundle:
    """Build range levels and one same-session breakout trade per valid session."""
    spec = MES_ORB_LONG_SPEC if direction == "long" else MES_ORB_SHORT_SPEC
    normalized = _validate_parameters(spec, parameters)
    _validate_data(data)
    index = data.index.tz_convert("UTC")
    if not index.equals(data.index):
        data = data.copy()
        data.index = index
    schedule = _schedule(index) if schedule is None else schedule
    index_set = set(index)
    five_minutes = pd.Timedelta(minutes=5)
    range_bars = normalized["range_minutes"] // 5
    offset_points = normalized["breakout_offset_ticks"] * MES_TICK_SIZE

    long_entries = pd.Series(False, index=index, dtype=bool)
    long_exits = pd.Series(False, index=index, dtype=bool)
    short_entries = pd.Series(False, index=index, dtype=bool)
    short_exits = pd.Series(False, index=index, dtype=bool)
    issues: list[ORBSessionIssue] = []
    ranges: list[dict[str, Any]] = []

    for session_label, row in schedule.iterrows():
        session_date = str(pd.Timestamp(session_label).date())
        session_open = pd.Timestamp(row["market_open"]).tz_convert("UTC")
        session_close = pd.Timestamp(row["market_close"]).tz_convert("UTC")
        if session_open not in index_set:
            issues.append(ORBSessionIssue(session_date, "missing 09:30 session anchor"))
            continue
        expected_range = pd.date_range(
            session_open, periods=range_bars, freq=five_minutes
        )
        missing_range = [timestamp for timestamp in expected_range if timestamp not in index_set]
        if missing_range:
            issues.append(
                ORBSessionIssue(
                    session_date,
                    f"opening range missing {len(missing_range)} required bar(s)",
                )
            )
            continue
        exit_signal_time = session_close - five_minutes
        if exit_signal_time not in index_set or session_close not in index_set:
            issues.append(
                ORBSessionIssue(
                    session_date,
                    "missing bar required for same-session boundary exit",
                )
            )
            continue

        range_data = data.loc[expected_range]
        range_high = float(range_data["High"].max())
        range_low = float(range_data["Low"].min())
        range_end = session_open + pd.Timedelta(minutes=normalized["range_minutes"])
        start_position = index.searchsorted(range_end, side="left")
        end_position = index.searchsorted(exit_signal_time, side="left")
        candidates = data.iloc[start_position:end_position]
        next_timestamps = index[start_position + 1 : end_position + 1]
        contiguous = pd.Series(
            next_timestamps == candidates.index + five_minutes,
            index=candidates.index,
        )
        confirmed = (
            candidates["Close"] > range_high + offset_points
            if direction == "long"
            else candidates["Close"] < range_low - offset_points
        )
        qualifying = candidates.index[confirmed & contiguous]
        entry_time: pd.Timestamp | None = (
            pd.Timestamp(qualifying[0]) if len(qualifying) else None
        )

        if entry_time is not None:
            if direction == "long":
                long_entries.at[entry_time] = True
                long_exits.at[exit_signal_time] = True
            else:
                short_entries.at[entry_time] = True
                short_exits.at[exit_signal_time] = True
        ranges.append(
            {
                "session_date": session_date,
                "session_open": session_open,
                "session_close": session_close,
                "range_end": range_end,
                "range_high": range_high,
                "range_low": range_low,
                "entry_confirmation": entry_time,
            }
        )

    if not ranges:
        raise ValueError("No complete sessions can construct the approved opening range")
    issues_by_reason: dict[str, int] = {}
    for issue in issues:
        issues_by_reason[issue.reason] = issues_by_reason.get(issue.reason, 0) + 1
    metadata = {
        "session_timezone": SESSION_TIMEZONE,
        "session_anchor": "09:30",
        "calendar_session_count": len(schedule),
        "eligible_session_count": len(ranges),
        "incomplete_session_count": len(issues),
        "session_issue_counts": issues_by_reason,
        "session_issues": tuple(
            {"session_date": issue.session_date, "reason": issue.reason}
            for issue in issues
        ),
    }
    signals = SignalResult(
        entries=long_entries,
        exits=long_exits,
        short_entries=short_entries if direction == "short" else None,
        short_exits=short_exits if direction == "short" else None,
        parameters=normalized,
        metadata=metadata,
    )
    return ORBSignalBundle(
        signals=signals,
        opening_ranges=pd.DataFrame(ranges).set_index("session_date"),
        issues=tuple(issues),
        calendar_session_count=len(schedule),
        eligible_session_count=len(ranges),
    )


class MESOpeningRangeBreakoutStrategy:
    def __init__(self, direction: DirectionVariant) -> None:
        self.direction = direction
        self.spec = MES_ORB_LONG_SPEC if direction == "long" else MES_ORB_SHORT_SPEC

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        return _validate_parameters(self.spec, parameters)

    def generate_signals(
        self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]
    ) -> SignalResult:
        if not isinstance(data, pd.DataFrame):
            raise TypeError("MES ORB requires OHLC market data")
        return generate_orb_signal_bundle(
            data, parameters, direction=self.direction
        ).signals


MES_ORB_LONG_STRATEGY = MESOpeningRangeBreakoutStrategy("long")
MES_ORB_SHORT_STRATEGY = MESOpeningRangeBreakoutStrategy("short")
