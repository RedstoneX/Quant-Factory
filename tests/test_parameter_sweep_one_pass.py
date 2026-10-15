"""One-pass parameter sweeps equal one simulation per setting (real VectorBT PRO)."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import backtesting.experiments.runner as runner
import backtesting.run_rsi_demo as demo
from backtesting.experiments import ExecutionConfig, METRIC_COLUMNS, SignalResult, execute_experiment, extract_metrics
from backtesting.screening import screen_metrics
from backtesting.screening.deflated_sharpe import deflated_sharpe
from market_data import DataAudit
from strategies import get_strategy


def _data(rows: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 1, rows))
    open_ = close + rng.normal(0, 0.3, rows)
    index = pd.date_range("2022-01-03", periods=rows, freq="B")
    return pd.DataFrame(
        {
            "Open": open_,
            "High": np.maximum(open_, close) + rng.uniform(0, 1, rows),
            "Low": np.minimum(open_, close) - rng.uniform(0, 1, rows),
            "Close": close,
            "Volume": rng.uniform(1e5, 1e6, rows),
        },
        index=index,
    )


def _audit(data: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="vectorbtpro.YFData.pull",
        interval="1 day",
        requested_start="2022-01-03",
        requested_dynamic_end_policy="test",
        latest_completed_exchange_session=str(data.index[-1].date()),
        prices_adjusted=True,
        adjustment_verification="test",
        download_time="2024-01-01T17:00:00-04:00",
        download_timezone="America/New_York",
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


def _assert_same_portfolio(one_pass, reference) -> None:
    np.testing.assert_allclose(
        [extract_metrics(one_pass)[name] for name in METRIC_COLUMNS],
        [extract_metrics(reference)[name] for name in METRIC_COLUMNS],
        rtol=1e-12,
    )
    pd.testing.assert_frame_equal(one_pass.trades.records_readable, reference.trades.records_readable)
    pd.testing.assert_frame_equal(one_pass.orders.records_readable, reference.orders.records_readable)
    pd.testing.assert_series_equal(one_pass.value, reference.value)


@pytest.mark.licensed_vectorbt
def test_experiment_outputs_equal_one_simulation_per_setting(tmp_path: Path) -> None:
    config = replace(demo.EXPERIMENT_CONFIG, output_path=tmp_path / "results.csv")
    assert len(config.parameter_combinations) >= 4
    data = _data()
    captured: dict[str, object] = {}
    result = execute_experiment(
        config, data, _audit(data), write_output=False, portfolio_observer=captured.__setitem__
    )

    strategy = get_strategy(config.strategy_id)
    reference_values = []
    for position, supplied in enumerate(config.parameter_combinations):
        normalized = strategy.validate_parameters(dict(supplied))
        aligned, _ = runner.validate_for_simulation(data, strategy.generate_signals(data, normalized), config)
        reference = runner._construct_portfolio(data, aligned, config)
        reference_values.append(reference.value.to_numpy(dtype=float))
        metrics = extract_metrics(reference)
        expected = screen_metrics(
            experiment_id=config.experiment_id,
            strategy_id=strategy.spec.identity.strategy_id,
            strategy_version=strategy.spec.identity.version,
            parameters=normalized,
            execution_assumptions=result.execution_assumptions,
            metrics=metrics,
            config=config.screening,
        )
        screened = result.screening_results[position]
        assert (screened.parameter_row_id, screened.passed, screened.rejection_reasons) == (
            expected.parameter_row_id,
            expected.passed,
            expected.rejection_reasons,
        )
        row = result.ranked_results.loc[result.ranked_results["parameter_row_id"] == expected.parameter_row_id]
        np.testing.assert_allclose(
            row[list(METRIC_COLUMNS)].to_numpy(dtype=float)[0],
            [metrics[name] for name in METRIC_COLUMNS],
            rtol=1e-12,
        )
        _assert_same_portfolio(captured[expected.parameter_row_id], reference)

    assert len(captured) == len(config.parameter_combinations)
    np.testing.assert_allclose(
        result.deflated_sharpe.trial_probabilities,
        deflated_sharpe(np.column_stack(reference_values), config.execution.initial_cash).trial_probabilities,
        rtol=1e-12,
    )


def _signal(index: pd.Index, start: int, step: int, name: str | None = None) -> pd.Series:
    signal = pd.Series(False, index=index, dtype=bool, name=name)
    signal.iloc[start::step] = True
    return signal


def _long_short_settings(index: pd.Index) -> list[SignalResult]:
    return [
        SignalResult(
            entries=_signal(index, 3 + offset, 20),
            exits=_signal(index, 9 + offset, 20),
            short_entries=_signal(index, 12 + offset, 20),
            short_exits=_signal(index, 17 + offset, 20),
            parameters={"setting": offset},
            stop_loss=pd.Series(0.02, index=index) if offset % 2 == 0 else None,
            take_profit=pd.Series(0.03, index=index) if offset == 2 else None,
            trailing_stop=pd.Series(0.015, index=index) if offset == 3 else None,
        )
        for offset in range(5)
    ]


def _named_long_settings(index: pd.Index) -> list[SignalResult]:
    return [
        SignalResult(
            entries=_signal(index, 2 + offset, 15, "Close"),
            exits=_signal(index, 8 + offset, 15, "Close"),
            parameters={"setting": offset},
        )
        for offset in range(4)
    ]


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize(
    ("execution", "settings"),
    [
        (
            ExecutionConfig.next_bar_open(
                initial_cash=10_000, fees=0.0005, slippage=0.0, slippage_points=0.05,
                direction="both", leverage=1.0, accumulate=False,
            ),
            _long_short_settings,
        ),
        (
            ExecutionConfig.same_bar_close(
                initial_cash=10_000, fees=0.0005, slippage=0.0002,
                direction="longonly", leverage=1.0, accumulate=False,
                position_sizing="all_cash_whole_shares", order_size=1.0,
            ),
            _named_long_settings,
        ),
    ],
    ids=["long-short-mixed-stops", "named-whole-shares"],
)
def test_one_pass_columns_equal_single_setting_portfolios(execution, settings) -> None:
    config = replace(demo.EXPERIMENT_CONFIG, execution=execution)
    data = _data()
    aligned = settings(data.index)
    sweep = runner._construct_portfolio(data, tuple(aligned), config)
    assert sweep.wrapper.shape_2d[1] == len(aligned)
    for position, setting in enumerate(aligned):
        _assert_same_portfolio(
            runner._setting_portfolio(sweep, position), runner._construct_portfolio(data, setting, config)
        )
