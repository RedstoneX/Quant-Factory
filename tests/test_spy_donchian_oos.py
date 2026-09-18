"""Donchian-specific chronological out-of-sample tests."""

from __future__ import annotations

from pathlib import Path
import json
from types import SimpleNamespace

import pandas as pd
import pytest

import backtesting.run_spy_donchian_oos as donchian_oos
from backtesting.out_of_sample import (
    OutOfSampleProgressionError,
    execute_out_of_sample,
    split_chronologically,
)
from backtesting.robustness import load_lock_artifact
from backtesting.screening import parameter_row_identity
from market_data.models import DataAudit


def _frame(rows: int = 180) -> pd.DataFrame:
    index = pd.date_range("2020-01-02", periods=rows, freq="B", tz="America/New_York")
    values = pd.Series(range(rows), index=index, dtype=float) + 100
    return pd.DataFrame(
        {
            "Open": values,
            "High": values + 1,
            "Low": values - 1,
            "Close": values,
            "Volume": 1_000,
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


def _fake_evaluator(
    calls: list[dict[str, object]],
    *,
    passing_by_partition: dict[str, set[tuple[int, int]]] | None = None,
):
    def evaluate(config, data, audit, *, write_output):
        assert write_output is False
        partition = config.experiment_id.rsplit(":", 1)[-1]
        calls.append(
            {
                "partition": partition,
                "start": str(data.index[0].date()),
                "end": str(data.index[-1].date()),
                "parameters": tuple(dict(item) for item in config.parameter_combinations),
            }
        )
        rows = []
        screening = []
        for parameters in config.parameter_combinations:
            normalized = dict(parameters)
            pair = (normalized["entry_lookback"], normalized["exit_lookback"])
            row_id = parameter_row_identity(
                config.experiment_id,
                config.strategy_id,
                normalized,
            )
            if partition == "test":
                score = -normalized["entry_lookback"]
            else:
                score = (
                    normalized["entry_lookback"] / 100
                    - normalized["exit_lookback"] / 1000
                )
            passed = (
                passing_by_partition is None
                or pair in passing_by_partition.get(partition, set())
            )
            rows.append(
                {
                    "parameter_row_id": row_id,
                    "entry_lookback": normalized["entry_lookback"],
                    "exit_lookback": normalized["exit_lookback"],
                    "total_return": score,
                    "annualized_return": score / 2,
                    "sharpe_ratio": 1.0 if passed else -1.0,
                    "max_drawdown": -0.1,
                    "number_of_trades": 30,
                    "win_rate": 0.6,
                    "screening_status": "passed" if passed else "screened_out",
                    "screening_rejection_reasons": "" if passed else "fixture rejection",
                }
            )
            screening.append(
                SimpleNamespace(
                    parameter_row_id=row_id,
                    normalized_parameters=normalized,
                    passed=passed,
                )
            )
        ranked = pd.DataFrame(rows).sort_values(
            ["screening_status", "total_return", "entry_lookback", "exit_lookback"],
            ascending=[True, False, True, True],
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
        108,
        36,
        36,
    )
    assert split.train.end < split.selection.start < split.test.start
    assert set(split.train.data.index).isdisjoint(split.selection.data.index)
    assert set(split.selection.data.index).isdisjoint(split.test.data.index)


def test_training_failure_stops_before_selection_and_test() -> None:
    data = _frame()
    calls: list[dict[str, object]] = []
    with pytest.raises(OutOfSampleProgressionError, match="training screening"):
        execute_out_of_sample(
            donchian_oos.OOS_CONFIG,
            data,
            _audit(data),
            evaluator=_fake_evaluator(calls, passing_by_partition={"train": set()}),
            write_output=False,
        )
    assert [call["partition"] for call in calls] == ["train"]


def test_selection_failure_stops_before_lock_and_test() -> None:
    data = _frame()
    calls: list[dict[str, object]] = []
    with pytest.raises(OutOfSampleProgressionError, match="selection screening"):
        execute_out_of_sample(
            donchian_oos.OOS_CONFIG,
            data,
            _audit(data),
            evaluator=_fake_evaluator(
                calls,
                passing_by_partition={
                    "train": {(20, 10), (55, 20), (55, 10)},
                    "selection": set(),
                },
            ),
            write_output=False,
        )
    assert [call["partition"] for call in calls] == ["train", "selection"]


def test_selection_failure_writes_no_lock_failure_artifact(tmp_path: Path) -> None:
    data = _frame()
    calls: list[dict[str, object]] = []
    config = donchian_oos.OOS_CONFIG.__class__(
        experiment=donchian_oos.OOS_CONFIG.experiment,
        split=donchian_oos.OOS_CONFIG.split,
        output_path=tmp_path / "spy_donchian_oos.json",
        shortlist_size=donchian_oos.OOS_CONFIG.shortlist_size,
    )
    with pytest.raises(OutOfSampleProgressionError, match="selection screening"):
        execute_out_of_sample(
            config,
            data,
            _audit(data),
            evaluator=_fake_evaluator(
                calls,
                passing_by_partition={
                    "train": {(20, 10), (55, 20), (55, 10)},
                    "selection": set(),
                },
            ),
        )
    payload = json.loads(config.output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["failure_stage"] == "selection"
    assert payload["selection_status"] == "screened_out"
    assert payload["test_status"] == "not_run"
    assert payload["parameter_lock"] is None
    assert payload["metrics"] == {}


def test_lock_precedes_exactly_one_test_candidate_and_test_cannot_reselect() -> None:
    data = _frame()
    calls: list[dict[str, object]] = []
    result = execute_out_of_sample(
        donchian_oos.OOS_CONFIG,
        data,
        _audit(data),
        evaluator=_fake_evaluator(calls),
        write_output=False,
    )
    assert [call["partition"] for call in calls] == ["train", "selection", "test"]
    assert len(calls[0]["parameters"]) == 3
    assert len(calls[1]["parameters"]) == 3
    assert len(calls[2]["parameters"]) == 1
    assert result.selected_parameters == {"entry_lookback": 55, "exit_lookback": 10}
    assert calls[2]["parameters"] == (result.selected_parameters,)
    assert dict(result.parameter_lock.normalized_parameters) == result.selected_parameters
    assert result.test_result.ranked_results.iloc[0]["total_return"] == -55


def test_test_partition_values_cannot_change_shortlist_or_lock() -> None:
    data = _frame()
    first = execute_out_of_sample(
        donchian_oos.OOS_CONFIG,
        data,
        _audit(data),
        evaluator=_fake_evaluator([]),
        write_output=False,
    )
    changed = data.copy()
    changed.iloc[144:, changed.columns.get_loc("Close")] = -1_000_000
    second = execute_out_of_sample(
        donchian_oos.OOS_CONFIG,
        changed,
        _audit(changed),
        evaluator=_fake_evaluator([]),
        write_output=False,
    )
    assert first.shortlist_parameters == second.shortlist_parameters
    assert first.selected_parameters == second.selected_parameters
    assert first.parameter_lock.lock_id == second.parameter_lock.lock_id


def test_schema_compatible_artifact_loads_for_robustness(tmp_path: Path) -> None:
    data = _frame()
    config = donchian_oos.OOS_CONFIG.__class__(
        experiment=donchian_oos.OOS_CONFIG.experiment,
        split=donchian_oos.OOS_CONFIG.split,
        output_path=tmp_path / "spy_donchian_oos.json",
        shortlist_size=donchian_oos.OOS_CONFIG.shortlist_size,
    )
    execute_out_of_sample(
        config,
        data,
        _audit(data),
        evaluator=_fake_evaluator([]),
    )
    evidence = load_lock_artifact(
        config.output_path,
        expected_experiment_id="spy_donchian_daily_long_oos",
        expected_strategy_id="spy_donchian_trend_breakout_long",
        expected_strategy_version="1.0.0",
        expected_execution={"execution_mode": "next_bar_open", "fees": 0.0005},
    )
    assert evidence.status == "passed"
    assert evidence.locked_parameters == {"entry_lookback": 55, "exit_lookback": 10}
    assert evidence.metrics["number_of_trades"] == 30
