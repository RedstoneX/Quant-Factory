"""Durability coverage for the one-row Decision-296 SPYM screen."""

from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
import pandas_market_calendars as mcal
import pytest

from backtesting.run_spym_intraday_momentum import (
    DATASET_ID,
    EXPECTED_DATASET_ROWS,
    EXPECTED_DATASET_SHA256,
    EXPECTED_FIRST_TIMESTAMP,
    EXPECTED_LAST_TIMESTAMP,
    SPYMMomentumExecution,
    execute_spym_intraday_momentum,
)
from backtesting.run_spym_intraday_momentum_durable import run_durable_screening
from dashboard.run_detail_adapter import (
    RunDetailDashboardAdapter,
    _is_legacy_spym_fixture_notice,
    _persisted_annualization_notice,
    _screening_outcome_fields,
)
from market_data import DataAudit
from market_data.catalog import DatasetManifest
from persistence import PersistenceService, RunStatus


def _synthetic_sessions() -> pd.DataFrame:
    """The three boundary bars per NYSE session the rule reads, sized to Decision 296.

    One prior session supplies the first 15:59 close, then exactly 133 eligible sessions:
    the first 70 open higher (long), the remaining 63 open lower (short), and every
    session moves in the signalled direction by a varying amount so the daily returns
    are positive with non-zero dispersion.
    """
    days = mcal.get_calendar("NYSE").schedule(start_date=EXPECTED_FIRST_TIMESTAMP[:10], end_date=EXPECTED_LAST_TIMESTAMP[:10]).index[:134]

    def at(day: pd.Timestamp, wall_time: str) -> pd.Timestamp:
        return pd.Timestamp(f"{day.date()} {wall_time}", tz="America/New_York").tz_convert("UTC")

    previous_close = 100.0
    rows = [(at(days[0], "15:59"), previous_close, previous_close)]
    for number, day in enumerate(days[1:]):
        is_long = number < 70
        open_0959 = previous_close + (0.5 if is_long else -0.5)
        move = (0.5 + 0.1 * (number % 3)) * (1 if is_long else -1)
        rows += [(at(day, "09:59"), open_0959, open_0959), (at(day, "15:30"), open_0959, open_0959), (at(day, "15:59"), open_0959 + move, open_0959 + move)]
        previous_close = open_0959 + move
    index = pd.DatetimeIndex([row[0] for row in rows])
    opens = [row[1] for row in rows]
    closes = [row[2] for row in rows]
    return pd.DataFrame({"Open": opens, "High": [max(o, c) for o, c in zip(opens, closes)], "Low": [min(o, c) for o, c in zip(opens, closes)], "Close": closes}, index=index)


def _fixture() -> SPYMMomentumExecution:
    """The real loader's output shape with the approved dataset identity and synthetic bars."""
    data = _synthetic_sessions()
    index = data.index
    metadata = {
        "dataset_id": DATASET_ID, "dataset": "EQUS.MINI", "schema": "ohlcv-1m", "symbol": "SPYM",
        "coverage_start": "2025-10-31", "latest_completed_session": "2026-07-13",
        "earliest_timestamp": EXPECTED_FIRST_TIMESTAMP, "latest_timestamp": EXPECTED_LAST_TIMESTAMP,
        "observed_regular_session_bar_count": 53_528, "possible_regular_session_minute_count": 67_110,
        "missing_regular_session_bar_count": 13_582, "missing_session_count": 0, "synthetic_bar_count": 0,
    }
    manifest = DatasetManifest(dataset_id=DATASET_ID, status="validated", asset_class="equity", symbol="SPYM", provider="databento",
                               timeframe="1m", format="parquet", canonical_relative_path=Path("equities/SPYM/1m/SPYM.parquet"),
                               sha256=EXPECTED_DATASET_SHA256, size_bytes=1, row_count=EXPECTED_DATASET_ROWS, metadata=metadata)
    audit = DataAudit(cache_schema_version=2, symbol="SPYM", provider="Databento", provider_implementation="EQUS.MINI ohlcv-1m", interval="1m",
                      requested_start="2025-10-31", requested_dynamic_end_policy="fixed", latest_completed_exchange_session="2026-07-13",
                      prices_adjusted=False, adjustment_verification="raw", download_time="2026-09-20T00:00:00Z", download_timezone="UTC",
                      actual_first_row_date=index[0].isoformat(), actual_last_row_date=index[-1].isoformat(), row_count=EXPECTED_DATASET_ROWS,
                      duplicate_timestamp_count=0, missing_open_count=0, missing_high_count=0, missing_low_count=0, missing_close_count=0,
                      missing_volume_count=0, expected_session_gap_count=0, unexpected_session_gaps=[], provider_warnings=[], cache_path="fixture", cache_action="verified", cache_decision_reason="test")
    return SPYMMomentumExecution(data=data, audit=audit, manifest=manifest, dataset_path=Path("/tmp/SPYM.parquet"))


