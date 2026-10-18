"""Reusable Alpaca historical-bar acquisition for cataloged datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pandas_market_calendars as mcal

from backtesting.vectorbt_runtime import require_vectorbtpro
from market_data.catalog import DataLocations, calculate_sha256

ALPACA_DATA_HOST = "https://data.alpaca.markets"
ALPACA_BARS_ENDPOINT_TEMPLATE = "/v2/stocks/{symbol}/bars"
ALPACA_TIMEFRAME_1M = "1Min"
CANONICAL_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
OPTIONAL_ALPACA_COLUMNS = ("trade_count", "vwap")
# ``vbt.AlpacaData.fetch_symbol`` column names -> stored column names.
VBT_ALPACA_COLUMNS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
    "Trade count": "trade_count",
    "VWAP": "vwap",
}


class AlpacaDataError(RuntimeError):
    """Raised when Alpaca data cannot be acquired or validated safely."""


@dataclass(frozen=True)
class AlpacaCredentials:
    """Alpaca credentials held only in process memory."""

    key_id: str
    secret_key: str

    @classmethod
    def from_env_file(cls, path: Path) -> "AlpacaCredentials":
        """Load only the two required Alpaca variables from a local env file."""
        values: dict[str, str] = {}
        with path.open("r", encoding="utf-8") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key.startswith("export "):
                    key = key[len("export ") :].strip()
                if key not in {"APCA_API_KEY_ID", "APCA_API_SECRET_KEY"}:
                    continue
                values[key] = value.strip().strip('"').strip("'")
        missing = [
            key
            for key in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY")
            if not values.get(key)
        ]
        if missing:
            raise AlpacaDataError(
                "Missing non-empty Alpaca credential variable(s): "
                + ", ".join(missing)
            )
        return cls(
            key_id=values["APCA_API_KEY_ID"],
            secret_key=values["APCA_API_SECRET_KEY"],
        )


@dataclass(frozen=True)
class AlpacaBarsRequest:
    """Configuration for one controlled Alpaca historical-bars dataset."""

    symbol: str = "SPY"
    asset_class: str = "equity"
    asset_type: str = "ETF"
    feed: str = "iex"
    timeframe: str = "1m"
    alpaca_timeframe: str = ALPACA_TIMEFRAME_1M
    exchange_calendar: str = "NYSE"
    market_timezone: str = "America/New_York"
    session_policy: str = "regular_trading_hours_only"
    adjustment: str = "raw"
    completed_session_count: int = 5
    dataset_id: str = "equities_SPY_1m_alpaca_iex"
    filename: str = "SPY_1m_alpaca_iex.parquet"
    coverage_start: str = ""
    coverage_end_policy: str = ""
    fund_name: str = ""
    ticker_history: dict[str, str] | None = None
    corporate_action_policy: str = ""
    cache_policy: str = ""
    sparse_bar_policy: str = ""
    approved_uses: tuple[str, ...] = (
        "controlled SPY one-minute IEX research after explicit feed review",
    )
    restrictions: tuple[str, ...] = (
        "IEX feed only; do not treat as SIP consolidated tape",
        "regular trading hours only",
        "raw adjustment setting",
    )

    @property
    def canonical_relative_path(self) -> Path:
        return Path("equities") / self.symbol / self.timeframe / self.filename

    @property
    def endpoint_path(self) -> str:
        return ALPACA_BARS_ENDPOINT_TEMPLATE.format(symbol=self.symbol)








def completed_sessions_from_start(
    request: AlpacaBarsRequest,
    *,
    start_date: str,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return completed exchange sessions from one inclusive start date."""
    current = pd.Timestamp.now(tz=request.market_timezone) if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize(request.market_timezone)
    current_utc = current.tz_convert("UTC")
    calendar = mcal.get_calendar(request.exchange_calendar)
    start = pd.Timestamp(start_date).date()
    schedule = calendar.schedule(start_date=start, end_date=current.date())
    completed = schedule.loc[schedule["market_close"] <= current_utc]
    if completed.empty:
        raise AlpacaDataError(
            f"No fully completed {request.exchange_calendar} sessions are available "
            f"from {start_date}"
        )
    return completed


