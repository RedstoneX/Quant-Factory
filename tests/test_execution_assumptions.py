"""Tests for realistic and comparison execution models."""

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from backtesting.execution_comparison import build_execution_comparison
from backtesting.experiments import (
    ExecutionConfig,
    ExperimentConfig,
    SignalResult,
    align_signals_for_execution,
    build_execution_price,
    build_portfolio,
    execute_experiment,
)
from market_data import DataAudit, MarketDataConfig
from strategies import get_strategy


def _execution(mode: str = "next_bar_open") -> ExecutionConfig:
    constructor = (
        ExecutionConfig.next_bar_open
        if mode == "next_bar_open"
        else ExecutionConfig.same_bar_close
    )
    return constructor(
        initial_cash=10_000,
        fees=0.0,
        slippage=0.0,
        direction="longonly",
        leverage=1.0,
        accumulate=False,
    )


def _signals(index: pd.Index) -> SignalResult:
    return SignalResult(
        entries=pd.Series([False, True, False, False], index=index),
        exits=pd.Series([False, False, True, True], index=index),
        parameters={"window": 7, "entry_threshold": 25, "exit_threshold": 60},
    )


def _data() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=4, freq="D")
    return pd.DataFrame(
        {
            "Open": [101.0, 111.0, 121.0, 131.0],
            "Close": [100.0, 110.0, 120.0, 130.0],
        },
        index=index,
    )


def _config(tmp_path: Path, execution: ExecutionConfig) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="execution_test",
        strategy_id="rsi_mean_reversion",
        parameter_combinations=(
            {"window": 7, "entry_threshold": 25, "exit_threshold": 60},
        ),
        market_data=MarketDataConfig(
            symbol="SPY",
            provider="Yahoo Finance",
            provider_implementation="test",
            interval="1 day",
            requested_start="2024-01-01",
            end_date_policy="test",
            adjusted=True,
            exchange_calendar="NYSE",
            market_timezone="America/New_York",
            cache_path=tmp_path / "cache.csv",
        ),
        execution=execution,
        ranking_columns=("total_return",),
        ranking_ascending=(False,),
        output_path=tmp_path / "results.csv",
        parameter_output_names=(("window", "rsi_window"),),
    )


def _audit(row_count: int) -> DataAudit:
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="test",
        interval="1 day",
        requested_start="2024-01-01",
        requested_dynamic_end_policy="test",
        latest_completed_exchange_session="2024-01-04",
        prices_adjusted=True,
        adjustment_verification="test",
        download_time="2024-01-04T17:00:00-05:00",
        download_timezone="America/New_York",
        actual_first_row_date="2024-01-01",
        actual_last_row_date="2024-01-04",
        row_count=row_count,
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
    )


def test_next_bar_shift_has_no_same_bar_or_future_execution() -> None:
    signals = _signals(_data().index)
    aligned = align_signals_for_execution(signals, _execution())
    assert aligned.entries.tolist() == [False, False, True, False]
    assert aligned.exits.tolist() == [False, False, False, True]
    assert not aligned.entries.iloc[0]
    assert not aligned.exits.iloc[0]
    assert signals.exits.iloc[-1]
    assert aligned.exits.sum() == 1  # final-bar signal has no future fill


def test_rsi_signal_prefix_is_unchanged_by_future_rows() -> None:
    index = pd.date_range("2024-01-01", periods=60, freq="D")
    close = pd.Series(
        [100 + ((i % 12) - 6) * 2 for i in range(len(index))],
        index=index,
        dtype=float,
    )
    strategy = get_strategy("rsi_mean_reversion")
    parameters = {"window": 7, "entry_threshold": 25, "exit_threshold": 60}
    prefix = strategy.generate_signals(close.iloc[:45], parameters)
    full = strategy.generate_signals(close, parameters)
    pd.testing.assert_series_equal(prefix.entries, full.entries.iloc[:45])
    pd.testing.assert_series_equal(prefix.exits, full.exits.iloc[:45])


