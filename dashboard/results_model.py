"""Persistence-neutral data contracts for the selected-run Results workspace.

The model deliberately accepts ordinary mappings so persisted artifact schemas stay
owned by the persistence layer.  It validates and derives presentation data without
mutating source evidence or depending on Dash, VectorBT Pro, or a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Iterable, Mapping, Sequence


UTC = timezone.utc
SUPPORTED_INTERVALS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1D": timedelta(days=1),
}


class ResultsDataError(ValueError):
    """Fail-closed error for corrupt or ambiguous persisted Results evidence."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class OhlcBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    source_count: int = 1


@dataclass(frozen=True)
class IntervalBars:
    interval: str
    bars: tuple[OhlcBar, ...]
    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class TradeEvent:
    trade_id: str
    leg: str
    timestamp: datetime
    price: float

    def __post_init__(self) -> None:
        _aware_timestamp(self.timestamp, field=f"Trade {self.trade_id} {self.leg} timestamp")
        _finite_number(self.price, field=f"Trade {self.trade_id} {self.leg} price")


@dataclass(frozen=True)
class EventBarMapping:
    event: TradeEvent
    interval: str
    bar_timestamp: datetime | None
    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class TradeGroup:
    trade_id: str
    status: str
    direction: str | None
    entry: TradeEvent | None
    exit: TradeEvent | None
    valuation_price: float | None
    pnl: float | None
    return_value: float | None
    outcome: str | None
    unavailable_reasons: tuple[str, ...]
    valuation_timestamp: datetime | None = None


@dataclass(frozen=True)
class TradeGrouping:
    groups: tuple[TradeGroup, ...]
    closed_count: int
    open_count: int
    unconfirmed_count: int
    profitable_closed_count: int


