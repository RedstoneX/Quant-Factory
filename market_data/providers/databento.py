"""Databento historical OHLCV acquisition for cataloged datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import pandas_market_calendars as mcal

from market_data.catalog import DataLocations, calculate_sha256

DATABENTO_PROVIDER = "databento"
SPYM_DATABENTO_DATASET = "EQUS.MINI"
SPYM_DATABENTO_SCHEMA = "ohlcv-1m"


class DatabentoDataError(RuntimeError):
    """Raised when Databento data cannot be acquired or validated safely."""


class DatabentoHistoricalClient(Protocol):
    """Small Databento client surface used by acquisition and tests."""

    metadata: Any
    symbology: Any
    timeseries: Any


@dataclass(frozen=True)
class DatabentoOhlcvRequest:
    """Configuration for one controlled Databento OHLCV dataset."""

    symbol: str
    dataset: str
    schema: str
    stype_in: str
    asset_class: str
    asset_type: str
    timeframe: str
    exchange_calendar: str
    market_timezone: str
    session_policy: str
    adjustment: str
    coverage_start: str
    coverage_end_policy: str
    dataset_id: str
    filename: str
    fund_name: str
    ticker_history: dict[str, str]
    corporate_action_policy: str
    cache_policy: str
    approved_uses: tuple[str, ...]
    restrictions: tuple[str, ...]

    @property
    def canonical_relative_path(self) -> Path:
        return Path("equities") / self.symbol / self.timeframe / self.filename


@dataclass(frozen=True)
class DatabentoAcquisitionResult:
    """Result of one Databento acquisition or cache reuse."""

    frame: pd.DataFrame
    manifest: dict[str, Any]
    parquet_path: Path
    manifest_path: Path
    cache_reused: bool
    estimated_cost_usd: float


def completed_sessions_from_start(
    request: DatabentoOhlcvRequest,
    *,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return completed exchange sessions from the request's start date."""
    current = pd.Timestamp.now(tz=request.market_timezone) if now is None else pd.Timestamp(now)
    if current.tzinfo is None:
        current = current.tz_localize(request.market_timezone)
    current_utc = current.tz_convert("UTC")
    calendar = mcal.get_calendar(request.exchange_calendar)
    schedule = calendar.schedule(
        start_date=pd.Timestamp(request.coverage_start).date(),
        end_date=current.date(),
    )
    completed = schedule.loc[schedule["market_close"] <= current_utc]
    if completed.empty:
        raise DatabentoDataError(
            f"No fully completed {request.exchange_calendar} sessions are available "
            f"from {request.coverage_start}"
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


def _safe_json(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])


