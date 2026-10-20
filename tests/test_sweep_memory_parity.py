"""The VectorBT PRO mono-chunk sweep gives the same results at every chunk size and cache budget.

Chunk size equal to the grid is one all-settings simulation with every signal generated up
front (the pre-chunking behaviour); smaller chunks must not change a single metric, trade,
luck statistic or the chosen setting, on the whole history and inside a walk-forward window.
A signal cache that evicts (or caches nothing) must not change walk-forward or out-of-sample.
"""

from __future__ import annotations

import re
from functools import partial

import numpy as np
import pandas as pd
import pytest

import backtesting.experiments.chunking as chunking
import backtesting.experiments.runner as runner
import backtesting.experiments.windows as windows
from backtesting.experiments import SignalResult, execute_experiment
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from tests.test_spy_donchian_oos import _audit
from tests.test_walk_forward_splitter_vbt import DONCHIAN, _market

pytestmark = pytest.mark.licensed_vectorbt


def _sweep(chunk: int, evaluation_range=None, signal_cache=None):
    data = _market()
    trades: dict[str, pd.DataFrame] = {}
    result = execute_experiment(
        DONCHIAN, data, _audit(data), write_output=False, evaluation_range=evaluation_range,
        signal_cache=signal_cache, chunk_settings=chunk,
        portfolio_observer=lambda row_id, pf: trades.__setitem__(row_id, pf.trades.records_readable),
    )
    return result, trades


def _assert_same(left, right) -> None:
    (result, trades), (other, other_trades) = left, right
    pd.testing.assert_frame_equal(result.ranked_results, other.ranked_results, check_exact=True)
    assert result.ranked_results["parameter_row_id"].iloc[0] == other.ranked_results["parameter_row_id"].iloc[0]
    assert trades.keys() == other_trades.keys()
    for row_id, frame in trades.items():
        pd.testing.assert_frame_equal(frame, other_trades[row_id], check_exact=True)
    assert result.deflated_sharpe == other.deflated_sharpe
    assert result.overfitting_pbo == other.overfitting_pbo
    assert result.validation_results == other.validation_results


@pytest.mark.parametrize("chunk", [1, 2])
def test_chunked_sweep_equals_one_all_settings_simulation(chunk: int) -> None:
    whole = _sweep(len(DONCHIAN.parameter_combinations))
    assert len(whole[1]) == len(DONCHIAN.parameter_combinations) > chunk
    _assert_same(_sweep(chunk), whole)


def test_chunked_window_equals_one_all_settings_simulation() -> None:
    data = _market()
    window = (data.index[300], data.index[599])
    whole = _sweep(len(DONCHIAN.parameter_combinations), window, {})
    _assert_same(_sweep(2, window, {}), whole)


def test_many_chunks_merge_in_settings_order() -> None:
    """More chunks than settings-per-chunk x 3: 61 settings in 31 chunks of 2 (last one short)."""
    data = _market()
    settings = []
    for seed in range(61):
        rng = np.random.default_rng(seed)
        entries = pd.Series(rng.random(len(data)) < 0.1, index=data.index, name="Close")
        exits = pd.Series(rng.random(len(data)) < 0.1, index=data.index, name="Close")
        settings.append(SignalResult(entries=entries, exits=exits, parameters={"seed": seed}))

    def sweep(chunk: int):
        return chunking.simulate_in_chunks(
            data, settings, EXPERIMENT_CONFIG, runner._construct_portfolio, keep_portfolios=False, chunk_settings=chunk
        )

    chunked, whole = sweep(2), sweep(61)
    assert [len(part) for part in chunked] == [61, 61, 0, 61]
    assert chunked[0] == whole[0]
    for left, right in zip(chunked[1], whole[1]):
        np.testing.assert_array_equal(left, right)


def _staged_run(budget: int, stage: str) -> str:
    """The whole walk-forward or out-of-sample outcome (run times masked), 2 settings per chunk."""
    from dataclasses import replace

    from backtesting.out_of_sample.runner import execute_out_of_sample
    from backtesting.run_spy_donchian_oos import OOS_CONFIG
    from backtesting.walk_forward.runner import execute_walk_forward
    from tests.test_walk_forward_splitter_vbt import _wf_config

    data = _market()
    evaluator = partial(execute_experiment, chunk_settings=2)
    try:
        if stage == "walk_forward":
            config = _wf_config(300, 100, 100, 100, "rolling", "drop", 30, experiment=DONCHIAN)
            outcome = execute_walk_forward(
                config, data, _audit(data), evaluator=evaluator, write_output=False, signal_cache_bytes=budget
            )
        else:
            experiment = replace(OOS_CONFIG.experiment, parameter_combinations=DONCHIAN.parameter_combinations)
            outcome = execute_out_of_sample(
                replace(OOS_CONFIG, experiment=experiment), data, _audit(data),
                evaluator=evaluator, write_output=False, signal_cache_bytes=budget,
            )
        text = repr(outcome)
    except Exception as exc:  # the same failure, at the same point, is part of parity
        text = f"{type(exc).__name__}: {exc}"
    return re.sub(r"\d{4}-\d{2}-\d{2}T[\d:.]+\+00:00", "<run time>", text)


def _one_setting_bytes() -> int:
    from strategies import get_strategy

    strategy = get_strategy(DONCHIAN.strategy_id)
    first = strategy.validate_parameters(dict(DONCHIAN.parameter_combinations[0]))
    return windows._signal_bytes(strategy.generate_signals(_market(), first))


@pytest.mark.parametrize("stage", ["walk_forward", "out_of_sample"])
def test_evicting_signal_cache_changes_nothing(stage: str) -> None:
    unlimited = _staged_run(10**12, stage)
    # 1 byte: nothing is ever cached. One setting's bytes: every new setting evicts the last.
    for budget in (1, _one_setting_bytes()):
        assert _staged_run(budget, stage) == unlimited


def test_chunk_size_follows_bar_count() -> None:
    # 1-minute QQQ, 100 settings: (2,500 - 1,400 - 840) MB / 115.5 MB per setting -> 2.
    assert chunking.chunk_settings_for(1_050_000, 100) == 2
    # 5-minute (5x fewer bars): (2,500 - 1,400 - 168) MB / 23.1 MB -> 40; never below 1.
    assert chunking.chunk_settings_for(210_000, 100) == 40
    assert chunking.chunk_settings_for(1_050_000, 1_000) == 1