def _aware_timestamp(value: Any, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ResultsDataError(
                "invalid_timestamp", f"{field} is not a valid ISO-8601 timestamp."
            ) from exc
    else:
        raise ResultsDataError(
            "invalid_timestamp", f"{field} must be a timezone-aware timestamp."
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResultsDataError(
            "timezone_required", f"{field} must include a timezone offset."
        )
    return parsed.astimezone(UTC)


def _finite_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResultsDataError("invalid_number", f"{field} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise ResultsDataError("nonfinite_number", f"{field} must be finite.")
    return number


def validate_ohlc_rows(
    rows: Iterable[Mapping[str, Any]], *, source_interval: str = "1m"
) -> tuple[OhlcBar, ...]:
    """Validate persisted source OHLC without sorting, filling, or repairing it."""

    source_width = SUPPORTED_INTERVALS.get(source_interval)
    if source_width is None:
        raise ResultsDataError(
            "unsupported_source_interval",
            f"Source bars interval {source_interval!r} is not supported.",
        )

    validated: list[OhlcBar] = []
    previous: datetime | None = None
    previous_bucket: datetime | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ResultsDataError(
                "invalid_row", f"OHLC row {index} must be an object."
            )
        timestamp = _aware_timestamp(
            row.get("timestamp"), field=f"OHLC row {index} timestamp"
        )
        if previous is not None and timestamp <= previous:
            relationship = "duplicates" if timestamp == previous else "is out of order"
            raise ResultsDataError(
                "unordered_timestamp",
                f"OHLC row {index} {relationship}; timestamps must be unique and increasing.",
            )
        source_bucket = _bucket_start(timestamp, source_width)
        if previous_bucket is not None and source_bucket == previous_bucket:
            raise ResultsDataError(
                "duplicate_source_bucket",
                f"OHLC row {index} duplicates the preceding {source_interval} UTC epoch-left bucket.",
            )
        if timestamp != source_bucket:
            raise ResultsDataError(
                "misaligned_source_bar",
                f"OHLC row {index} is not aligned to its {source_interval} UTC epoch-left bucket.",
            )
        values = {
            name: _finite_number(row.get(name), field=f"OHLC row {index} {name}")
            for name in ("open", "high", "low", "close")
        }
        if values["high"] < max(values["open"], values["close"], values["low"]):
            raise ResultsDataError(
                "inconsistent_ohlc",
                f"OHLC row {index} high is below another recorded price.",
            )
        if values["low"] > min(values["open"], values["close"], values["high"]):
            raise ResultsDataError(
                "inconsistent_ohlc",
                f"OHLC row {index} low is above another recorded price.",
            )
        validated.append(OhlcBar(timestamp=timestamp, **values))
        previous = timestamp
        previous_bucket = source_bucket
    return tuple(validated)


def _bucket_start(timestamp: datetime, width: timedelta) -> datetime:
    epoch_seconds = int(timestamp.astimezone(UTC).timestamp())
    width_seconds = int(width.total_seconds())
    return datetime.fromtimestamp(
        epoch_seconds - (epoch_seconds % width_seconds), tz=UTC
    )


def prepare_interval(
    rows: Iterable[Mapping[str, Any]],
    interval: str,
    *,
    source_interval: str = "1m",
) -> IntervalBars:
    """Return truthful interval bars or an explicit unsupported/unavailable state."""

    if interval not in SUPPORTED_INTERVALS:
        return IntervalBars(
            interval=interval,
            bars=(),
            available=False,
            reason=f"Bars interval {interval!r} is not supported.",
        )
    if source_interval != "1m":
        return IntervalBars(
            interval=interval,
            bars=(),
            available=False,
            reason=(
                f"Bars interval {interval} is unavailable because truthful aggregation "
                f"currently requires persisted 1m OHLC, not {source_interval}."
            ),
        )
    source = validate_ohlc_rows(rows, source_interval=source_interval)
    if not source:
        return IntervalBars(
            interval=interval,
            bars=(),
            available=False,
            reason="No persisted OHLC bars are available for this run.",
        )
    if interval == "1m":
        return IntervalBars(interval=interval, bars=source, available=True)

    width = SUPPORTED_INTERVALS[interval]
    aggregated: list[OhlcBar] = []
    bucket: datetime | None = None
    bucket_rows: list[OhlcBar] = []

    def append_bucket() -> None:
        if bucket is None or not bucket_rows:
            return
        aggregated.append(
            OhlcBar(
                timestamp=bucket,
                open=bucket_rows[0].open,
                high=max(row.high for row in bucket_rows),
                low=min(row.low for row in bucket_rows),
                close=bucket_rows[-1].close,
                source_count=sum(row.source_count for row in bucket_rows),
            )
        )

    for row in source:
        row_bucket = _bucket_start(row.timestamp, width)
        if bucket is not None and row_bucket != bucket:
            append_bucket()
            bucket_rows = []
        bucket = row_bucket
        bucket_rows.append(row)
    append_bucket()
    return IntervalBars(interval=interval, bars=tuple(aggregated), available=True)


def map_event_to_bar(event: TradeEvent, interval_bars: IntervalBars) -> EventBarMapping:
    """Map an exact persisted event to its containing rendered bar."""

    if not interval_bars.available:
        return EventBarMapping(
            event=event,
            interval=interval_bars.interval,
            bar_timestamp=None,
            available=False,
            reason=interval_bars.reason or "The selected bars are unavailable.",
        )
    width = SUPPORTED_INTERVALS.get(interval_bars.interval)
    if width is None:
        return EventBarMapping(
            event=event,
            interval=interval_bars.interval,
            bar_timestamp=None,
            available=False,
            reason=f"Bars interval {interval_bars.interval!r} is not supported.",
        )
    containing_timestamp = _bucket_start(event.timestamp, width)
    if not any(bar.timestamp == containing_timestamp for bar in interval_bars.bars):
        return EventBarMapping(
            event=event,
            interval=interval_bars.interval,
            bar_timestamp=None,
            available=False,
            reason=(
                "The persisted trade event falls in a bucket with no persisted OHLC bar; "
                "no marker position was fabricated."
            ),
        )
    return EventBarMapping(
        event=event,
        interval=interval_bars.interval,
        bar_timestamp=containing_timestamp,
        available=True,
    )


def _first(row: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _optional_number(value: Any, *, field: str, reasons: list[str]) -> float | None:
    if value in (None, ""):
        return None
    try:
        return _finite_number(value, field=field)
    except ResultsDataError as exc:
        reasons.append(exc.reason)
        return None


def _event(
    row: Mapping[str, Any],
    *,
    trade_id: str,
    leg: str,
    timestamp_keys: Sequence[str],
    price_keys: Sequence[str],
    reasons: list[str],
) -> TradeEvent | None:
    raw_timestamp = _first(row, timestamp_keys)
    raw_price = _first(row, price_keys)
    if raw_timestamp is None and raw_price is None:
        reasons.append(f"{leg.title()} event is not recorded.")
        return None
    if raw_timestamp is None or raw_price is None:
        reasons.append(f"{leg.title()} event timestamp and price are not both recorded.")
        return None
    try:
        timestamp = _aware_timestamp(raw_timestamp, field=f"Trade {trade_id} {leg} timestamp")
        price = _finite_number(raw_price, field=f"Trade {trade_id} {leg} price")
    except ResultsDataError as exc:
        reasons.append(exc.reason)
        return None
    return TradeEvent(trade_id=trade_id, leg=leg, timestamp=timestamp, price=price)


def _valuation(
    row: Mapping[str, Any], *, trade_id: str, reasons: list[str]
) -> tuple[datetime | None, float | None]:
    raw_timestamp = _first(
        row,
        (
            "valuation_timestamp",
            "Valuation Timestamp",
            "Current Timestamp",
            "Exit Index",
        ),
    )
    raw_price = _first(
        row,
        (
            "valuation_price",
            "Valuation Price",
            "Current Price",
            "Avg Exit Price",
            "Exit Price",
        ),
    )
    if raw_timestamp is None and raw_price is None:
        reasons.append("Open-trade valuation timestamp and price are not recorded.")
        return None, None
    if raw_timestamp is None or raw_price is None:
        reasons.append(
            "Open-trade valuation timestamp and price are not both recorded."
        )
        return None, None
    try:
        timestamp = _aware_timestamp(
            raw_timestamp, field=f"Trade {trade_id} valuation timestamp"
        )
        price = _finite_number(raw_price, field=f"Trade {trade_id} valuation price")
    except ResultsDataError as exc:
        reasons.append(exc.reason)
        return None, None
    return timestamp, price


def group_trade_rows(rows: Iterable[Mapping[str, Any]]) -> TradeGrouping:
    """Build truthful closed/open trade groups from persisted trade records."""

    groups: list[TradeGroup] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ResultsDataError(
                "invalid_trade_row", f"Trade row {index - 1} must be an object."
            )
        source_id = _first(row, ("trade_id", "Trade Id", "Exit Trade Id"))
        trade_id = str(source_id) if source_id not in (None, "") else str(index)
        reasons: list[str] = []
        status_value = _first(row, ("status", "Status"))
        normalized_status = str(status_value).strip().lower() if status_value else ""
        if normalized_status == "closed":
            status = "closed"
        elif normalized_status == "open":
            status = "open"
        else:
            status = "unconfirmed"
            reasons.append("Trade status is not recorded as closed or open.")

        direction_value = _first(row, ("direction", "Direction"))
        direction = str(direction_value).strip().lower() if direction_value else None
        entry = _event(
            row,
            trade_id=trade_id,
            leg="entry",
            timestamp_keys=("entry_timestamp", "Entry Timestamp", "Entry Index"),
            price_keys=("entry_price", "Entry Price", "Avg Entry Price", "Open Price"),
            reasons=reasons,
        )
        exit_event = None
        if status == "closed":
            exit_event = _event(
                row,
                trade_id=trade_id,
                leg="exit",
                timestamp_keys=("exit_timestamp", "Exit Timestamp", "Exit Index"),
                price_keys=("exit_price", "Exit Price", "Avg Exit Price", "Close Price"),
                reasons=reasons,
            )
            if entry is None or exit_event is None:
                status = "unconfirmed"
                reasons.append("Closed status lacks complete persisted entry and exit events.")
            elif exit_event.timestamp < entry.timestamp:
                status = "unconfirmed"
                reasons.append(
                    "Closed trade exit timestamp precedes its persisted entry timestamp."
                )
        elif status == "open" and entry is None:
            status = "unconfirmed"
            reasons.append("Open status lacks a complete persisted entry event.")

        valuation_timestamp = None
        valuation_price = None
        if status == "open":
            valuation_timestamp, valuation_price = _valuation(
                row, trade_id=trade_id, reasons=reasons
            )
            if (
                entry is not None
                and valuation_timestamp is not None
                and valuation_timestamp < entry.timestamp
            ):
                valuation_timestamp = None
                valuation_price = None
                reasons.append(
                    "Open-trade valuation timestamp precedes its persisted entry timestamp."
                )

        pnl = None
        return_value = None
        if status == "closed":
            pnl = _optional_number(
                _first(row, ("pnl", "PnL", "Profit", "Net PnL")),
                field=f"Trade {trade_id} P&L",
                reasons=reasons,
            )
            return_value = _optional_number(
                _first(row, ("return", "Return", "Trade Return")),
                field=f"Trade {trade_id} return",
                reasons=reasons,
            )
        outcome = None
        if status == "closed" and pnl is not None:
            outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "flat"
        elif status == "closed":
            reasons.append("Closed trade outcome is unavailable because P&L is not recorded.")

        groups.append(
            TradeGroup(
                trade_id=trade_id,
                status=status,
                direction=direction,
                entry=entry,
                exit=exit_event if status == "closed" else None,
                valuation_price=valuation_price,
                pnl=pnl if status == "closed" else None,
                return_value=return_value if status == "closed" else None,
                outcome=outcome,
                unavailable_reasons=tuple(dict.fromkeys(reasons)),
                valuation_timestamp=valuation_timestamp,
            )
        )

    return TradeGrouping(
        groups=tuple(groups),
        closed_count=sum(group.status == "closed" for group in groups),
        open_count=sum(group.status == "open" for group in groups),
        unconfirmed_count=sum(group.status == "unconfirmed" for group in groups),
        profitable_closed_count=sum(group.outcome == "win" for group in groups),
    )
