"""SPY Donchian out-of-sample entry point driven by the real experiment engine.

The price series is a 36-bar staircase (24 bars of +1, 12 bars of -0.75): every
approved Donchian survivor breaks out once per cycle and exits on the pullback.
Flattening a region removes every trade in it, which is how each screening
failure is triggered with real inputs.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json

import numpy as np
import pandas as pd
import pytest

import backtesting.run_spy_donchian_oos as donchian_oos
from backtesting.out_of_sample import (
    OutOfSampleProgressionError,
    execute_out_of_sample,
    split_chronologically,
)
from backtesting.robustness import load_lock_artifact
from backtesting.screening import ScreeningConfig
from market_data.models import DataAudit

licensed = pytest.mark.licensed_vectorbt

SCREENING = ScreeningConfig(
    minimum_trades=1,
    minimum_total_return=0.0,
    minimum_annualized_return=0.0,
    minimum_sharpe_ratio=None,
    maximum_drawdown=0.35,
)
# 360 rows split 60/20/20: train bars 0-216, selection 216-288, test 288-360.
TRAIN, SELECTION, TEST = (0, 216), (216, 288), (288, 360)


def _frame(rows: int = 360, flat: tuple[tuple[int, int], ...] = ()) -> pd.DataFrame:
    index = pd.date_range("2020-01-02", periods=rows, freq="B", tz="America/New_York")
    steps = np.tile(np.array([1.0] * 24 + [-0.75] * 12), rows // 36 + 1)[:rows]
    close = pd.Series(100 + np.cumsum(steps), index=index)
    for start, end in flat:
        close.iloc[start:end] = close.iloc[start]
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": 1_000.0,
        },
        index=index,
    )


def _audit(data: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="fixture",
        interval="1 day",
        requested_start=str(data.index[0].date()),
        requested_dynamic_end_policy="fixture",
        latest_completed_exchange_session=str(data.index[-1].date()),
        prices_adjusted=True,
        adjustment_verification="fixture adjusted OHLC",
        download_time="2026-01-01T00:00:00Z",
        download_timezone="UTC",
        actual_first_row_date=str(data.index[0].date()),
        actual_last_row_date=str(data.index[-1].date()),
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
        cache_action="fixture",
        cache_decision_reason="fixture",
    )


def _config(tmp_path: Path):
    """The production entry-point config with a tiny-data screen and a temp output."""
    return replace(
        donchian_oos.OOS_CONFIG,
        experiment=replace(donchian_oos.OOS_CONFIG.experiment, screening=SCREENING),
        output_path=tmp_path / "spy_donchian_oos.json",
    )


def _run(tmp_path, data, *, write_output=False):
    return execute_out_of_sample(
        _config(tmp_path), data, _audit(data), write_output=write_output
    )


def _partition(result) -> str:
    return result.experiment_id.split(":")[-1]


def _passing_parameters(result) -> tuple[dict[str, int], ...]:
    """Parameters of every row that passed the real screen, in rank order."""
    by_id = {item.parameter_row_id: item for item in result.screening_results}
    return tuple(
        dict(by_id[row_id].normalized_parameters)
        for row_id in result.passing_results["parameter_row_id"]
    )


def test_entry_point_uses_exact_three_approved_survivors() -> None:
    assert donchian_oos.APPROVED_SURVIVOR_PARAMETERS == (
        {"entry_lookback": 20, "exit_lookback": 10},
        {"entry_lookback": 55, "exit_lookback": 20},
        {"entry_lookback": 55, "exit_lookback": 10},
    )
    assert donchian_oos.EXPERIMENT_CONFIG.parameter_combinations == (
        donchian_oos.APPROVED_SURVIVOR_PARAMETERS
    )
    assert donchian_oos.EXPERIMENT_CONFIG.strategy_id == (
        "spy_donchian_trend_breakout_long"
    )
    assert donchian_oos.OOS_CONFIG.shortlist_size == 3
    assert donchian_oos.OOS_CONFIG.output_path.name == "spy_donchian_oos.json"


def test_donchian_oos_split_is_chronological_and_non_overlapping() -> None:
    split = split_chronologically(_frame(), donchian_oos.OOS_CONFIG.split)
    assert (split.train.row_count, split.selection.row_count, split.test.row_count) == (
        216,
        72,
        72,
    )
    assert split.train.end < split.selection.start < split.test.start
    assert set(split.train.data.index).isdisjoint(split.selection.data.index)
    assert set(split.selection.data.index).isdisjoint(split.test.data.index)


@licensed
def test_training_failure_stops_before_selection_and_test(tmp_path: Path) -> None:
    with pytest.raises(OutOfSampleProgressionError, match="training slice"):
        _run(tmp_path, _frame(flat=(TRAIN,)), write_output=True)
    payload = json.loads((tmp_path / "spy_donchian_oos.json").read_text(encoding="utf-8"))
    assert payload["failure_stage"] == "training"
    assert payload["selection_status"] == "not_run"
    assert payload["test_status"] == "not_run"


@licensed
def test_selection_failure_stops_before_lock_and_test(tmp_path: Path) -> None:
    with pytest.raises(OutOfSampleProgressionError, match="selection slice"):
        _run(tmp_path, _frame(flat=(SELECTION,)))
    assert not (tmp_path / "spy_donchian_oos.json").exists()


@licensed
def test_selection_failure_writes_no_lock_failure_artifact(tmp_path: Path) -> None:
    with pytest.raises(OutOfSampleProgressionError, match="selection slice"):
        _run(tmp_path, _frame(flat=(SELECTION,)), write_output=True)
    payload = json.loads((tmp_path / "spy_donchian_oos.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["failure_stage"] == "selection"
    assert payload["training_status"] == "passed"
    assert payload["selection_status"] == "screened_out"
    assert payload["test_status"] == "not_run"
    assert payload["parameter_lock"] is None
    assert payload["metrics"] == {}


@licensed
def test_lock_precedes_exactly_one_test_candidate_and_test_cannot_reselect(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, _frame())
    stages = (result.training_result, result.selection_result, result.test_result)
    assert [_partition(stage) for stage in stages] == ["train", "selection", "test"]
    assert len(result.training_result.normalized_parameters) == 3
    assert result.shortlist_parameters == _passing_parameters(result.training_result)
    assert 1 <= len(result.shortlist_parameters) <= 3
    assert result.selection_result.normalized_parameters == result.shortlist_parameters
    assert result.selected_parameters == _passing_parameters(result.selection_result)[0]
    assert result.test_result.normalized_parameters == (result.selected_parameters,)
    assert dict(result.parameter_lock.normalized_parameters) == result.selected_parameters
    assert result.test_result.ranked_results.iloc[0]["total_return"] > 0


@licensed
def test_test_partition_values_cannot_change_shortlist_or_lock(tmp_path: Path) -> None:
    first = _run(tmp_path, _frame())
    second = _run(tmp_path, _frame(flat=(TEST,)))
    assert first.shortlist_parameters == second.shortlist_parameters
    assert first.selected_parameters == second.selected_parameters
    assert first.parameter_lock.lock_id == second.parameter_lock.lock_id
    assert second.test_result.ranked_results.iloc[0]["number_of_trades"] == 0


@licensed
def test_schema_compatible_artifact_loads_for_robustness(tmp_path: Path) -> None:
    config = _config(tmp_path)
    data = _frame()
    result = execute_out_of_sample(config, data, _audit(data))
    evidence = load_lock_artifact(
        config.output_path,
        expected_experiment_id="spy_donchian_daily_long_oos",
        expected_strategy_id="spy_donchian_trend_breakout_long",
        expected_strategy_version="1.0.0",
        expected_execution={"execution_mode": "next_bar_open", "fees": 0.0005},
    )
    assert evidence.status == "passed"
    assert evidence.locked_parameters == result.selected_parameters
    assert evidence.metrics["number_of_trades"] >= 1