@pytest.mark.licensed_vectorbt
def test_durable_success_persists_one_dashboard_readable_row_and_integrity_manifest(tmp_path: Path) -> None:
    database = tmp_path / "state" / "screen.sqlite3"
    outcome = run_durable_screening(database=database, artifact_root=tmp_path, run_id="spym-success", loader=_fixture)

    assert outcome.exit_code == 0
    service = PersistenceService(database)
    try:
        assert service.runs.get("spym-success").status == RunStatus.SUCCEEDED
        assert len(service.results.list_parameter_results("spym-success")) == 1
        detail = service.run_detail("spym-success")
        assert detail["provenance"]["checksum"] == EXPECTED_DATASET_SHA256
        assert detail["execution_assumptions"]["assumptions_json"].find('"broker_orders":"disabled"') >= 0
        artifacts = service.retrieve_run_artifacts("spym-success", artifact_root=tmp_path)
        assert all(item.valid for item in artifacts.validations)
        assert {item.logical_name for item in artifacts.artifacts} == {"dataset_manifest", "equity_curve", "metrics", "parameter_results", "run_summary", "trades_and_orders", "validation_evidence"}
        base = tmp_path / "state" / "artifacts" / "spym-success"
        validation = json.loads((base / "validation_evidence.json").read_text())
        metrics = json.loads((base / "metrics.json").read_text())
        trades = json.loads((base / "trades_and_orders.json").read_text())
        assert validation["screening"] == {"evaluated_combinations": 1, "passed": 1, "screened_out": 0}
        assert validation["evidence_label"] == "source_defined_development_screen"
        assert validation["evidence_classification"]
        assert validation["max_drawdown_basis"] == "end-of-eligible-session strategy equity only"
        assert "Intraday equity path" in validation["max_drawdown_limitation"]
        assert (trades["instrument"], trades["price_unit"], trades["pnl_unit"]) == ("SPYM", "currency", "USD")
        assert len(trades["trades"]) == 133
        assert len(trades["orders"]) == 266
        database_metrics = json.loads(service.results.list_parameter_results("spym-success")[0].metrics_json)
        assert database_metrics["number_of_trades"] == metrics["metrics"]["number_of_trades"] == len(trades["trades"]) == 133
        assert "base price: observed current 15:30 Open" in trades["entry_price"]
        assert "fill applies 0.02% adverse slippage" in trades["exit_price"]
        view = RunDetailDashboardAdapter(database, artifact_root=tmp_path).selected_run_detail("spym-success")
        assert not any("ingestion and execution fixture" in notice for notice in view.evidence.notices)
        assert any("persisted 252 sessions/year" in notice for notice in view.evidence.notices)
    finally:
        service.close()


def test_metrics_artifact_annualization_notice() -> None:
    assert _persisted_annualization_notice(
        {
            "annualization": {
                "sessions_per_year": 252,
                "risk_free_rate": 0.0,
                "basis": "complete exchange-session-close portfolio equity and session returns",
            }
        }
    ) == (
        "Annualized return uses the persisted 252 sessions/year and 0 risk-free basis "
        "from complete exchange-session-close portfolio equity and session returns."
    )


