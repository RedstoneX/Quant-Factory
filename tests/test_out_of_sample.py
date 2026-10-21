"""Chronological out-of-sample evaluation driven by the real experiment engine.

The price series is a 12-bar sawtooth (ten bars of -2, two bars of +11): the
real RSI mean-reversion strategy enters once per cycle near the trough and
exits on the rebound.  Flattening a region removes every trade in it, which is
how each screening failure is triggered with real inputs.
"""

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
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
from backtesting.screening import ScreeningConfig
from market_data.models import DataAudit

licensed = pytest.mark.licensed_vectorbt

FAST_EXIT = {"window": 7, "entry_threshold": 30, "exit_threshold": 50}
SLOW_EXIT = {"window": 7, "entry_threshold": 30, "exit_threshold": 60}
NEVER_ENTERS = {"window": 21, "entry_threshold": 30, "exit_threshold": 50}
SCREENING = ScreeningConfig(
    minimum_trades=1,
    minimum_total_return=0.0,
    minimum_annualized_return=0.0,
    minimum_sharpe_ratio=0.5,
    maximum_drawdown=0.35,
)
# 120 rows split 60/20/20: train bars 0-72, selection 72-96, test 96-120.
TRAIN, SELECTION, TEST = (0, 72), (72, 96), (96, 120)


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
    shortlist_size: int = 1,
    parameters: tuple[dict[str, int], ...] = (FAST_EXIT, SLOW_EXIT),
) -> OutOfSampleConfig:
    experiment = replace(
        EXPERIMENT_CONFIG,
        parameter_combinations=parameters,
        screening=SCREENING,
        output_path=tmp_path / "base.csv",
    )
    return OutOfSampleConfig(
        experiment=experiment,
        split=ChronologicalSplitConfig(minimum_rows_per_partition=10),
        output_path=tmp_path / "oos.json",
        shortlist_size=shortlist_size,
    )


def _run(tmp_path, data, *, write_output=False, **config_kwargs):
    return execute_out_of_sample(
        _config(tmp_path, **config_kwargs), data, _audit(data), write_output=write_output
    )


def _partition(result) -> str:
    return result.experiment_id.split(":")[-1]


def _top_passing_parameters(result) -> dict[str, int]:
    """Parameters of the best-ranked row that passed the real screen."""
    row_id = result.passing_results.iloc[0]["parameter_row_id"]
    match = next(item for item in result.screening_results if item.parameter_row_id == row_id)
    return dict(match.normalized_parameters)


