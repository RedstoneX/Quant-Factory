"""Reusable Alpaca historical-bar acquisition for cataloged datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any, Protocol

import pandas as pd
import pandas_market_calendars as mcal
import requests

from market_data.catalog import DataLocations, calculate_sha256

ALPACA_DATA_HOST = "https://data.alpaca.markets"
ALPACA_BARS_ENDPOINT_TEMPLATE = "/v2/stocks/{symbol}/bars"
ALPACA_TIMEFRAME_1M = "1Min"
CANONICAL_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
OPTIONAL_ALPACA_COLUMNS = ("trade_count", "vwap")


class AlpacaDataError(RuntimeError):
    """Raised when Alpaca data cannot be acquired or validated safely."""


class HttpClient(Protocol):
    """Minimal requests-compatible HTTP client used for deterministic tests."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any],
        timeout: float,
    ) -> Any:
        """Return a response object with status_code, json(), and text."""


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


@dataclass(frozen=True)
class AlpacaAcquisitionResult:
    """Result of one Alpaca acquisition or cache reuse."""

    frame: pd.DataFrame
    manifest: dict[str, Any]
    parquet_path: Path
    manifest_path: Path
    cache_reused: bool
    requested_sessions: list[str]
    missing_sessions: list[str]
    missing_bar_count: int


@dataclass(frozen=True)
class MissingRange:
    """One missing requested time range that should be downloaded."""

    session: str
    start: pd.Timestamp
    end: pd.Timestamp