def test_next_bar_portfolio_uses_next_open_price(tmp_path: Path) -> None:
    data = _data()
    portfolio = build_portfolio(data, _signals(data.index), _config(tmp_path, _execution()))
    assert portfolio.asset_flow.iloc[1] == 0
    assert portfolio.asset_flow.iloc[2] > 0
    orders = portfolio.orders.records_readable
    assert orders.iloc[0]["Price"] == data["Open"].iloc[2]


def test_same_bar_close_mode_preserves_unshifted_comparison(tmp_path: Path) -> None:
    data = _data()
    signals = _signals(data.index)
    aligned = align_signals_for_execution(signals, _execution("same_bar_close"))
    assert aligned is signals
    portfolio = build_portfolio(
        data, signals, _config(tmp_path, _execution("same_bar_close"))
    )
    assert portfolio.asset_flow.iloc[1] > 0
    assert portfolio.orders.records_readable.iloc[0]["Price"] == data["Close"].iloc[1]


def _futures_execution(direction: str, *, quantity: float = 1.0) -> ExecutionConfig:
    return ExecutionConfig.next_bar_open(
        initial_cash=10_000,
        fees=0.0,
        slippage=0.0,
        direction=direction,  # type: ignore[arg-type]
        leverage=1.0,
        accumulate=False,
        position_sizing="fixed_units",
        order_size=quantity,
        price_multiplier=5.0,
        fixed_fee_per_contract_per_side=0.62,
        slippage_ticks=1.0,
        tick_size=0.25,
    )


def test_long_futures_fee_and_slippage_direction(tmp_path: Path) -> None:
    data = _data()
    signals = _signals(data.index)
    execution = _futures_execution("longonly")
    aligned = align_signals_for_execution(signals, execution)
    prices = build_execution_price(data, aligned, execution)
    assert prices.iloc[2] == (data["Open"].iloc[2] + 0.25) * 5
    assert prices.iloc[3] == (data["Open"].iloc[3] - 0.25) * 5

    portfolio = build_portfolio(data, signals, _config(tmp_path, execution))
    orders = portfolio.orders.records_readable
    assert orders["Price"].tolist() == pytest.approx(
        [prices.iloc[2], prices.iloc[3]]
    )
    assert orders["Fees"].tolist() == pytest.approx([0.62, 0.62])
    assert orders["Fees"].sum() == pytest.approx(1.24)


def test_short_futures_fee_and_slippage_direction(tmp_path: Path) -> None:
    data = _data()
    index = data.index
    signals = SignalResult(
        entries=pd.Series(False, index=index),
        exits=pd.Series(False, index=index),
        short_entries=pd.Series([False, True, False, False], index=index),
        short_exits=pd.Series([False, False, True, False], index=index),
        parameters={"window": 7, "entry_threshold": 25, "exit_threshold": 60},
    )
    execution = _futures_execution("shortonly")
    aligned = align_signals_for_execution(signals, execution)
    prices = build_execution_price(data, aligned, execution)
    assert prices.iloc[2] == (data["Open"].iloc[2] - 0.25) * 5
    assert prices.iloc[3] == (data["Open"].iloc[3] + 0.25) * 5

    portfolio = build_portfolio(data, signals, _config(tmp_path, execution))
    orders = portfolio.orders.records_readable
    assert orders["Price"].tolist() == pytest.approx(
        [prices.iloc[2], prices.iloc[3]]
    )
    assert orders["Fees"].tolist() == pytest.approx([0.62, 0.62])


def test_futures_slippage_can_be_configured_in_price_points() -> None:
    execution = replace(
        _futures_execution("longonly"),
        slippage_ticks=0.0,
        tick_size=None,
        slippage_points=0.5,
    )
    aligned = align_signals_for_execution(_signals(_data().index), execution)
    prices = build_execution_price(_data(), aligned, execution)
    assert execution.absolute_slippage_points == 0.5
    assert prices.iloc[2] == (_data()["Open"].iloc[2] + 0.5) * 5
    assert prices.iloc[3] == (_data()["Open"].iloc[3] - 0.5) * 5