def test_split_is_contiguous_chronological_and_deterministic():
    data = _frame()
    config = ChronologicalSplitConfig(minimum_rows_per_partition=10)
    first = split_chronologically(data, config)
    second = split_chronologically(data, config)
    assert (first.train.row_count, first.selection.row_count, first.test.row_count) == (
        72,
        24,
        24,
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


@licensed
def test_selection_excludes_test_and_lock_precedes_single_test_evaluation(tmp_path):
    result = _run(tmp_path, _frame())
    stages = (result.training_result, result.selection_result, result.test_result)
    assert [_partition(stage) for stage in stages] == ["train", "selection", "test"]
    audits = [stage.market_data_audit for stage in stages]
    assert audits[0].actual_last_row_date < audits[1].actual_first_row_date
    assert audits[1].actual_last_row_date < audits[2].actual_first_row_date
    assert len(result.training_result.normalized_parameters) == 2
    assert result.shortlist_parameters == (_top_passing_parameters(result.training_result),)
    assert result.selection_result.normalized_parameters == result.shortlist_parameters
    assert result.selected_parameters == _top_passing_parameters(result.selection_result)
    assert result.test_result.normalized_parameters == (result.selected_parameters,)
    assert dict(result.parameter_lock.normalized_parameters) == result.selected_parameters
    assert result.test_result.ranked_results.iloc[0]["number_of_trades"] >= 1


@licensed
def test_only_passing_training_shortlist_reaches_selection(tmp_path):
    # RSI(21) never dips below 30 on this series, so that candidate has no trade.
    result = _run(tmp_path, _frame(), shortlist_size=2, parameters=(FAST_EXIT, NEVER_ENTERS))
    assert len(result.training_result.normalized_parameters) == 2
    assert len(result.training_result.passing_results) == 1
    assert result.shortlist_parameters == (FAST_EXIT,)
    assert result.selection_result.normalized_parameters == (FAST_EXIT,)


@licensed
def test_stable_tie_breaking_controls_shortlist_membership(tmp_path):
    first = _run(tmp_path, _frame(), shortlist_size=1)
    second = _run(tmp_path, _frame(), shortlist_size=1)
    assert len(first.training_result.passing_results) == 2
    assert first.shortlist_parameters == second.shortlist_parameters
    assert first.shortlist_parameters == (_top_passing_parameters(first.training_result),)


@licensed
def test_no_training_survivor_reason_leads_with_screen_rejection(tmp_path):
    with pytest.raises(OutOfSampleProgressionError) as excinfo:
        _run(tmp_path, _frame(flat=(TRAIN,)))
    assert str(excinfo.value).startswith("lost money on the years it was built on")
    assert "training slice" in str(excinfo.value)


@licensed
def test_no_training_survivor_stops_before_selection_and_test(tmp_path):
    with pytest.raises(OutOfSampleProgressionError, match="selection was not evaluated"):
        _run(tmp_path, _frame(flat=(TRAIN,)), write_output=True)
    report = json.loads((tmp_path / "oos.json").read_text())
    assert report["failure_stage"] == "training"
    assert report["training_status"] == "screened_out"
    assert report["selection_status"] == "not_run"
    assert report["test_status"] == "not_run"


@licensed
def test_no_selection_survivor_stops_before_lock_and_test(tmp_path):
    with pytest.raises(OutOfSampleProgressionError, match="parameters were not locked"):
        _run(tmp_path, _frame(flat=(SELECTION,)), write_output=True)
    report = json.loads((tmp_path / "oos.json").read_text())
    assert report["failure_stage"] == "selection"
    assert report["training_status"] == "passed"
    assert report["selection_status"] == "screened_out"
    assert report["test_status"] == "not_run"
    assert report["parameter_lock"] is None


@licensed
def test_held_out_values_cannot_change_selected_parameters(tmp_path):
    first = _run(tmp_path, _frame())
    second = _run(tmp_path, _frame(flat=(TEST,)))
    assert first.selected_parameters == second.selected_parameters
    assert first.shortlist_parameters == second.shortlist_parameters
    assert first.parameter_lock.lock_id == second.parameter_lock.lock_id
    assert first.test_result.ranked_results.iloc[0]["number_of_trades"] >= 1
    assert second.test_result.ranked_results.iloc[0]["number_of_trades"] == 0


@licensed
def test_report_records_split_lock_and_test_only_metrics(tmp_path):
    result = _run(tmp_path, _frame(), write_output=True)
    text = (tmp_path / "oos.json").read_text(encoding="utf-8")
    assert result.parameter_lock.lock_id in text
    assert '"train"' in text and '"selection"' in text and '"test"' in text
    assert '"test_metrics"' in text


# --- Unseen data gate, owner ruling 19 Oct 2026: no Sharpe minimum, net return > 0.


@licensed
def test_unseen_gate_passes_on_net_return_without_a_sharpe_minimum(tmp_path):
    result = _run(tmp_path, _frame(), write_output=True)
    assert result.training_result.screening_config.minimum_sharpe_ratio is None
    assert result.test_result.ranked_results.iloc[0]["screening_status"] == "passed"
    report = json.loads((tmp_path / "oos.json").read_text())
    assert report["test_status"] == "passed"
    assert report["metrics"]["total_return"] > 0
    assert report["metrics"]["sharpe_ratio"] == pytest.approx(
        float(result.test_result.ranked_results.iloc[0]["sharpe_ratio"])
    )


@licensed
def test_unseen_gate_fails_when_test_net_return_is_not_positive(tmp_path):
    result = _run(tmp_path, _frame(flat=(TEST,)))
    row = result.test_result.ranked_results.iloc[0]
    assert row["total_return"] == 0
    assert row["screening_status"] == "screened_out"


@licensed
def test_unseen_gate_fails_when_every_setting_lost_money_on_training(tmp_path):
    with pytest.raises(
        OutOfSampleProgressionError, match="^lost money on the years it was built on"
    ):
        _run(tmp_path, _frame(flat=(TRAIN,)), write_output=True)


def test_cost_screen_keeps_its_sharpe_minimum():
    from backtesting.out_of_sample.runner import unseen_data_screening

    assert EXPERIMENT_CONFIG.screening.minimum_sharpe_ratio == 0.5
    relaxed = unseen_data_screening(EXPERIMENT_CONFIG)
    assert relaxed.screening.minimum_sharpe_ratio is None
    assert EXPERIMENT_CONFIG.screening.minimum_sharpe_ratio == 0.5
