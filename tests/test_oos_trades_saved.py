"""The locked out-of-sample test run hands its portfolio to an observer, so its trades can be saved."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from backtesting.out_of_sample import ChronologicalSplitConfig, OutOfSampleConfig, execute_out_of_sample
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.screening import ScreeningConfig
from orchestration.candidate_pipeline_screening_evidence import capture_screening_portfolios
from tests.test_out_of_sample import _audit

pytestmark = pytest.mark.licensed_vectorbt


def _wavy(rows: int = 600) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D", tz="America/New_York")
    close = pd.Series(100 + 10 * np.sin(np.arange(rows) / 5.0), index=index)
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Volume": 1000.0}, index=index)


def test_oos_test_partition_portfolio_is_observed_once(tmp_path):
    data = _wavy()
    experiment = replace(
        EXPERIMENT_CONFIG,
        parameter_combinations=({"window": 7, "entry_threshold": 30, "exit_threshold": 55},),
        output_path=tmp_path / "base.csv",
        screening=ScreeningConfig(minimum_trades=1, minimum_total_return=-1.0, minimum_annualized_return=-1.0,
                                  minimum_sharpe_ratio=-100.0, maximum_drawdown=1.0),
    )
    config = OutOfSampleConfig(
        experiment=experiment,
        split=ChronologicalSplitConfig(minimum_rows_per_partition=10),
        output_path=tmp_path / "oos.json",
        shortlist_size=1,
    )
    captured: dict = {}
    result = execute_out_of_sample(
        config, data, _audit(data), write_output=False,
        test_portfolio_observer=capture_screening_portfolios(captured),
    )
    row = result.test_result.ranked_results.iloc[0]
    assert list(captured) == [row["parameter_row_id"]]
    trades = captured[row["parameter_row_id"]].trades
    assert len(trades) == row["number_of_trades"]
    assert len(trades) > 0
