"""Full-history signals for walk-forward / out-of-sample evaluation.

Signals are computed once on the full history: each window keeps its indicator warm-up,
a window's results do not depend on any bar after it (no look-ahead), and one parameter
set's signals are generated once however many windows are evaluated. Fold boundaries are
unchanged; tests/test_splitter_library_parity.py proves VectorBT PRO ``Splitter`` yields them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments import execute_experiment
from backtesting.run_spy_donchian import _config as donchian_config
from backtesting.walk_forward import WalkForwardConfig
from backtesting.walk_forward.runner import execute_walk_forward
from strategies import get_strategy
from tests.test_spy_donchian_oos import _audit

pytestmark = pytest.mark.licensed_vectorbt


def _wf_config(train, selection, test, step, mode, policy, minimum, experiment):
    return WalkForwardConfig(
        experiment=experiment,
        training_window_size=train,
        selection_window_size=selection or None,
        test_window_size=test,
        step_size=step,
        training_mode=mode,
        minimum_rows_per_window=minimum,
        shortlist_size=1,
        incomplete_final_window=policy,
        output_path=Path("unused.json"),
    )


# --- 2. full-history signals ----------------------------------------------------------------


def _market(rows: int = 900, seed: int = 7) -> pd.DataFrame:
    index = pd.bdate_range("2018-01-02", periods=rows, tz="America/New_York")
    close = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0, 0.012, rows))), index=index)
    open_ = close.shift(1).fillna(close.iloc[0])
    return pd.DataFrame(
        {
            "Open": open_,
            "High": np.maximum(open_, close) * 1.004,
            "Low": np.minimum(open_, close) * 0.996,
            "Close": close,
            "Volume": 1_000,
        },
        index=index,
    )


DONCHIAN = donchian_config("longonly")


def test_full_history_signals_differ_from_slice_only_in_the_warm_up():
    data = _market()
    strategy = get_strategy(DONCHIAN.strategy_id)
    for supplied in DONCHIAN.parameter_combinations:
        normalized = strategy.validate_parameters(dict(supplied))
        full = strategy.generate_signals(data, normalized)
        start, stop = 400, 600
        window = strategy.generate_signals(data.iloc[start:stop], normalized)
        warm_up = normalized["entry_lookback"]  # longest rolling window (prior-bar channel)
        for name in ("entries", "exits"):
            ours, sliced = getattr(full, name).iloc[start:stop], getattr(window, name)
            assert ours.iloc[warm_up:].equals(sliced.iloc[warm_up:])


def test_window_result_does_not_depend_on_later_bars():
    data = _market()
    audit = _audit(data)
    window = (data.index[400], data.index[599])
    full = execute_experiment(DONCHIAN, data, audit, write_output=False, evaluation_range=window)
    truncated = execute_experiment(
        DONCHIAN, data.loc[: window[1]], audit, write_output=False, evaluation_range=window
    )
    metrics = ["total_return", "number_of_trades", "sharpe_ratio", "max_drawdown"]
    pd.testing.assert_frame_equal(full.ranked_results[metrics], truncated.ranked_results[metrics])


def test_whole_range_matches_a_plain_run():
    data = _market(500)
    audit = _audit(data)
    plain = execute_experiment(DONCHIAN, data, audit, write_output=False)
    ranged = execute_experiment(
        DONCHIAN, data, audit, write_output=False, evaluation_range=(data.index[0], data.index[-1])
    )
    pd.testing.assert_frame_equal(plain.ranked_results, ranged.ranked_results)


def test_signals_are_generated_once_per_parameter_set(monkeypatch):
    data = _market()
    strategy_type = type(get_strategy(DONCHIAN.strategy_id))
    calls: list[int] = []
    original = strategy_type.generate_signals

    def counting(self, frame, parameters):
        calls.append(len(frame))
        return original(self, frame, parameters)

    monkeypatch.setattr(strategy_type, "generate_signals", counting)
    config = _wf_config(300, 100, 100, 100, "rolling", "drop", 30, experiment=DONCHIAN)
    result = execute_walk_forward(config, data, _audit(data), write_output=False)
    assert result.total_fold_count == 5
    assert len(calls) == len(DONCHIAN.parameter_combinations)
    assert set(calls) == {len(data)}
