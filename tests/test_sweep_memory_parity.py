"""The VectorBT PRO mono-chunk sweep gives the same results at every chunk size, with signals
alive for one chunk only.

Chunk size equal to the grid is one all-settings simulation with every signal generated up
front (the pre-chunking behaviour); smaller chunks must not change a single metric, trade,
luck statistic or the chosen setting, on the whole history and inside a walk-forward window.
"""

from __future__ import annotations

import pandas as pd
import pytest

import backtesting.experiments.chunking as chunking
import backtesting.experiments.runner as runner
from backtesting.experiments import execute_experiment
from tests.test_spy_donchian_oos import _audit
from tests.test_walk_forward_splitter_vbt import DONCHIAN, _market

pytestmark = pytest.mark.licensed_vectorbt


def _sweep(monkeypatch, chunk: int, evaluation_range=None, signal_cache=None):
    monkeypatch.setattr(chunking, "SWEEP_CHUNK_SETTINGS", chunk)
    data = _market()
    trades: dict[str, pd.DataFrame] = {}
    result = execute_experiment(
        DONCHIAN, data, _audit(data), write_output=False, evaluation_range=evaluation_range,
        signal_cache=signal_cache,
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
def test_chunked_sweep_equals_one_all_settings_simulation(monkeypatch, chunk: int) -> None:
    whole = _sweep(monkeypatch, len(DONCHIAN.parameter_combinations))
    assert len(whole[1]) == len(DONCHIAN.parameter_combinations) > chunk
    _assert_same(_sweep(monkeypatch, chunk), whole)


def test_chunked_window_equals_one_all_settings_simulation(monkeypatch) -> None:
    data = _market()
    window = (data.index[300], data.index[599])
    whole = _sweep(monkeypatch, len(DONCHIAN.parameter_combinations), window, {})
    _assert_same(_sweep(monkeypatch, 2, window, {}), whole)


def test_signals_are_generated_one_chunk_at_a_time(monkeypatch) -> None:
    sizes: list[int] = []
    generate = runner.generate_signals_once

    def spy(strategy, data, accepted, cache):
        sizes.append(len(accepted))
        return generate(strategy, data, accepted, cache)

    monkeypatch.setattr(runner, "generate_signals_once", spy)
    _sweep(monkeypatch, 2)
    count = len(DONCHIAN.parameter_combinations)
    assert sizes == [2] * (count // 2) + ([count % 2] if count % 2 else [])
