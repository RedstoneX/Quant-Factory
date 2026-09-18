"""Typed models shared by Quant Factory strategies."""

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

StrategyFamily = Literal[
    "mean_reversion",
    "trend_following",
    "trend_pullback",
    "breakout",
    "range_breakout",
    "volatility_expansion",
    "regime_filtered",
]
Direction = Literal["long", "short", "both"]
ParameterClassification = Literal[
    "fixed",
    "source_defined",
    "bounded_discrete",
    "local_sensitivity",
    "structural_choice",
]
ApprovalState = Literal["draft", "approved", "rejected"]


@dataclass(frozen=True)
class StrategyIdentity:
    strategy_id: str
    name: str
    family: StrategyFamily
    version: str
    description: str
    direction: Direction


@dataclass(frozen=True)
class DataRequirements:
    required_fields: tuple[str, ...]
    supported_intervals: tuple[str, ...]
    asset_classes: tuple[str, ...]
    minimum_history_bars: int
    adjusted_prices: bool


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    value_type: type
    default: Any
    description: str
    optimizable: bool
    allowed_values: tuple[Any, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    classification: ParameterClassification = "fixed"
    reference_value: Any = None
    source: str = ""
    rationale: str = ""
    structural: bool = False
    expected_grid_contribution: int | None = None
    approval_state: ApprovalState = "draft"

    @property
    def candidate_values(self) -> tuple[Any, ...]:
        """Return the approved candidate values, if any."""
        return self.allowed_values or ()

    @property
    def optimized(self) -> bool:
        """Expose the governance term while preserving the existing API."""
        return self.optimizable

    def validate(self, value: Any) -> None:
        if not isinstance(value, self.value_type) or (
            self.value_type is int and isinstance(value, bool)
        ):
            raise TypeError(
                f"{self.name} must be {self.value_type.__name__}, "
                f"not {type(value).__name__}"
            )
        if self.allowed_values is not None and value not in self.allowed_values:
            raise ValueError(
                f"{self.name} must be one of {self.allowed_values}; got {value!r}"
            )
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{self.name} must be at least {self.minimum}; got {value!r}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{self.name} must be at most {self.maximum}; got {value!r}")


@dataclass(frozen=True)
class TradingAssumptions:
    signal_timing: str
    execution_timing: str
    position_sizing: str
    fee_rate: float
    slippage_rate: float
    stop_loss: str | None
    profit_target: str | None
    maximum_holding_period: int | None
    pyramiding: bool
    same_bar_limitation: str | None


@dataclass(frozen=True)
class StrategySpecification:
    identity: StrategyIdentity
    data: DataRequirements
    parameters: tuple[ParameterDefinition, ...]
    assumptions: TradingAssumptions
    hypothesis: str = ""
    source: str = ""
    approval_state: ApprovalState = "draft"

    @property
    def parameter_map(self) -> dict[str, ParameterDefinition]:
        return {definition.name: definition for definition in self.parameters}

    @property
    def reference_configuration(self) -> dict[str, Any]:
        return {
            definition.name: definition.reference_value
            for definition in self.parameters
        }


@dataclass(frozen=True)
class SignalResult:
    entries: pd.Series
    exits: pd.Series
    parameters: dict[str, Any]
    short_entries: pd.Series | None = None
    short_exits: pd.Series | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