def test_futures_costs_scale_with_contract_quantity(tmp_path: Path) -> None:
    execution = _futures_execution("longonly", quantity=3)
    portfolio = build_portfolio(
        _data(), _signals(_data().index), _config(tmp_path, execution)
    )
    orders = portfolio.orders.records_readable
    assert orders["Size"].tolist() == pytest.approx([3.0, 3.0])
    assert orders["Fees"].tolist() == pytest.approx([1.86, 1.86])
    assert orders["Fees"].sum() == pytest.approx(3.72)


def test_rsi_percentage_fee_and_slippage_behavior_is_unchanged(tmp_path: Path) -> None:
    execution = ExecutionConfig.next_bar_open(
        initial_cash=10_000,
        fees=0.001,
        slippage=0.01,
        direction="longonly",
        leverage=1.0,
        accumulate=False,
    )
    portfolio = build_portfolio(
        _data(), _signals(_data().index), _config(tmp_path, execution)
    )
    orders = portfolio.orders.records_readable
    assert orders.iloc[0]["Price"] == pytest.approx(_data()["Open"].iloc[2] * 1.01)
    assert orders.iloc[1]["Price"] == pytest.approx(_data()["Open"].iloc[3] * 0.99)
    assert orders["Fees"].sum() > 0


def test_typed_execution_rejects_unsupported_combinations() -> None:
    with pytest.raises(ValueError, match="Unsupported execution mode"):
        ExecutionConfig(
            mode="intraday_vwap",  # type: ignore[arg-type]
            signal_timing="completed_bar_close",
            execution_price_field="Open",
            initial_cash=10_000,
            fees=0.0005,
            slippage=0.0002,
            position_sizing="all_available_cash",
            direction="longonly",
            leverage=1.0,
            accumulate=False,
        )
    with pytest.raises(ValueError, match="requires price field Open"):
        ExecutionConfig(
            mode="next_bar_open",
            signal_timing="completed_bar_close",
            execution_price_field="Close",
            initial_cash=10_000,
            fees=0.0005,
            slippage=0.0002,
            position_sizing="all_available_cash",
            direction="longonly",
            leverage=1.0,
            accumulate=False,
        )


def test_result_records_actual_execution_assumptions(tmp_path: Path) -> None:
    index = pd.date_range("2024-01-01", periods=80, freq="D")
    data = pd.DataFrame(
        {
            "Open": [99 + ((i % 12) - 6) * 2 for i in range(len(index))],
            "Close": [100 + ((i % 12) - 6) * 2 for i in range(len(index))],
        },
        index=index,
        dtype=float,
    )
    result = execute_experiment(
        _config(tmp_path, _execution()), data, _audit(len(data)), write_output=False
    )
    assert result.execution_assumptions["execution_mode"] == "next_bar_open"
    assert result.execution_assumptions["execution_price"] == "Open"
    assert result.execution_assumptions["signal_timing_label"] == (
        "Signal calculated after market close"
    )
    assert result.ranked_results.loc[0, "execution_timing"] == "next_available_bar"


def test_execution_comparison_reports_metric_and_ranking_change(tmp_path: Path) -> None:
    index = pd.date_range("2024-01-01", periods=80, freq="D")
    data = pd.DataFrame(
        {
            "Open": [99 + ((i % 12) - 6) * 2 for i in range(len(index))],
            "Close": [100 + ((i % 12) - 6) * 2 for i in range(len(index))],
        },
        index=index,
        dtype=float,
    )
    same = execute_experiment(
        _config(tmp_path, _execution("same_bar_close")),
        data,
        _audit(len(data)),
        write_output=False,
    )
    realistic = execute_experiment(
        _config(tmp_path, _execution()), data, _audit(len(data)), write_output=False
    )
    comparison = build_execution_comparison(same, realistic)
    assert comparison.loc[0, "old_mode"] == "same_bar_close"
    assert comparison.loc[0, "new_mode"] == "next_bar_open"
    assert "change_total_return" in comparison.columns
