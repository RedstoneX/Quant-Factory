"""Signal generation and parameter grid for a long-only RSI strategy."""

from itertools import product
from typing import Any, Mapping

import pandas as pd

from backtesting.vectorbt_runtime import require_vectorbtpro

from strategies.models import (
    DataRequirements,
    ParameterDefinition,
    SignalResult,
    StrategyIdentity,
    StrategySpecification,
    TradingAssumptions,
)

RSI_WINDOWS = (7, 14, 21)
ENTRY_THRESHOLDS = (20, 25, 30)
EXIT_THRESHOLDS = (50, 55, 60)

RSI_MEAN_REVERSION_SPEC = StrategySpecification(
    identity=StrategyIdentity(
        strategy_id="rsi_mean_reversion",
        name="RSI Mean Reversion",
        family="mean_reversion",
        version="1.0.0",
        description="Long-only RSI threshold-crossing mean reversion.",
        direction="long",
    ),
    data=DataRequirements(
        required_fields=("Close",),
        supported_intervals=("1 day",),
        asset_classes=("equity", "etf"),
        minimum_history_bars=max(RSI_WINDOWS) + 1,
        adjusted_prices=True,
    ),
    parameters=(
        ParameterDefinition(
            name="window",
            value_type=int,
            default=14,
            allowed_values=RSI_WINDOWS,
            minimum=1,
            description="RSI lookback window in bars.",
            optimizable=True,
            classification="bounded_discrete",
            reference_value=14,
            source="existing approved RSI experiment",
            rationale=(
                "Compare the three previously approved lookback horizons while "
                "preserving the original 14-bar reference."
            ),
            expected_grid_contribution=len(RSI_WINDOWS),
            approval_state="approved",
        ),
        ParameterDefinition(
            name="entry_threshold",
            value_type=int,
            default=30,
            allowed_values=ENTRY_THRESHOLDS,
            minimum=0,
            maximum=100,
            description="Enter when RSI crosses below this level.",
            optimizable=True,
            classification="local_sensitivity",
            reference_value=30,
            source="existing approved RSI experiment",
            rationale=(
                "Evaluate the previously approved oversold entry levels around "
                "the 30 reference threshold."
            ),
            expected_grid_contribution=len(ENTRY_THRESHOLDS),
            approval_state="approved",
        ),
        ParameterDefinition(
            name="exit_threshold",
            value_type=int,
            default=55,
            allowed_values=EXIT_THRESHOLDS,
            minimum=0,
            maximum=100,
            description="Exit when RSI crosses above this level.",
            optimizable=True,
            classification="local_sensitivity",
            reference_value=55,
            source="existing approved RSI experiment",
            rationale=(
                "Evaluate the previously approved recovery exits around the 55 "
                "reference threshold."
            ),
            expected_grid_contribution=len(EXIT_THRESHOLDS),
            approval_state="approved",
        ),
    ),
    assumptions=TradingAssumptions(
        signal_timing="RSI crossing calculated from the adjusted daily close",
        execution_timing="Defined by the experiment execution configuration",
        position_sizing="All available cash, one long position",
        fee_rate=0.0005,
        slippage_rate=0.0002,
        stop_loss=None,
        profit_target=None,
        maximum_holding_period=None,
        pyramiding=False,
        same_bar_limitation=(
            "Same-bar-close execution uses the final close both to calculate RSI "
            "and fill the resulting order, so it can overstate implementability."
        ),
    ),
    hypothesis=(
        "Daily SPY may mean-revert after RSI crosses into an oversold region and "
        "recover after RSI crosses above a higher exit threshold."
    ),
    source="user-approved existing Quant Factory RSI vertical slice",
    approval_state="approved",
)


class RSIMeanReversionStrategy:
    spec = RSI_MEAN_REVERSION_SPEC

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, Any]:
        definitions = self.spec.parameter_map
        unsupported = set(parameters) - set(definitions)
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValueError(f"Unsupported parameter(s): {names}")

        normalized = {
            name: parameters.get(name, definition.default)
            for name, definition in definitions.items()
        }
        for name, value in normalized.items():
            expected = definitions[name].value_type
            if not isinstance(value, expected) or (
                expected is int and isinstance(value, bool)
            ):
                raise TypeError(
                    f"{name} must be {expected.__name__}, "
                    f"not {type(value).__name__}"
                )
        if normalized["entry_threshold"] >= normalized["exit_threshold"]:
            raise ValueError("exit_threshold must be greater than entry_threshold")
        for name, value in normalized.items():
            definitions[name].validate(value)
        return normalized

    def generate_signals(
        self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]
    ) -> SignalResult:
        normalized = self.validate_parameters(parameters)
        close = data["Close"] if isinstance(data, pd.DataFrame) else data
        entries, exits = _generate_signals(close, **normalized)
        return SignalResult(entries=entries, exits=exits, parameters=normalized)


RSI_MEAN_REVERSION_STRATEGY = RSIMeanReversionStrategy()


def get_strategy_spec() -> StrategySpecification:
    """Return the stable specification for this strategy."""
    return RSI_MEAN_REVERSION_SPEC


def build_parameter_grid(
    windows: tuple[int, ...] = RSI_WINDOWS,
    entry_thresholds: tuple[int, ...] = ENTRY_THRESHOLDS,
    exit_thresholds: tuple[int, ...] = EXIT_THRESHOLDS,
) -> list[tuple[int, int, int]]:
    """Return every valid ``(window, entry, exit)`` parameter combination."""
    return [
        (window, entry, exit_)
        for window, entry, exit_ in product(
            windows, entry_thresholds, exit_thresholds
        )
        if exit_ > entry
    ]


def generate_signals(
    close: pd.Series,
    window: int,
    entry_threshold: int,
    exit_threshold: int,
) -> tuple[pd.Series, pd.Series]:
    """Generate long entries below and exits above the RSI thresholds."""
    result = RSI_MEAN_REVERSION_STRATEGY.generate_signals(
        close,
        {
            "window": window,
            "entry_threshold": entry_threshold,
            "exit_threshold": exit_threshold,
        },
    )
    return result.entries, result.exits


def _generate_signals(
    close: pd.Series,
    window: int,
    entry_threshold: int,
    exit_threshold: int,
) -> tuple[pd.Series, pd.Series]:
    """Preserved RSI calculation and crossing rules."""

    vbt = require_vectorbtpro()
    rsi = vbt.RSI.run(close, window=window)
    entries = rsi.rsi_crossed_below(entry_threshold)
    exits = rsi.rsi_crossed_above(exit_threshold)
    return entries, exits
