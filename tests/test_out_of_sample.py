"""Deterministic tests for chronological held-out evaluation."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from backtesting.out_of_sample import (
    ChronologicalSplitConfig,
    OutOfSampleConfig,
    OutOfSampleProgressionError,
    execute_out_of_sample,
    split_chronologically,
)
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.screening import parameter_row_identity
from market_data.models import DataAudit


def _frame(rows: int = 100) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D", tz="America/New_York")
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


def _config(tmp_path: Path, *, shortlist_size: int = 1) -> OutOfSampleConfig:
    experiment = replace(
        EXPERIMENT_CONFIG,
        parameter_combinations=(
            {"window": 7, "entry_threshold": 20, "exit_threshold": 50},
            {"window": 14, "entry_threshold": 25, "exit_threshold": 55},
        ),
        output_path=tmp_path / "base.csv",
    )
    return OutOfSampleConfig(
        experiment=experiment,
        split=ChronologicalSplitConfig(minimum_rows_per_partition=10),
        output_path=tmp_path / "oos.json",
        shortlist_size=shortlist_size,
    )


def _fake_evaluator(
    calls: list[dict[str, object]],
    *,
    passing_windows: dict[str, set[int]] | None = None,
    training_tie: bool = False,
):
    def evaluate(config, data, audit, *, write_output):
        assert write_output is False
        calls.append(
            {
                "partition": config.experiment_id.rsplit(":", 1)[-1],
                "start": str(data.index[0].date()),
                "end": str(data.index[-1].date()),
                "parameters": tuple(dict(item) for item in config.parameter_combinations),
            }
        )
        results = []
        screening = []
        for parameters in config.parameter_combinations:
            normalized = dict(parameters)
            row_id = parameter_row_identity(
                config.experiment_id,
                config.strategy_id,
                normalized,
            )
            # Selection deterministically prefers the larger window. Test would
            # prefer the smaller one, proving test metrics cannot reselect it.
            partition = config.experiment_id.rsplit(":", 1)[-1]
            score = (
                1
                if partition == "train" and training_tie
                else normalized["window"] if partition != "test" else -normalized["window"]
            )
            passed = (
                passing_windows is None
                or normalized["window"] in passing_windows.get(partition, set())
            )
            results.append(
                {
                    "parameter_row_id": row_id,
                    "total_return": score,
                    "window": normalized["window"],
                    "screening_status": "passed" if passed else "screened_out",
                }
            )
            screening.append(
                SimpleNamespace(
                    parameter_row_id=row_id,
                    normalized_parameters=normalized,
                    passed=passed,
                )
            )
        ranked = pd.DataFrame(results).sort_values(
            ["screening_status", "total_return", "window"],
            ascending=[True, False, True],
            key=lambda values: values.map({"passed": 0, "screened_out": 1})
            if values.name == "screening_status"
            else values,
            kind="mergesort",
        ).reset_index(drop=True)
        passing = ranked.loc[ranked["screening_status"] == "passed"].reset_index(
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


def test_split_is_contiguous_chronological_and_deterministic():
    data = _frame()
    config = ChronologicalSplitConfig(minimum_rows_per_partition=10)
    first = split_chronologically(data, config)
    second = split_chronologically(data, config)
    assert (first.train.row_count, first.selection.row_count, first.test.row_count) == (
        60,
        20,
        20,
    )
    assert first.train.end < first.selection.start < first.test.start
    assert first.train.data.equals(second.train.data)
    assert set(first.train.data.index).isdisjoint(first.test.data.index)


@pytest.mark.parametrize("mutation", ["reverse", "duplicate", "too_short"])
def test_split_rejects_unsafe_inputs(mutation):
    data = _frame()
    config = ChronologicalSplitConfig(minimum_rows_per_partition=10)
    if mutation == "reverse":
        data = data.iloc[::-1]
    elif mutation == "duplicate":
        data.index = pd.DatetimeIndex([data.index[0]] * len(data))
    else:
        data = data.iloc[:20]
    with pytest.raises(ValueError):
        split_chronologically(data, config)


def test_fraction_policy_validation():
    with pytest.raises(ValueError, match="sum to one"):
        ChronologicalSplitConfig(0.5, 0.2, 0.2)
    with pytest.raises(ValueError, match="between zero and one"):
        ChronologicalSplitConfig(0.0, 0.5, 0.5)


@pytest.mark.parametrize("value", [0, -1])
def test_shortlist_size_must_be_positive(tmp_path, value):
    with pytest.raises(ValueError, match="shortlist_size must be positive"):
        replace(_config(tmp_path), shortlist_size=value)


def test_shortlist_size_rejects_non_integer(tmp_path):
    with pytest.raises(TypeError, match="shortlist_size must be int"):
        replace(_config(tmp_path), shortlist_size=1.5)


def test_selection_excludes_test_and_lock_precedes_single_test_evaluation(tmp_path):
    data = _frame()
    calls: list[dict[str, object]] = []
    result = execute_out_of_sample(
        _config(tmp_path),
        data,
        _audit(data),
        evaluator=_fake_evaluator(calls),
        write_output=False,
    )
    assert [call["partition"] for call in calls] == ["train", "selection", "test"]
    assert calls[1]["end"] < calls[2]["start"]
    assert len(calls[0]["parameters"]) == 2
    assert len(calls[1]["parameters"]) == 1
    assert len(calls[2]["parameters"]) == 1
    assert result.selected_parameters["window"] == 14
    assert calls[2]["parameters"] == (result.selected_parameters,)
    assert dict(result.parameter_lock.normalized_parameters) == result.selected_parameters
    assert result.shortlist_parameters == calls[1]["parameters"]


def test_only_passing_training_shortlist_reaches_selection(tmp_path):
    data = _frame()
    calls: list[dict[str, object]] = []
    result = execute_out_of_sample(
        _config(tmp_path, shortlist_size=2),
        data,
        _audit(data),
        evaluator=_fake_evaluator(
            calls,
            passing_windows={"train": {7}, "selection": {7}, "test": {7}},
        ),
        write_output=False,
    )
    assert len(calls[0]["parameters"]) == 2
    assert calls[1]["parameters"] == (
        {"window": 7, "entry_threshold": 20, "exit_threshold": 50},
    )
    assert result.shortlist_parameters == calls[1]["parameters"]


def test_stable_tie_breaking_controls_shortlist_membership(tmp_path):
    data = _frame()
    calls: list[dict[str, object]] = []
    execute_out_of_sample(
        _config(tmp_path, shortlist_size=1),
        data,
        _audit(data),
        evaluator=_fake_evaluator(calls, training_tie=True),
        write_output=False,
    )
    assert calls[1]["parameters"][0]["window"] == 7


def test_no_training_survivor_stops_before_selection_and_test(tmp_path):
    data = _frame()
    calls: list[dict[str, object]] = []
    with pytest.raises(
        OutOfSampleProgressionError,
        match="training screening produced no passing candidates; selection was not evaluated",
    ):
        execute_out_of_sample(
            _config(tmp_path),
            data,
            _audit(data),
            evaluator=_fake_evaluator(
                calls,
                passing_windows={"train": set(), "selection": {7}, "test": {7}},
            ),
            write_output=False,
        )
    assert [call["partition"] for call in calls] == ["train"]


def test_no_selection_survivor_stops_before_lock_and_test(tmp_path):
    data = _frame()
    calls: list[dict[str, object]] = []
    with pytest.raises(
        OutOfSampleProgressionError,
        match="selection screening produced no passing candidates; parameters were not locked",
    ):
        execute_out_of_sample(
            _config(tmp_path),
            data,
            _audit(data),
            evaluator=_fake_evaluator(
                calls,
                passing_windows={"train": {7, 14}, "selection": set(), "test": {7}},
            ),
            write_output=False,
        )
    assert [call["partition"] for call in calls] == ["train", "selection"]


def test_held_out_values_cannot_change_selected_parameters(tmp_path):
    data = _frame()
    config = _config(tmp_path)
    first = execute_out_of_sample(
        config, data, _audit(data), evaluator=_fake_evaluator([]), write_output=False
    )
    changed = data.copy()
    changed.iloc[80:, changed.columns.get_loc("Close")] = -1_000_000
    second = execute_out_of_sample(
        config,
        changed,
        _audit(changed),
        evaluator=_fake_evaluator([]),
        write_output=False,
    )
    assert first.selected_parameters == second.selected_parameters
    assert first.shortlist_parameters == second.shortlist_parameters
    assert first.parameter_lock.lock_id == second.parameter_lock.lock_id


def test_report_records_split_lock_and_test_only_metrics(tmp_path):
    data = _frame()
    config = _config(tmp_path)
    result = execute_out_of_sample(
        config, data, _audit(data), evaluator=_fake_evaluator([])
    )
    text = config.output_path.read_text(encoding="utf-8")
    assert result.parameter_lock.lock_id in text
    assert '"train"' in text and '"selection"' in text and '"test"' in text
    assert '"test_metrics"' in text
