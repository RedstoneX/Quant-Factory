"""Alpaca SIP one-minute bars: full-market history with validated incremental top-up.

Bars are split-adjusted, include pre- and post-market minutes, and carry a
``session`` column (pre / regular / post / closed) so the regular session can be
selected.

Each symbol has two data slots (``.a`` / ``.b``). A top-up writes the inactive
slot, reads it back and validates it, then atomically replaces the manifest that
points at it (with its sha256). That manifest rename is the single commit point,
so readers always see a data file and manifest that match, and the active slot is
never written. A failed candidate moves to quarantine and nothing is committed.
Manifests go to the persistent downloaded-manifest folder inside the data mount.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import requests

from market_data.alpaca_sip_universe import (
    HISTORY_START,
    SURVIVORSHIP_NOTE,
    UNIVERSE_AS_OF,
    UNIVERSE_NAME,
    asset_type,
    universe_group,
)
from market_data.bar_outliers import METHOD as SUSPECT_METHOD, flag_suspect_bars
from market_data.listing_gap import cut_at_last_listing_gap
from market_data.catalog import (
    DataLocations,
    DatasetManifest,
    DatasetUnavailableError,
    calculate_sha256,
    verify_dataset_file,
)
from market_data.providers.alpaca import ALPACA_DATA_HOST, AlpacaCredentials, HttpClient

FEED = "sip"
ADJUSTMENT = "split"
ALPACA_TIMEFRAME = "1Min"
PAGE_LIMIT = 10_000
MAX_REQUESTS_PER_MINUTE = 190  # Alpaca allows 200 per minute; keep a margin.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF_SECONDS = 60.0
DATA_DELAY = pd.Timedelta(minutes=20)
MARKET_TIMEZONE = "America/New_York"
EXCHANGE_CALENDAR = "NYSE"
SESSION_VALUES = ("pre", "regular", "post", "closed")
PRICE_COLUMNS = ("open", "high", "low", "close")
COLUMNS = ("timestamp", *PRICE_COLUMNS, "volume", "trade_count", "vwap", "session")
CREDENTIAL_VARIABLES = ("QF_ALPACA_API_KEY", "QF_ALPACA_SECRET_KEY")
OVERLAP_RELATIVE_TOLERANCE = 1e-6


class AlpacaSipError(RuntimeError):
    """Raised when SIP bars cannot be acquired safely."""


class AlpacaSipValidationError(AlpacaSipError):
    """Raised when a candidate file fails validation and was quarantined."""


def credentials_from_environment(environ: Mapping[str, str] | None = None) -> AlpacaCredentials:
    """Read the two Alpaca credentials from the environment, never echoing them."""
    values = os.environ if environ is None else environ
    missing = [name for name in CREDENTIAL_VARIABLES if not values.get(name, "").strip()]
    if missing:
        raise AlpacaSipError(
            "Missing Alpaca credentials: set " + " and ".join(missing) + " in the environment"
        )
    return AlpacaCredentials(
        key_id=values["QF_ALPACA_API_KEY"].strip(),
        secret_key=values["QF_ALPACA_SECRET_KEY"].strip(),
    )


class RequestThrottle:
    """Sliding one-minute window that keeps requests under the provider limit."""

    def __init__(
        self,
        max_per_minute: int = MAX_REQUESTS_PER_MINUTE,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_per_minute < 1:
            raise ValueError("max_per_minute must be at least 1")
        self.max_per_minute = max_per_minute
        self.clock = clock
        self.sleep = sleep
        self._sent: deque[float] = deque()

    def _expire(self, now: float) -> None:
        while self._sent and now - self._sent[0] >= 60.0:
            self._sent.popleft()

    def wait(self) -> None:
        now = self.clock()
        self._expire(now)
        if len(self._sent) >= self.max_per_minute:
            self.sleep(60.0 - (now - self._sent[0]))
            now = self.clock()
            self._expire(now)
        self._sent.append(now)


@dataclass(frozen=True)
class SipDataset:
    """Naming of one symbol's stored SIP file and manifest."""

    symbol: str

    @property
    def dataset_id(self) -> str:
        return f"equities_{self.symbol}_1m_alpaca_sip"

    def slot_relative_path(self, slot: str) -> Path:
        name = f"{self.symbol}_1m_alpaca_sip.{slot}.parquet"
        return Path("equities") / self.symbol / "1m" / name

    def manifest_path(self, locations: DataLocations) -> Path:
        return locations.downloaded_manifest_dir / f"{self.dataset_id}.json"


