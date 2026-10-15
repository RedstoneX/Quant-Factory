"""Chunked sweeps and the reused locked column equal the all-at-once, re-simulated results."""

import numpy as np
import pandas as pd
import pytest

import backtesting.experiments.chunking as chunking
import backtesting.experiments.runner as runner
from backtesting.experiments import SignalResult
from backtesting.robustness import NeighborhoodConfig, ParameterNeighborhoodDefinition, build_neighborhood, evaluate_neighborhood
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from strategies import get_strategy
from test_parameter_sweep_one_pass import _audit, _data
from test_robustness_evaluation import LOCKED, robustness_config


def _settings(index: pd.Index, count: int) -> list[SignalResult]:
    settings = []
    for seed in range(count):
        rng = np.random.default_rng(seed)
        entries = pd.Series(rng.random(len(index)) < 0.1, index=index, name="Close")
        exits = pd.Series(rng.random(len(index)) < 0.1, index=index, name="Close")
        settings.append(SignalResult(entries=entries, exits=exits, parameters={"seed": seed}))
    return settings


def _run(data, settings, chunk):
    return chunking.simulate_in_chunks(
        data, settings, EXPERIMENT_CONFIG, runner._construct_portfolio, keep_portfolios=True, chunk_settings=chunk
    )


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize("chunk", [1, 3, 7])
def test_chunked_sweep_is_identical_to_one_call(chunk: int) -> None:
    data = _data()
    settings = _settings(data.index, 7)
    whole = _run(data, settings, len(settings))
    chunked = _run(data, settings, chunk)
    assert chunked[0] == whole[0]
    for left, right in zip(chunked[1], whole[1]):
        np.testing.assert_array_equal(left, right)
    for left, right in zip(chunked[2], whole[2]):
        pd.testing.assert_series_equal(left.value, right.value)
        pd.testing.assert_frame_equal(left.orders.records_readable, right.orders.records_readable)
        pd.testing.assert_frame_equal(left.trades.records_readable, right.trades.records_readable)


@pytest.mark.licensed_vectorbt
def test_locked_column_equals_resimulating_the_locked_setting() -> None:
    data = _data()
    config = robustness_config(
        neighborhood=NeighborhoodConfig(
            definitions=(ParameterNeighborhoodDefinition("window", "explicit_values", explicit_values=(7, 14, 21)),),
            minimum_valid_neighbors=3,
            required_pass_proportion=0.6,
            maximum_absolute_degradation=0.05,
            maximum_relative_degradation=0.5,
        ),
    )
    strategy = get_strategy(config.strategy_id)
    neighborhood = build_neighborhood(strategy, LOCKED, config.neighborhood)
    result = evaluate_neighborhood(config, neighborhood, EXPERIMENT_CONFIG, data, _audit(data))

    locked_signals = strategy.generate_signals(data, dict(LOCKED))
    reference = runner.build_portfolio(data, locked_signals, EXPERIMENT_CONFIG)
    np.testing.assert_array_equal(result.locked_returns.to_numpy(dtype=float), reference.returns.to_numpy(dtype=float))
    assert result.locked_returns.index.equals(reference.returns.index)
