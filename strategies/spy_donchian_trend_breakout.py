"""Approved SPY daily Donchian trend-breakout candidate."""

from __future__ import annotations

from itertools import product
from typing import Any, Literal, Mapping

import pandas as pd

from strategies.models import (
    DataRequirements,
    ParameterDefinition,
    SignalResult,
    StrategyIdentity,
    StrategySpecification,
    TradingAssumptions,
)

ENTRY_LOOKBACKS = (20, 55)
EXIT_LOOKBACKS = (10, 20)
DirectionVariant = Literal["long", "short"]

PARAMETER_DEFINITIONS = (
    ParameterDefinition(
        name="entry_lookback",
        value_type=int,
        default=20,
        description="Prior-session Donchian breakout lookback in daily bars.",
        optimizable=True,
        allowed_values=ENTRY_LOOKBACKS,
        minimum=1,
        classification="bounded_discrete",
        reference_value=20,
        source="User-approved SPY Donchian trend-breakout specification",
        rationale="Evaluate only the approved classic Donchian entry windows.",
        expected_grid_contribution=len(ENTRY_LOOKBACKS),
        approval_state="approved",
    ),
    ParameterDefinition(
        name="exit_lookback",
        value_type=int,
        default=10,
        description="Prior-session opposite-channel exit lookback in daily bars.",
        optimizable=True,
        allowed_values=EXIT_LOOKBACKS,
        minimum=1,
        classification="bounded_discrete",
        reference_value=10,
        source="User-approved SPY Donchian trend-breakout specification",
        rationale="Evaluate only the approved shorter exit windows.",
        expected_grid_contribution=len(EXIT_LOOKBACKS),
        approval_state="approved",
    ),
)


def _spec(direction: DirectionVariant) -> StrategySpecification:
    label = "Long" if direction == "long" else "Short"
    return StrategySpecification(
        identity=StrategyIdentity(
            strategy_id=f"spy_donchian_trend_breakout_{direction}",
            name=f"SPY Donchian Trend Breakout — {label}",
            family="trend_following",
            version="1.0.0",
            description=(
                f"{label}-only SPY daily close breakout of a prior Donchian "
                "channel with opposite-channel exit."
            ),
            direction=direction,
        ),
        data=DataRequirements(
            required_fields=("Open", "High", "Low", "Close"),
            supported_intervals=("1 day",),
            asset_classes=("equity", "etf"),
            minimum_history_bars=max(ENTRY_LOOKBACKS) + 1,
            adjusted_prices=True,
        ),
        parameters=PARAMETER_DEFINITIONS,
        assumptions=TradingAssumptions(
            signal_timing="Completed daily close versus prior Donchian channel",
            execution_timing="Next daily session open",
            position_sizing="All available cash, one position",
            fee_rate=0.0005,
            slippage_rate=0.0002,
            stop_loss=None,
            profit_target=None,
            maximum_holding_period=None,
            pyramiding=False,
            same_bar_limitation=None,
        ),
        hypothesis=(
            f"SPY may continue in the {direction} direction after a completed "
            "daily close breaks a prior Donchian channel."
        ),
        source="Explicit user-approved SPY Donchian trend-breakout specification",
        approval_state="approved",
    )


SPY_DONCHIAN_LONG_SPEC = _spec("long")
SPY_DONCHIAN_SHORT_SPEC = _spec("short")


def build_parameter_grid() -> tuple[dict[str, int], ...]:
    """Return valid Donchian lookback pairs for one direction variant."""
    return tuple(
        {"entry_lookback": entry, "exit_lookback": exit_}
        for entry, exit_ in product(ENTRY_LOOKBACKS, EXIT_LOOKBACKS)
        if exit_ < entry
    )


