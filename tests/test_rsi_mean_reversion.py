"""Strategy and focused RSI runner tests."""

from itertools import product

import pandas as pd
import pytest
import vectorbtpro as vbt

import backtesting.run_rsi_demo as demo
from strategies import StrategyRegistry, get_strategy
from strategies.rsi_mean_reversion import (
    ENTRY_THRESHOLDS,
    EXIT_THRESHOLDS,
    RSI_WINDOWS,
    RSI_MEAN_REVERSION_STRATEGY,
    build_parameter_grid,
    get_strategy_spec,
    generate_signals,
)


def test_strategy_specification_fields() -> None:
    spec = get_strategy_spec()
    assert spec.identity.strategy_id == "rsi_mean_reversion"
    assert spec.identity.family == "mean_reversion"
    assert spec.identity.direction == "long"
    assert spec.data.required_fields == ("Close",)
    assert spec.data.supported_intervals == ("1 day",)
    assert spec.data.adjusted_prices is True
    assert spec.data.minimum_history_bars == 22
    assert spec.assumptions.pyramiding is False
    assert spec.assumptions.stop_loss is None
    assert spec.assumptions.profit_target is None
    assert spec.assumptions.same_bar_limitation is not None
    assert set(spec.parameter_map) == {
        "window",
        "entry_threshold",
        "exit_threshold",
    }
    assert spec.parameter_map["window"].allowed_values == RSI_WINDOWS


def test_strategy_registry() -> None:
    assert get_strategy("rsi_mean_reversion") is RSI_MEAN_REVERSION_STRATEGY
    with pytest.raises(KeyError, match="Unknown strategy ID"):
        get_strategy("unknown")

    registry = StrategyRegistry()
    registry.register(RSI_MEAN_REVERSION_STRATEGY)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(RSI_MEAN_REVERSION_STRATEGY)


def test_valid_parameters_and_defaults() -> None:
    strategy = get_strategy("rsi_mean_reversion")
    assert strategy.validate_parameters({}) == {
        "window": 14,
        "entry_threshold": 30,
        "exit_threshold": 55,
    }
    assert strategy.validate_parameters(
        {"window": 7, "entry_threshold": 20, "exit_threshold": 60}
    ) == {"window": 7, "entry_threshold": 20, "exit_threshold": 60}


@pytest.mark.parametrize(
    ("parameters", "error", "message"),
    [
        ({"window": 0}, ValueError, "window"),
        ({"window": 7.0}, TypeError, "window must be int"),
        ({"entry_threshold": -1}, ValueError, "entry_threshold"),
        ({"exit_threshold": 101}, ValueError, "exit_threshold"),
        (
            {"entry_threshold": 30, "exit_threshold": 30},
            ValueError,
            "greater than",
        ),
        ({"unknown": 1}, ValueError, "Unsupported parameter"),
    ],
)
def test_invalid_parameters_fail_clearly(
    parameters: dict[str, object], error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        get_strategy("rsi_mean_reversion").validate_parameters(parameters)


def test_signal_arrays_align_with_price_index() -> None:
    index = pd.date_range("2024-01-01", periods=40, freq="D")
    close = pd.Series(
        [100 + ((i % 10) - 5) * 2 for i in range(len(index))],
        index=index,
        dtype=float,
    )
    entries, exits = generate_signals(close, 7, 30, 55)
    assert entries.index.equals(close.index)
    assert exits.index.equals(close.index)


def test_common_interface_signal_result_matches_preserved_rsi_rules() -> None:
    index = pd.date_range("2024-01-01", periods=50, freq="D")
    close = pd.Series(
        [100 + ((i % 10) - 5) * 2 for i in range(len(index))],
        index=index,
        dtype=float,
    )
    result = get_strategy("rsi_mean_reversion").generate_signals(
        pd.DataFrame({"Close": close}),
        {"window": 7, "entry_threshold": 30, "exit_threshold": 55},
    )
    rsi = vbt.RSI.run(close, window=7)
    pd.testing.assert_series_equal(result.entries, rsi.rsi_crossed_below(30))
    pd.testing.assert_series_equal(result.exits, rsi.rsi_crossed_above(55))
    assert result.entries.index.equals(close.index)
    assert result.exits.index.equals(close.index)
    assert result.short_entries is None
    assert result.short_exits is None
    assert result.parameters == {
        "window": 7,
        "entry_threshold": 30,
        "exit_threshold": 55,
    }


def test_parameter_grid_is_unchanged() -> None:
    expected = set(product(RSI_WINDOWS, ENTRY_THRESHOLDS, EXIT_THRESHOLDS))
    assert len(build_parameter_grid()) == 27
    assert set(build_parameter_grid()) == expected
    assert all(exit_ > entry for _, entry, exit_ in build_parameter_grid())


@pytest.mark.parametrize("exit_threshold", [20, 19])
def test_generate_signals_rejects_invalid_thresholds(exit_threshold: int) -> None:
    with pytest.raises(ValueError, match="greater than"):
        generate_signals(pd.Series([100.0, 99.0, 98.0]), 7, 20, exit_threshold)


def test_rsi_demo_configuration_preserves_grid_and_assumptions() -> None:
    assert demo.EXPERIMENT_CONFIG.strategy_id == "rsi_mean_reversion"
    assert demo.EXPERIMENT_CONFIG.market_data is demo.DATA_CONFIG
    assert demo.EXPERIMENT_CONFIG.parameter_combinations == demo.PARAMETER_COMBINATIONS
    assert len(demo.PARAMETER_COMBINATIONS) == 27
    assert demo.EXPERIMENT_CONFIG.output_path == demo.RESULT_PATH
    assert demo.EXPERIMENT_CONFIG.initial_cash == 10_000
    assert demo.EXPERIMENT_CONFIG.fees == 0.0005
    assert demo.EXPERIMENT_CONFIG.slippage == 0.0002
