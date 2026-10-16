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

Each incremental top-up re-fetches the whole most recent stored session, because
Alpaca fills late gaps and corrects bars there (15 Oct: a 74-minute hole in every
symbol, served later). Bars before that session are kept and must match byte-for-byte.
Missing regular-session minutes are listed in the manifest's ``validation_notes``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
from typing import Any

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

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
from market_data.providers.alpaca import ALPACA_DATA_HOST, AlpacaCredentials, fetch_alpaca_bars

FEED = "sip"
ADJUSTMENT = "split"
ALPACA_TIMEFRAME = "1Min"
DATA_DELAY = pd.Timedelta(minutes=20)
MARKET_TIMEZONE = "America/New_York"
EXCHANGE_CALENDAR = "NYSE"
SESSION_VALUES = ("pre", "regular", "post", "closed")
PRICE_COLUMNS = ("open", "high", "low", "close")
COLUMNS = ("timestamp", *PRICE_COLUMNS, "volume", "trade_count", "vwap", "session")
CREDENTIAL_VARIABLES = ("QF_ALPACA_API_KEY", "QF_ALPACA_SECRET_KEY")
OVERLAP_RELATIVE_TOLERANCE = 1e-6
GAP_NOTE_LIMIT = 20  # days listed in the manifest, as for suspect_bar_examples


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


