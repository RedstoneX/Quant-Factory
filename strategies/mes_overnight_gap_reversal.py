"""Fixed same-session MES overnight-gap reversal candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, time, timedelta
from hashlib import sha256
import json
import math
from numbers import Real
from typing import Any, Mapping, Sequence

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
DEVELOPMENT_SESSION_START = date(2019, 5, 6)
DEVELOPMENT_SESSION_END = date(2023, 12, 29)
PRIOR_CLOSE_TIME = "15:55"
CURRENT_OPEN_TIME = "09:30"
ENTRY_TIME = "09:35"
EXIT_TIME = "10:00"
CURRENT_REQUIRED_TIMES = (
    "09:30",
    "09:35",
    "09:40",
    "09:45",
    "09:50",
    "09:55",
    "10:00",
)
INITIAL_CASH = 100_000.0
POINT_VALUE = 5.0
TICK_SIZE = 0.25
FEE_PER_SIDE = 0.62


MES_OVERNIGHT_GAP_REVERSAL_SPEC = StrategySpecification(
    identity=StrategyIdentity(
        strategy_id="mes_overnight_gap_reversal",
        name="MES Overnight-Gap Reversal",
        family="mean_reversion",
        version="1.0.0",
        description=(
            "Fixed MES transfer: reverse the prior cash-close to current cash-open "
            "gap from 09:35 through 10:00 in the same NYSE session."
        ),
        direction="both",
    ),
    data=DataRequirements(
        required_fields=("Open", "High", "Low", "Close", "Volume"),
        supported_intervals=("5m",),
        asset_classes=("futures",),
        minimum_history_bars=8,
        adjusted_prices=False,
    ),
    parameters=(),
    assumptions=TradingAssumptions(
        signal_timing=(
            "Prior NYSE-session 15:55 MES close compared with current-session "
            "09:30 MES open"
        ),
        execution_timing="Enter 09:35 raw open and exit 10:00 raw open",
        position_sizing="Exactly one MES contract; USD 5.00 per index point",
        fee_rate=0.0,
        slippage_rate=0.0,
        stop_loss=None,
        profit_target=None,
        maximum_holding_period=25,
        pyramiding=False,
        same_bar_limitation=(
            "Candidate-local prices apply one adverse 0.25-point tick per side; "
            "the generic completed-bar execution schema is not used."
        ),
    ),
    hypothesis=(
        "A positive MES prior-cash-close to current-cash-open gap reverses from "
        "09:35 to 10:00, while a negative gap reverses upward over that interval."
    ),
    source=(
        "Source-inspired MES transfer from Liu and Tse (2017), Iwanaga and "
        "Sakemoto (2026), and Grant, Wolf, and Yu (2005); not a replication."
    ),
    approval_state="approved",
)


@dataclass(frozen=True, order=True)
class MESMappingInterval:
    start_date: date
    end_date_exclusive: date
    instrument_id: str

    def contains(self, session_date: date) -> bool:
        return self.start_date <= session_date < self.end_date_exclusive

    def document(self) -> dict[str, str]:
        return {
            "start_date_inclusive": self.start_date.isoformat(),
            "end_date_exclusive": self.end_date_exclusive.isoformat(),
            "instrument_id": self.instrument_id,
        }


@dataclass(frozen=True)
class MESGapTrade:
    session_date: str
    prior_session_date: str
    mapping_instrument_id: str
    gap: float
    direction: str
    direction_value: int
    entry_timestamp: pd.Timestamp
    exit_timestamp: pd.Timestamp
    entry_raw: float
    exit_raw: float
    entry_fill: float
    exit_fill: float
    fee_per_side: float
    net_pnl: float


@dataclass(frozen=True)
class MESGapSignalBundle:
    signals: SignalResult
    scheduled_sessions: tuple[str, ...]
    completed_trades: tuple[MESGapTrade, ...]
    excluded_sessions: tuple[dict[str, Any], ...]
    daily_net_pnl: pd.Series


def _parse_date(value: object, *, label: str) -> date:
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"MES mapping {label} must be an ISO date") from exc
    return parsed


def normalize_mes_mapping(
    response: Mapping[str, Any],
    *,
    coverage_start: date = DEVELOPMENT_SESSION_START,
    coverage_end_exclusive: date = DEVELOPMENT_SESSION_END + timedelta(days=1),
) -> tuple[MESMappingInterval, ...]:
    """Validate complete Databento ``[d0, d1)`` MES.c.0 resolution intervals."""
    if not isinstance(response, Mapping):
        raise TypeError("MES symbology response must be a mapping")
    if response.get("status") != 0 or response.get("message") != "OK":
        raise ValueError("MES symbology response must have status 0 and message OK")
    if response.get("partial") not in ([], ()):
        raise ValueError("MES symbology response contains partial intervals")
    if response.get("not_found") not in ([], ()):
        raise ValueError("MES symbology response contains not-found intervals")
    result = response.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("MES symbology response result is missing")
    raw_intervals = result.get("MES.c.0")
    if not isinstance(raw_intervals, Sequence) or isinstance(raw_intervals, (str, bytes)):
        raise ValueError("MES.c.0 symbology intervals are missing")
    intervals: list[MESMappingInterval] = []
    for item in raw_intervals:
        if not isinstance(item, Mapping):
            raise ValueError("MES.c.0 mapping interval must be an object")
        start = _parse_date(item.get("d0"), label="d0")
        end_exclusive = _parse_date(item.get("d1"), label="d1")
        raw_instrument_id = item.get("s")
        if (
            isinstance(raw_instrument_id, bool)
            or not isinstance(raw_instrument_id, (str, int))
        ):
            raise ValueError("MES mapping interval has an invalid instrument ID")
        instrument_id = str(raw_instrument_id).strip()
        if start >= end_exclusive:
            raise ValueError("MES mapping interval must have a positive [d0, d1) span")
        if not instrument_id.isdecimal() or int(instrument_id) <= 0:
            raise ValueError("MES mapping interval has an invalid instrument ID")
        intervals.append(MESMappingInterval(start, end_exclusive, instrument_id))
    intervals.sort()
    if not intervals:
        raise ValueError("MES.c.0 symbology resolution is empty")
    for previous, current in zip(intervals, intervals[1:]):
        if current.start_date < previous.end_date_exclusive:
            raise ValueError("MES mapping intervals overlap")
        if current.start_date > previous.end_date_exclusive:
            raise ValueError("MES mapping intervals have incomplete calendar coverage")
    if (
        intervals[0].start_date > coverage_start
        or intervals[-1].end_date_exclusive < coverage_end_exclusive
    ):
        raise ValueError("MES mapping intervals do not cover the development boundary")
    return tuple(intervals)


def mes_mapping_checksum(intervals: Sequence[MESMappingInterval]) -> str:
    document = [item.document() for item in intervals]
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _mapping_for_date(
    intervals: Sequence[MESMappingInterval], session_date: date
) -> MESMappingInterval:
    matches = [item for item in intervals if item.contains(session_date)]
    if len(matches) != 1:
        raise RuntimeError(
            f"complete MES mapping does not identify exactly one interval for {session_date}"
        )
    return matches[0]


def _validate_data(data: pd.DataFrame) -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"MES gap data is missing columns: {missing}")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("MES gap data requires a DatetimeIndex")
    if data.index.tz is None:
        raise ValueError("MES gap timestamps must be timezone-aware UTC")
    if not data.index.is_unique or not data.index.is_monotonic_increasing:
        raise ValueError("MES gap timestamps must be unique and chronological")
    utc = data.loc[:, ["Open", "High", "Low", "Close", "Volume"]].copy()
    utc.index = utc.index.tz_convert("UTC")
    return utc


def _session_timestamp(session_label: object, wall_time: str) -> pd.Timestamp:
    value = pd.Timestamp(session_label).date()
    return pd.Timestamp(f"{value} {wall_time}", tz=SESSION_TIMEZONE).tz_convert("UTC")


def _development_schedule() -> pd.DataFrame:
    return mcal.get_calendar(SESSION_CALENDAR).schedule(
        start_date=DEVELOPMENT_SESSION_START,
        end_date=DEVELOPMENT_SESSION_END,
    )


def _is_early_close(schedule: pd.DataFrame, session_label: object) -> bool:
    if "market_close" not in schedule.columns:
        return False
    market_close = pd.Timestamp(schedule.loc[session_label, "market_close"])
    if market_close.tzinfo is None:
        raise ValueError("NYSE schedule market_close timestamps must be timezone-aware")
    return market_close.tz_convert(SESSION_TIMEZONE).time() < time(16, 0)


def _bar_is_valid(row: pd.Series) -> bool:
    prices = [row[name] for name in ("Open", "High", "Low", "Close")]
    volume = row["Volume"]
    return bool(
        all(isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value)) and value > 0 for value in prices)
        and isinstance(volume, Real)
        and not isinstance(volume, bool)
        and math.isfinite(float(volume))
        and volume >= 0
    )


def generate_mes_overnight_gap_reversal_bundle(
    data: pd.DataFrame,
    parameters: Mapping[str, Any] | None = None,
    *,
    mapping_intervals: Sequence[MESMappingInterval],
    schedule: pd.DataFrame | None = None,
) -> MESGapSignalBundle:
    """Classify every development session and build the fixed same-day signals."""
    if parameters not in (None, {}):
        raise ValueError("MES overnight-gap reversal has no tunable parameters")
    data = _validate_data(data)
    schedule = _development_schedule() if schedule is None else schedule
    labels = list(schedule.index)
    entries = pd.Series(False, index=data.index, dtype=bool)
    exits = pd.Series(False, index=data.index, dtype=bool)
    short_entries = pd.Series(False, index=data.index, dtype=bool)
    short_exits = pd.Series(False, index=data.index, dtype=bool)
    daily_pnl = pd.Series(0.0, index=pd.DatetimeIndex(labels), dtype=float)
    daily_pnl.index.name = "session"
    trades: list[MESGapTrade] = []
    excluded: list[dict[str, Any]] = []
    index_set = set(data.index)

    for position, session_label in enumerate(labels):
        session_day = pd.Timestamp(session_label).date()
        session_text = session_day.isoformat()
        if position == 0:
            excluded.append(
                {"session_date": session_text, "reason": "missing_prior_session_boundary"}
            )
            continue
        prior_label = labels[position - 1]
        prior_day = pd.Timestamp(prior_label).date()
        if _is_early_close(schedule, prior_label):
            excluded.append(
                {
                    "session_date": session_text,
                    "reason": "prior_session_early_close",
                    "prior_session_date": prior_day.isoformat(),
                }
            )
            continue
        prior_close_timestamp = _session_timestamp(prior_label, PRIOR_CLOSE_TIME)
        current_timestamps = tuple(
            _session_timestamp(session_label, value) for value in CURRENT_REQUIRED_TIMES
        )
        required = (prior_close_timestamp,) + current_timestamps
        missing = [item.isoformat() for item in required if item not in index_set]
        if missing:
            excluded.append(
                {
                    "session_date": session_text,
                    "reason": "missing_required_boundary_bar",
                    "details": tuple(missing),
                }
            )
            continue
        invalid = [item.isoformat() for item in required if not _bar_is_valid(data.loc[item])]
        if invalid:
            excluded.append(
                {
                    "session_date": session_text,
                    "reason": "invalid_required_boundary_bar",
                    "details": tuple(invalid),
                }
            )
            continue
        prior_mapping = _mapping_for_date(mapping_intervals, prior_day)
        current_mapping = _mapping_for_date(mapping_intervals, session_day)
        if prior_mapping != current_mapping:
            excluded.append(
                {
                    "session_date": session_text,
                    "reason": "roll_mapping_boundary",
                    "prior_instrument_id": prior_mapping.instrument_id,
                    "current_instrument_id": current_mapping.instrument_id,
                }
            )
            continue

        current_open_timestamp = current_timestamps[0]
        entry_timestamp = current_timestamps[1]
        exit_timestamp = current_timestamps[-1]
        prior_close = float(data.at[prior_close_timestamp, "Close"])
        current_open = float(data.at[current_open_timestamp, "Open"])
        gap = current_open / prior_close - 1.0
        if gap == 0.0:
            excluded.append({"session_date": session_text, "reason": "zero_gap"})
            continue
        direction_value = -1 if gap > 0 else 1
        direction = "short" if direction_value < 0 else "long"
        entry_raw = float(data.at[entry_timestamp, "Open"])
        exit_raw = float(data.at[exit_timestamp, "Open"])
        entry_fill = entry_raw + direction_value * TICK_SIZE
        exit_fill = exit_raw - direction_value * TICK_SIZE
        net_pnl = (
            direction_value * (exit_fill - entry_fill) * POINT_VALUE
            - 2.0 * FEE_PER_SIDE
        )
        if direction_value > 0:
            entries.at[entry_timestamp] = True
            exits.at[exit_timestamp] = True
        else:
            short_entries.at[entry_timestamp] = True
            short_exits.at[exit_timestamp] = True
        daily_pnl.at[session_label] = net_pnl
        trades.append(
            MESGapTrade(
                session_date=session_text,
                prior_session_date=prior_day.isoformat(),
                mapping_instrument_id=current_mapping.instrument_id,
                gap=gap,
                direction=direction,
                direction_value=direction_value,
                entry_timestamp=entry_timestamp,
                exit_timestamp=exit_timestamp,
                entry_raw=entry_raw,
                exit_raw=exit_raw,
                entry_fill=entry_fill,
                exit_fill=exit_fill,
                fee_per_side=FEE_PER_SIDE,
                net_pnl=net_pnl,
            )
        )

    reason_counts: dict[str, int] = {}
    for item in excluded:
        reason = str(item["reason"])
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    metadata = {
        "session_timezone": SESSION_TIMEZONE,
        "calendar_session_count": len(labels),
        "completed_trade_count": len(trades),
        "long_trade_count": sum(item.direction == "long" for item in trades),
        "short_trade_count": sum(item.direction == "short" for item in trades),
        "excluded_session_count": len(excluded),
        "exclusion_reason_counts": reason_counts,
        "excluded_sessions": tuple(excluded),
        "source_rule": (
            "positive prior-15:55-close/current-09:30-open gap => short; "
            "negative gap => long; zero gap => flat"
        ),
    }
    return MESGapSignalBundle(
        signals=SignalResult(
            entries=entries,
            exits=exits,
            short_entries=short_entries,
            short_exits=short_exits,
            parameters={},
            metadata=metadata,
        ),
        scheduled_sessions=tuple(pd.Timestamp(item).date().isoformat() for item in labels),
        completed_trades=tuple(trades),
        excluded_sessions=tuple(excluded),
        daily_net_pnl=daily_pnl,
    )


class MESOvernightGapReversalStrategy:
    spec = MES_OVERNIGHT_GAP_REVERSAL_SPEC

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        if parameters:
            raise ValueError("MES overnight-gap reversal has no tunable parameters")
        return {}

    def generate_signals(
        self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]
    ) -> SignalResult:
        raise RuntimeError(
            "MES overnight-gap reversal requires candidate-local roll mapping; "
            "use generate_mes_overnight_gap_reversal_bundle"
        )


MES_OVERNIGHT_GAP_REVERSAL_STRATEGY = MESOvernightGapReversalStrategy()


def trade_document(trade: MESGapTrade) -> dict[str, Any]:
    """Return one JSON-ready exact trade record for durable evidence."""
    document = asdict(trade)
    document["entry_timestamp"] = trade.entry_timestamp.isoformat()
    document["exit_timestamp"] = trade.exit_timestamp.isoformat()
    return document
