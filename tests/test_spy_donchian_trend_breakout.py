"""Deterministic tests for the SPY Donchian trend-breakout candidate."""

from __future__ import annotations

import pandas as pd
import pytest

import backtesting.run_spy_donchian as runner
from backtesting.experiments.runner import align_signals_for_execution
from market_data import DataAudit, MarketDataResult
from strategies import get_strategy
from strategies.spy_donchian_trend_breakout import (
    ENTRY_LOOKBACKS,
    EXIT_LOOKBACKS,
    SPY_DONCHIAN_LONG_STRATEGY,
    SPY_DONCHIAN_SHORT_STRATEGY,
    build_approved_variants,
    build_parameter_grid,
    generate_donchian_signals,
)


def _ohlc(close: list[float]) -> pd.DataFrame:
    index = pd.date_range("2024-01-02", periods=len(close), freq="B")
    values = pd.Series(close, index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": values,
            "High": values + 0.5,
            "Low": values - 0.5,
            "Close": values,
            "Volume": 1_000,
        },
        index=index,
    )


def _audit(frame: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=1,
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="test fixture",
        interval="1 day",
        requested_start=frame.index[0].date().isoformat(),
        requested_dynamic_end_policy="fixture",
        latest_completed_exchange_session=frame.index[-1].date().isoformat(),
        prices_adjusted=True,
        adjustment_verification="fixture adjusted OHLC",
        download_time="2024-01-01T00:00:00+00:00",
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
        unexpected_session_gaps=[],
        provider_warnings=[],
        cache_path="fixture",
        cache_action="fixture",
        cache_decision_reason="fixture",
    )


def test_strategy_registry_and_exact_six_approved_variants() -> None:
    assert get_strategy("spy_donchian_trend_breakout_long") is SPY_DONCHIAN_LONG_STRATEGY
    assert get_strategy("spy_donchian_trend_breakout_short") is SPY_DONCHIAN_SHORT_STRATEGY
    assert build_parameter_grid() == (
        {"entry_lookback": 20, "exit_lookback": 10},
        {"entry_lookback": 55, "exit_lookback": 10},
        {"entry_lookback": 55, "exit_lookback": 20},
    )
    variants = build_approved_variants()
    assert len(variants) == 6
    assert {
        (item["entry_lookback"], item["exit_lookback"], item["direction"])
        for item in variants
    } == {
        (20, 10, "long"),
        (20, 10, "short"),
        (55, 10, "long"),
        (55, 10, "short"),
        (55, 20, "long"),
        (55, 20, "short"),
    }


@pytest.mark.parametrize("lookback", ENTRY_LOOKBACKS)
def test_warmup_period_has_no_entries(lookback: int) -> None:
    data = _ohlc([100 + i for i in range(lookback)])
    signals = generate_donchian_signals(
        data,
        {"entry_lookback": lookback, "exit_lookback": 10 if lookback == 20 else 20},
        direction="long",
    )
    assert not signals.entries.any()


def test_channels_exclude_current_bar_to_prevent_lookahead() -> None:
    data = _ohlc([10] * 20 + [19, 20.5, 11])
    data.iloc[20, data.columns.get_loc("High")] = 20.0
    signals = generate_donchian_signals(
        data,
        {"entry_lookback": 20, "exit_lookback": 10},
        direction="long",
    )
    assert bool(signals.entries.iloc[20]) is True
    assert bool(signals.entries.iloc[21]) is True


def test_raw_close_signal_executes_on_next_open_after_alignment() -> None:
    data = _ohlc([10] * 20 + [14, 9])
    signals = generate_donchian_signals(
        data,
        {"entry_lookback": 20, "exit_lookback": 10},
        direction="long",
    )
    aligned = align_signals_for_execution(signals, runner._config("longonly").execution)
    assert signals.entries[signals.entries].index.tolist() == [data.index[20]]
    assert aligned.entries[aligned.entries].index.tolist() == [data.index[21]]


def test_long_and_short_rules_are_symmetric() -> None:
    long_data = _ohlc([10] * 20 + [14, 8])
    short_data = _ohlc([10] * 20 + [6, 12])
    long = generate_donchian_signals(
        long_data,
        {"entry_lookback": 20, "exit_lookback": 10},
        direction="long",
    )
    short = generate_donchian_signals(
        short_data,
        {"entry_lookback": 20, "exit_lookback": 10},
        direction="short",
    )
    assert long.entries.tolist() == short.short_entries.tolist()
    assert long.exits.tolist() == short.short_exits.tolist()
    assert bool(short.entries.any()) is False
    assert bool(short.exits.any()) is False


@pytest.mark.parametrize(
    ("parameters", "error", "message"),
    [
        ({"entry_lookback": 20, "exit_lookback": 20}, ValueError, "less than"),
        ({"entry_lookback": 21, "exit_lookback": 10}, ValueError, "one of"),
        ({"entry_lookback": 20.0, "exit_lookback": 10}, TypeError, "must be int"),
        ({"unknown": 1}, ValueError, "Unsupported parameter"),
    ],
)
def test_parameter_validation_fails_clearly(
    parameters: dict[str, object], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        get_strategy("spy_donchian_trend_breakout_long").validate_parameters(parameters)


def test_strategy_specification_matches_approved_boundaries() -> None:
    spec = SPY_DONCHIAN_LONG_STRATEGY.spec
    assert spec.identity.family == "trend_following"
    assert spec.data.required_fields == ("Open", "High", "Low", "Close")
    assert spec.data.supported_intervals == ("1 day",)
    assert spec.data.adjusted_prices is True
    assert spec.data.minimum_history_bars == 56
    assert spec.assumptions.pyramiding is False
    assert spec.parameter_map["entry_lookback"].allowed_values == ENTRY_LOOKBACKS
    assert spec.parameter_map["exit_lookback"].allowed_values == EXIT_LOOKBACKS


def test_baseline_runner_produces_exact_six_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _ohlc([100 + (i % 12) for i in range(90)])
    monkeypatch.setattr(
        runner,
        "load_market_data",
        lambda config: MarketDataResult(data=frame, audit=_audit(frame)),
    )
    result = runner.run_baseline_screen(write_output=False)
    assert len(result) == 6
    assert result["direction_variant"].value_counts().to_dict() == {
        "longonly": 3,
        "shortonly": 3,
    }
    assert set(result["entry_lookback"]) == {20, 55}
    assert set(result["exit_lookback"]) == {10, 20}
    assert set(result["screening_status"]).issubset({"passed", "screened_out"})
    assert runner.RESULT_PATH.name == "spy_donchian_baseline.csv"
