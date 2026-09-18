"""Equity data-source contracts shared by acquisition and dashboard surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from market_data.catalog import DEFAULT_MANIFEST_DIR


class EquityDatasetUnsuitableError(RuntimeError):
    """Raised when a dataset cannot safely satisfy its equity contract."""


@dataclass(frozen=True)
class EquityDataSourceContract:
    contract_id: str
    symbol: str
    fund_name: str
    former_symbol: str
    symbol_effective_date: str
    provider: str
    dataset: str
    schema: str
    timeframe: str
    calendar: str
    market_timezone: str
    timestamp_timezone: str
    session_policy: str
    adjustment: str
    coverage_start: str
    coverage_end_policy: str
    dataset_id: str
    manifest_reference: str
    corporate_action_policy: str
    cache_policy: str


SPYM_EQUITY_DATA_CONTRACT = EquityDataSourceContract(
    contract_id="spym_equity_data_source.v1",
    symbol="SPYM",
    fund_name="State Street SPDR Portfolio S&P 500 ETF",
    former_symbol="SPLG",
    symbol_effective_date="2025-10-31",
    provider="databento",
    dataset="EQUS.MINI",
    schema="ohlcv-1m",
    timeframe="1m",
    calendar="NYSE",
    market_timezone="America/New_York",
    timestamp_timezone="UTC",
    session_policy="regular_trading_hours_only",
    adjustment="raw",
    coverage_start="2025-10-31",
    coverage_end_policy="latest_fully_completed_nyse_session",
    dataset_id="equities_SPYM_1m_databento_equs_mini",
    manifest_reference="data/manifests/equities_SPYM_1m_databento_equs_mini.json",
    corporate_action_policy=(
        "Preserve raw provider bars; record and review splits, cash dividends, "
        "and other corporate actions separately. Do not splice SPLG bars into "
        "SPYM history without a separately checksummed manifest and explicit lineage."
    ),
    cache_policy=(
        "Reuse only a checksum-matching manifest/cache pair; refresh missing completed "
        "NYSE sessions incrementally; never overwrite an unverifiable cache."
    ),
)


def spym_databento_request():
    """Build the approved Databento acquisition request for SPYM."""
    from market_data.providers.databento import DatabentoOhlcvRequest

    return DatabentoOhlcvRequest(
        symbol=SPYM_EQUITY_DATA_CONTRACT.symbol,
        dataset=SPYM_EQUITY_DATA_CONTRACT.dataset,
        schema=SPYM_EQUITY_DATA_CONTRACT.schema,
        stype_in="raw_symbol",
        asset_class="equity",
        asset_type="ETF",
        timeframe=SPYM_EQUITY_DATA_CONTRACT.timeframe,
        exchange_calendar=SPYM_EQUITY_DATA_CONTRACT.calendar,
        market_timezone=SPYM_EQUITY_DATA_CONTRACT.market_timezone,
        session_policy=SPYM_EQUITY_DATA_CONTRACT.session_policy,
        adjustment=SPYM_EQUITY_DATA_CONTRACT.adjustment,
        dataset_id=SPYM_EQUITY_DATA_CONTRACT.dataset_id,
        filename="SPYM_1m_databento_equs_mini.parquet",
        coverage_start=SPYM_EQUITY_DATA_CONTRACT.coverage_start,
        coverage_end_policy=SPYM_EQUITY_DATA_CONTRACT.coverage_end_policy,
        fund_name=SPYM_EQUITY_DATA_CONTRACT.fund_name,
        ticker_history={
            "former_symbol": SPYM_EQUITY_DATA_CONTRACT.former_symbol,
            "current_symbol": SPYM_EQUITY_DATA_CONTRACT.symbol,
            "effective_date": SPYM_EQUITY_DATA_CONTRACT.symbol_effective_date,
        },
        corporate_action_policy=SPYM_EQUITY_DATA_CONTRACT.corporate_action_policy,
        cache_policy=SPYM_EQUITY_DATA_CONTRACT.cache_policy,
        approved_uses=(
            "Milestone 21 SPYM operational equity data fixture after explicit "
            "Databento EQUS.MINI entitlement, cost, and ticker-history review",
        ),
        restrictions=(
            "Databento EQUS.MINI only; do not substitute another feed silently",
            "regular trading hours only",
            "raw adjustment setting",
            "SPYM history only; do not splice SPLG bars into this dataset",
        ),
    )


def validate_spym_manifest(manifest: Mapping[str, Any]) -> None:
    """Fail closed unless a manifest proves the complete SPYM contract."""
    contract = SPYM_EQUITY_DATA_CONTRACT
    expected = {
        "dataset_id": contract.dataset_id,
        "status": "validated",
        "asset_class": "equity",
        "asset_type": "ETF",
        "symbol": contract.symbol,
        "provider": contract.provider,
        "dataset": contract.dataset,
        "schema": contract.schema,
        "timeframe": contract.timeframe,
        "exchange_calendar": contract.calendar,
        "market_timezone": contract.market_timezone,
        "timezone": contract.timestamp_timezone,
        "session_policy": contract.session_policy,
        "adjustment": contract.adjustment,
    }
    failures = [
        f"{key} must be {value!r}"
        for key, value in expected.items()
        if manifest.get(key) != value
    ]
    digest = str(manifest.get("sha256", ""))
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        failures.append("sha256 must be a lowercase 64-character digest")
    if int(manifest.get("row_count", 0)) <= 0:
        failures.append("row_count must be positive")
    zero_fields = (
        "duplicate_timestamp_count",
        "missing_session_count",
        "out_of_session_bar_count",
        "invalid_bar_count",
        "null_count",
        "ohlc_violation_count",
        "negative_volume_count",
        "synthetic_bar_count",
    )
    for field in zero_fields:
        if manifest.get(field) != 0:
            failures.append(f"{field} must be recorded as zero")
    observed = int(manifest.get("observed_regular_session_bar_count", 0))
    possible = int(manifest.get("possible_regular_session_minute_count", 0))
    missing_bars = int(manifest.get("missing_regular_session_bar_count", -1))
    if observed <= 0 or possible <= 0 or observed > possible:
        failures.append("observed/possible minute coverage is invalid")
    if missing_bars != possible - observed:
        failures.append("missing minute count must equal possible minus observed bars")
    if manifest.get("monotonic_increasing") is not True:
        failures.append("timestamps must be monotonic increasing")
    earliest = str(manifest.get("earliest_timestamp", ""))
    if not earliest.startswith(contract.coverage_start):
        failures.append(f"coverage must begin on {contract.coverage_start}")
    if manifest.get("coverage_end_policy") != contract.coverage_end_policy:
        failures.append("coverage end policy is not the approved bounded policy")
    if manifest.get("corporate_action_policy") != contract.corporate_action_policy:
        failures.append("corporate-action policy is missing or mismatched")
    if manifest.get("ticker_history") != {
        "former_symbol": contract.former_symbol,
        "current_symbol": contract.symbol,
        "effective_date": contract.symbol_effective_date,
    }:
        failures.append("ticker history is missing or mismatched")
    requested = manifest.get("requested_coverage")
    if not isinstance(requested, Mapping):
        failures.append("requested coverage is missing")
    else:
        sessions = requested.get("sessions")
        if not isinstance(sessions, list) or not sessions:
            failures.append("requested sessions must be non-empty")
        elif sessions[0] != contract.coverage_start:
            failures.append(f"requested sessions must begin on {contract.coverage_start}")
        if requested.get("end") != manifest.get("latest_completed_session_close"):
            failures.append("manifest must identify the latest completed session close")
    if manifest.get("latest_completed_session") not in manifest.get(
        "requested_sessions", []
    ):
        failures.append("latest completed session is not in requested sessions")
    symbol_resolution = manifest.get("symbol_resolution")
    if not isinstance(symbol_resolution, Mapping):
        failures.append("Databento symbol resolution is missing")
    else:
        entries = symbol_resolution.get("result", {}).get(contract.symbol, [])
        if not entries:
            failures.append("Databento symbol resolution did not recognize SPYM")
    if failures:
        raise EquityDatasetUnsuitableError("; ".join(failures))


def load_spym_manifest(
    manifest_dir: Path = DEFAULT_MANIFEST_DIR,
) -> Mapping[str, Any] | None:
    """Load the committed SPYM manifest for fail-closed dashboard health."""
    path = manifest_dir / f"{SPYM_EQUITY_DATA_CONTRACT.dataset_id}.json"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def spym_dashboard_health(manifest: Mapping[str, Any] | None) -> dict[str, str]:
    """Return stable provider and dataset fields for dashboard presentation."""
    contract = SPYM_EQUITY_DATA_CONTRACT
    base = {
        "instrument": f"{contract.symbol} · {contract.fund_name}",
        "ticker_history": f"{contract.former_symbol} → {contract.symbol} on {contract.symbol_effective_date}",
        "provider": "Databento",
        "feed": "EQUS.MINI · consolidated/aggregated U.S. equity feed",
        "schema": contract.schema,
        "timeframe": contract.timeframe,
        "calendar_session": "NYSE · regular session only",
        "timestamps": "UTC",
        "prices": "Raw; corporate actions reviewed separately",
        "dataset_id": contract.dataset_id,
        "manifest": contract.manifest_reference,
    }
    if manifest is None:
        return {
            **base,
            "provider_status": "selected",
            "dataset_status": "unavailable",
            "validation_state": "fail_closed",
        }
    try:
        validate_spym_manifest(manifest)
    except EquityDatasetUnsuitableError as exc:
        return {
            **base,
            "provider_status": "selected",
            "dataset_status": "unsuitable",
            "validation_state": f"fail_closed: {exc}",
        }
    return {
        **base,
        "provider_status": "selected",
        "dataset_status": "validated",
        "validation_state": "suitable",
    }