def expected_regular_minutes(schedule: pd.DataFrame) -> pd.DatetimeIndex:
    """Build expected UTC minute starts for regular trading hours."""
    indexes = [
        pd.date_range(
            start=row.market_open,
            end=row.market_close,
            freq="1min",
            inclusive="left",
        )
        for row in schedule.itertuples()
    ]
    if not indexes:
        return pd.DatetimeIndex([], tz="UTC", name="timestamp")
    combined = indexes[0]
    for index in indexes[1:]:
        combined = combined.append(index)
    return pd.DatetimeIndex(combined, name="timestamp").tz_convert("UTC")


def _session_labels(schedule: pd.DataFrame) -> list[str]:
    return [pd.Timestamp(item).date().isoformat() for item in schedule.index]




def fetch_alpaca_bars(
    credentials: "AlpacaCredentials",
    *,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    feed: str,
    adjustment: str,
    error: type[Exception] = AlpacaDataError,
    alpaca_data: Any = None,
) -> pd.DataFrame:
    """Every one-minute bar in [start, end] from ``vbt.AlpacaData.fetch_symbol``.

    alpaca-py (under VectorBT PRO) follows page tokens and retries rate limits.
    VectorBT drops bars at or after ``end``, so one minute is added to keep ``end``
    inclusive. Returns timestamp, open, high, low, close, volume, trade_count, vwap.
    ``alpaca_data`` stands in for ``vbt.AlpacaData`` in tests.
    """
    if alpaca_data is None:
        alpaca_data = require_vectorbtpro().AlpacaData
    try:
        raw, _ = alpaca_data.fetch_symbol(
            symbol,
            client_type="stocks",
            client_config=dict(api_key=credentials.key_id, secret_key=credentials.secret_key),
            start=start,
            end=end + pd.Timedelta(minutes=1),
            timeframe="1m",
            feed=feed,
            adjustment=adjustment,
            sort="asc",
        )
    except Exception as exc:  # alpaca-py APIError / requests errors carry no credentials
        status = getattr(exc, "status_code", None)
        raise error(
            f"Alpaca bars request failed: HTTP {status} {type(exc).__name__}: {exc}"
        ) from exc
    if raw is None or raw.empty:
        return pd.DataFrame(columns=[*CANONICAL_COLUMNS, *OPTIONAL_ALPACA_COLUMNS])
    frame = raw.rename(columns=VBT_ALPACA_COLUMNS).reindex(columns=list(VBT_ALPACA_COLUMNS.values()))
    frame.insert(0, "timestamp", pd.DatetimeIndex(raw.index).tz_convert("UTC").astype("datetime64[ns, UTC]"))
    return frame.reset_index(drop=True)






def _filter_regular_session(frame: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    masks = []
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    for row in schedule.itertuples():
        masks.append((timestamps >= row.market_open) & (timestamps < row.market_close))
    if not masks:
        return frame.iloc[0:0].copy()
    keep = masks[0]
    for mask in masks[1:]:
        keep = keep | mask
    return frame.loc[keep].copy().reset_index(drop=True)


def _coverage_for_schedule(frame: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    """Return frame rows that belong to the supplied exchange schedule."""
    expected = expected_regular_minutes(schedule)
    if frame.empty:
        return frame.copy()
    filtered = _filter_regular_session(frame, schedule)
    return filtered.loc[filtered["timestamp"].isin(expected)].reset_index(drop=True)


def _count_ohlc_violations(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    invalid = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
    return int(invalid.sum())


def _count_invalid_prices(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    invalid = pd.Series(False, index=frame.index)
    for column in ("open", "high", "low", "close"):
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = invalid | values.isna() | (values <= 0)
    return int(invalid.sum())


def _count_negative_volume(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    return int((volume < 0).sum())


def _null_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {column: int(frame[column].isna().sum()) for column in frame.columns}


def _safe_json(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    return value








def manifest_sha256(manifest: dict[str, Any]) -> str:
    """Return a deterministic digest for manifest content in tests."""
    payload = json.dumps(manifest, sort_keys=True, default=_safe_json).encode("utf-8")
    return sha256(payload).hexdigest()
