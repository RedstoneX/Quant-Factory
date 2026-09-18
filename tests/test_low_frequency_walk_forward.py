"""Low-frequency fixed-parameter walk-forward evidence tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from backtesting.experiments import ExperimentConfig
from backtesting.run_spy_donchian import DATA_CONFIG, _config as baseline_config
import backtesting.run_spy_donchian_low_frequency_walk_forward as donchian_lf
from backtesting.walk_forward import WalkForwardConfig
from backtesting.walk_forward.low_frequency import (
    LowFrequencyEvidenceConfig,
    LowFrequencyFoldEvidence,
    aggregate_low_frequency_evidence,
    execute_low_frequency_evidence,
)
from market_data.models import DataAudit

FIXED = {"entry_lookback": 20, "exit_lookback": 10}


def _frame(rows: int = 22, start: str = "2020-01-02") -> pd.DataFrame:
    index = pd.date_range(start, periods=rows, freq="B", tz="America/New_York")
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


def _experiment(tmp_path: Path, parameters=(FIXED,)) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="fixture_low_frequency",
        strategy_id="spy_donchian_trend_breakout_long",
        parameter_combinations=parameters,
        market_data=DATA_CONFIG,
        execution=baseline_config("longonly").execution,
        ranking_columns=("total_return", "sharpe_ratio"),
        ranking_ascending=(False, False),
        output_path=tmp_path / "fixture.csv",
        screening=baseline_config("longonly").screening,
    )


def _config(
    tmp_path: Path,
    *,
    minimum_validation_trades: int = 8,
    parameters=(FIXED,),
) -> LowFrequencyEvidenceConfig:
    walk_forward = WalkForwardConfig(
        experiment=_experiment(tmp_path, parameters),
        training_window_size=6,
        selection_window_size=None,
        test_window_size=4,
        step_size=4,
        training_mode="expanding",
        minimum_rows_per_window=2,
        shortlist_size=1,
        incomplete_final_window="drop",
        output_path=tmp_path / "evidence.json",
    )
    return LowFrequencyEvidenceConfig(
        walk_forward=walk_forward,
        fixed_parameters=FIXED,
        output_path=tmp_path / "evidence.json",
        minimum_validation_trades=minimum_validation_trades,
        forbidden_start_date="2024-05-28",
    )


def _fake_evaluator(calls: list[dict[str, object]], rows_by_fold=None):
    rows_by_fold = rows_by_fold or {}

    def evaluate(config, data, audit, *, write_output):
        assert write_output is False
        fold_id = config.experiment_id.split(":")[-2]
        calls.append(
            {
                "fold_id": fold_id,
                "parameters": tuple(dict(item) for item in config.parameter_combinations),
                "start": str(data.index[0].date()),
                "end": str(data.index[-1].date()),
            }
        )
        values = {
            "entry_lookback": 20,
            "exit_lookback": 10,
            "total_return": 0.02,
            "annualized_return": 0.04,
            "sharpe_ratio": 0.8,
            "max_drawdown": -0.05,
            "number_of_trades": 8,
            "win_rate": 0.6,
        } | rows_by_fold.get(fold_id, {})
        ranked = pd.DataFrame([values])
        return SimpleNamespace(ranked_results=ranked)

    return evaluate


def test_fold_chronology_non_overlap_and_fixed_parameters(tmp_path):
    calls: list[dict[str, object]] = []
    data = _frame()
    result = execute_low_frequency_evidence(
        _config(tmp_path),
        data,
        _audit(data),
        evaluator=_fake_evaluator(calls),
        write_output=False,
    )
    assert len(result.folds) == 4
    assert result.fixed_parameters == FIXED
    for fold in result.folds:
        assert fold.train_end < fold.validation_start
    assert result.folds[0].validation_end < result.folds[1].validation_start
    assert all(call["parameters"] == (FIXED,) for call in calls)


def test_configuration_requires_exactly_the_fixed_parameter_set(tmp_path):
    with pytest.raises(ValueError, match="only fixed_parameters"):
        _config(
            tmp_path,
            parameters=(
                FIXED,
                {"entry_lookback": 55, "exit_lookback": 10},
            ),
        )


def test_low_frequency_classification_is_locked_before_validation(tmp_path):
    with pytest.raises(ValueError, match="strategy_frequency"):
        replace(_config(tmp_path), strategy_frequency="daily")


def test_eight_trade_floor_marks_insufficient_not_passed(tmp_path):
    calls: list[dict[str, object]] = []
    data = _frame()
    result = execute_low_frequency_evidence(
        _config(tmp_path),
        data,
        _audit(data),
        evaluator=_fake_evaluator(
            calls,
            rows_by_fold={"fold_001": {"number_of_trades": 7}},
        ),
        write_output=False,
    )
    first = result.folds[0]
    assert first.evidence_status == "insufficient_evidence"
    assert first.performance_status == "insufficient_evidence"
    assert first.combined_status == "insufficient_evidence"


def test_failed_performance_is_distinct_from_insufficient_evidence(tmp_path):
    calls: list[dict[str, object]] = []
    data = _frame()
    result = execute_low_frequency_evidence(
        _config(tmp_path),
        data,
        _audit(data),
        evaluator=_fake_evaluator(
            calls,
            rows_by_fold={
                "fold_001": {
                    "number_of_trades": 8,
                    "total_return": -0.01,
                    "annualized_return": -0.02,
                    "sharpe_ratio": -0.2,
                }
            },
        ),
        write_output=False,
    )
    first = result.folds[0]
    assert first.evidence_status == "passed"
    assert first.performance_status == "failed"
    assert first.combined_status == "failed"


def _fold(
    fold_id: str,
    *,
    evidence: str = "passed",
    combined: str = "passed",
    drawdown: float = -0.05,
) -> LowFrequencyFoldEvidence:
    return LowFrequencyFoldEvidence(
        fold_id=fold_id,
        train_start="2020-01-01",
        train_end="2020-01-10",
        train_row_count=8,
        validation_start="2020-01-13",
        validation_end="2020-01-20",
        validation_row_count=6,
        parameters=dict(FIXED),
        trade_count=8 if evidence == "passed" else 7,
        total_return=0.01,
        annualized_return=0.02,
        sharpe_ratio=0.8,
        max_drawdown=drawdown,
        evidence_status=evidence,
        performance_status=combined if evidence == "passed" else "insufficient_evidence",
        combined_status=combined if evidence == "passed" else "insufficient_evidence",
    )


def test_aggregate_threshold_calculation(tmp_path):
    config = _config(tmp_path)
    passed = aggregate_low_frequency_evidence(
        (_fold("a"), _fold("b"), _fold("c", combined="failed")),
        config,
    )
    assert passed.status == "passed"
    assert passed.passing_fold_count == 2
    assert passed.passing_percentage == pytest.approx(2 / 3)

    failed = aggregate_low_frequency_evidence(
        (
            _fold("a", combined="failed"),
            _fold("b", combined="failed"),
            _fold("c"),
        ),
        config,
    )
    assert failed.status == "failed"
    assert "60%" in " ".join(failed.reasons)

    insufficient = aggregate_low_frequency_evidence(
        (_fold("a"), _fold("b", evidence="insufficient_evidence")),
        config,
    )
    assert insufficient.status == "insufficient_evidence"

    drawdown_breach = aggregate_low_frequency_evidence(
        (_fold("a"), _fold("b"), _fold("c", drawdown=-0.36)),
        config,
    )
    assert drawdown_breach.status == "failed"


def test_rejects_any_input_on_or_after_forbidden_start_date(tmp_path):
    calls: list[dict[str, object]] = []
    data = _frame(start="2024-05-23")
    with pytest.raises(ValueError, match="on or after 2024-05-28"):
        execute_low_frequency_evidence(
            _config(tmp_path),
            data,
            _audit(data),
            evaluator=_fake_evaluator(calls),
            write_output=False,
        )
    assert calls == []


def test_donchian_entrypoint_uses_one_fixed_candidate_and_pre_cutoff_boundary():
    assert donchian_lf.EXPERIMENT_CONFIG.parameter_combinations == (FIXED,)
    assert donchian_lf.LOW_FREQUENCY_CONFIG.strategy_frequency == "low_frequency"
    assert donchian_lf.FORBIDDEN_START_DATE == "2024-05-28"
    assert donchian_lf.WALK_FORWARD_CONFIG.selection_window_size is None
