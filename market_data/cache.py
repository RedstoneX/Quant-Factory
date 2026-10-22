"""Local cache persistence and compatibility validation."""

import json

import pandas as pd

from market_data.models import DataAudit, MarketDataConfig
from market_data.validation import clean_and_validate_data


def read_cache(config: MarketDataConfig) -> tuple[pd.DataFrame, DataAudit]:
    frame = pd.read_csv(config.cache_path, index_col=0)
    values = json.loads(config.metadata_path.read_text(encoding="utf-8"))
    return frame, DataAudit.from_dict(values)


def cache_compatibility(
    frame: pd.DataFrame,
    audit: DataAudit,
    config: MarketDataConfig,
    completed_through: pd.Timestamp,
    current_date,
    calendar=None,
) -> tuple[bool, str, pd.DataFrame | None]:
    expected = {
        "cache_schema_version": config.cache_schema_version,
        "symbol": config.symbol,
        "provider": config.provider,
        "provider_implementation": config.provider_implementation,
        "interval": config.interval,
        "requested_start": config.requested_start,
        "prices_adjusted": config.adjusted,
    }
    values = audit.to_dict()
    for key, expected_value in expected.items():
        if values.get(key) != expected_value:
            return False, f"cache metadata mismatch for {key}", None
    try:
        cleaned, _ = clean_and_validate_data(
            frame,
            config=config,
            completed_through=completed_through,
            current_date=current_date,
            calendar=calendar,
        )
    except Exception as exc:
        return False, f"cache integrity validation failed: {exc}", None
    cached_last = cleaned.index[-1].date()
    required_last = pd.Timestamp(completed_through).date()
    if cached_last != required_last:
        return (
            False,
            f"cache ends {cached_last}, latest completed session is {required_last}",
            None,
        )
    return True, "cache configuration, integrity, and coverage are current", cleaned


def write_cache(
    frame: pd.DataFrame,
    audit: DataAudit,
    config: MarketDataConfig,
) -> None:
    config.cache_path.parent.mkdir(parents=True, exist_ok=True)
    csv_tmp = config.cache_path.with_suffix(".csv.tmp")
    metadata_tmp = config.metadata_path.with_suffix(".json.tmp")
    frame.to_csv(csv_tmp)
    metadata_tmp.write_text(
        json.dumps(audit.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    csv_tmp.replace(config.cache_path)
    metadata_tmp.replace(config.metadata_path)
