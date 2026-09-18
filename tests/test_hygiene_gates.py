"""Focused tests for pre-simulation data and logic hygiene gates."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

import backtesting.experiments.runner as runner_module
from backtesting.experiments import SignalResult, execute_experiment, validate_for_simulation
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.validation import (
    ExperimentValidationError,
    raise_for_blocking_failures,
    validate_market_data,
)
from market_data import DataAudit


def _data(periods: int = 40) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=periods, freq="D")
    close = pd.Series(
        [100 + ((i % 10) - 5) for i in range(periods)], index=index, dtype=float
    )
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": 1_000,
        },
        index=index,
    )


def _audit(data: pd.DataFrame) -> DataAudit:
    first = str(data.index[0].date()) if len(data) else ""
    last = str(data.index[-1].date()) if len(data) else ""
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="test",
        interval="1 day",
        requested_start="2024-01-01",
        requested_dynamic_end_policy="test",
        latest_completed_exchange_session=last,
        prices_adjusted=True,
        adjustment_verification="test",
        download_time="2024-02-09T17:00:00-05:00",
        download_timezone="America/New_York",
        actual_first_row_date=first,
        actual_last_row_date=last,
        row_count=len(data),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
    )


def _signals(data: pd.DataFrame) -> SignalResult:
    entries = pd.Series(False, index=data.index)
    exits = pd.Series(False, index=data.index)
    entries.iloc[5] = True
    exits.iloc[10] = True
    return SignalResult(entries=entries, exits=exits, parameters={})


def _one_combination_config():
    return replace(
        EXPERIMENT_CONFIG,
        parameter_combinations=(
            {"window": 7, "entry_threshold": 25, "exit_threshold": 60},
        ),
    )


def _assert_market_gate_fails(data: pd.DataFrame, gate_id: str) -> None:
    results = validate_market_data(
        data, ("Close",), EXPERIMENT_CONFIG.execution
    )
    with pytest.raises(ExperimentValidationError) as caught:
        raise_for_blocking_failures(results)
    assert gate_id in {failure.gate_id for failure in caught.value.failures}


def test_empty_data_and_missing_open_fail() -> None:
    _assert_market_gate_fails(pd.DataFrame(), "data.non_empty")
    _assert_market_gate_fails(_data().drop(columns="Open"), "data.required_columns")


def test_duplicate_unsorted_and_null_timestamps_fail() -> None:
    duplicate = _data()
    duplicate.index = duplicate.index.where(
        duplicate.index != duplicate.index[5], duplicate.index[4]
    )
    _assert_market_gate_fails(duplicate, "timestamps.unique")

    unsorted = _data().iloc[[1, 0, *range(2, 40)]]
    _assert_market_gate_fails(unsorted, "timestamps.monotonic")

    null_index = _data()
    index_values = list(null_index.index)
    index_values[3] = pd.NaT
    null_index.index = pd.DatetimeIndex(index_values)
    _assert_market_gate_fails(null_index, "timestamps.non_null")


def test_null_non_finite_and_impossible_ohlc_fail() -> None:
    malformed = _data()
    malformed.iloc[2, malformed.columns.get_loc("Open")] = np.nan
    malformed.iloc[3, malformed.columns.get_loc("Close")] = np.inf
    malformed.iloc[4, malformed.columns.get_loc("High")] = (
        malformed.iloc[4]["Low"] - 1
    )
    results = validate_market_data(
        malformed, ("Close",), EXPERIMENT_CONFIG.execution
    )
    with pytest.raises(ExperimentValidationError) as caught:
        raise_for_blocking_failures(results)
    gate_ids = {failure.gate_id for failure in caught.value.failures}
    assert {
        "prices.non_null",
        "prices.finite_positive",
        "prices.ohlc_relationships",
    }.issubset(gate_ids)


@pytest.mark.parametrize("failure", ["length", "index", "null"])
def test_signal_alignment_failures_are_blocking(failure: str) -> None:
    data = _data()
    signals = _signals(data)
    if failure == "length":
        signals = SignalResult(
            entries=signals.entries.iloc[:-1],
            exits=signals.exits,
            parameters={},
        )
    elif failure == "index":
        signals = SignalResult(
            entries=signals.entries.set_axis(data.index.shift(1, freq="D")),
            exits=signals.exits,
            parameters={},
        )
    else:
        entries = signals.entries.astype("object")
        entries.iloc[3] = None
        signals = SignalResult(entries=entries, exits=signals.exits, parameters={})

    with pytest.raises(ExperimentValidationError) as caught:
        validate_for_simulation(data, signals, EXPERIMENT_CONFIG)
    assert any(result.gate_id.startswith("signals.") for result in caught.value.failures)


def test_contradictory_execution_assumptions_are_blocking() -> None:
    execution = replace(EXPERIMENT_CONFIG.execution)
    object.__setattr__(execution, "execution_price_field", "Close")
    config = replace(EXPERIMENT_CONFIG, execution=execution)
    with pytest.raises(ExperimentValidationError) as caught:
        validate_for_simulation(_data(), _signals(_data()), config)
    assert "assumptions.consistency" in {
        failure.gate_id for failure in caught.value.failures
    }


def test_valid_inputs_pass_and_results_record_gate_status() -> None:
    data = _data(80)
    result = execute_experiment(
        _one_combination_config(), data, _audit(data), write_output=False
    )
    assert result.validation_results
    assert not any(item.is_blocking_failure for item in result.validation_results)
    assert result.ranked_results.loc[0, "validation_status"] == "passed"
    assert result.ranked_results.loc[0, "validation_gate_count"] >= 15


def test_simulator_is_not_called_after_blocking_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_simulator(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Simulator must not run")

    monkeypatch.setattr(
        runner_module.vbt.Portfolio, "from_signals", forbidden_simulator
    )
    invalid = _data().drop(columns="Open")
    with pytest.raises(ExperimentValidationError):
        execute_experiment(
            _one_combination_config(), invalid, _audit(invalid), write_output=False
        )
    assert called is False