@dataclass(frozen=True)
class TopUpResult:
    symbol: str
    status: str  # full | incremental | refetched_after_adjustment_change | current
    row_count: int
    new_rows: int
    path: Path


def empty_frame() -> pd.DataFrame:
    frame = pd.DataFrame({column: pd.Series(dtype="float64") for column in COLUMNS})
    frame["timestamp"] = pd.Series(dtype="datetime64[ns, UTC]")
    frame["trade_count"] = pd.Series(dtype="Int64")
    frame["session"] = pd.Series(dtype="object")
    return frame


def _optional_column(raw: pd.DataFrame, key: str, dtype: str) -> pd.Series:
    if key not in raw.columns:
        return pd.Series(pd.NA, index=raw.index, dtype=dtype)
    return pd.to_numeric(raw[key], errors="coerce").astype(dtype)


def bars_to_frame(bars: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert Alpaca bar dicts to the stored column layout (without sessions)."""
    if not bars:
        return empty_frame().drop(columns=["session"])
    raw = pd.DataFrame(bars)
    missing = {"t", "o", "h", "l", "c", "v"}.difference(raw.columns)
    if missing:
        raise AlpacaSipError(f"Alpaca bars are missing field(s): {sorted(missing)}")
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(raw["t"], utc=True),
            "open": raw["o"].astype("float64"),
            "high": raw["h"].astype("float64"),
            "low": raw["l"].astype("float64"),
            "close": raw["c"].astype("float64"),
            "volume": raw["v"].astype("float64"),
            "trade_count": _optional_column(raw, "n", "Int64"),
            "vwap": _optional_column(raw, "vw", "float64"),
        }
    )


def mark_sessions(frame: pd.DataFrame) -> pd.DataFrame:
    """Label each bar pre / regular / post by the NYSE schedule (early closes included)."""
    frame = frame.copy()
    if frame.empty:
        frame["session"] = pd.Series(dtype="object")
        return frame
    timestamps = frame["timestamp"]
    local_dates = timestamps.dt.tz_convert(MARKET_TIMEZONE).dt.normalize().dt.tz_localize(None)
    schedule = mcal.get_calendar(EXCHANGE_CALENDAR).schedule(
        start_date=local_dates.min().date(), end_date=local_dates.max().date()
    )
    opens = local_dates.map(schedule["market_open"])
    closes = local_dates.map(schedule["market_close"])
    frame["session"] = np.select(
        [opens.isna(), timestamps < opens, timestamps < closes],
        ["closed", "pre", "regular"],
        default="post",
    ).astype(object)
    return frame


def validate_bars(
    frame: pd.DataFrame, *, end: pd.Timestamp, previous: pd.DataFrame | None
) -> list[str]:
    """Return every integrity problem; an empty list means the frame may be stored."""
    if list(frame.columns) != list(COLUMNS):
        return [f"columns {list(frame.columns)} differ from {list(COLUMNS)}"]
    if frame.empty:
        return ["no bars"]
    problems: list[str] = []
    required = ["timestamp", *PRICE_COLUMNS, "volume", "session"]
    null_counts = {column: int(frame[column].isna().sum()) for column in required}
    if any(null_counts.values()):
        problems.append(f"null values {null_counts}")
    prices = frame[list(PRICE_COLUMNS)]
    if int((prices <= 0).any(axis=1).sum()):
        problems.append("non-positive prices")
    ohlc_bad = (frame["high"] < prices.max(axis=1)) | (frame["low"] > prices.min(axis=1))
    if int(ohlc_bad.sum()):
        problems.append(f"{int(ohlc_bad.sum())} bars violate high/low bounds")
    if int((frame["volume"] < 0).sum()):
        problems.append("negative volume")
    timestamps = frame["timestamp"]
    if int(timestamps.duplicated().sum()):
        problems.append(f"{int(timestamps.duplicated().sum())} duplicate timestamps")
    if not timestamps.is_monotonic_increasing:
        problems.append("timestamps are not increasing")
    if int((timestamps != timestamps.dt.floor("min")).sum()):
        problems.append("timestamps not aligned to whole minutes")
    if timestamps.max() > end:
        problems.append(f"bar after the available-data end {end.isoformat()}")
    unknown = set(frame["session"].dropna().unique()).difference(SESSION_VALUES)
    if unknown:
        problems.append(f"unknown session labels {sorted(unknown)}")
    if previous is not None and not previous.empty:
        problems.extend(_prefix_problems(frame, previous))
    return problems


def _prefix_problems(frame: pd.DataFrame, previous: pd.DataFrame) -> list[str]:
    keys = ["timestamp", *PRICE_COLUMNS, "volume"]
    head = frame.iloc[: len(previous)][keys].reset_index(drop=True)
    if len(head) != len(previous) or not head.equals(previous[keys].reset_index(drop=True)):
        return ["previously stored bars changed during an incremental top-up"]
    return []


def _overlap_matches(stored_last: pd.Series, fetched: pd.DataFrame) -> bool:
    """True when the re-fetched last stored bar still has the stored prices."""
    if fetched.empty or fetched["timestamp"].iloc[0] != stored_last["timestamp"]:
        return False
    first = fetched.iloc[0]
    return all(
        np.isclose(first[column], stored_last[column], rtol=OVERLAP_RELATIVE_TOLERANCE, atol=0.0)
        for column in PRICE_COLUMNS
    )


def _describe_failure(response: Any, status_code: int) -> str:
    details = f"HTTP {status_code}"
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get("message"):
        details += f" message={payload['message']}"
    return f"Alpaca SIP bars request failed: {details}"


class AlpacaSipProvider:
    """Fetch, validate and store Alpaca SIP one-minute bars for one symbol at a time."""

    def __init__(
        self,
        *,
        credentials: AlpacaCredentials,
        locations: DataLocations,
        client: HttpClient | None = None,
        throttle: RequestThrottle | None = None,
        base_url: str = ALPACA_DATA_HOST,
        timeout: float = 60.0,
        max_retries: int = 5,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], pd.Timestamp] = lambda: pd.Timestamp.now(tz=UTC),
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.credentials = credentials
        self.locations = locations
        self.client = client or requests.Session()
        self.throttle = throttle or RequestThrottle()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.sleep = sleep
        self.now = now

    def available_end(self) -> pd.Timestamp:
        """Timestamp of the last complete bar the free plan serves (now minus 20 minutes)."""
        return (self.now() - DATA_DELAY).floor("min") - pd.Timedelta(minutes=1)

    def fetch(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Download every bar in [start, end], following page tokens, with sessions marked."""
        url = f"{self.base_url}/v2/stocks/{symbol}/bars"
        params: dict[str, Any] = {
            "timeframe": ALPACA_TIMEFRAME,
            "start": start.tz_convert(UTC).isoformat().replace("+00:00", "Z"),
            "end": end.tz_convert(UTC).isoformat().replace("+00:00", "Z"),
            "feed": FEED,
            "adjustment": ADJUSTMENT,
            "limit": PAGE_LIMIT,
            "sort": "asc",
        }
        pages: list[pd.DataFrame] = []
        while True:
            payload = self._get_page(url, params)
            bars = payload.get("bars") or []
            if not isinstance(bars, list):
                raise AlpacaSipError("Alpaca bars response has an unexpected shape")
            pages.append(bars_to_frame(bars))
            token = payload.get("next_page_token")
            if not token:
                break
            params = {**params, "page_token": token}
        frame = pd.concat(pages, ignore_index=True) if len(pages) > 1 else pages[0]
        return mark_sessions(frame.reset_index(drop=True))

    def _get_page(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "APCA-API-KEY-ID": self.credentials.key_id,
            "APCA-API-SECRET-KEY": self.credentials.secret_key,
        }
        for attempt in range(self.max_retries + 1):
            self.throttle.wait()
            try:
                response = self.client.get(url, headers=headers, params=params, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt >= self.max_retries:
                    raise AlpacaSipError(
                        f"Alpaca SIP bars request failed after retries: {type(exc).__name__}"
                    ) from exc
                self.sleep(self._backoff(attempt, None))
                continue
            status_code = int(response.status_code)
            if status_code == 200:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise AlpacaSipError("Alpaca bars response is not a JSON object")
                return payload
            if status_code not in RETRY_STATUSES or attempt >= self.max_retries:
                raise AlpacaSipError(_describe_failure(response, status_code))
            self.sleep(self._backoff(attempt, response))
        raise AlpacaSipError("Alpaca request retry loop ended unexpectedly")

    def _backoff(self, attempt: int, response: Any) -> float:
        headers = getattr(response, "headers", None) or {}
        retry_after = headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
        return min(self.backoff_seconds * (2**attempt), MAX_BACKOFF_SECONDS)

    def top_up(self, symbol: str, *, since: str = HISTORY_START) -> TopUpResult:
        """Bring one symbol's stored file up to the newest available complete bar."""
        dataset = SipDataset(symbol)
        asset_type(symbol)
        end = self.available_end()
        target, existing = self._committed(dataset)
        slot = "b" if target is not None and target.name.endswith(".a.parquet") else "a"
        if target is None or existing is None or existing.empty:
            start = pd.Timestamp(since, tz=MARKET_TIMEZONE)
            return self._store(dataset, self.fetch(symbol, start, end), None, "full", start, end, slot)
        last_stored = existing.iloc[-1]
        if last_stored["timestamp"] >= end:
            return TopUpResult(symbol, "current", len(existing), 0, target)
        # Re-fetch the last stored bar too: if its split-adjusted prices moved, a split
        # happened since the last run and every stored bar needs the new adjustment.
        fetched = self.fetch(symbol, last_stored["timestamp"], end)
        if not _overlap_matches(last_stored, fetched):
            start = existing["timestamp"].iloc[0]
            refetched = self.fetch(symbol, start, end)
            return self._store(
                dataset, refetched, None, "refetched_after_adjustment_change", start, end, slot
            )
        new_bars = fetched.loc[fetched["timestamp"] > last_stored["timestamp"]]
        if new_bars.empty:
            return TopUpResult(symbol, "current", len(existing), 0, target)
        combined = pd.concat([existing, new_bars], ignore_index=True)
        start = existing["timestamp"].iloc[0]
        return self._store(dataset, combined, existing, "incremental", start, end, slot)

    def _committed(self, dataset: SipDataset) -> tuple[Path | None, pd.DataFrame | None]:
        """Return the committed data file and its bars, verified against the manifest."""
        manifest_path = dataset.manifest_path(self.locations)
        if not manifest_path.is_file():
            return None, None
        try:
            manifest = DatasetManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
            path = verify_dataset_file(manifest, self.locations)
        except (DatasetUnavailableError, ValueError) as exc:
            raise AlpacaSipError(
                f"{dataset.symbol}: committed data does not match its manifest ({exc}); "
                "nothing written - inspect before re-running"
            ) from exc
        return path, pd.read_parquet(path)

    def _store(
        self,
        dataset: SipDataset,
        frame: pd.DataFrame,
        previous: pd.DataFrame | None,
        mode: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        slot: str,
    ) -> TopUpResult:
        frame, new_cut = cut_at_last_listing_gap(frame)
        earlier_cut = _stored_history_cut(dataset.manifest_path(self.locations))
        if new_cut is not None:
            previous = None  # the kept bars are not a continuation of the stored prefix
            if earlier_cut is not None:
                new_cut = {**new_cut, "discarded_from": earlier_cut["discarded_from"],
                           "discarded_rows": earlier_cut["discarded_rows"] + new_cut["discarded_rows"]}
        history_cut = new_cut or earlier_cut
        target = self.locations.root / dataset.slot_relative_path(slot)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(target.name + ".tmp")
        frame.loc[:, list(COLUMNS)].to_parquet(tmp_path, index=False)
        on_disk = pd.read_parquet(tmp_path)
        problems = validate_bars(on_disk, end=end, previous=previous)
        if problems:
            quarantined = self._quarantine(dataset, tmp_path, problems)
            raise AlpacaSipValidationError(
                f"{dataset.symbol}: validation failed ({'; '.join(problems)}); candidate "
                f"quarantined at {quarantined}; stored file left unchanged"
            )
        new_rows = len(on_disk) - (0 if previous is None else len(previous))
        os.replace(tmp_path, target)  # inactive slot: no committed manifest points here
        manifest = build_manifest(dataset, on_disk, target, slot, mode, start, end, new_rows, history_cut)
        write_manifest(manifest, dataset.manifest_path(self.locations))  # the commit
        return TopUpResult(dataset.symbol, mode, len(on_disk), new_rows, target)

    def _quarantine(self, dataset: SipDataset, tmp_path: Path, problems: list[str]) -> Path:
        folder = self.locations.quarantine / "alpaca_sip"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = folder / f"{dataset.dataset_id}_{stamp}.parquet"
        shutil.move(tmp_path, destination)
        note = {
            "dataset_id": dataset.dataset_id,
            "quarantined_at_utc": datetime.now(UTC).isoformat(),
            "problems": problems,
            "committed_data_and_manifest_unchanged": True,
        }
        destination.with_suffix(".json").write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")
        return destination


def build_manifest(
    dataset: SipDataset,
    frame: pd.DataFrame,
    parquet_path: Path,
    slot: str,
    mode: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    new_rows: int,
    history_cut: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe one validated stored file in the repository's manifest format."""
    acquired = datetime.now(UTC).isoformat()
    relative = dataset.slot_relative_path(slot).as_posix()
    first = frame["timestamp"].iloc[0].isoformat()
    last = frame["timestamp"].iloc[-1].isoformat()
    session_counts = {key: int(value) for key, value in frame["session"].value_counts().items()}
    suspect, suspect_counts = flag_suspect_bars(frame)
    suspect_examples = [stamp.isoformat() for stamp in frame.loc[suspect, "timestamp"].iloc[:20]]
    manifest: dict[str, Any] = {
        "dataset_id": dataset.dataset_id,
        "status": "validated",
        "provider": "alpaca",
        "provider_display": "Alpaca",
        "feed": FEED,
        "symbol": dataset.symbol,
        "asset_class": "equity",
        "asset_type": asset_type(dataset.symbol),
        "timeframe": "1m",
        "alpaca_timeframe": ALPACA_TIMEFRAME,
        "format": "parquet",
        "canonical_relative_path": relative,
        "local_canonical_path": relative,
        "storage_slot": slot,
        "storage_policy": "two slots (.a/.b); the manifest rename commits the new slot; "
        "resolve data by dataset_id, never by pinning the slot path",
        "original_source_path": f"{ALPACA_DATA_HOST}/v2/stocks/{dataset.symbol}/bars",
        "sha256": calculate_sha256(parquet_path),
        "size_bytes": parquet_path.stat().st_size,
        "row_count": int(len(frame)),
        "earliest_timestamp": first,
        "latest_timestamp": last,
        "full_stored_coverage": {"first_timestamp": first, "last_timestamp": last, "row_count": int(len(frame))},
        "requested_coverage": {"start": start.isoformat(), "end": end.isoformat()},
        # Later listings (e.g. SOFI, COIN, IBIT) simply start later; that is not a gap.
        "first_available_bar": first,
        "history_starts_after_requested_start": bool(frame["timestamp"].iloc[0] > start),
        "timezone": "UTC",
        "market_timezone": MARKET_TIMEZONE,
        "exchange_calendar": EXCHANGE_CALENDAR,
        "session_policy": "extended_hours_included",
        "session_column": "session",
        "timestamp_column": "timestamp",
        "session_values": list(SESSION_VALUES),
        "regular_session_policy": "session == 'regular': timestamps >= market_open and < market_close",
        "session_counts": session_counts,
        "adjustment": ADJUSTMENT,
        "columns": list(COLUMNS),
        "duplicate_timestamp_count": 0,
        "null_count": 0,
        "ohlc_violation_count": 0,
        "monotonic_increasing": True,
        "last_top_up": {"mode": mode, "new_rows": int(new_rows), "at_utc": acquired},
        "universe": {
            "name": UNIVERSE_NAME,
            "as_of": UNIVERSE_AS_OF,
            "group": universe_group(dataset.symbol),
            "survivorship_bias": SURVIVORSHIP_NOTE,
        },
        "acquisition_timestamp": acquired,
        "imported_at_utc": acquired,
        "validated_by": "market_data.providers.alpaca_sip.AlpacaSipProvider",
        "source": {"host": ALPACA_DATA_HOST, "endpoint_path": f"/v2/stocks/{dataset.symbol}/bars"},
        "approved_uses": ["one-minute US equity and ETF backtest research"],
        "restrictions": [
            "survivorship bias: universe is today's large-cap list, see universe.survivorship_bias",
            "split-adjusted only; dividends are not adjusted",
            "includes pre- and post-market bars; filter session == 'regular' for regular hours",
            "no trading-cost data attached",
        ],
        # Flagged, not fatal: spikes are listed here and dropped by the catalog loader, never edited.
        "suspect_bar_count": suspect_counts["any"],
        "suspect_bar_counts_by_column": {k: v for k, v in suspect_counts.items() if k != "any"},
        "suspect_bar_examples": suspect_examples,
        "suspect_bar_method": SUSPECT_METHOD,
        "validation_notes": [],
    }
    if history_cut is not None:  # ticker reuse: bars before the cut are a different security
        manifest["history_cut"] = history_cut
    return manifest


def _stored_history_cut(manifest_path: Path) -> dict[str, Any] | None:
    if not manifest_path.is_file():
        return None
    cut = json.loads(manifest_path.read_text(encoding="utf-8")).get("history_cut")
    return cut if isinstance(cut, dict) else None


def write_manifest(manifest: dict[str, Any], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = manifest_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(manifest_path)