def bars_to_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Give fetched bars the stored dtypes (without sessions)."""
    if raw.empty:
        return empty_frame().drop(columns=["session"])
    frame = raw.copy()
    frame["trade_count"] = pd.to_numeric(frame["trade_count"], errors="coerce").astype("Int64")
    return frame


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
    frame: pd.DataFrame,
    *,
    end: pd.Timestamp,
    previous: pd.DataFrame | None,
    notes: list[str] | None = None,
) -> list[str]:
    """Return every integrity problem; an empty list means the frame may be stored.

    ``notes`` (when given) collects findings that are reported but not fatal: missing
    regular-session minutes in the newly stored bars, which the next top-up re-fetches.
    """
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
    if notes is not None and not problems:
        kept = 0 if previous is None else len(previous)
        notes.extend(regular_session_gaps(frame.iloc[kept:], end=end))
    return problems


def regular_session_gaps(frame: pd.DataFrame, *, end: pd.Timestamp) -> list[str]:
    """Describe regular-session minutes the NYSE schedule expects but ``frame`` lacks."""
    if frame.empty:
        return []
    timestamps = frame["timestamp"]
    local_dates = timestamps.dt.tz_convert(MARKET_TIMEZONE).dt.date
    schedule = mcal.get_calendar(EXCHANGE_CALENDAR).schedule(
        start_date=local_dates.min(), end_date=local_dates.max()
    )
    if schedule.empty:
        return []
    expected = mcal.date_range(schedule, "1min", closed="left", force_close=False)  # bar opens
    expected = expected[(expected >= timestamps.iloc[0]) & (expected <= end)]
    missing = expected.difference(pd.DatetimeIndex(timestamps))
    if missing.empty:
        return []
    by_day = pd.Series(missing, index=missing.tz_convert(MARKET_TIMEZONE).date).groupby(level=0)
    notes = [
        f"regular-session gap: {len(group)} missing minutes on {day} "
        f"({group.iloc[0].isoformat()} to {group.iloc[-1].isoformat()})"
        for day, group in by_day
    ]
    if len(notes) > GAP_NOTE_LIMIT:
        notes = notes[:GAP_NOTE_LIMIT] + [f"... {len(notes) - GAP_NOTE_LIMIT} more days with gaps"]
    return [f"{len(missing)} regular-session minutes missing in the newly stored bars", *notes]


def last_session_start(timestamps: pd.Series) -> pd.Timestamp:
    """Start (market-time midnight, in UTC) of the exchange day holding the last stored bar."""
    return timestamps.iloc[-1].tz_convert(MARKET_TIMEZONE).normalize().tz_convert("UTC")


def ends_at_or_after(frame: pd.DataFrame, existing: pd.DataFrame) -> bool:
    """False when a re-fetch came back shorter than the store (never drop stored bars)."""
    return not frame.empty and frame["timestamp"].iloc[-1] >= existing["timestamp"].iloc[-1]


def same_bars(frame: pd.DataFrame, other: pd.DataFrame) -> bool:
    """True when both hold the same timestamps, prices and volumes."""
    keys = ["timestamp", *PRICE_COLUMNS, "volume"]
    return len(frame) == len(other) and bool(
        (frame[keys].to_numpy() == other[keys].to_numpy()).all()
    )


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


class AlpacaSipProvider:
    """Fetch, validate and store Alpaca SIP one-minute bars for one symbol at a time."""

    def __init__(
        self,
        *,
        credentials: AlpacaCredentials,
        locations: DataLocations,
        now: Callable[[], pd.Timestamp] = lambda: pd.Timestamp.now(tz=UTC),
        alpaca_data: Any = None,
    ) -> None:
        self.credentials = credentials
        self.locations = locations
        self.now = now
        self.alpaca_data = alpaca_data  # None means ``vbt.AlpacaData``; tests pass a fake

    def available_end(self) -> pd.Timestamp:
        """Timestamp of the last complete bar the free plan serves (now minus 20 minutes)."""
        return (self.now() - DATA_DELAY).floor("min") - pd.Timedelta(minutes=1)

    def fetch(self, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Download every bar in [start, end] via ``vbt.AlpacaData``, with sessions marked."""
        raw = fetch_alpaca_bars(
            self.credentials,
            symbol=symbol,
            start=start,
            end=end,
            feed=FEED,
            adjustment=ADJUSTMENT,
            error=AlpacaSipError,
            alpaca_data=self.alpaca_data,
        )
        return mark_sessions(bars_to_frame(raw))

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
        # The vendor fills late gaps and corrects bars in the most recent session, so that
        # whole session is re-fetched and replaces the stored one; every earlier bar is kept
        # and the prefix check proves it unchanged.
        start = existing["timestamp"].iloc[0]
        kept = existing.loc[existing["timestamp"] < last_session_start(existing["timestamp"])]
        if kept.empty:  # the store holds only that session: re-fetch all of it
            combined, previous = self.fetch(symbol, start, end), None
        else:
            # Re-fetch the last kept bar too: if its split-adjusted prices moved, a split
            # happened since the last run and every stored bar needs the new adjustment.
            anchor = kept.iloc[-1]
            fetched = self.fetch(symbol, anchor["timestamp"], end)
            if not _overlap_matches(anchor, fetched):
                refetched = self.fetch(symbol, start, end)
                return self._store(
                    dataset, refetched, None, "refetched_after_adjustment_change", start, end, slot
                )
            later = fetched.loc[fetched["timestamp"] > anchor["timestamp"]]
            combined, previous = pd.concat([kept, later], ignore_index=True), kept
        if not ends_at_or_after(combined, existing) or same_bars(combined, existing):
            return TopUpResult(symbol, "current", len(existing), 0, target)
        return self._store(
            dataset, combined, previous, "incremental", start, end, slot, stored_rows=len(existing)
        )

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
        stored_rows: int | None = None,
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
        notes: list[str] = []
        problems = validate_bars(on_disk, end=end, previous=previous, notes=notes)
        if problems:
            quarantined = self._quarantine(dataset, tmp_path, problems)
            raise AlpacaSipValidationError(
                f"{dataset.symbol}: validation failed ({'; '.join(problems)}); candidate "
                f"quarantined at {quarantined}; stored file left unchanged"
            )
        if stored_rows is None:
            stored_rows = 0 if previous is None else len(previous)
        new_rows = len(on_disk) - stored_rows
        os.replace(tmp_path, target)  # inactive slot: no committed manifest points here
        manifest = build_manifest(
            dataset, on_disk, target, slot, mode, start, end, new_rows, history_cut, notes
        )
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
    validation_notes: list[str] | None = None,
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
        # Reported, not fatal: vendor gaps in the newest session are re-fetched next run.
        "validation_notes": list(validation_notes or []),
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
