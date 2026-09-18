"""Typed configuration and results for reusable market-data loading."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
CACHE_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class MarketDataConfig:
    """Configuration for one daily market-data request."""

    symbol: str
    provider: str
    provider_implementation: str
    interval: str
    requested_start: str
    end_date_policy: str
    adjusted: bool
    exchange_calendar: str
    market_timezone: str
    cache_path: Path
    legacy_cache_paths: tuple[Path, ...] = ()
    cache_schema_version: int = CACHE_SCHEMA_VERSION

    @property
    def metadata_path(self) -> Path:
        return self.cache_path.with_suffix(".metadata.json")


@dataclass(frozen=True)
class DataAudit:
    """Auditable facts about a cleaned market-data result."""

    cache_schema_version: int
    symbol: str
    provider: str
    provider_implementation: str
    interval: str
    requested_start: str
    requested_dynamic_end_policy: str
    latest_completed_exchange_session: str
    prices_adjusted: bool
    adjustment_verification: str
    download_time: str
    download_timezone: str
    actual_first_row_date: str
    actual_last_row_date: str
    row_count: int
    duplicate_timestamp_count: int
    missing_open_count: int
    missing_high_count: int
    missing_low_count: int
    missing_close_count: int
    missing_volume_count: int
    expected_session_gap_count: int
    unexpected_session_gaps: list[str] = field(default_factory=list)
    provider_warnings: list[str] = field(default_factory=list)
    cache_path: str = ""
    cache_action: str = ""
    cache_decision_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "DataAudit":
        fields = cls.__dataclass_fields__
        return cls(**{key: value for key, value in values.items() if key in fields})


@dataclass(frozen=True)
class MarketDataResult:
    """Clean data and its audit report."""

    data: Any
    audit: DataAudit