def build_approved_variants() -> tuple[dict[str, int | str], ...]:
    """Return exactly the six user-approved structural variants."""
    return tuple(
        {
            "strategy_id": f"spy_donchian_trend_breakout_{direction}",
            "direction": direction,
            **parameters,
        }
        for parameters in build_parameter_grid()
        for direction in ("long", "short")
    )


def _validate_parameters(
    spec: StrategySpecification, parameters: Mapping[str, Any]
) -> dict[str, int]:
    definitions = spec.parameter_map
    unsupported = set(parameters) - set(definitions)
    if unsupported:
        raise ValueError(
            f"Unsupported parameter(s): {', '.join(sorted(unsupported))}"
        )
    normalized = {
        name: parameters.get(name, definition.default)
        for name, definition in definitions.items()
    }
    for name, value in normalized.items():
        definitions[name].validate(value)
    if normalized["exit_lookback"] >= normalized["entry_lookback"]:
        raise ValueError("exit_lookback must be less than entry_lookback")
    return normalized


def _validate_data(data: pd.DataFrame) -> None:
    required = {"Open", "High", "Low", "Close"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError(f"Donchian data is missing columns: {missing}")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise TypeError("Donchian strategy requires a DatetimeIndex")
    if not data.index.is_monotonic_increasing or not data.index.is_unique:
        raise ValueError("Donchian timestamps must be unique and chronological")


def generate_donchian_signals(
    data: pd.DataFrame,
    parameters: Mapping[str, Any],
    *,
    direction: DirectionVariant,
) -> SignalResult:
    """Generate completed-close Donchian signals without current-bar leakage."""
    spec = SPY_DONCHIAN_LONG_SPEC if direction == "long" else SPY_DONCHIAN_SHORT_SPEC
    normalized = _validate_parameters(spec, parameters)
    _validate_data(data)

    high_channel = (
        data["High"].shift(1).rolling(normalized["entry_lookback"]).max()
    )
    low_channel = (
        data["Low"].shift(1).rolling(normalized["entry_lookback"]).min()
    )
    exit_high_channel = (
        data["High"].shift(1).rolling(normalized["exit_lookback"]).max()
    )
    exit_low_channel = (
        data["Low"].shift(1).rolling(normalized["exit_lookback"]).min()
    )
    close = data["Close"]

    false = pd.Series(False, index=data.index, dtype=bool)
    if direction == "long":
        entries = (close > high_channel).fillna(False).astype(bool)
        exits = (close < exit_low_channel).fillna(False).astype(bool)
        return SignalResult(
            entries=entries,
            exits=exits,
            parameters=normalized,
            metadata={
                "entry_channel": "prior_high",
                "exit_channel": "prior_low",
            },
        )

    short_entries = (close < low_channel).fillna(False).astype(bool)
    short_exits = (close > exit_high_channel).fillna(False).astype(bool)
    return SignalResult(
        entries=false.copy(),
        exits=false.copy(),
        short_entries=short_entries,
        short_exits=short_exits,
        parameters=normalized,
        metadata={
            "entry_channel": "prior_low",
            "exit_channel": "prior_high",
        },
    )


class SPYDonchianTrendBreakoutStrategy:
    def __init__(self, direction: DirectionVariant) -> None:
        self.direction = direction
        self.spec = SPY_DONCHIAN_LONG_SPEC if direction == "long" else SPY_DONCHIAN_SHORT_SPEC

    def validate_parameters(self, parameters: Mapping[str, Any]) -> dict[str, int]:
        return _validate_parameters(self.spec, parameters)

    def generate_signals(
        self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]
    ) -> SignalResult:
        if isinstance(data, pd.Series):
            raise TypeError("Donchian strategy requires OHLC data, not a Series")
        return generate_donchian_signals(data, parameters, direction=self.direction)


SPY_DONCHIAN_LONG_STRATEGY = SPYDonchianTrendBreakoutStrategy("long")
SPY_DONCHIAN_SHORT_STRATEGY = SPYDonchianTrendBreakoutStrategy("short")
