"""Deflated Sharpe Ratio and effective-trial count against published numbers."""

import math

import numpy as np
import pytest

pytestmark = pytest.mark.licensed_vectorbt

from backtesting.screening.deflated_sharpe import deflated_sharpe


def _fixture() -> np.ndarray:
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0004, 0.01, size=(500, 8))
    returns[:, 1] = returns[:, 0] * 0.9 + rng.normal(0, 0.002, 500)
    return 1_000 * np.cumprod(1 + returns, axis=0)


def test_matches_library_on_fixture() -> None:
    # Pinned against the pre-migration hand-written implementation's value
    # for the best trial on this fixture (0.6340389958490836; library 0.634039).
    result = deflated_sharpe(_fixture(), 1_000)
    assert result.trials == 8
    assert result.effective_trials == 8.0
    assert result.observations == 500
    assert result.best_trial_index == 0
    assert result.probability == pytest.approx(0.6340389958490836, abs=1e-4)
    assert result.probability == result.trial_probabilities[0]


def test_flat_settings_are_undefined() -> None:
    rng = np.random.default_rng(3)
    walk = 1_000 * np.cumprod(1 + rng.normal(0.001, 0.01, size=300))
    values = np.column_stack([walk, walk, np.full(300, 1_000.0)])
    result = deflated_sharpe(values, 1_000)
    assert result.trials == 3
    assert math.isnan(result.trial_probabilities[2])


# --- Runner integration: the luck check is recorded but never screens. ---
from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pandas as pd  # noqa: E402

import backtesting.experiments.runner as runner_module  # noqa: E402
from backtesting.experiments import (  # noqa: E402
    ExecutionConfig,
    ExperimentConfig,
    SignalResult,
    execute_experiment,
)
from market_data import DataAudit, MarketDataConfig  # noqa: E402
from strategies import get_strategy  # noqa: E402

CASH = 10_000.0
COMBINATIONS = (
    {"window": 7, "entry_threshold": 25, "exit_threshold": 60},
    {"window": 14, "entry_threshold": 30, "exit_threshold": 50},
    {"window": 9, "entry_threshold": 20, "exit_threshold": 55},
    {"window": -1, "entry_threshold": 30, "exit_threshold": 50},
)


def _data() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=90, freq="D")
    close = [100 + ((i % 13) - 6) * 2 + i * 0.1 for i in range(len(index))]
    return pd.DataFrame(
        {
            "Open": [value - 1 for value in close],
            "High": [value + 2 for value in close],
            "Low": [value - 2 for value in close],
            "Close": close,
            "Volume": [1_000.0] * len(index),
        },
        index=index,
    )


def _audit(data: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=2, symbol="SPY", provider="test",
        provider_implementation="test", interval="1 day",
        requested_start="2024-01-01", requested_dynamic_end_policy="test",
        latest_completed_exchange_session="2024-03-30", prices_adjusted=True,
        adjustment_verification="test", download_time="2024-03-30T17:00:00-04:00",
        download_timezone="America/New_York", actual_first_row_date="2024-01-01",
        actual_last_row_date="2024-03-30", row_count=len(data),
        duplicate_timestamp_count=0, missing_open_count=0, missing_high_count=0,
        missing_low_count=0, missing_close_count=0, missing_volume_count=0,
        expected_session_gap_count=0,
    )


def _config(tmp_path: Path, **execution_overrides: object) -> ExperimentConfig:
    execution = ExecutionConfig.next_bar_open(
        initial_cash=CASH, fees=0.0005, slippage=0.0002, direction="longonly",
        accumulate=False, leverage=1.0,
    )
    return ExperimentConfig(
        experiment_id="batch_equivalence",
        strategy_id="rsi_mean_reversion",
        parameter_combinations=COMBINATIONS,
        market_data=MarketDataConfig(
            symbol="SPY", provider="test", provider_implementation="test",
            interval="1 day", requested_start="2024-01-01", end_date_policy="test",
            adjusted=True, exchange_calendar="NYSE",
            market_timezone="America/New_York", cache_path=tmp_path / "cache.csv",
        ),
        execution=replace(execution, **execution_overrides),
        ranking_columns=("total_return", "sharpe_ratio"),
        ranking_ascending=(False, False),
        output_path=tmp_path / "results.csv",
    )


class _Trades:
    def __init__(self, count: int) -> None:
        self._count = count
        self.win_rate = 0.5

    def count(self) -> int:
        return self._count


class _Column:
    """Deterministic long-only engine whose value depends on every input."""

    def __init__(self, close, entries, exits, price, sl_stop, tp_stop) -> None:
        held, position, trades = [], False, 0
        for entry, exit_ in zip(entries, exits):
            if not position and entry:
                position, trades = True, trades + 1
            elif position and exit_:
                position = False
            held.append(position)
        held = pd.Series(held, index=close.index)
        stop_drag = (sl_stop.fillna(0) - tp_stop.fillna(0) * 0.1) if sl_stop is not None else 0
        pnl = held.shift(1, fill_value=False) * (price.diff().fillna(0) - stop_drag)
        self.value = CASH + pnl.cumsum()
        returns = self.value / self.value.shift(1).fillna(CASH) - 1
        self.total_return = float(self.value.iloc[-1] / CASH - 1)
        self.annualized_return = self.total_return * 4
        self.sharpe_ratio = float(returns.mean() / returns.std()) if returns.std() else 0.0
        self.max_drawdown = float((self.value / self.value.cummax() - 1).min())
        self.trades = _Trades(trades)


class _Portfolio:
    calls: list[dict] = []

    @classmethod
    def from_signals(cls, *, close, entries, exits, price, **kwargs):
        cls.calls.append(dict(kwargs, entries=entries, exits=exits, price=price))
        return _Column(
            close, entries, exits, price, kwargs.get("sl_stop"), kwargs.get("tp_stop")
        )


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch):
    strategy = get_strategy("rsi_mean_reversion")

    def signals(data: pd.DataFrame, parameters: dict) -> SignalResult:
        normalized = strategy.validate_parameters(parameters)
        offset = normalized["window"] % 5
        entries = pd.Series(False, index=data.index)
        exits = pd.Series(False, index=data.index)
        entries.iloc[offset::11] = True
        exits.iloc[offset + 5 :: 11] = True
        return SignalResult(entries=entries, exits=exits, parameters=normalized)

    monkeypatch.setattr(strategy, "generate_signals", signals)
    _Portfolio.calls = []
    monkeypatch.setattr(
        runner_module, "require_vectorbtpro", lambda: SimpleNamespace(Portfolio=_Portfolio)
    )
    return _Portfolio


def _run(config: ExperimentConfig):
    data = _data()
    return execute_experiment(
        config, data, _audit(data), write_output=False, run_timestamp="fixed"
    )


def test_deflated_sharpe_is_record_only(engine, tmp_path, monkeypatch) -> None:
    config = _config(tmp_path)
    recorded = _run(config)
    luck = recorded.deflated_sharpe
    assert luck is not None and luck.trials == len(recorded.normalized_parameters) >= 2
    assert luck.effective_trials == luck.trials
    assert all(r.deflated_sharpe_probability is not None for r in recorded.screening_results)

    monkeypatch.setattr(runner_module, "deflated_sharpe", lambda *_a, **_k: None)
    without = _run(config)
    assert without.deflated_sharpe is None
    pd.testing.assert_frame_equal(recorded.ranked_results, without.ranked_results)
    for left, right in zip(recorded.screening_results, without.screening_results):
        assert left.passed == right.passed
        assert left.rule_results == right.rule_results
        assert left.rejection_reasons == right.rejection_reasons
