"""Fixed SPYM transfer test of Gao, Han, Li & Zhou intraday momentum."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd
import pandas_market_calendars as mcal

from strategies.models import (
    DataRequirements,
    SignalResult,
    StrategyIdentity,
    StrategySpecification,
    TradingAssumptions,
)

SESSION_TIMEZONE = "America/New_York"
SESSION_CALENDAR = "NYSE"
SIGNAL_PREVIOUS_CLOSE = "15:59"
SIGNAL_CURRENT_CLOSE = "09:59"
ENTRY_TIME = "15:30"
EXIT_TIME = "15:59"

SPYM_INTRADAY_MOMENTUM_SPEC = StrategySpecification(
    identity=StrategyIdentity(
        strategy_id="spym_intraday_momentum",
        name="SPYM Intraday Momentum",
        family="trend_following",
        version="1.0.0",
        description=(
            "Fixed SPYM transfer test: prior regular-session 15:59 close to "
            "current 09:59 close determines a same-day 15:30-to-15:59 position."
        ),
        direction="both",
    ),
    data=DataRequirements(
        required_fields=("Open", "Close"),
        supported_intervals=("1m",),
        asset_classes=("equity", "etf"),
        minimum_history_bars=4,
        adjusted_prices=False,
    ),
    parameters=(),
    assumptions=TradingAssumptions(
        signal_timing=(
            "Previous regular-session 15:59 raw close compared with current 09:59 "
            "raw close"
        ),
        execution_timing="Enter current 15:30 open and exit current 15:59 close",
        position_sizing="All available cash at 1x; no accumulation",
        fee_rate=0.0005,
        slippage_rate=0.0002,
        stop_loss=None,
        profit_target=None,
        maximum_holding_period=None,
        pyramiding=False,
        same_bar_limitation=(
            "The candidate-specific VectorBT adapter supplies the observed entry "
            "open and exit close directly; it does not approximate either timestamp."
        ),
    ),
    hypothesis=(
        "SPYM is a transfer test, not a SPY reproduction, of Gao, Han, Li & Zhou "
        "(2018): positive overnight-to-morning intraday momentum is long and zero "
        "or negative momentum is short."
    ),
    source="Gao, Han, Li & Zhou, Market Intraday Momentum, JFE 2018, DOI 10.1016/j.jfineco.2018.05.009",
    approval_state="approved",
)


@dataclass(frozen=True)
class IntradayMomentumSession:
    session_date: str
    previous_session_date: str
    previous_close: float
    current_close: float
    signal: str
    entry_timestamp: pd.Timestamp
    exit_timestamp: pd.Timestamp


@dataclass(frozen=True)
class IntradayMomentumSignalBundle:
    signals: SignalResult
    eligible_sessions: tuple[IntradayMomentumSession, ...]
    excluded_sessions: tuple[dict[str, str], ...]
    calendar_session_count: int


def _validate_data(data: pd.DataFrame) -> pd.DataFrame:
    missing = sorted({"Open", "Close"} - set(data.columns))
    if missing:
        raise ValueError(f"SPYM intraday momentum data is missing columns: {missing}")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("SPYM intraday momentum requires a DatetimeIndex")
    if data.index.tz is None:
        raise ValueError("SPYM intraday momentum timestamps must be timezone-aware UTC")
    if not data.index.is_monotonic_increasing or not data.index.is_unique:
        raise ValueError("SPYM intraday momentum timestamps must be unique and chronological")
    utc = data.copy()
    utc.index = utc.index.tz_convert("UTC")
    return utc


def _schedule(index: pd.DatetimeIndex) -> pd.DataFrame:
    local = index.tz_convert(SESSION_TIMEZONE)
    return mcal.get_calendar(SESSION_CALENDAR).schedule(
        start_date=local[0].date(), end_date=local[-1].date()
    )


def _session_timestamp(session_date: object, wall_time: str) -> pd.Timestamp:
    return pd.Timestamp(f"{pd.Timestamp(session_date).date()} {wall_time}", tz=SESSION_TIMEZONE).tz_convert("UTC")


def generate_intraday_momentum_signal_bundle(
    data: pd.DataFrame,
    parameters: Mapping[str, Any] | None = None,
    *,
    schedule: pd.DataFrame | None = None,
) -> IntradayMomentumSignalBundle:
    """Select complete sessions and return the source-defined long/short signals."""
    if parameters not in (None, {}):
        raise ValueError("SPYM intraday momentum has no tunable parameters")
    data = _validate_data(data)
    schedule = _schedule(data.index) if schedule is None else schedule
    index_set = set(data.index)
    entries = pd.Series(False, index=data.index, dtype=bool)
    exits = pd.Series(False, index=data.index, dtype=bool)
    short_entries = pd.Series(False, index=data.index, dtype=bool)
    short_exits = pd.Series(False, index=data.index, dtype=bool)
    eligible: list[IntradayMomentumSession] = []
    excluded: list[dict[str, str]] = []

    labels = list(schedule.index)
    for position, session_label in enumerate(labels):
        session_date = str(pd.Timestamp(session_label).date())
        if position == 0:
            excluded.append({"session_date": session_date, "reason": "no prior regular session"})
            continue
        previous_label = labels[position - 1]
        previous_date = str(pd.Timestamp(previous_label).date())
        previous_close_time = _session_timestamp(previous_label, SIGNAL_PREVIOUS_CLOSE)
        current_close_time = _session_timestamp(session_label, SIGNAL_CURRENT_CLOSE)
        entry_time = _session_timestamp(session_label, ENTRY_TIME)
        exit_time = _session_timestamp(session_label, EXIT_TIME)
        required = (
            (previous_close_time, f"prior regular-session 15:59 ({previous_date})"),
            (current_close_time, "current 09:59"),
            (entry_time, "current 15:30"),
            (exit_time, "current 15:59"),
        )
        missing = [label for timestamp, label in required if timestamp not in index_set]
        if missing:
            excluded.append(
                {
                    "session_date": session_date,
                    "reason": "missing required boundary bar(s): " + ", ".join(missing),
                }
            )
            continue
        previous_close = float(data.at[previous_close_time, "Close"])
        current_close = float(data.at[current_close_time, "Close"])
        signal = "long" if current_close > previous_close else "short"
        if signal == "long":
            entries.at[entry_time] = True
            exits.at[exit_time] = True
        else:
            short_entries.at[entry_time] = True
            short_exits.at[exit_time] = True
        eligible.append(
            IntradayMomentumSession(
                session_date=session_date,
                previous_session_date=previous_date,
                previous_close=previous_close,
                current_close=current_close,
                signal=signal,
                entry_timestamp=entry_time,
                exit_timestamp=exit_time,
            )
        )

    metadata = {
        "session_timezone": SESSION_TIMEZONE,
        "calendar_session_count": len(schedule),
        "eligible_session_count": len(eligible),
        "excluded_session_count": len(excluded),
        "long_session_count": sum(item.signal == "long" for item in eligible),
        "short_session_count": sum(item.signal == "short" for item in eligible),
        "zero_signal_count": sum(
            item.current_close == item.previous_close for item in eligible
        ),
        "excluded_sessions": tuple(excluded),
        "source_rule": (
            "positive prior-15:59-to-current-09:59 close change => long; "
            "zero or negative => short"
        ),
    }
    return IntradayMomentumSignalBundle(
        signals=SignalResult(
            entries=entries,
            exits=exits,
            short_entries=short_entries,
            short_exits=short_exits,
            parameters={},
            metadata=metadata,
        ),
        eligible_sessions=tuple(eligible),
        excluded_sessions=tuple(excluded),
        calendar_session_count=len(schedule),
    )


class SPYMIntradayMomentumStrategy:
    spec = SPYM_INTRADAY_MOMENTUM_SPEC

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        if parameters:
            raise ValueError("SPYM intraday momentum has no tunable parameters")
        return {}

    def generate_signals(
        self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]
    ) -> SignalResult:
        if not isinstance(data, pd.DataFrame):
            raise TypeError("SPYM intraday momentum requires an OHLC dataframe")
        return generate_intraday_momentum_signal_bundle(data, parameters).signals


SPYM_INTRADAY_MOMENTUM_STRATEGY = SPYMIntradayMomentumStrategy()