def _normalize_databento_frame(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return _empty_frame()
    frame = raw.reset_index()
    timestamp_column = next(
        (
            column
            for column in ("ts_event", "timestamp", "index")
            if column in frame.columns
        ),
        None,
    )
    if timestamp_column is None:
        raise DatabentoDataError(
            "Databento OHLCV frame has no recognizable timestamp column"
        )
    rename = {timestamp_column: "timestamp"}
    if "Open" in frame.columns:
        rename.update(
            {
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
    frame = frame.rename(columns=rename)
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DatabentoDataError(
            "Databento OHLCV frame is missing required column(s): "
            + ", ".join(missing)
        )
    frame = frame.loc[:, required].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)


def _coverage_for_schedule(frame: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    masks = []
    for row in schedule.itertuples():
        masks.append((timestamps >= row.market_open) & (timestamps < row.market_close))
    if not masks:
        return frame.iloc[0:0].copy()
    keep = masks[0]
    for mask in masks[1:]:
        keep = keep | mask
    expected = expected_regular_minutes(schedule)
    filtered = frame.loc[keep].copy()
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
    return int((pd.to_numeric(frame["volume"], errors="coerce") < 0).sum())


def _null_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {column: int(frame[column].isna().sum()) for column in frame.columns}


def _missing_sessions(
    frame: pd.DataFrame,
    schedule: pd.DataFrame,
) -> list[str]:
    actual = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    missing: list[str] = []
    for session_label, row in schedule.iterrows():
        session_expected = pd.date_range(
            start=row.market_open,
            end=row.market_close,
            freq="1min",
            inclusive="left",
        )
        if len(session_expected.intersection(actual)) == 0:
            missing.append(pd.Timestamp(session_label).date().isoformat())
    return missing


def manifest_sha256(manifest: dict[str, Any]) -> str:
    """Return a deterministic digest for manifest content in tests."""
    payload = json.dumps(manifest, sort_keys=True, default=_safe_json).encode("utf-8")
    return sha256(payload).hexdigest()


class DatabentoOhlcvProvider:
    """Download, validate, store, and manifest Databento OHLCV bars."""

    def __init__(
        self,
        *,
        client: DatabentoHistoricalClient,
        locations: DataLocations,
    ) -> None:
        self.client = client
        self.locations = locations

    def estimate_cost(
        self,
        request: DatabentoOhlcvRequest,
        *,
        schedule: pd.DataFrame,
    ) -> float:
        """Return Databento's current cost estimate for the request."""
        return float(
            self.client.metadata.get_cost(
                dataset=request.dataset,
                symbols=[request.symbol],
                schema=request.schema,
                stype_in=request.stype_in,
                start=schedule["market_open"].iloc[0].isoformat(),
                end=schedule["market_close"].iloc[-1].isoformat(),
            )
        )

    def acquire_from_start(
        self,
        request: DatabentoOhlcvRequest,
        *,
        now: pd.Timestamp | None = None,
        repo_manifest_dir: Path,
        max_cost_usd: float = 1.0,
    ) -> DatabentoAcquisitionResult:
        """Acquire completed sessions from the contract start date."""
        schedule = completed_sessions_from_start(request, now=now)
        estimated_cost = self.estimate_cost(request, schedule=schedule)
        if estimated_cost >= max_cost_usd:
            raise DatabentoDataError(
                f"Estimated Databento cost ${estimated_cost:.6f} exceeds "
                f"the ${max_cost_usd:.2f} limit"
            )
        parquet_path = self.locations.root / request.canonical_relative_path
        manifest_path = repo_manifest_dir / f"{request.dataset_id}.json"
        existing, previous_manifest = self._read_existing_verified(
            request=request,
            parquet_path=parquet_path,
            manifest_path=manifest_path,
        )
        if self._covers_schedule(existing, schedule):
            manifest = self._build_manifest(
                request=request,
                frame=existing,
                schedule=schedule,
                parquet_path=parquet_path,
                estimated_cost_usd=estimated_cost,
                cache_status="full_reuse",
                cache_reused=True,
                previous_manifest=previous_manifest,
            )
            manifest["sha256"] = calculate_sha256(parquet_path)
            manifest["size_bytes"] = parquet_path.stat().st_size
            self._write_manifest(manifest, manifest_path)
            return DatabentoAcquisitionResult(
                frame=existing,
                manifest=manifest,
                parquet_path=parquet_path,
                manifest_path=manifest_path,
                cache_reused=True,
                estimated_cost_usd=estimated_cost,
            )

        raw_store = self.client.timeseries.get_range(
            dataset=request.dataset,
            symbols=[request.symbol],
            schema=request.schema,
            stype_in=request.stype_in,
            start=schedule["market_open"].iloc[0].isoformat(),
            end=schedule["market_close"].iloc[-1].isoformat(),
        )
        raw_frame = raw_store.to_df(price_type="float", pretty_ts=True, map_symbols=True)
        frame = _coverage_for_schedule(_normalize_databento_frame(raw_frame), schedule)
        manifest = self._build_manifest(
            request=request,
            frame=frame,
            schedule=schedule,
            parquet_path=parquet_path,
            estimated_cost_usd=estimated_cost,
            cache_status="created" if existing.empty else "refreshed",
            cache_reused=False,
            previous_manifest=previous_manifest,
        )
        self._write_parquet_and_manifest(frame, manifest, parquet_path, manifest_path)
        manifest["sha256"] = calculate_sha256(parquet_path)
        manifest["size_bytes"] = parquet_path.stat().st_size
        self._write_manifest(manifest, manifest_path)
        stored = pd.read_parquet(parquet_path)
        stored["timestamp"] = pd.to_datetime(stored["timestamp"], utc=True)
        return DatabentoAcquisitionResult(
            frame=stored.sort_values("timestamp", kind="mergesort").reset_index(drop=True),
            manifest=manifest,
            parquet_path=parquet_path,
            manifest_path=manifest_path,
            cache_reused=False,
            estimated_cost_usd=estimated_cost,
        )

    def _read_existing_verified(
        self,
        *,
        request: DatabentoOhlcvRequest,
        parquet_path: Path,
        manifest_path: Path,
    ) -> tuple[pd.DataFrame, dict[str, Any] | None]:
        if not parquet_path.is_file():
            return _empty_frame(), None
        if not manifest_path.is_file():
            raise DatabentoDataError(
                f"Canonical Databento Parquet exists without a manifest: {parquet_path}"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {
            "dataset_id": request.dataset_id,
            "provider": DATABENTO_PROVIDER,
            "dataset": request.dataset,
            "schema": request.schema,
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "adjustment": request.adjustment,
        }
        for key, expected_value in expected.items():
            if manifest.get(key) != expected_value:
                raise DatabentoDataError(
                    f"Existing Databento manifest mismatch for {key}: "
                    f"expected {expected_value!r}, got {manifest.get(key)!r}"
                )
        actual_hash = calculate_sha256(parquet_path)
        if actual_hash != manifest.get("sha256"):
            raise DatabentoDataError(
                "Existing Databento Parquet SHA-256 does not match its manifest; "
                "refusing unsafe reuse or overwrite"
            )
        frame = pd.read_parquet(parquet_path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        return frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True), manifest

    def _covers_schedule(self, frame: pd.DataFrame, schedule: pd.DataFrame) -> bool:
        if frame.empty:
            return False
        missing = _missing_sessions(frame, schedule)
        return not missing

    def _resolve_symbol(
        self,
        request: DatabentoOhlcvRequest,
        schedule: pd.DataFrame,
    ) -> dict[str, Any]:
        return self.client.symbology.resolve(
            dataset=request.dataset,
            symbols=[request.symbol],
            stype_in=request.stype_in,
            stype_out="instrument_id",
            start_date=pd.Timestamp(schedule.index[0]).date().isoformat(),
            end_date=pd.Timestamp(schedule.index[-1]).date().isoformat(),
        )

    def _build_manifest(
        self,
        *,
        request: DatabentoOhlcvRequest,
        frame: pd.DataFrame,
        schedule: pd.DataFrame,
        parquet_path: Path,
        estimated_cost_usd: float,
        cache_status: str,
        cache_reused: bool,
        previous_manifest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        expected = expected_regular_minutes(schedule)
        actual = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
        missing = expected.difference(actual)
        missing_sessions = _missing_sessions(frame, schedule)
        null_counts = _null_counts(frame)
        duplicate_count = int(frame["timestamp"].duplicated(keep=False).sum())
        invalid_price_count = _count_invalid_prices(frame)
        negative_volume_count = _count_negative_volume(frame)
        ohlc_violations = _count_ohlc_violations(frame)
        symbol_resolution = self._resolve_symbol(request, schedule)
        symbol_entries = []
        if isinstance(symbol_resolution, dict):
            symbol_entries = symbol_resolution.get("result", {}).get(request.symbol, [])
        row_count = len(frame)
        validation_status = (
            "validated"
            if (
                row_count > 0
                and not missing_sessions
                and duplicate_count == 0
                and sum(null_counts.values()) == 0
                and invalid_price_count == 0
                and negative_volume_count == 0
                and ohlc_violations == 0
                and actual.is_monotonic_increasing
                and bool(symbol_entries)
            )
            else "provisional"
        )
        earliest = actual.min().isoformat() if row_count else ""
        latest = actual.max().isoformat() if row_count else ""
        acquired = pd.Timestamp.now(tz=UTC).isoformat()
        possible_count = len(expected)
        observed_count = row_count
        return {
            "dataset_id": request.dataset_id,
            "status": validation_status,
            "provider": DATABENTO_PROVIDER,
            "provider_display": "Databento",
            "dataset": request.dataset,
            "schema": request.schema,
            "symbol": request.symbol,
            "stype_in": request.stype_in,
            "asset_class": request.asset_class,
            "asset_type": request.asset_type,
            "timeframe": request.timeframe,
            "format": "parquet",
            "canonical_relative_path": request.canonical_relative_path.as_posix(),
            "source_archive": "",
            "original_source_path": "Databento Historical API /timeseries.get_range",
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
            "regular_session_policy": "store bars with timestamps >= market_open and < market_close",
            "adjustment": request.adjustment,
            "requested_coverage": {
                "completed_session_count": len(schedule),
                "sessions": _session_labels(schedule),
                "start": schedule["market_open"].iloc[0].isoformat(),
                "end": schedule["market_close"].iloc[-1].isoformat(),
                "first_timestamp": earliest,
                "last_timestamp": latest,
                "row_count": row_count,
            },
            "actual_coverage": {
                "first_timestamp": earliest,
                "last_timestamp": latest,
                "row_count": row_count,
            },
            "latest_completed_session": pd.Timestamp(schedule.index[-1]).date().isoformat(),
            "latest_completed_session_close": schedule["market_close"].iloc[-1].isoformat(),
            "requested_sessions": _session_labels(schedule),
            "cache_reused": cache_reused,
            "cache_status": cache_status,
            "previous_manifest_sha256": (
                previous_manifest.get("sha256") if previous_manifest else ""
            ),
            "estimated_cost_usd": estimated_cost_usd,
            "actual_cost_usd": estimated_cost_usd,
            "missing_sessions": missing_sessions,
            "missing_session_count": len(missing_sessions),
            "missing_regular_session_bar_count": int(len(missing)),
            "missing_regular_session_bar_examples": [
                timestamp.isoformat() for timestamp in missing[:10]
            ],
            "possible_regular_session_minute_count": possible_count,
            "observed_regular_session_bar_count": observed_count,
            "absent_regular_session_minute_count": int(len(missing)),
            "observed_regular_session_bar_ratio": (
                observed_count / possible_count if possible_count else 0.0
            ),
            "synthetic_bar_count": 0,
            "duplicate_timestamp_count": duplicate_count,
            "out_of_session_bar_count": 0,
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
            "validated_by": "market_data.providers.databento.DatabentoOhlcvProvider",
            "source": {
                "dataset": request.dataset,
                "schema": request.schema,
                "api": "Databento Historical /timeseries.get_range",
            },
            "symbol_resolution": symbol_resolution,
            "coverage_start": request.coverage_start,
            "coverage_end_policy": request.coverage_end_policy,
            "fund_name": request.fund_name,
            "ticker_history": request.ticker_history,
            "corporate_action_policy": request.corporate_action_policy,
            "cache_policy": request.cache_policy,
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
