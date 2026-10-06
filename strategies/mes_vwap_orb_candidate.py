"""Fixed owner-approved MES ORB Candidate with VWAP and body confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd

from strategies.mes_opening_range_breakout import MES_TICK_SIZE, _schedule
from strategies.models import (
    DataRequirements,
    SignalResult,
    StrategyIdentity,
    StrategySpecification,
    TradingAssumptions,
)

CANDIDATE_ID = "idea_c0567d88820547bd96396abc9f5a7eac"
CANDIDATE_VERSION = "e73228ce418c11a1393a482bd0eb183487e2caccdc1b5e02e44690bcfc948519"
STRATEGY_VERSION = "1.0.0"
STRATEGY_ID = "mes_15m_orb_vwap_quality_candidate"
OPENING_RANGE_MINUTES = 15
BREAKOUT_BUFFER_TICKS = 4
MINIMUM_BODY_RATIO = 0.55
TARGET_R_MULTIPLE = 1.5
FIVE_MINUTES = pd.Timedelta(minutes=5)


@dataclass(frozen=True)
class CandidateSessionIssue:
    session_date: str
    reason: str


@dataclass(frozen=True)
class CandidateSignalBundle:
    signals: SignalResult
    opening_ranges: pd.DataFrame
    issues: tuple[CandidateSessionIssue, ...]
    calendar_session_count: int
    eligible_session_count: int


MES_VWAP_ORB_SPEC = StrategySpecification(
    identity=StrategyIdentity(
        strategy_id=STRATEGY_ID,
        name="MES 15-minute ORB with VWAP and breakout-quality confirmation",
        family="opening_range_breakout",
        version=STRATEGY_VERSION,
        description=(
            "One qualified 09:30–09:45 ET MES breakout, filtered by session VWAP "
            "and a fixed candle-body ratio; flat by 15:55 ET."
        ),
        direction="both",
    ),
    data=DataRequirements(
        required_fields=("Open", "High", "Low", "Close", "Volume"),
        supported_intervals=("5m",),
        asset_classes=("futures",),
        minimum_history_bars=4,
        adjusted_prices=False,
    ),
    parameters=(),
    assumptions=TradingAssumptions(
        signal_timing="Completed five-minute close after 09:45 ET",
        execution_timing="Next contiguous five-minute bar open",
        position_sizing="One MES contract; at most one trade per session",
        fee_rate=0.0,
        slippage_rate=0.0,
        stop_loss="Opposite 09:30–09:45 ET opening-range boundary",
        profit_target="1.5R, where R is entry price to initial stop distance",
        maximum_holding_period=None,
        pyramiding=False,
        same_bar_limitation=(
            "If one five-minute bar crosses both stop and target, the stop is "
            "counted first; bar OHLC does not reveal the intrabar order."
        ),
    ),
    hypothesis=(
        "A first 15-minute opening-range breakout may show same-session "
        "continuation when it agrees with session VWAP and has a body ratio "
        "of at least 0.55."
    ),
    source=f"Owner-approved QF Candidate {CANDIDATE_ID} version {CANDIDATE_VERSION}",
    approval_state="approved",
)


def _validate_data(data: pd.DataFrame) -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"MES VWAP ORB data is missing columns: {missing}")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("MES VWAP ORB requires a DatetimeIndex")
    if data.index.tz is None:
        raise ValueError("MES VWAP ORB timestamps must be timezone-aware")
    if not data.index.is_monotonic_increasing or not data.index.is_unique:
        raise ValueError("MES VWAP ORB timestamps must be unique and chronological")
    normalized = data.copy()
    normalized.index = normalized.index.tz_convert("UTC")
    return normalized


def generate_candidate_signals(
    data: pd.DataFrame,
    *,
    schedule: pd.DataFrame | None = None,
) -> CandidateSignalBundle:
    """Build exact fixed Candidate signals and per-entry stop/target distances."""
    frame = _validate_data(data)
    index = frame.index
    schedule = _schedule(index) if schedule is None else schedule
    index_set = set(index)
    entries = pd.Series(False, index=index, dtype=bool)
    exits = pd.Series(False, index=index, dtype=bool)
    short_entries = pd.Series(False, index=index, dtype=bool)
    short_exits = pd.Series(False, index=index, dtype=bool)
    stop_loss = pd.Series(np.nan, index=index, dtype=float)
    take_profit = pd.Series(np.nan, index=index, dtype=float)
    issues: list[CandidateSessionIssue] = []
    ranges: list[dict[str, Any]] = []
    breakout_points = BREAKOUT_BUFFER_TICKS * MES_TICK_SIZE

    for session_label, row in schedule.iterrows():
        session_date = str(pd.Timestamp(session_label).date())
        session_open = pd.Timestamp(row["market_open"]).tz_convert("UTC")
        session_close = pd.Timestamp(row["market_close"]).tz_convert("UTC")
        expected = pd.date_range(
            session_open, session_close, freq=FIVE_MINUTES, inclusive="left"
        )
        missing = expected.difference(index)
        if not missing.empty:
            issues.append(
                CandidateSessionIssue(
                    session_date,
                    f"missing or non-contiguous regular-session bars ({len(missing)})",
                )
            )
            continue
        if session_close - session_open < pd.Timedelta(hours=6, minutes=25):
            issues.append(CandidateSessionIssue(session_date, "early close before 15:55 ET"))
            continue
        day = frame.loc[expected]
        volumes = pd.to_numeric(day["Volume"], errors="coerce")
        if not np.isfinite(volumes.to_numpy(dtype=float)).all() or (volumes <= 0).any():
            issues.append(CandidateSessionIssue(session_date, "missing or unusable volume"))
            continue
        if not np.isfinite(day[["Open", "High", "Low", "Close"]].to_numpy(dtype=float)).all():
            issues.append(CandidateSessionIssue(session_date, "missing or invalid OHLC values"))
            continue

        range_end = session_open + pd.Timedelta(minutes=OPENING_RANGE_MINUTES)
        range_index = pd.date_range(
            session_open, periods=OPENING_RANGE_MINUTES // 5, freq=FIVE_MINUTES
        )
        range_data = day.loc[range_index]
        range_high = float(range_data["High"].max())
        range_low = float(range_data["Low"].min())
        typical_price = (day["High"] + day["Low"] + day["Close"]) / 3.0
        cumulative_volume = volumes.cumsum()
        vwap = (typical_price * volumes).cumsum() / cumulative_volume
        exit_signal_time = session_close - pd.Timedelta(minutes=10)
        candidates = day.loc[(day.index >= range_end) & (day.index < exit_signal_time)]

        selected: tuple[pd.Timestamp, str, float, float] | None = None
        for timestamp, candle in candidates.iterrows():
            next_timestamp = timestamp + FIVE_MINUTES
            if next_timestamp not in index_set:
                continue
            height = float(candle["High"] - candle["Low"])
            body_ratio = abs(float(candle["Close"] - candle["Open"])) / height if height > 0 else 0.0
            if body_ratio < MINIMUM_BODY_RATIO:
                continue
            long_signal = (
                float(candle["Close"]) >= range_high + breakout_points
                and float(candle["Close"]) > float(vwap.at[timestamp])
            )
            short_signal = (
                float(candle["Close"]) <= range_low - breakout_points
                and float(candle["Close"]) < float(vwap.at[timestamp])
            )
            if not long_signal and not short_signal:
                continue
            direction = "long" if long_signal else "short"
            entry_price = float(frame.at[next_timestamp, "Open"])
            stop_price = range_low if direction == "long" else range_high
            risk = entry_price - stop_price if direction == "long" else stop_price - entry_price
            if risk <= 0 or entry_price <= 0:
                issues.append(CandidateSessionIssue(session_date, "next-bar entry invalidates the opening-range stop"))
                continue
            selected = (timestamp, direction, entry_price, risk)
            break

        if selected is not None:
            timestamp, direction, entry_price, risk = selected
            risk_fraction = risk / entry_price
            if direction == "long":
                entries.at[timestamp] = True
                exits.at[exit_signal_time] = True
            else:
                short_entries.at[timestamp] = True
                short_exits.at[exit_signal_time] = True
            stop_loss.at[timestamp] = risk_fraction
            take_profit.at[timestamp] = TARGET_R_MULTIPLE * risk_fraction
        ranges.append(
            {
                "session_date": session_date,
                "session_open": session_open,
                "session_close": session_close,
                "range_end": range_end,
                "range_high": range_high,
                "range_low": range_low,
                "entry_confirmation": selected[0] if selected else None,
                "entry_direction": selected[1] if selected else None,
            }
        )

    if not ranges and not issues:
        raise ValueError("No exchange sessions are available in the MES VWAP ORB data")
    signals = SignalResult(
        entries=entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=short_exits,
        parameters={},
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    return CandidateSignalBundle(
        signals=signals,
        opening_ranges=pd.DataFrame(ranges).set_index("session_date") if ranges else pd.DataFrame(),
        issues=tuple(issues),
        calendar_session_count=len(schedule),
        eligible_session_count=len(ranges),
    )


class MESVWAPORBCandidateStrategy:
    spec = MES_VWAP_ORB_SPEC

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        if parameters:
            raise ValueError("The accepted MES VWAP ORB Candidate has no tunable parameters")
        return {}

    def generate_signals(
        self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]
    ) -> SignalResult:
        if not isinstance(data, pd.DataFrame):
            raise TypeError("MES VWAP ORB requires OHLCV market data")
        self.validate_parameters(parameters)
        return generate_candidate_signals(data).signals


MES_VWAP_ORB_CANDIDATE_STRATEGY = MESVWAPORBCandidateStrategy()
