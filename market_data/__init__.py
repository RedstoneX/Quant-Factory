"""Reusable, audited market-data loading."""

from pathlib import Path

import pandas as pd

from market_data.cache import cache_compatibility, read_cache, write_cache
from market_data.catalog import (
    calculate_sha256,
    DataLocations,
    DatasetManifest,
    DatasetUnavailableError,
    load_data_locations,
    load_dataset_manifest,
    resolve_dataset_path,
    verify_dataset_file,
)
from market_data.calendars import (
    get_exchange_calendar,
    latest_completed_session,
    resolve_now,
)
from market_data.models import DataAudit, MarketDataConfig, MarketDataResult, OHLCV_COLUMNS
from market_data.validation import clean_and_validate_data, expected_session_gaps

AUDIT_FIELDS = tuple(DataAudit.__dataclass_fields__)


def download_yahoo_data(
    config: MarketDataConfig,
    completed_through: pd.Timestamp,
) -> tuple[pd.DataFrame, list[str]]:
    """Load the optional VectorBT Pro Yahoo provider only when it is used."""
    from market_data.providers.yahoo import download_yahoo_data as provider_download

    return provider_download(config, completed_through)


def _cache_display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _build_audit(
    frame: pd.DataFrame,
    config: MarketDataConfig,
    completed_through: pd.Timestamp,
    provider_warnings: list[str],
    cache_action: str,
    cache_decision_reason: str,
    download_time: pd.Timestamp,
    calendar=None,
) -> DataAudit:
    gaps = expected_session_gaps(frame, config=config, calendar=calendar)
    missing = frame.loc[:, list(OHLCV_COLUMNS)].isna().sum()
    latest_date = pd.Timestamp(completed_through).date()
    actual_last = frame.index[-1].date()
    warnings_out = list(provider_warnings)
    if actual_last < latest_date:
        warnings_out.append(
            "Provider availability lag: latest completed exchange session "
            f"{latest_date} was not returned; using {actual_last}."
        )
    return DataAudit(
        cache_schema_version=config.cache_schema_version,
        symbol=config.symbol,
        provider=config.provider,
        provider_implementation=config.provider_implementation,
        interval=config.interval,
        requested_start=config.requested_start,
        requested_dynamic_end_policy=config.end_date_policy,
        latest_completed_exchange_session=latest_date.isoformat(),
        prices_adjusted=config.adjusted,
        adjustment_verification=(
            "auto_adjust passed explicitly through vectorbtpro.YFData.pull "
            "to yfinance history"
        ),
        download_time=download_time.isoformat(),
        download_timezone=config.market_timezone,
        actual_first_row_date=frame.index[0].date().isoformat(),
        actual_last_row_date=actual_last.isoformat(),
        row_count=len(frame),
        duplicate_timestamp_count=int(frame.index.duplicated().sum()),
        missing_open_count=int(missing["Open"]),
        missing_high_count=int(missing["High"]),
        missing_low_count=int(missing["Low"]),
        missing_close_count=int(missing["Close"]),
        missing_volume_count=int(missing["Volume"]),
        expected_session_gap_count=len(gaps),
        unexpected_session_gaps=gaps,
        provider_warnings=warnings_out,
        cache_path=_cache_display_path(config.cache_path),
        cache_action=cache_action,
        cache_decision_reason=cache_decision_reason,
    )


def load_market_data(
    config: MarketDataConfig,
    now: pd.Timestamp | None = None,
    *,
    allow_download: bool = True,
) -> MarketDataResult:
    """Load clean market data from a compatible cache or supported provider."""
    if not isinstance(allow_download, bool):
        raise ValueError("allow_download must be a boolean")
    if config.provider == "Databento" and config.provider_implementation.startswith(
        "verified_local_catalog:"
    ):
        return _load_verified_catalog_data(config, now=now)
    if config.provider != "Yahoo Finance":
        raise ValueError(f"Unsupported market-data provider: {config.provider}")
    now = resolve_now(config, now)
    calendar = get_exchange_calendar(config)
    completed_through = latest_completed_session(config, now=now, calendar=calendar)
    cache_reason = "configured cache does not exist"
    cache_action = "created"

    if config.cache_path.is_file() and config.metadata_path.is_file():
        try:
            cached_frame, cached_audit = read_cache(config)
            compatible, cache_reason, cleaned = cache_compatibility(
                cached_frame,
                cached_audit,
                config=config,
                completed_through=completed_through,
                current_date=now.date(),
                calendar=calendar,
            )
        except Exception as exc:
            compatible = False
            cleaned = None
            cache_reason = f"cache read failed: {exc}"
        if compatible and cleaned is not None:
            audit = _build_audit(
                cleaned,
                config=config,
                completed_through=completed_through,
                provider_warnings=list(cached_audit.provider_warnings),
                cache_action="reused",
                cache_decision_reason=cache_reason,
                download_time=pd.Timestamp(cached_audit.download_time),
                calendar=calendar,
            )
            return MarketDataResult(data=cleaned, audit=audit)
        cache_action = "refreshed"
    elif any(path.is_file() for path in config.legacy_cache_paths):
        cache_action = "replaced"
        cache_reason = "legacy cache is incompatible with the active request"

    if not allow_download:
        raise DatasetUnavailableError(
            "no compatible local market-data cache is available and downloads are disabled: "
            f"{cache_reason}"
        )

    raw, provider_warnings = download_yahoo_data(config, completed_through)
    cleaned, _ = clean_and_validate_data(
        raw,
        config=config,
        completed_through=completed_through,
        current_date=now.date(),
        calendar=calendar,
    )
    audit = _build_audit(
        cleaned,
        config=config,
        completed_through=completed_through,
        provider_warnings=provider_warnings,
        cache_action=cache_action,
        cache_decision_reason=cache_reason,
        download_time=now,
        calendar=calendar,
    )
    write_cache(cleaned, audit, config)
    return MarketDataResult(data=cleaned, audit=audit)


