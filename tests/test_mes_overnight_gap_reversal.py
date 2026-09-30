"""Decisive portable tests for the fixed R11 MES gap screen."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import backtesting.run_mes_overnight_gap_reversal as runner
from backtesting.screening import screen_metrics
from market_data import DataAudit
from market_data.catalog import DataLocations, DatasetManifest
from strategies import get_strategy
from strategies.mes_overnight_gap_reversal import (
    DEVELOPMENT_SESSION_END,
    DEVELOPMENT_SESSION_START,
    FEE_PER_SIDE,
    MESMappingInterval,
    generate_mes_overnight_gap_reversal_bundle,
    mes_mapping_checksum,
    normalize_mes_mapping,
)


def _time(day: str, wall_time: str) -> pd.Timestamp:
    return pd.Timestamp(f"{day} {wall_time}", tz="America/New_York").tz_convert("UTC")


def _schedule(*days: str) -> pd.DataFrame:
    return pd.DataFrame(index=pd.DatetimeIndex(days))


def _row(price: float) -> dict[str, float]:
    return {
        "Open": price,
        "High": price + 0.5,
        "Low": price - 0.5,
        "Close": price,
        "Volume": 10.0,
    }


def _data() -> pd.DataFrame:
    days = ("2023-12-20", "2023-12-21", "2023-12-22", "2023-12-26")
    rows: dict[pd.Timestamp, dict[str, float]] = {}
    for day in days:
        for wall_time in ("09:30", "09:35", "09:40", "09:45", "09:50", "09:55", "10:00", "15:55"):
            rows[_time(day, wall_time)] = _row(100.0)
    rows[_time("2023-12-21", "09:30")]["Open"] = 102.0
    rows[_time("2023-12-21", "09:35")]["Open"] = 101.0
    rows[_time("2023-12-21", "10:00")]["Open"] = 100.0
    rows[_time("2023-12-22", "09:30")]["Open"] = 98.0
    rows[_time("2023-12-22", "09:35")]["Open"] = 99.0
    rows[_time("2023-12-22", "10:00")]["Open"] = 100.0
    frame = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    frame.index = pd.DatetimeIndex(frame.index)
    return frame


def _mapping() -> tuple[MESMappingInterval, ...]:
    return (
        MESMappingInterval(
            DEVELOPMENT_SESSION_START,
            DEVELOPMENT_SESSION_END + timedelta(days=1),
            "12345",
        ),
    )


def _audit() -> DataAudit:
    data = _data()
    return DataAudit(
        cache_schema_version=1,
        symbol="MES",
        provider="Databento",
        provider_implementation="fixture",
        interval="5m",
        requested_start="2019-05-06T00:00:00+00:00",
        requested_dynamic_end_policy="fixed",
        latest_completed_exchange_session="2023-12-29",
        prices_adjusted=False,
        adjustment_verification="raw",
        download_time="2026-07-07T00:00:00+00:00",
        download_timezone="UTC",
        actual_first_row_date=data.index[0].isoformat(),
        actual_last_row_date=data.index[-1].isoformat(),
        row_count=len(data),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
        unexpected_session_gaps=[],
        provider_warnings=[],
        cache_path="fixture",
        cache_action="verified",
        cache_decision_reason="test",
    )


def _mapping_response(*, partial=None, not_found=None, message="OK"):
    return {
        "result": {
            "MES.c.0": [
                {"d0": "2019-05-06", "d1": "2022-01-01", "s": "111"},
                {"d0": "2022-01-01", "d1": "2023-12-30", "s": "222"},
            ]
        },
        "symbols": ["MES.c.0"],
        "partial": [] if partial is None else partial,
        "not_found": [] if not_found is None else not_found,
        "message": message,
        "status": 0,
    }


def _portfolio(bundle, *, pnl_offset: float = 0.0):
    trade_rows = []
    order_rows = []
    for trade in bundle.completed_trades:
        trade_rows.append(
            {
                "Size": 1.0,
                "Avg Entry Price": trade.entry_fill * 5.0,
                "Avg Exit Price": trade.exit_fill * 5.0,
                "Entry Index": trade.entry_timestamp,
                "Exit Index": trade.exit_timestamp,
                "PnL": trade.net_pnl + pnl_offset,
                "Entry Fees": FEE_PER_SIDE,
                "Exit Fees": FEE_PER_SIDE,
                "Status": "Closed",
                "Direction": trade.direction.title(),
            }
        )
        order_rows.extend(
            [
                {
                    "Fill Index": trade.entry_timestamp,
                    "Size": 1.0,
                    "Price": trade.entry_fill * 5.0,
                    "Fees": FEE_PER_SIDE,
                    "Side": "Buy" if trade.direction == "long" else "Sell",
                },
                {
                    "Fill Index": trade.exit_timestamp,
                    "Size": 1.0,
                    "Price": trade.exit_fill * 5.0,
                    "Fees": FEE_PER_SIDE,
                    "Side": "Sell" if trade.direction == "long" else "Buy",
                },
            ]
        )
    return SimpleNamespace(
        trades=SimpleNamespace(records_readable=pd.DataFrame(trade_rows)),
        orders=SimpleNamespace(records_readable=pd.DataFrame(order_rows)),
        value=pd.Series(
            [100_000.0, 100_000.0 + sum(item.net_pnl for item in bundle.completed_trades)]
        ),
    )


def test_strategy_is_registered_as_fixed_owner_approved_candidate() -> None:
    strategy = get_strategy("mes_overnight_gap_reversal")
    assert strategy.spec.approval_state == "approved"
    assert strategy.spec.parameters == ()
    assert strategy.validate_parameters({}) == {}
    with pytest.raises(ValueError, match="no tunable parameters"):
        strategy.validate_parameters({"threshold": 1})


def test_mapping_normalization_requires_complete_ok_response_and_stable_checksum() -> None:
    first = normalize_mes_mapping(_mapping_response())
    reordered = _mapping_response()
    reordered["result"]["MES.c.0"].reverse()
    second = normalize_mes_mapping(reordered)

    assert first == second
    assert len(first) == 2
    assert mes_mapping_checksum(first) == mes_mapping_checksum(second)
    assert len(mes_mapping_checksum(first)) == 64
    assert runner.market_data_identity()["symbology_request"]["end_date"] == "2023-12-30"
    with pytest.raises(ValueError, match="partial"):
        normalize_mes_mapping(_mapping_response(partial=["MES.c.0"]))
    with pytest.raises(ValueError, match="not-found"):
        normalize_mes_mapping(_mapping_response(not_found=["MES.c.0"]))
    with pytest.raises(ValueError, match="status 0 and message OK"):
        normalize_mes_mapping(_mapping_response(message="Partial"))
    invalid_id = _mapping_response()
    invalid_id["result"]["MES.c.0"][0]["s"] = None
    with pytest.raises(ValueError, match="invalid instrument ID"):
        normalize_mes_mapping(invalid_id)


def test_mapping_normalization_rejects_gaps_overlaps_and_short_coverage() -> None:
    response = _mapping_response()
    response["result"]["MES.c.0"][1]["d0"] = "2022-01-02"
    with pytest.raises(ValueError, match="incomplete calendar coverage"):
        normalize_mes_mapping(response)

    response = _mapping_response()
    response["result"]["MES.c.0"][1]["d0"] = "2021-12-31"
    with pytest.raises(ValueError, match="overlap"):
        normalize_mes_mapping(response)

    response = _mapping_response()
    response["result"]["MES.c.0"][0]["d0"] = "2019-05-07"
    with pytest.raises(ValueError, match="development boundary"):
        normalize_mes_mapping(response)


def test_session_classifier_preserves_positive_negative_zero_and_exact_costs() -> None:
    data = _data()
    schedule = _schedule("2023-12-20", "2023-12-21", "2023-12-22", "2023-12-26")
    bundle = generate_mes_overnight_gap_reversal_bundle(
        data, mapping_intervals=_mapping(), schedule=schedule
    )

    assert [item.direction for item in bundle.completed_trades] == ["short", "long"]
    short, long = bundle.completed_trades
    assert (short.entry_fill, short.exit_fill) == (100.75, 100.25)
    assert (long.entry_fill, long.exit_fill) == (99.25, 99.75)
    assert short.net_pnl == pytest.approx(1.26)
    assert long.net_pnl == pytest.approx(1.26)
    assert bundle.signals.short_entries.at[_time("2023-12-21", "09:35")]
    assert bundle.signals.short_exits.at[_time("2023-12-21", "10:00")]
    assert bundle.signals.entries.at[_time("2023-12-22", "09:35")]
    assert bundle.signals.exits.at[_time("2023-12-22", "10:00")]
    assert bundle.signals.metadata["exclusion_reason_counts"] == {
        "missing_prior_session_boundary": 1,
        "zero_gap": 1,
    }
    assert bundle.daily_net_pnl.tolist() == pytest.approx([0.0, 1.26, 1.26, 0.0])


def test_roll_boundary_excludes_before_gap_and_missing_or_invalid_bar_stays_flat() -> None:
    data = _data()
    schedule = _schedule("2023-12-20", "2023-12-21", "2023-12-22", "2023-12-26")
    mapping = (
        MESMappingInterval(DEVELOPMENT_SESSION_START, pd.Timestamp("2023-12-22").date(), "old"),
        MESMappingInterval(
            pd.Timestamp("2023-12-22").date(),
            DEVELOPMENT_SESSION_END + timedelta(days=1),
            "new",
        ),
    )
    bundle = generate_mes_overnight_gap_reversal_bundle(
        data, mapping_intervals=mapping, schedule=schedule
    )
    assert [item.direction for item in bundle.completed_trades] == ["short"]
    assert any(item["reason"] == "roll_mapping_boundary" for item in bundle.excluded_sessions)
    assert bundle.daily_net_pnl.iloc[2] == 0.0

    missing = data.drop(index=_time("2023-12-21", "09:45"))
    missing_bundle = generate_mes_overnight_gap_reversal_bundle(
        missing, mapping_intervals=_mapping(), schedule=schedule
    )
    assert missing_bundle.excluded_sessions[1]["reason"] == "missing_required_boundary_bar"
    invalid = data.copy()
    invalid.at[_time("2023-12-21", "09:50"), "Volume"] = -1
    invalid_bundle = generate_mes_overnight_gap_reversal_bundle(
        invalid, mapping_intervals=_mapping(), schedule=schedule
    )
    assert invalid_bundle.excluded_sessions[1]["reason"] == "invalid_required_boundary_bar"


def test_session_after_nyse_early_close_is_explicitly_excluded() -> None:
    data = _data()
    schedule = _schedule("2023-12-20", "2023-12-21")
    schedule["market_close"] = pd.DatetimeIndex(
        ["2023-12-20T18:00:00Z", "2023-12-21T21:00:00Z"]
    )
    bundle = generate_mes_overnight_gap_reversal_bundle(
        data,
        mapping_intervals=_mapping(),
        schedule=schedule,
    )

    assert bundle.excluded_sessions[-1] == {
        "session_date": "2023-12-21",
        "reason": "prior_session_early_close",
        "prior_session_date": "2023-12-20",
    }


def test_predicate_loader_materializes_only_fixed_pre_2024_slice(monkeypatch, tmp_path: Path) -> None:
    metadata = {
        "dataset_id": runner.DATASET_ID,
        "status": "validated",
        "sha256": runner.EXPECTED_DATASET_SHA256,
        "row_count": runner.EXPECTED_DATASET_ROWS,
        "earliest_timestamp": runner.EXPECTED_FIRST_TIMESTAMP,
        "latest_timestamp": runner.EXPECTED_LAST_TIMESTAMP,
        "continuous_symbol": "MES.c.0",
        "roll_rule": "calendar/front-expiry rank zero",
        "price_adjustment": "none; original unadjusted contract prices",
        "imported_at_utc": "2026-07-07T00:00:00Z",
    }
    manifest = DatasetManifest(
        dataset_id=runner.DATASET_ID,
        status="validated",
        asset_class="futures",
        symbol="MES",
        provider="Databento",
        timeframe="5m",
        format="parquet",
        canonical_relative_path=Path("futures/MES/5m/MES.parquet"),
        sha256=runner.EXPECTED_DATASET_SHA256,
        size_bytes=1,
        row_count=runner.EXPECTED_DATASET_ROWS,
        metadata=metadata,
    )
    locations = DataLocations(
        root=tmp_path,
        manifests=tmp_path,
        quarantine=tmp_path,
        backup_archive=None,
        extracted_root=None,
        verify_sha256_before_use=True,
    )
    captured = {}

    def read_parquet(path, *, engine, columns, filters):
        captured.update(path=path, engine=engine, columns=columns, filters=filters)
        return pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.5],
                "volume": [1, 2],
                "ts_event": pd.DatetimeIndex(
                    ["2019-05-06T00:00:00Z", "2023-12-29T23:55:00Z"]
                ),
            }
        )

    monkeypatch.setattr(runner, "load_dataset_manifest", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(runner, "load_data_locations", lambda *args, **kwargs: locations)
    monkeypatch.setattr(runner, "verify_dataset_file", lambda *args, **kwargs: tmp_path / "MES.parquet")
    monkeypatch.setattr(pd, "read_parquet", read_parquet)
    loaded = runner.load_mes_gap_inputs(mapping_response=_mapping_response())

    assert loaded.data.index.min() == runner.DEVELOPMENT_START
    assert loaded.data.index.max() < runner.DEVELOPMENT_END
    assert captured["engine"] == "pyarrow"
    assert captured["columns"][-1] == "ts_event"
    assert captured["filters"] == [
        ("ts_event", ">=", runner.DEVELOPMENT_START.to_pydatetime()),
        ("ts_event", "<", runner.DEVELOPMENT_END.to_pydatetime()),
    ]


def test_loader_rejects_any_materialized_row_at_the_prospective_cutoff(monkeypatch, tmp_path: Path) -> None:
    manifest = SimpleNamespace(
        metadata={
            "dataset_id": runner.DATASET_ID,
            "status": "validated",
            "sha256": runner.EXPECTED_DATASET_SHA256,
            "row_count": runner.EXPECTED_DATASET_ROWS,
            "earliest_timestamp": runner.EXPECTED_FIRST_TIMESTAMP,
            "latest_timestamp": runner.EXPECTED_LAST_TIMESTAMP,
            "continuous_symbol": "MES.c.0",
            "roll_rule": "calendar/front-expiry rank zero",
            "price_adjustment": "none; original unadjusted contract prices",
            "imported_at_utc": "2026-07-07T00:00:00Z",
        },
        canonical_relative_path=Path("MES.parquet"),
        sha256=runner.EXPECTED_DATASET_SHA256,
    )
    monkeypatch.setattr(runner, "load_dataset_manifest", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(runner, "load_data_locations", lambda *args, **kwargs: object())
    monkeypatch.setattr(runner, "verify_dataset_file", lambda *args, **kwargs: tmp_path / "MES.parquet")
    frame = pd.DataFrame(
        {
            "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
            "volume": [1], "ts_event": pd.DatetimeIndex([runner.DEVELOPMENT_END]),
        }
    )
    monkeypatch.setattr(pd, "read_parquet", lambda *args, **kwargs: frame)
    with pytest.raises(RuntimeError, match="fixed timestamp boundary"):
        runner.load_mes_gap_inputs(mapping_response=_mapping_response())


def test_schedule_complete_metrics_include_flat_sessions_and_exact_formulas() -> None:
    bundle = generate_mes_overnight_gap_reversal_bundle(
        _data(),
        mapping_intervals=_mapping(),
        schedule=_schedule("2023-12-20", "2023-12-21", "2023-12-22", "2023-12-26"),
    )
    equity, returns, metrics = runner.schedule_complete_metrics(bundle)
    expected_final = runner.INITIAL_CASH + 2.52

    assert equity.tolist() == pytest.approx([100_000.0, 100_001.26, 100_002.52, 100_002.52])
    assert len(returns) == 4
    assert returns.iloc[0] == 0.0
    assert metrics["total_return"] == pytest.approx(expected_final / 100_000.0 - 1.0)
    assert metrics["annualized_return"] == pytest.approx((expected_final / 100_000.0) ** (252 / 4) - 1.0)
    assert metrics["sharpe_ratio"] == pytest.approx(returns.mean() / returns.std(ddof=1) * 252**0.5)
    assert metrics["max_drawdown"] == 0.0
    assert metrics["number_of_trades"] == 2
    assert metrics["win_rate"] == 1.0


def test_exact_screening_boundaries_are_conjunctive() -> None:
    passing = screen_metrics(
        experiment_id=runner.EXPERIMENT_ID,
        strategy_id="mes_overnight_gap_reversal",
        strategy_version="1.0.0",
        parameters={},
        execution_assumptions=runner.execution_assumptions(),
        metrics={
            "number_of_trades": 750,
            "total_return": 0.000001,
            "annualized_return": 0.000001,
            "sharpe_ratio": 0.5,
            "max_drawdown": -0.35,
            "win_rate": 0.4,
        },
        config=runner.SCREENING_CONFIG,
    )
    assert passing.passed
    failed = screen_metrics(
        experiment_id=runner.EXPERIMENT_ID,
        strategy_id="mes_overnight_gap_reversal",
        strategy_version="1.0.0",
        parameters={},
        execution_assumptions=runner.execution_assumptions(),
        metrics={
            "number_of_trades": 749,
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe_ratio": 0.499,
            "max_drawdown": -0.350001,
            "win_rate": 1.0,
        },
        config=runner.SCREENING_CONFIG,
    )
    assert not failed.passed
    assert failed.failed_rule_count == 5


def test_vectorbt_call_and_manual_cross_check_are_exact_and_fail_closed() -> None:
    data = _data()
    bundle = generate_mes_overnight_gap_reversal_bundle(
        data,
        mapping_intervals=_mapping(),
        schedule=_schedule("2023-12-20", "2023-12-21", "2023-12-22", "2023-12-26"),
    )
    captured = {}
    portfolio = _portfolio(bundle)

    class Portfolio:
        @staticmethod
        def from_signals(**kwargs):
            captured.update(kwargs)
            return portfolio

    built = runner.build_vectorbt_portfolio(
        data, bundle, vbt=SimpleNamespace(Portfolio=Portfolio)
    )
    assert built is portfolio
    assert captured["size"] == 1.0
    assert captured["fixed_fees"] == FEE_PER_SIDE
    assert captured["fees"] == captured["slippage"] == 0.0
    assert captured["price"].at[_time("2023-12-21", "09:35")] == 100.75 * 5.0
    validation = runner.validate_vectorbt_against_manual(portfolio, bundle)
    assert validation[0]["completed_trade_count"] == 2

    with pytest.raises(RuntimeError, match="VectorBT/manual MES trade mismatch"):
        runner.validate_vectorbt_against_manual(_portfolio(bundle, pnl_offset=0.01), bundle)


def test_execute_produces_one_screened_row_from_authoritative_daily_metrics() -> None:
    data = _data()
    schedule = _schedule("2023-12-20", "2023-12-21", "2023-12-22", "2023-12-26")
    expected_bundle = generate_mes_overnight_gap_reversal_bundle(
        data, mapping_intervals=_mapping(), schedule=schedule
    )
    portfolio = _portfolio(expected_bundle)

    class Portfolio:
        @staticmethod
        def from_signals(**kwargs):
            del kwargs
            return portfolio

    execution = runner.execute_mes_overnight_gap_reversal(
        data,
        _audit(),
        _mapping(),
        vbt=SimpleNamespace(Portfolio=Portfolio),
        schedule=schedule,
    )
    row = execution.result.ranked_results.iloc[0]
    assert len(execution.result.ranked_results) == 1
    assert row["number_of_trades"] == 2
    assert row["screening_status"] == "screened_out"
    assert "number_of_trades failed" in row["screening_rejection_reasons"]
    assert execution.daily_equity.iloc[-1] == pytest.approx(100_002.52)
