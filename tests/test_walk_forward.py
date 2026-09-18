"""Deterministic tests for rolling walk-forward evaluation."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.screening import parameter_row_identity
from backtesting.walk_forward import (
    WalkForwardConfig,
    build_walk_forward_windows,
    execute_walk_forward,
)
from market_data.models import DataAudit


def _frame(rows: int = 40) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    values = pd.Series(range(rows), index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": values + 100,
            "High": values + 101,
            "Low": values + 99,
            "Close": values + 100,
            "Volume": 1_000,
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
    selection_size: int | None = 5,
    step: int = 5,
    final_policy: str = "drop",
    shortlist_size: int = 2,
) -> WalkForwardConfig:
    experiment = replace(
        EXPERIMENT_CONFIG,
        parameter_combinations=(
            {"window": 7, "entry_threshold": 20, "exit_threshold": 50},
            {"window": 14, "entry_threshold": 25, "exit_threshold": 55},
        ),
        output_path=tmp_path / "base.csv",
    )
    return WalkForwardConfig(
        experiment=experiment,
        training_window_size=10,
        selection_window_size=selection_size,
        test_window_size=5,
        step_size=step,
        training_mode=mode,
        minimum_rows_per_window=2,
        shortlist_size=shortlist_size,
        incomplete_final_window=final_policy,
        output_path=tmp_path / "walk_forward.json",
    )


def _fake_evaluator(
    calls: list[dict[str, object]],
    *,
    fail_training: set[str] = frozenset(),
    fail_selection: set[str] = frozenset(),
    selection_choice: dict[str, int] | None = None,
):
    def evaluate(config, data, audit, *, write_output):
        parts = config.experiment_id.split(":")
        fold_id, stage = parts[-2], parts[-1]
        parameters = tuple(dict(item) for item in config.parameter_combinations)
        calls.append(
            {
                "fold_id": fold_id,
                "stage": stage,
                "parameters": parameters,
                "start": str(data.index[0].date()),
                "end": str(data.index[-1].date()),
            }
        )
        rows = []
        screening = []
        for normalized in parameters:
            row_id = parameter_row_identity(
                config.experiment_id, config.strategy_id, normalized
            )
            passed = not (
                stage == "train" and fold_id in fail_training
                or stage == "selection" and fold_id in fail_selection
            )
            preferred = (selection_choice or {}).get(fold_id, 14)
            if stage == "selection":
                score = 100 if normalized["window"] == preferred else 1
            else:
                score = normalized["window"]
            rows.append(
                {
                    "parameter_row_id": row_id,
                    "screening_status": "passed" if passed else "screened_out",
                    "window": normalized["window"],
                    "total_return": normalized["window"] / 100,
                    "annualized_return": normalized["window"] / 200,
                    "sharpe_ratio": score / 10,
                    "max_drawdown": -normalized["window"] / 1000,
                    "number_of_trades": normalized["window"],
                    "win_rate": 0.5,
                    "score": score,
                }
            )
            screening.append(
                SimpleNamespace(
                    parameter_row_id=row_id,
                    normalized_parameters=dict(normalized),
                    passed=passed,
                )
            )
        ranked = pd.DataFrame(rows).sort_values(
            ["screening_status", "score", "window"],
            ascending=[True, False, True],
            key=lambda values: values.map({"passed": 0, "screened_out": 1})
            if values.name == "screening_status"
            else values,
            kind="mergesort",
        ).reset_index(drop=True)
        passing = ranked.loc[ranked.screening_status == "passed"].reset_index(
            drop=True
        )
        return SimpleNamespace(
            ranked_results=ranked,
            passing_results=passing,
            screening_results=tuple(screening),
            strategy_id=config.strategy_id,
            strategy_version="1.0.0",
        )

    return evaluate


def test_rolling_windows_are_ordered_and_non_overlapping(tmp_path):
    windows = build_walk_forward_windows(_frame(), _config(tmp_path))
    assert len(windows) == 5
    assert windows[0].train.row_count == 10
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
    assert windows[0].train.row_count == 10
    assert windows[1].train.row_count == 15


def test_step_size_controls_test_spacing(tmp_path):
    windows = build_walk_forward_windows(_frame(), _config(tmp_path, step=10))
    assert len(windows) == 3
    assert windows[1].test.start == "2020-01-26"


def test_incomplete_final_window_policy(tmp_path):
    data = _frame(37)
    dropped = build_walk_forward_windows(data, _config(tmp_path))
    included = build_walk_forward_windows(
        data, _config(tmp_path, final_policy="include")
    )
    assert len(dropped) == 4
    assert len(included) == 5
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


def test_training_shortlist_and_locked_test_parameters(tmp_path):
    calls = []
    result = execute_walk_forward(
        _config(tmp_path, shortlist_size=1),
        _frame(),
        _audit(_frame()),
        evaluator=_fake_evaluator(calls),
        write_output=False,
    )
    first = [call for call in calls if call["fold_id"] == "fold_001"]
    assert [call["stage"] for call in first] == ["train", "selection", "test"]
    assert len(first[0]["parameters"]) == 2
    assert first[1]["parameters"] == (first[0]["parameters"][1],)
    assert first[2]["parameters"] == first[1]["parameters"]
    assert result.folds[0].parameter_lock is not None


def test_failed_training_fold_continues_without_selection_or_test(tmp_path):
    calls = []
    result = execute_walk_forward(
        _config(tmp_path),
        _frame(),
        _audit(_frame()),
        evaluator=_fake_evaluator(calls, fail_training={"fold_002"}),
        write_output=False,
    )
    second = [call["stage"] for call in calls if call["fold_id"] == "fold_002"]
    assert second == ["train"]
    assert result.failed_fold_ids == ("fold_002",)
    assert result.successful_fold_count == 4


def test_failed_selection_fold_never_evaluates_test(tmp_path):
    calls = []
    result = execute_walk_forward(
        _config(tmp_path),
        _frame(),
        _audit(_frame()),
        evaluator=_fake_evaluator(calls, fail_selection={"fold_003"}),
        write_output=False,
    )
    third = [call["stage"] for call in calls if call["fold_id"] == "fold_003"]
    assert third == ["train", "selection"]
    assert result.folds[2].parameter_lock is None
    assert "selection screening" in result.folds[2].failure_reason


def test_test_and_future_mutations_do_not_change_first_fold_selection(tmp_path):
    data = _frame()
    first = execute_walk_forward(
        _config(tmp_path),
        data,
        _audit(data),
        evaluator=_fake_evaluator([]),
        write_output=False,
    )
    changed = data.copy()
    changed.iloc[15:, changed.columns.get_loc("Close")] = -999_999
    second = execute_walk_forward(
        _config(tmp_path),
        changed,
        _audit(changed),
        evaluator=_fake_evaluator([]),
        write_output=False,
    )
    assert first.folds[0].shortlist_parameters == second.folds[0].shortlist_parameters
    assert first.folds[0].selected_parameters == second.folds[0].selected_parameters
    assert first.folds[0].parameter_lock.lock_id == second.folds[0].parameter_lock.lock_id


def test_optional_selection_locks_best_passing_training_row(tmp_path):
    calls = []
    result = execute_walk_forward(
        _config(tmp_path, selection_size=None),
        _frame(),
        _audit(_frame()),
        evaluator=_fake_evaluator(calls),
        write_output=False,
    )
    assert result.folds[0].selection_result is None
    assert result.folds[0].selected_parameters["window"] == 14
    assert [call["stage"] for call in calls[:2]] == ["train", "test"]


def test_stability_and_aggregate_calculations_are_deterministic(tmp_path):
    choices = {
        "fold_001": 14,
        "fold_002": 14,
        "fold_003": 7,
        "fold_004": 7,
        "fold_005": 14,
    }
    config = _config(tmp_path)
    first = execute_walk_forward(
        config,
        _frame(),
        _audit(_frame()),
        evaluator=_fake_evaluator([], selection_choice=choices),
        write_output=False,
    )
    second = execute_walk_forward(
        config,
        _frame(),
        _audit(_frame()),
        evaluator=_fake_evaluator([], selection_choice=choices),
        write_output=False,
    )
    assert first.selected_parameters_by_fold == second.selected_parameters_by_fold
    assert first.unique_parameter_set_count == 2
    assert first.parameter_change_percentage == pytest.approx(0.5)
    assert first.maximum_consecutive_persistence == 2
    expected = (1.14 * 1.14 * 1.07 * 1.07 * 1.14) - 1
    assert first.compounded_return == pytest.approx(expected)
    assert first.total_trades == 56
    assert first.average_fold_metrics["total_return"] == pytest.approx(0.112)
    assert first.median_fold_metrics["total_return"] == pytest.approx(0.14)


def test_report_contains_fold_provenance_and_failures(tmp_path):
    config = _config(tmp_path)
    result = execute_walk_forward(
        config,
        _frame(),
        _audit(_frame()),
        evaluator=_fake_evaluator([], fail_training={"fold_001"}),
    )
    text = config.output_path.read_text(encoding="utf-8")
    assert result.total_fold_count == 5
    assert '"fold_001"' in text
    assert '"failed_folds": 1' in text
    assert '"parameter_change_percentage"' in text