def recent_completed_sessions(
    request: AlpacaBarsRequest,
    *,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return the most recent fully completed exchange sessions."""
    if request.completed_session_count <= 0:
        raise ValueError("completed_session_count must be positive")
    current = pd.Timestamp.now(tz=request.market_timezone) if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize(request.market_timezone)
    current_utc = current.tz_convert("UTC")
    calendar = mcal.get_calendar(request.exchange_calendar)
    lookback_start = (current - pd.Timedelta(days=21)).date()
    schedule = calendar.schedule(start_date=lookback_start, end_date=current.date())
    completed = schedule.loc[schedule["market_close"] <= current_utc]
    if len(completed) < request.completed_session_count:
        raise AlpacaDataError(
            "Fewer completed sessions are available than requested: "
            f"{len(completed)} < {request.completed_session_count}"
        )
    return completed.tail(request.completed_session_count)


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


def _normalize_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _bars_to_frame(bars: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bar in bars:
        rows.append(
            {
                "timestamp": _normalize_timestamp(bar["t"]),
                "open": float(bar["o"]),
                "high": float(bar["h"]),
                "low": float(bar["l"]),
                "close": float(bar["c"]),
                "volume": float(bar["v"]),
                "trade_count": int(bar["n"]) if bar.get("n") is not None else pd.NA,
                "vwap": float(bar["vw"]) if bar.get("vw") is not None else pd.NA,
            }
        )
    if not rows:
        return pd.DataFrame(columns=[*CANONICAL_COLUMNS, *OPTIONAL_ALPACA_COLUMNS])
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def _deduplicate(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    duplicate_count = int(frame["timestamp"].duplicated(keep=False).sum())
    deduped = frame.drop_duplicates("timestamp", keep="last")
    return deduped.sort_values("timestamp", kind="mergesort").reset_index(drop=True), duplicate_count


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


def _empty_bars_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[*CANONICAL_COLUMNS, *OPTIONAL_ALPACA_COLUMNS])


def _session_expected_minutes(schedule: pd.DataFrame, session_label: str) -> pd.DatetimeIndex:
    row = schedule.loc[pd.Timestamp(session_label)]
    return pd.date_range(
        start=row.market_open,
        end=row.market_close,
        freq="1min",
        inclusive="left",
    )


def _group_missing_ranges(
    *,
    schedule: pd.DataFrame,
    existing: pd.DataFrame,
    sparse_bar_policy: str = "",
) -> tuple[list[str], list[MissingRange]]:
    existing_timestamps = (
        pd.DatetimeIndex([], tz="UTC")
        if existing.empty
        else pd.DatetimeIndex(pd.to_datetime(existing["timestamp"], utc=True))
    )
    already_present_sessions: list[str] = []
    missing_ranges: list[MissingRange] = []
    for session_label in _session_labels(schedule):
        expected = _session_expected_minutes(schedule, session_label)
        if sparse_bar_policy:
            observed = expected.intersection(existing_timestamps)
            if len(observed) > 0:
                already_present_sessions.append(session_label)
                continue
            missing_ranges.append(
                MissingRange(
                    session=session_label,
                    start=expected[0],
                    end=expected[-1] + pd.Timedelta(minutes=1),
                )
            )
            continue
        missing = expected.difference(existing_timestamps)
        if len(missing) == 0:
            already_present_sessions.append(session_label)
            continue
        groups: list[list[pd.Timestamp]] = []
        current_group: list[pd.Timestamp] = []
        previous: pd.Timestamp | None = None
        for timestamp in missing:
            current = pd.Timestamp(timestamp)
            if previous is None or current == previous + pd.Timedelta(minutes=1):
                current_group.append(current)
            else:
                groups.append(current_group)
                current_group = [current]
            previous = current
        if current_group:
            groups.append(current_group)
        for group in groups:
            missing_ranges.append(
                MissingRange(
                    session=session_label,
                    start=group[0],
                    end=group[-1] + pd.Timedelta(minutes=1),
                )
            )
    return already_present_sessions, missing_ranges


class AlpacaHistoricalBarsProvider:
    """Download, validate, store, and manifest Alpaca historical bars."""

    def __init__(
        self,
        *,
        credentials: AlpacaCredentials,
        locations: DataLocations,
        client: HttpClient | None = None,
        base_url: str = ALPACA_DATA_HOST,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.credentials = credentials
        self.locations = locations
        self.client = client or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def acquire_recent_sessions(
        self,
        request: AlpacaBarsRequest,
        *,
        now: pd.Timestamp | None = None,
        repo_manifest_dir: Path | None = None,
    ) -> AlpacaAcquisitionResult:
        """Acquire the requested recent sessions while preserving older data."""
        schedule = recent_completed_sessions(request, now=now)
        return self.acquire_schedule(
            request,
            schedule=schedule,
            repo_manifest_dir=repo_manifest_dir,
        )

    def acquire_from_start(
        self,
        request: AlpacaBarsRequest,
        *,
        start_date: str,
        now: pd.Timestamp | None = None,
        repo_manifest_dir: Path | None = None,
    ) -> AlpacaAcquisitionResult:
        """Acquire completed sessions from one inclusive start date."""
        schedule = completed_sessions_from_start(request, start_date=start_date, now=now)
        return self.acquire_schedule(
            request,
            schedule=schedule,
            repo_manifest_dir=repo_manifest_dir,
        )

    def acquire_schedule(
        self,
        request: AlpacaBarsRequest,
        *,
        schedule: pd.DataFrame,
        repo_manifest_dir: Path | None = None,
    ) -> AlpacaAcquisitionResult:
        """Acquire one explicit exchange schedule while preserving older data."""
        if schedule.empty:
            raise AlpacaDataError("Cannot acquire an empty Alpaca schedule")
        requested_sessions = _session_labels(schedule)
        parquet_path = self.locations.root / request.canonical_relative_path
        manifest_path = (
            repo_manifest_dir / f"{request.dataset_id}.json"
            if repo_manifest_dir is not None
            else self.locations.manifests / f"{request.dataset_id}.json"
        )

        existing, previous_manifest = self._read_existing_verified(
            request=request,
            parquet_path=parquet_path,
            manifest_path=manifest_path,
        )
        already_present_sessions, missing_ranges = _group_missing_ranges(
            schedule=schedule,
            existing=existing,
            sparse_bar_policy=request.sparse_bar_policy,
        )
        request_frame_before_download = _coverage_for_schedule(existing, schedule)
        full_reuse = len(missing_ranges) == 0 and not existing.empty

        if full_reuse:
            duplicate_count = int(existing["timestamp"].duplicated(keep=False).sum())
            manifest = self._build_manifest(
                request=request,
                frame=existing,
                schedule=schedule,
                parquet_path=parquet_path,
                duplicate_timestamp_count=duplicate_count,
                out_of_session_bar_count=0,
                already_present_sessions=already_present_sessions,
                newly_downloaded_sessions=[],
                newly_downloaded_ranges=[],
                cache_status="full_reuse",
                cache_reused=True,
                previous_manifest=previous_manifest,
            )
            manifest["sha256"] = calculate_sha256(parquet_path)
            manifest["size_bytes"] = parquet_path.stat().st_size
            self._write_manifest(manifest, manifest_path)
            missing_sessions = list(manifest["missing_sessions"])
            return AlpacaAcquisitionResult(
                frame=existing.sort_values("timestamp", kind="mergesort").reset_index(drop=True),
                manifest=manifest,
                parquet_path=parquet_path,
                manifest_path=manifest_path,
                cache_reused=True,
                requested_sessions=requested_sessions,
                missing_sessions=missing_sessions,
                missing_bar_count=int(manifest["missing_regular_session_bar_count"]),
            )

        fetched_parts = [
            self._download_time_range(request, missing_range.start, missing_range.end)
            for missing_range in missing_ranges
        ]
        nonempty_fetched_parts = [part for part in fetched_parts if not part.empty]
        fetched = (
            pd.concat(nonempty_fetched_parts, ignore_index=True)
            if nonempty_fetched_parts
            else _empty_bars_frame()
        )
        if existing.empty:
            merged = fetched
        elif fetched.empty:
            merged = existing
        else:
            merged = pd.concat([existing, fetched], ignore_index=True)
        merged, duplicate_count_before_deduplication = _deduplicate(merged)
        full_schedule = self._schedule_for_stored_frame(request, merged, schedule)
        regular_frame = _filter_regular_session(merged, full_schedule)
        out_of_session_bar_count = len(merged) - len(regular_frame)
        frame = _coverage_for_schedule(merged, full_schedule)
        requested_frame = _coverage_for_schedule(frame, schedule)
        duplicate_count_after_filter = int(frame["timestamp"].duplicated(keep=False).sum())
        newly_downloaded_sessions = sorted(
            {missing_range.session for missing_range in missing_ranges}
        )
        cache_status = "created" if existing.empty else "incremental_update"
        manifest = self._build_manifest(
            request=request,
            frame=frame,
            schedule=schedule,
            parquet_path=parquet_path,
            duplicate_timestamp_count=(
                duplicate_count_before_deduplication + duplicate_count_after_filter
            ),
            out_of_session_bar_count=out_of_session_bar_count,
            already_present_sessions=already_present_sessions,
            newly_downloaded_sessions=newly_downloaded_sessions,
            newly_downloaded_ranges=missing_ranges,
            cache_status=cache_status,
            cache_reused=False,
            previous_manifest=previous_manifest,
            request_frame_before_download=request_frame_before_download,
            request_frame_after_download=requested_frame,
        )
        self._write_parquet_and_manifest(frame, manifest, parquet_path, manifest_path)
        manifest["sha256"] = calculate_sha256(parquet_path)
        manifest["size_bytes"] = parquet_path.stat().st_size
        self._write_manifest(manifest, manifest_path)
        stored_frame = pd.read_parquet(parquet_path)
        stored_frame["timestamp"] = pd.to_datetime(stored_frame["timestamp"], utc=True)
        return AlpacaAcquisitionResult(
            frame=stored_frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True),
            manifest=manifest,
            parquet_path=parquet_path,
            manifest_path=manifest_path,
            cache_reused=False,
            requested_sessions=requested_sessions,
            missing_sessions=list(manifest["missing_sessions"]),
            missing_bar_count=int(manifest["missing_regular_session_bar_count"]),
        )

    def _read_existing_verified(
        self,
        *,
        request: AlpacaBarsRequest,
        parquet_path: Path,
        manifest_path: Path,
    ) -> tuple[pd.DataFrame, dict[str, Any] | None]:
        if not parquet_path.is_file():
            return _empty_bars_frame(), None
        if not manifest_path.is_file():
            raise AlpacaDataError(
                f"Canonical Alpaca Parquet exists without a manifest: {parquet_path}"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {
            "dataset_id": request.dataset_id,
            "provider": "alpaca",
            "feed": request.feed,
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "adjustment": request.adjustment,
        }
        for key, expected_value in expected.items():
            if manifest.get(key) != expected_value:
                raise AlpacaDataError(
                    f"Existing Alpaca manifest mismatch for {key}: "
                    f"expected {expected_value!r}, got {manifest.get(key)!r}"
                )
        actual_hash = calculate_sha256(parquet_path)
        if actual_hash != manifest.get("sha256"):
            raise AlpacaDataError(
                "Existing Alpaca Parquet SHA-256 does not match its manifest; "
                "refusing unsafe reuse or overwrite"
            )
        frame = pd.read_parquet(parquet_path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        return frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True), manifest

    def _read_existing_frame(self, parquet_path: Path) -> pd.DataFrame:
        if not parquet_path.is_file():
            return pd.DataFrame(columns=[*CANONICAL_COLUMNS, *OPTIONAL_ALPACA_COLUMNS])
        frame = pd.read_parquet(parquet_path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        return frame

    def _download_range(
        self,
        request: AlpacaBarsRequest,
        schedule: pd.DataFrame,
    ) -> pd.DataFrame:
        start = schedule["market_open"].iloc[0].tz_convert("UTC")
        end = schedule["market_close"].iloc[-1].tz_convert("UTC")
        return self._download_time_range(request, start, end)

    def _download_time_range(
        self,
        request: AlpacaBarsRequest,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> pd.DataFrame:
        bars: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            payload = self._request_page(
                request=request,
                start=start,
                end=end,
                page_token=page_token,
            )
            page_bars = payload.get("bars", [])
            if not isinstance(page_bars, list):
                raise AlpacaDataError("Alpaca bars response has an unexpected shape")
            bars.extend(page_bars)
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        return _bars_to_frame(bars)

    def _schedule_for_stored_frame(
        self,
        request: AlpacaBarsRequest,
        frame: pd.DataFrame,
        fallback_schedule: pd.DataFrame,
    ) -> pd.DataFrame:
        if frame.empty:
            return fallback_schedule
        timestamps = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
        calendar = mcal.get_calendar(request.exchange_calendar)
        return calendar.schedule(
            start_date=timestamps.min().tz_convert(request.market_timezone).date(),
            end_date=timestamps.max().tz_convert(request.market_timezone).date(),
        )

    def _request_page(
        self,
        *,
        request: AlpacaBarsRequest,
        start: pd.Timestamp,
        end: pd.Timestamp,
        page_token: str | None,
    ) -> dict[str, Any]:
        url = self.base_url + request.endpoint_path
        params: dict[str, Any] = {
            "timeframe": request.alpaca_timeframe,
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "feed": request.feed,
            "adjustment": request.adjustment,
            "limit": 10_000,
            "sort": "asc",
        }
        if page_token:
            params["page_token"] = page_token
        headers = {
            "APCA-API-KEY-ID": self.credentials.key_id,
            "APCA-API-SECRET-KEY": self.credentials.secret_key,
        }
        for attempt in range(self.max_retries + 1):
            response = self.client.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
            status_code = int(response.status_code)
            if status_code == 200:
                return response.json()
            if status_code not in {408, 429, 500, 502, 503, 504}:
                raise AlpacaDataError(self._format_error(response, status_code))
            if attempt >= self.max_retries:
                raise AlpacaDataError(self._format_error(response, status_code))
            time.sleep(self.backoff_seconds * (2**attempt))
        raise AlpacaDataError("Alpaca request retry loop ended unexpectedly")

    @staticmethod
    def _format_error(response: Any, status_code: int) -> str:
        code = None
        message = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                code = payload.get("code")
                message = payload.get("message")
        except Exception:
            message = getattr(response, "text", "")
        details = f"HTTP {status_code}"
        if code:
            details += f" code={code}"
        if message:
            details += f" message={message}"
        return f"Alpaca historical bars request failed: {details}"

    def _build_manifest(
        self,
        *,
        request: AlpacaBarsRequest,
        frame: pd.DataFrame,
        schedule: pd.DataFrame,
        parquet_path: Path,
        duplicate_timestamp_count: int,
        out_of_session_bar_count: int,
        already_present_sessions: list[str],
        newly_downloaded_sessions: list[str],
        newly_downloaded_ranges: list[MissingRange],
        cache_status: str,
        cache_reused: bool,
        previous_manifest: dict[str, Any] | None,
        request_frame_before_download: pd.DataFrame | None = None,
        request_frame_after_download: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        expected = expected_regular_minutes(schedule)
        actual = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
        requested_frame = _coverage_for_schedule(frame, schedule)
        requested_actual = pd.DatetimeIndex(
            pd.to_datetime(requested_frame["timestamp"], utc=True)
        )
        missing = expected.difference(requested_actual)
        missing_sessions: list[str] = []
        for session, row in schedule.iterrows():
            session_expected = expected[
                (expected >= row.market_open) & (expected < row.market_close)
            ]
            if len(session_expected.difference(requested_actual)) == len(
                session_expected
            ):
                missing_sessions.append(pd.Timestamp(session).date().isoformat())
        null_counts = _null_counts(frame)
        ohlc_violations = _count_ohlc_violations(frame)
        invalid_price_count = _count_invalid_prices(frame)
        negative_volume_count = _count_negative_volume(frame)
        row_count = len(frame)
        possible_minute_count = len(expected)
        observed_minute_count = len(requested_actual)
        absent_minute_count = len(missing)
        accepts_sparse_bars = bool(request.sparse_bar_policy)
        unexplained_provider_gap_count = (
            0 if accepts_sparse_bars and not missing_sessions else int(len(missing))
        )
        validation_status = (
            "validated"
            if (
                row_count > 0
                and not missing_sessions
                and (accepts_sparse_bars or len(missing) == 0)
                and duplicate_timestamp_count == 0
                and out_of_session_bar_count == 0
                and sum(null_counts.values()) == 0
                and invalid_price_count == 0
                and negative_volume_count == 0
                and ohlc_violations == 0
                and actual.is_monotonic_increasing
            )
            else "provisional"
        )
        earliest = actual.min().isoformat() if row_count else ""
        latest = actual.max().isoformat() if row_count else ""
        requested_first = (
            requested_actual.min().isoformat() if len(requested_actual) else ""
        )
        requested_last = (
            requested_actual.max().isoformat() if len(requested_actual) else ""
        )
        before_count = (
            len(request_frame_before_download)
            if request_frame_before_download is not None
            else len(requested_frame)
        )
        after_count = (
            len(request_frame_after_download)
            if request_frame_after_download is not None
            else len(requested_frame)
        )
        acquired = pd.Timestamp.now(tz=UTC).isoformat()
        latest_completed_session = pd.Timestamp(schedule.index[-1]).date().isoformat()
        latest_completed_session_close = schedule["market_close"].iloc[-1].isoformat()
        return {
            "dataset_id": request.dataset_id,
            "status": validation_status,
            "provider": "alpaca",
            "provider_display": "Alpaca",
            "feed": request.feed,
            "symbol": request.symbol,
            "asset_class": request.asset_class,
            "asset_type": request.asset_type,
            "timeframe": request.timeframe,
            "alpaca_timeframe": request.alpaca_timeframe,
            "format": "parquet",
            "canonical_relative_path": request.canonical_relative_path.as_posix(),
            "source_archive": "",
            "original_source_path": f"{ALPACA_DATA_HOST}{request.endpoint_path}",
            "sha256": "",
            "size_bytes": 0,
            "row_count": row_count,
            "earliest_timestamp": earliest,
            "latest_timestamp": latest,
            "full_stored_coverage": {
                "first_timestamp": earliest,
                "last_timestamp": latest,
                "row_count": row_count,
            },
            "timezone": "UTC",
            "market_timezone": request.market_timezone,
            "exchange_calendar": request.exchange_calendar,
            "session_policy": request.session_policy,
            "regular_session_policy": "include bars with timestamps >= market_open and < market_close",
            "adjustment": request.adjustment,
            "requested_coverage": {
                "completed_session_count": len(schedule),
                "sessions": _session_labels(schedule),
                "start": schedule["market_open"].iloc[0].isoformat(),
                "end": schedule["market_close"].iloc[-1].isoformat(),
                "first_timestamp": requested_first,
                "last_timestamp": requested_last,
                "row_count": len(requested_frame),
            },
            "current_acquisition_coverage": {
                "requested_sessions": _session_labels(schedule),
                "already_present_sessions": already_present_sessions,
                "newly_downloaded_sessions": newly_downloaded_sessions,
                "row_count_before_download": before_count,
                "row_count_after_download": after_count,
            },
            "newly_downloaded_coverage": {
                "sessions": newly_downloaded_sessions,
                "ranges": [
                    {
                        "session": missing_range.session,
                        "start": missing_range.start.isoformat(),
                        "end": missing_range.end.isoformat(),
                    }
                    for missing_range in newly_downloaded_ranges
                ],
            },
            "actual_coverage": {
                "first_timestamp": earliest,
                "last_timestamp": latest,
                "row_count": row_count,
            },
            "latest_completed_session": latest_completed_session,
            "latest_completed_session_close": latest_completed_session_close,
            "requested_sessions": _session_labels(schedule),
            "already_present_sessions": already_present_sessions,
            "newly_downloaded_sessions": newly_downloaded_sessions,
            "cache_reused": cache_reused,
            "cache_status": cache_status,
            "previous_manifest_sha256": (
                previous_manifest.get("sha256") if previous_manifest else ""
            ),
            "missing_sessions": missing_sessions,
            "missing_session_count": len(missing_sessions),
            "missing_regular_session_bar_count": int(len(missing)),
            "missing_regular_session_bar_examples": [
                timestamp.isoformat() for timestamp in missing[:10]
            ],
            "possible_regular_session_minute_count": possible_minute_count,
            "observed_regular_session_bar_count": observed_minute_count,
            "absent_regular_session_minute_count": absent_minute_count,
            "observed_regular_session_bar_ratio": (
                observed_minute_count / possible_minute_count
                if possible_minute_count
                else 0.0
            ),
            "accepted_sparse_bar_policy": request.sparse_bar_policy,
            "no_trade_minute_count": absent_minute_count if accepts_sparse_bars else 0,
            "provider_delivery_gap_count": unexplained_provider_gap_count,
            "absent_minute_classification": (
                "accepted_no_reported_iex_trade_minute"
                if accepts_sparse_bars
                else "missing_expected_bar"
            ),
            "synthetic_bar_count": 0,
            "duplicate_timestamp_count": int(duplicate_timestamp_count),
            "out_of_session_bar_count": int(out_of_session_bar_count),
            "invalid_price_count": invalid_price_count,
            "negative_volume_count": negative_volume_count,
            "invalid_bar_count": invalid_price_count + ohlc_violations,
            "null_counts": null_counts,
            "null_count": int(sum(null_counts.values())),
            "ohlc_violation_count": ohlc_violations,
            "monotonic_increasing": bool(actual.is_monotonic_increasing),
            "columns": list(frame.columns),
            "acquisition_timestamp": acquired,
            "imported_at_utc": acquired,
            "validated_by": "market_data.providers.alpaca.AlpacaHistoricalBarsProvider",
            "source": {
                "host": ALPACA_DATA_HOST,
                "endpoint_path": request.endpoint_path,
            },
            "coverage_start": request.coverage_start,
            "coverage_end_policy": request.coverage_end_policy,
            "fund_name": request.fund_name,
            "ticker_history": request.ticker_history or {},
            "corporate_action_policy": request.corporate_action_policy,
            "cache_policy": request.cache_policy,
            "sparse_bar_policy": request.sparse_bar_policy,
            "approved_uses": list(request.approved_uses),
            "restrictions": list(request.restrictions),
            "validation_notes": [],
            "local_canonical_path": request.canonical_relative_path.as_posix(),
        }

    def _write_parquet_and_manifest(
        self,
        frame: pd.DataFrame,
        manifest: dict[str, Any],
        parquet_path: Path,
        manifest_path: Path,
    ) -> None:
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = parquet_path.with_name(parquet_path.name + ".tmp.parquet")
        frame.to_parquet(tmp_path, index=False)
        tmp_path.replace(parquet_path)
        self._write_manifest(manifest, manifest_path)

    @staticmethod
    def _write_manifest(manifest: dict[str, Any], manifest_path: Path) -> None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = manifest_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(manifest, indent=2, default=_safe_json) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(manifest_path)


def manifest_sha256(manifest: dict[str, Any]) -> str:
    """Return a deterministic digest for manifest content in tests."""
    payload = json.dumps(manifest, sort_keys=True, default=_safe_json).encode("utf-8")
    return sha256(payload).hexdigest()