def _load_verified_catalog_data(
    config: MarketDataConfig, *, now: pd.Timestamp | None
) -> MarketDataResult:
    """Read a fixed, validated local Databento slice without acquisition."""
    dataset_id = config.provider_implementation.removeprefix("verified_local_catalog:")
    locations = load_data_locations()
    manifest = load_dataset_manifest(dataset_id, locations.manifests)
    if (
        manifest.provider != config.provider
        or manifest.symbol != config.symbol
        or manifest.timeframe != config.interval
        or manifest.format.lower() != "parquet"
        or config.cache_path != manifest.canonical_relative_path
        or config.adjusted
    ):
        raise DatasetUnavailableError("Saved setup does not match the validated catalog identity")
    path = verify_dataset_file(manifest, locations)
    if not locations.verify_sha256_before_use and calculate_sha256(path) != manifest.sha256:
        raise DatasetUnavailableError("Verified catalog SHA-256 mismatch")
    start = pd.Timestamp(config.requested_start)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    if now is None:
        raise ValueError("The fixed catalog slice requires an explicit end boundary")
    end = pd.Timestamp(now)
    if end.tzinfo is None:
        raise ValueError("The fixed catalog end boundary must be timezone-aware")
    end = end.tz_convert("UTC")
    if end < start:
        raise ValueError("The fixed catalog end boundary precedes the start")
    first_available = pd.Timestamp(manifest.metadata["earliest_timestamp"])
    last_available = pd.Timestamp(manifest.metadata["latest_timestamp"])
    if start < first_available or end > last_available:
        raise DatasetUnavailableError("The requested fixed period exceeds verified catalog coverage")
    frame = pd.read_parquet(
        path,
        engine="pyarrow",
        columns=["open", "high", "low", "close", "volume", "ts_event"],
        filters=[
            ("ts_event", ">=", start.to_pydatetime()),
            ("ts_event", "<=", end.to_pydatetime()),
        ],
    )
    frame = frame.rename(columns=str.title)
    if frame.empty or set(frame.columns) != set(OHLCV_COLUMNS):
        raise DatasetUnavailableError("The verified catalog slice is empty or has invalid OHLCV fields")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise DatasetUnavailableError("The verified catalog timestamps are not timezone-aware")
    frame.index = frame.index.tz_convert("UTC")
    if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        raise DatasetUnavailableError("The verified catalog timestamps are not unique and ordered")
    missing = frame.loc[:, list(OHLCV_COLUMNS)].isna().sum()
    if missing.any():
        raise DatasetUnavailableError("The verified catalog slice contains missing OHLCV values")
    audit = DataAudit(
        cache_schema_version=config.cache_schema_version,
        symbol=config.symbol,
        provider=config.provider,
        provider_implementation=config.provider_implementation,
        interval=config.interval,
        requested_start=config.requested_start,
        requested_dynamic_end_policy=config.end_date_policy,
        latest_completed_exchange_session=end.date().isoformat(),
        prices_adjusted=False,
        adjustment_verification="validated catalog manifest; original unadjusted prices",
        download_time=str(manifest.metadata["imported_at_utc"]),
        download_timezone="UTC",
        actual_first_row_date=frame.index[0].date().isoformat(),
        actual_last_row_date=frame.index[-1].date().isoformat(),
        row_count=len(frame),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
        cache_path=str(path),
        cache_action="reused",
        cache_decision_reason=f"validated catalog file {dataset_id} verified before read",
        manifest_reference=f"data/manifests/{dataset_id}.json",
        checksum=manifest.sha256,
    )
    return MarketDataResult(data=frame, audit=audit)


def format_audit(audit: DataAudit) -> str:
    """Format a concise audit report for command-line runners."""
    lines = ["Dataset quality report:"]
    values = audit.to_dict()
    for field in AUDIT_FIELDS:
        value = values[field]
        if field in {"provider_warnings", "unexpected_session_gaps"} and not value:
            value = "None"
        lines.append(f"  {field}: {value}")
    return "\n".join(lines)


__all__ = [
    "DataLocations",
    "DataAudit",
    "DatasetManifest",
    "DatasetUnavailableError",
    "MarketDataConfig",
    "MarketDataResult",
    "format_audit",
    "load_data_locations",
    "load_dataset_manifest",
    "load_market_data",
    "resolve_dataset_path",
    "verify_dataset_file",
]
