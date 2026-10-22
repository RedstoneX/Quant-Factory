"""Low-frequency fixed-parameter walk-forward evidence tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments import ExperimentConfig
from backtesting.run_spy_donchian import DATA_CONFIG, _config as baseline_config
import backtesting.run_spy_donchian_low_frequency_walk_forward as donchian_lf
from backtesting.screening import ScreeningConfig
from backtesting.walk_forward import WalkForwardConfig
from backtesting.walk_forward.low_frequency import (
    LowFrequencyEvidenceConfig,
    LowFrequencyFoldEvidence,
    aggregate_low_frequency_evidence,
    execute_low_frequency_evidence,
)
from market_data.models import DataAudit

FIXED = {"entry_lookback": 20, "exit_lookback": 10}


def _frame(rows: int = 288, start: str = "2020-01-02", flat=(), slide=()) -> pd.DataFrame:
    """36-bar staircase (24 bars of +1, 12 of -0.75): one Donchian breakout per cycle.

    Flattening a region removes every trade in it; sliding one turns it into a
    steady -0.5 per bar decline from its first bar.
    """
    index = pd.date_range(start, periods=rows, freq="B", tz="America/New_York")
    steps = np.tile(np.array([1.0] * 24 + [-0.75] * 12), rows // 36 + 1)[:rows]
    close = pd.Series(100 + np.cumsum(steps), index=index)
    for begin, end in flat:
        close.iloc[begin:end] = close.iloc[begin]
    for begin, end in slide:
        close.iloc[begin:end] = close.iloc[begin] - 0.5 * np.arange(end - begin)
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


licensed = pytest.mark.licensed_vectorbt
SCREENING = ScreeningConfig(
    minimum_trades=1,
    minimum_total_return=0.0,
    minimum_annualized_return=0.0,
    minimum_sharpe_ratio=None,
    maximum_drawdown=0.35,
)
# Expanding folds: train 0-72, then validation windows of one 36-bar cycle each.
FIRST_VALIDATION = (72, 108)


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
        screening=SCREENING,
    )


def _config(
    tmp_path: Path,
    *,
    minimum_validation_trades: int = 1,
    parameters=(FIXED,),
) -> LowFrequencyEvidenceConfig:
    walk_forward = WalkForwardConfig(
        experiment=_experiment(tmp_path, parameters),
        training_window_size=72,
        selection_window_size=None,
        test_window_size=36,
        step_size=36,
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


@licensed
def test_fold_chronology_non_overlap_and_fixed_parameters(tmp_path):
    data = _frame()
    result = execute_low_frequency_evidence(
        _config(tmp_path), data, _audit(data), write_output=False
    )
    assert len(result.folds) == 6
    assert result.fixed_parameters == FIXED
    for fold in result.folds:
        assert fold.train_end < fold.validation_start
        assert fold.parameters == FIXED
        assert fold.trade_count >= 1
        assert fold.combined_status == "passed"
    assert result.folds[0].validation_end < result.folds[1].validation_start


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


@licensed
def test_trade_floor_marks_insufficient_not_passed(tmp_path):
    # A flat first validation window has no breakout, so it sits below the floor.
    data = _frame(flat=(FIRST_VALIDATION,))
    result = execute_low_frequency_evidence(
        _config(tmp_path), data, _audit(data), write_output=False
    )
    first = result.folds[0]
    assert first.trade_count == 0
    assert result.folds[1].combined_status == "passed"
    assert first.evidence_status == "insufficient_evidence"
    assert first.performance_status == "insufficient_evidence"
    assert first.combined_status == "insufficient_evidence"


@licensed
def test_failed_performance_is_distinct_from_insufficient_evidence(tmp_path):
    # The first validation window breaks out, then slides down: one trade that loses money.
    data = _frame(slide=((FIRST_VALIDATION[0] + 12, FIRST_VALIDATION[1]),))
    result = execute_low_frequency_evidence(
        _config(tmp_path), data, _audit(data), write_output=False
    )
    first = result.folds[0]
    assert first.trade_count >= 1
    assert first.total_return < 0
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
    data = _frame(start="2024-05-23")
    with pytest.raises(ValueError, match="on or after 2024-05-28"):
        execute_low_frequency_evidence(
            _config(tmp_path), data, _audit(data), write_output=False
        )


def test_donchian_entrypoint_uses_one_fixed_candidate_and_pre_cutoff_boundary():
    assert donchian_lf.EXPERIMENT_CONFIG.parameter_combinations == (FIXED,)
    assert donchian_lf.LOW_FREQUENCY_CONFIG.strategy_frequency == "low_frequency"
    assert donchian_lf.FORBIDDEN_START_DATE == "2024-05-28"
    assert donchian_lf.WALK_FORWARD_CONFIG.selection_window_size is None