def test_data_failure_marks_terminal_run_without_compute_or_success_evidence(tmp_path: Path) -> None:
    calls = []

    def loader():
        raise RuntimeError("checksum mismatch")

    def executor(*args):
        calls.append(args)
        raise AssertionError("must not execute")

    database = tmp_path / "state" / "failure.sqlite3"
    outcome = run_durable_screening(database=database, artifact_root=tmp_path, run_id="spym-data-failure", loader=loader, executor=executor)
    assert outcome.exit_code == 1 and calls == []
    service = PersistenceService(database)
    try:
        assert service.runs.get("spym-data-failure").status == RunStatus.FAILED
        assert service.results.list_parameter_results("spym-data-failure") == ()
        assert service.results.list_artifacts("spym-data-failure") == ()
    finally:
        service.close()


@pytest.mark.licensed_vectorbt
def test_durable_run_fails_before_artifacts_when_ranked_trade_metric_disagrees_with_ledger(tmp_path: Path) -> None:
    def mismatched_executor(data, audit):
        result, portfolio, bundle = execute_spym_intraday_momentum(data, audit)
        result.ranked_results.loc[0, "number_of_trades"] = 2
        result.passing_results.loc[0, "number_of_trades"] = 2
        return result, portfolio, bundle

    database = tmp_path / "state" / "trade-mismatch.sqlite3"
    outcome = run_durable_screening(database=database, artifact_root=tmp_path, run_id="spym-trade-mismatch", loader=_fixture, executor=mismatched_executor)
    assert outcome.exit_code == 1
    service = PersistenceService(database)
    try:
        assert service.runs.get("spym-trade-mismatch").status == RunStatus.FAILED
        assert service.results.list_parameter_results("spym-trade-mismatch") == ()
        assert service.results.list_artifacts("spym-trade-mismatch") == ()
    finally:
        service.close()


@pytest.mark.licensed_vectorbt
def test_artifact_write_failure_rolls_back_success_evidence(tmp_path: Path) -> None:
    database = tmp_path / "state" / "atomic.sqlite3"
    # A plain file where the artifact directory must be created makes the real staging write fail.
    database.parent.mkdir(parents=True)
    (tmp_path / "state" / "artifacts").write_bytes(b"not a directory")
    outcome = run_durable_screening(database=database, artifact_root=tmp_path, run_id="spym-atomic", loader=_fixture)
    assert outcome.exit_code == 1
    service = PersistenceService(database)
    try:
        assert service.runs.get("spym-atomic").status == RunStatus.FAILED
        assert service.results.list_parameter_results("spym-atomic") == ()
        assert service.results.get_data_provenance("spym-atomic") is None
        assert service.results.list_artifacts("spym-atomic") == ()
    finally:
        service.close()
    assert not (tmp_path / "state" / "artifacts" / "spym-atomic").exists()


def test_spym_fixture_notice_and_annualization_fallback_remain_legacy_safe() -> None:
    dataset = {"symbol": "SPYM"}
    assert _is_legacy_spym_fixture_notice({"strategy_id": "spym_rsi_mean_reversion_fixture"}, dataset, None)
    assert not _is_legacy_spym_fixture_notice({"strategy_id": "spym_intraday_momentum"}, dataset, None)
    assert _persisted_annualization_notice({"annualization": {"sessions_per_year": 252, "risk_free_rate": 0.0, "basis": "daily strategy equity"}}) == "Annualized return uses the persisted 252 sessions/year and 0 risk-free basis from daily strategy equity."
    assert _persisted_annualization_notice({}) is None
    screening = _screening_outcome_fields({
        "stage": "screening",
        "screening": {"evaluated_combinations": 1, "passed": 1, "screened_out": 0},
        "promotion_blockers": ["development only"],
        "protected_data_used": False,
        "evidence_label": "source_defined_development_screen",
    })
    fields = {field.label: field.value for field in screening}
    assert fields["Stage"] == "Screening"
    assert fields["Normalized status"] == "passed"
