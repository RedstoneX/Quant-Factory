"""Deterministic Milestone 21A SPYM equity contract tests."""

from dataclasses import asdict

import pytest

import dashboard.app as dashboard_app
from market_data.equity_contract import (
    EquityDatasetUnsuitableError,
    SPYM_EQUITY_DATA_CONTRACT,
    load_spym_manifest,
    spym_databento_request,
    spym_dashboard_health,
    validate_spym_manifest,
)


def _manifest() -> dict[str, object]:
    contract = SPYM_EQUITY_DATA_CONTRACT
    return {
        "dataset_id": contract.dataset_id,
        "status": "validated",
        "asset_class": "equity",
        "asset_type": "ETF",
        "symbol": "SPYM",
        "provider": "databento",
        "dataset": "EQUS.MINI",
        "schema": "ohlcv-1m",
        "timeframe": "1m",
        "exchange_calendar": "NYSE",
        "market_timezone": "America/New_York",
        "timezone": "UTC",
        "session_policy": "regular_trading_hours_only",
        "adjustment": "raw",
        "sha256": "a" * 64,
        "row_count": 390,
        "duplicate_timestamp_count": 0,
        "missing_session_count": 0,
        "missing_regular_session_bar_count": 0,
        "possible_regular_session_minute_count": 390,
        "observed_regular_session_bar_count": 390,
        "out_of_session_bar_count": 0,
        "invalid_bar_count": 0,
        "null_count": 0,
        "ohlc_violation_count": 0,
        "negative_volume_count": 0,
        "synthetic_bar_count": 0,
        "monotonic_increasing": True,
        "earliest_timestamp": "2025-10-31T13:30:00+00:00",
        "requested_coverage": {
            "sessions": ["2025-10-31"],
            "end": "2025-10-31T20:00:00+00:00",
        },
        "requested_sessions": ["2025-10-31"],
        "latest_completed_session": "2025-10-31",
        "latest_completed_session_close": "2025-10-31T20:00:00+00:00",
        "coverage_end_policy": contract.coverage_end_policy,
        "corporate_action_policy": contract.corporate_action_policy,
        "ticker_history": {
            "former_symbol": "SPLG",
            "current_symbol": "SPYM",
            "effective_date": "2025-10-31",
        },
        "symbol_resolution": {
            "result": {"SPYM": [{"d0": "2025-10-31", "d1": "2025-10-31", "s": "19482"}]},
            "partial": [],
            "not_found": [],
        },
    }


def test_contract_identity_and_reusable_databento_request() -> None:
    contract = asdict(SPYM_EQUITY_DATA_CONTRACT)
    assert contract["former_symbol"] == "SPLG"
    assert contract["coverage_start"] == "2025-10-31"
    request = spym_databento_request()
    assert (request.symbol, request.dataset, request.schema) == (
        "SPYM",
        "EQUS.MINI",
        "ohlcv-1m",
    )
    assert request.adjustment == "raw"
    assert request.canonical_relative_path.as_posix() == (
        "equities/SPYM/1m/SPYM_1m_databento_equs_mini.parquet"
    )


def test_valid_manifest_is_suitable_and_dashboard_ready() -> None:
    manifest = _manifest()
    validate_spym_manifest(manifest)
    health = spym_dashboard_health(manifest)
    assert health["dataset_status"] == "validated"
    assert health["validation_state"] == "suitable"


def test_load_spym_manifest_returns_none_when_missing(tmp_path) -> None:
    assert load_spym_manifest(tmp_path) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataset", "IEXG.TOPS"),
        ("adjustment", "all"),
        ("missing_session_count", 1),
        ("out_of_session_bar_count", None),
        ("sha256", "bad"),
        ("synthetic_bar_count", 1),
    ],
)
def test_manifest_fails_closed_for_unsuitable_data(field: str, value: object) -> None:
    manifest = _manifest()
    manifest[field] = value
    with pytest.raises(EquityDatasetUnsuitableError):
        validate_spym_manifest(manifest)
    assert spym_dashboard_health(manifest)["dataset_status"] == "unsuitable"


def test_system_page_exposes_pending_provider_and_dataset_health(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_app, "load_spym_manifest", lambda: None)
    page = dashboard_app._system_page()
    rendered = str(page)
    assert "SPYM equity data contract" in rendered
    assert "EQUS.MINI" in rendered
    assert "fail_closed" in rendered


def test_system_page_exposes_validated_spym_manifest(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_app, "load_spym_manifest", _manifest)
    rendered = str(dashboard_app._system_page())
    assert "validated" in rendered
    assert "suitable" in rendered
