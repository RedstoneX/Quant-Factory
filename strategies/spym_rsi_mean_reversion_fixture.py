"""Fixture-only RSI signal contract for raw one-minute SPYM bars."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from strategies.models import (
    DataRequirements,
    ParameterDefinition,
    SignalResult,
    StrategyIdentity,
    StrategySpecification,
    TradingAssumptions,
)
from strategies.rsi_mean_reversion import _generate_signals

SPYM_RSI_WINDOW = 14
SPYM_RSI_ENTRY_THRESHOLD = 30
SPYM_RSI_EXIT_THRESHOLD = 55

SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC = StrategySpecification(
    identity=StrategyIdentity(
        strategy_id="spym_rsi_mean_reversion_fixture",
        name="SPYM RSI Mean Reversion Fixture",
        family="mean_reversion",
        version="1.0.0",
        description=(
            "Infrastructure-only RSI fixture for raw Databento SPYM one-minute bars."
        ),
        direction="long",
    ),
    data=DataRequirements(
        required_fields=("Open", "Close"),
        supported_intervals=("1m",),
        asset_classes=("equity", "etf"),
        minimum_history_bars=SPYM_RSI_WINDOW + 1,
        adjusted_prices=False,
    ),
    parameters=(
        ParameterDefinition(
            name="window",
            value_type=int,
            default=SPYM_RSI_WINDOW,
            allowed_values=(SPYM_RSI_WINDOW,),
            minimum=1,
            description="Fixed RSI lookback window in one-minute bars.",
            optimizable=False,
            classification="fixed",
            reference_value=SPYM_RSI_WINDOW,
            source="Milestone 21C infrastructure fixture",
            rationale=(
                "Reuse the existing RSI signal implementation with one fixed "
                "reference setting; do not perform parameter research."
            ),
            expected_grid_contribution=1,
            approval_state="approved",
        ),
        ParameterDefinition(
            name="entry_threshold",
            value_type=int,
            default=SPYM_RSI_ENTRY_THRESHOLD,
            allowed_values=(SPYM_RSI_ENTRY_THRESHOLD,),
            minimum=0,
            maximum=100,
            description="Enter when RSI crosses below this fixed level.",
            optimizable=False,
            classification="fixed",
            reference_value=SPYM_RSI_ENTRY_THRESHOLD,
            source="Milestone 21C infrastructure fixture",
            rationale="Fixed transparent signal threshold for execution plumbing.",
            expected_grid_contribution=1,
            approval_state="approved",
        ),
        ParameterDefinition(
            name="exit_threshold",
            value_type=int,
            default=SPYM_RSI_EXIT_THRESHOLD,
            allowed_values=(SPYM_RSI_EXIT_THRESHOLD,),
            minimum=0,
            maximum=100,
            description="Exit when RSI crosses above this fixed level.",
            optimizable=False,
            classification="fixed",
            reference_value=SPYM_RSI_EXIT_THRESHOLD,
            source="Milestone 21C infrastructure fixture",
            rationale="Fixed transparent exit threshold for execution plumbing.",
            expected_grid_contribution=1,
            approval_state="approved",
        ),
    ),
    assumptions=TradingAssumptions(
        signal_timing="RSI crossing calculated from completed raw one-minute SPYM close bars",
        execution_timing="Order filled at the next observed Databento one-minute open",
        position_sizing="Fixed whole-share quantity; one SPYM share per entry",
        fee_rate=0.0,
        slippage_rate=0.0,
        stop_loss=None,
        profit_target=None,
        maximum_holding_period=None,
        pyramiding=False,
        same_bar_limitation=None,
    ),
    hypothesis=(
        "This is an infrastructure fixture only: it proves that the validated "
        "SPYM dataset can flow through VectorBT Pro, persistence, artifacts, "
        "and lineage. It is not profitability evidence."
    ),
    source="Milestone 21C SPYM Databento reference execution fixture",
    approval_state="approved",
)


class SPYMRSIMeanReversionFixtureStrategy:
    spec = SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC

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
            definitions[name].validate(value)
        if normalized["entry_threshold"] >= normalized["exit_threshold"]:
            raise ValueError("exit_threshold must be greater than entry_threshold")
        return normalized

    def generate_signals(
        self, data: pd.DataFrame | pd.Series, parameters: Mapping[str, Any]
    ) -> SignalResult:
        normalized = self.validate_parameters(parameters)
        close = data["Close"] if isinstance(data, pd.DataFrame) else data
        entries, exits = _generate_signals(close, **normalized)
        return SignalResult(
            entries=entries,
            exits=exits,
            parameters=normalized,
            metadata={"fixture_only": True, "dataset_symbol": "SPYM"},
        )


SPYM_RSI_MEAN_REVERSION_FIXTURE_STRATEGY = SPYMRSIMeanReversionFixtureStrategy()
