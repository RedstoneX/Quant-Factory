"""Rolling walk-forward evaluation driven by the real experiment engine.

The price series is a 12-bar sawtooth (ten bars of -2, two bars of +11) so the
real RSI mean-reversion strategy enters once per cycle near the trough and exits
on the rebound.  Flattening a region removes every trade in it, which is how
screening failures are triggered with real inputs.
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.screening import ScreeningConfig
from backtesting.walk_forward import (
    WalkForwardConfig,
    build_walk_forward_windows,
    execute_walk_forward,
)
from market_data.models import DataAudit

licensed = pytest.mark.licensed_vectorbt

FAST_EXIT = {"window": 7, "entry_threshold": 30, "exit_threshold": 50}
SLOW_EXIT = {"window": 7, "entry_threshold": 30, "exit_threshold": 60}
SCREENING = ScreeningConfig(
    minimum_trades=1,
    minimum_total_return=0.0,
    minimum_annualized_return=0.0,
    minimum_sharpe_ratio=None,
    maximum_drawdown=0.35,
)


def _frame(rows: int = 120, flat: tuple[tuple[int, int], ...] = ()) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    steps = np.tile(np.array([-2.0] * 10 + [11.0] * 2), rows // 12 + 1)[:rows]
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
        provider="fixture",
        provider_implementation="fixture",
        interval="1 day",
        requested_start=str(data.index[0].date()),
        requested_dynamic_end_policy="fixture",
        latest_completed_exchange_session=str(data.index[-1].date()),
        prices_adjusted=True,
        adjustment_verification="fixture",
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
    )


def _config(
    tmp_path: Path,
    *,
    mode: str = "rolling",
    selection_size: int | None = 12,
    step: int = 36,
    final_policy: str = "drop",
    shortlist_size: int = 2,
    parameters: tuple[dict[str, int], ...] = (FAST_EXIT, SLOW_EXIT),
) -> WalkForwardConfig:
    experiment = replace(
        EXPERIMENT_CONFIG,
        parameter_combinations=parameters,
        screening=SCREENING,
        output_path=tmp_path / "base.csv",
    )
    return WalkForwardConfig(
        experiment=experiment,
        training_window_size=24,
        selection_window_size=selection_size,
        test_window_size=12,
        step_size=step,
        training_mode=mode,
        minimum_rows_per_window=2,
        shortlist_size=shortlist_size,
        incomplete_final_window=final_policy,
        output_path=tmp_path / "walk_forward.json",
    )


def _run(tmp_path, data, **config_kwargs):
    return execute_walk_forward(
        _config(tmp_path, **config_kwargs), data, _audit(data), write_output=False
    )


def _stage(result) -> str:
    return result.experiment_id.split(":")[-1]


def _top_passing_parameters(result) -> dict[str, int]:
    """Parameters of the best-ranked row that passed the real screen."""
    row_id = result.passing_results.iloc[0]["parameter_row_id"]
    match = next(item for item in result.screening_results if item.parameter_row_id == row_id)
    return dict(match.normalized_parameters)


def test_rolling_windows_are_ordered_and_non_overlapping(tmp_path):
    windows = build_walk_forward_windows(_frame(), _config(tmp_path))
    assert len(windows) == 3
    assert windows[0].train.row_count == 24
    assert windows[1].train.start > windows[0].train.start
    for fold in windows:
        assert fold.train.end < fold.selection.start < fold.test.start
        assert set(fold.train.data.index).isdisjoint(fold.test.data.index)
    assert windows[0].test.end < windows[1].test.start


def test_expanding_windows_keep_start_and_grow(tmp_path):
    windows = build_walk_forward_windows(
        _frame(), _config(tmp_path, mode="expanding")
    )
    assert windows[0].train.start == windows[1].train.start
    assert windows[0].train.row_count == 24
    assert windows[1].train.row_count == 60


def test_step_size_controls_test_spacing(tmp_path):
    windows = build_walk_forward_windows(_frame(), _config(tmp_path, step=12))
    assert len(windows) == 7
    assert windows[1].test.start == "2020-02-18"


def test_incomplete_final_window_policy(tmp_path):
    data = _frame(122)
    dropped = build_walk_forward_windows(data, _config(tmp_path, step=12))
    included = build_walk_forward_windows(
        data, _config(tmp_path, step=12, final_policy="include")
    )
    assert len(dropped) == 7
    assert len(included) == 8
    assert included[-1].test.row_count == 2


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("step_size", 4, "avoid overlapping tests"),
        ("shortlist_size", 0, "must be positive"),
        ("training_mode", "random", "unsupported training_mode"),
        ("incomplete_final_window", "maybe", "must be 'drop' or 'include'"),
    ],
)
def test_invalid_configuration(tmp_path, field, value, message):
    with pytest.raises(ValueError, match=message):
        replace(_config(tmp_path), **{field: value})


@licensed
def test_training_shortlist_and_locked_test_parameters(tmp_path):
    result = _run(tmp_path, _frame(), shortlist_size=1)
    fold = result.folds[0]
    stages = (fold.training_result, fold.selection_result, fold.test_result)
    assert [_stage(stage) for stage in stages] == ["train", "selection", "test"]
    assert all(stage.experiment_id.split(":")[-2] == "fold_001" for stage in stages)
    assert len(fold.training_result.normalized_parameters) == 2
    assert fold.shortlist_parameters == (_top_passing_parameters(fold.training_result),)
    assert fold.selection_result.normalized_parameters == fold.shortlist_parameters
    assert fold.test_result.normalized_parameters == (fold.selected_parameters,)
    assert fold.parameter_lock is not None
    assert (
        fold.training_result.market_data_audit.actual_last_row_date
        < fold.selection_result.market_data_audit.actual_first_row_date
        <= fold.selection_result.market_data_audit.actual_last_row_date
        < fold.test_result.market_data_audit.actual_first_row_date
    )
    assert fold.test_metrics["number_of_trades"] >= 1


@licensed
def test_failed_training_fold_continues_without_selection_or_test(tmp_path):
    # Fold 2 trains on bars 36-60; a flat training slice has no trade to pass.
    result = _run(tmp_path, _frame(flat=((36, 60),)))
    second = result.folds[1]
    assert second.status == "failed"
    assert second.training_result is not None
    assert second.selection_result is None and second.test_result is None
    assert "selection was not evaluated" in second.failure_reason
    assert result.failed_fold_ids == ("fold_002",)
    assert result.successful_fold_count == 2


@licensed
def test_failed_selection_fold_never_evaluates_test(tmp_path):
    # Fold 3 selects on bars 96-108; flattening only that slice fails selection.
    result = _run(tmp_path, _frame(flat=((96, 108),)))
    third = result.folds[2]
    assert third.status == "failed"
    assert _stage(third.selection_result) == "selection"
    assert third.test_result is None
    assert third.parameter_lock is None
    assert "parameters were not locked" in third.failure_reason
    assert result.failed_fold_ids == ("fold_003",)


@licensed
def test_test_and_future_mutations_do_not_change_first_fold_selection(tmp_path):
    first = _run(tmp_path, _frame())
    second = _run(tmp_path, _frame(flat=((36, 120),)))
    assert first.folds[0].shortlist_parameters == second.folds[0].shortlist_parameters
    assert first.folds[0].selected_parameters == second.folds[0].selected_parameters
    assert first.folds[0].parameter_lock.lock_id == second.folds[0].parameter_lock.lock_id
    assert first.folds[0].test_metrics != second.folds[0].test_metrics


@licensed
def test_optional_selection_locks_best_passing_training_row(tmp_path):
    result = _run(tmp_path, _frame(), selection_size=None, step=24)
    fold = result.folds[0]
    assert fold.selection_result is None
    assert [_stage(fold.training_result), _stage(fold.test_result)] == ["train", "test"]
    best = fold.training_result.passing_results.iloc[0]
    assert fold.selected_parameters == _top_passing_parameters(fold.training_result)
    assert fold.parameter_lock.selection_parameter_row_id == best["parameter_row_id"]


@licensed
def test_stability_and_aggregate_calculations_are_deterministic(tmp_path):
    first = _run(tmp_path, _frame())
    second = _run(tmp_path, _frame())
    assert first.selected_parameters_by_fold == second.selected_parameters_by_fold
    assert first.successful_fold_count == 3
    assert first.unique_parameter_set_count == 1
    assert first.parameter_change_percentage == pytest.approx(0.0)
    assert first.maximum_consecutive_persistence == 3
    returns = [fold.test_metrics["total_return"] for fold in first.folds]
    assert first.compounded_return == pytest.approx(float(np.prod([1 + r for r in returns]) - 1))
    assert first.total_trades == sum(
        int(fold.test_metrics["number_of_trades"]) for fold in first.folds
    )
    assert first.total_trades >= 3
    assert first.average_fold_metrics["total_return"] == pytest.approx(np.mean(returns))
    assert first.median_fold_metrics["total_return"] == pytest.approx(np.median(returns))


@licensed
def test_report_contains_fold_provenance_and_failures(tmp_path):
    config = _config(tmp_path)
    data = _frame(flat=((0, 24),))
    result = execute_walk_forward(config, data, _audit(data))
    text = config.output_path.read_text(encoding="utf-8")
    assert result.total_fold_count == 3
    assert result.failed_fold_ids == ("fold_001",)
    assert '"fold_001"' in text
    assert '"failed_folds": 1' in text
    assert '"parameter_change_percentage"' in text


def test_intraday_row_windows_never_split_a_day(tmp_path):
    # 7 bars per day: row-count cuts land mid-day and must move to the next day's first bar.
    days = pd.bdate_range("2024-01-01", periods=30, tz="UTC")
    index = pd.DatetimeIndex([day + pd.Timedelta(hours=14, minutes=30 * bar) for day in days for bar in range(7)])
    data = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0}, index=index)
    windows = build_walk_forward_windows(data, _config(tmp_path))
    assert windows
    for fold in windows:
        assert fold.train.end < fold.selection.start < fold.test.start
        for part in (fold.train, fold.selection, fold.test):
            assert part.data.index[0].time() == index[0].time()
