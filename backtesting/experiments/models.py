"""Typed models for reproducible strategy experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Mapping

import pandas as pd

from market_data import DataAudit, MarketDataConfig
from backtesting.screening.models import ScreeningConfig

if TYPE_CHECKING:
    from backtesting.screening.models import ScreeningResult
    from backtesting.validation.models import ValidationResult
    from strategies.parameter_governance import ParameterPlanSummary

PortfolioDirection = Literal["longonly", "shortonly", "both"]
ExecutionMode = Literal["same_bar_close", "next_bar_open"]
SignalTiming = Literal["completed_bar_close"]
PositionSizing = Literal["all_available_cash", "fixed_units"]
ExecutionPriceField = Literal["Open", "Close"]


@dataclass(frozen=True)
class ExecutionConfig:
    """Typed assumptions that directly control portfolio execution."""

    mode: ExecutionMode
    signal_timing: SignalTiming
    execution_price_field: ExecutionPriceField
    initial_cash: float
    fees: float
    slippage: float
    position_sizing: PositionSizing
    direction: PortfolioDirection
    leverage: float
    accumulate: bool
    order_size: float = float("inf")
    price_multiplier: float = 1.0
    fixed_fee_per_contract_per_side: float = 0.0
    slippage_points: float = 0.0
    slippage_ticks: float = 0.0
    tick_size: float | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"same_bar_close", "next_bar_open"}:
            raise ValueError(f"Unsupported execution mode: {self.mode}")
        if self.signal_timing != "completed_bar_close":
            raise ValueError(f"Unsupported signal timing: {self.signal_timing}")
        expected_price = {
            "same_bar_close": "Close",
            "next_bar_open": "Open",
        }[self.mode]
        if self.execution_price_field != expected_price:
            raise ValueError(
                f"Execution mode {self.mode} requires price field {expected_price}"
            )
        if self.position_sizing not in {"all_available_cash", "fixed_units"}:
            raise ValueError(
                f"Unsupported position sizing: {self.position_sizing}"
            )
        if self.position_sizing == "all_available_cash" and not math.isinf(
            self.order_size
        ):
            raise ValueError("all_available_cash requires infinite order_size")
        if self.position_sizing == "fixed_units" and (
            not math.isfinite(self.order_size) or self.order_size <= 0
        ):
            raise ValueError("fixed_units requires a positive finite order_size")
        if self.direction not in {"longonly", "shortonly", "both"}:
            raise ValueError(f"Unsupported direction: {self.direction}")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.fees < 0 or self.slippage < 0:
            raise ValueError("fees and slippage must be non-negative")
        if self.fixed_fee_per_contract_per_side < 0:
            raise ValueError("fixed fee per contract per side must be non-negative")
        if self.slippage_points < 0 or self.slippage_ticks < 0:
            raise ValueError("absolute slippage must be non-negative")
        if self.slippage_points and self.slippage_ticks:
            raise ValueError("configure slippage in points or ticks, not both")
        if self.slippage and (self.slippage_points or self.slippage_ticks):
            raise ValueError(
                "percentage and absolute slippage cannot be combined"
            )
        if self.slippage_ticks and (
            self.tick_size is None
            or not math.isfinite(self.tick_size)
            or self.tick_size <= 0
        ):
            raise ValueError("tick slippage requires a positive finite tick size")
        if self.tick_size is not None and (
            not math.isfinite(self.tick_size) or self.tick_size <= 0
        ):
            raise ValueError("tick size must be positive and finite")
        if self.fixed_fee_per_contract_per_side and self.position_sizing != "fixed_units":
            raise ValueError("fixed per-contract fees require fixed-unit sizing")
        if self.leverage <= 0:
            raise ValueError("leverage must be positive")
        if not math.isfinite(self.price_multiplier) or self.price_multiplier <= 0:
            raise ValueError("price_multiplier must be positive and finite")
        if not isinstance(self.accumulate, bool):
            raise TypeError("accumulate must be bool")

    @property
    def execution_timing(self) -> str:
        return (
            "same_bar_close"
            if self.mode == "same_bar_close"
            else "next_available_bar"
        )

    @property
    def signal_timing_label(self) -> str:
        return "Signal calculated after market close"

    @property
    def execution_timing_label(self) -> str:
        if self.mode == "same_bar_close":
            return "Order filled at same session close (research comparison only)"
        return "Order filled at next session open"

    @property
    def absolute_slippage_points(self) -> float:
        if self.slippage_ticks:
            assert self.tick_size is not None
            return self.slippage_ticks * self.tick_size
        return self.slippage_points

    @property
    def fixed_fee_per_order(self) -> float:
        if not self.fixed_fee_per_contract_per_side:
            return 0.0
        return self.fixed_fee_per_contract_per_side * self.order_size

    @classmethod
    def next_bar_open(
        cls,
        *,
        initial_cash: float,
        fees: float,
        slippage: float,
        direction: PortfolioDirection,
        leverage: float,
        accumulate: bool,
        position_sizing: PositionSizing = "all_available_cash",
        order_size: float = float("inf"),
        price_multiplier: float = 1.0,
        fixed_fee_per_contract_per_side: float = 0.0,
        slippage_points: float = 0.0,
        slippage_ticks: float = 0.0,
        tick_size: float | None = None,
    ) -> "ExecutionConfig":
        return cls(
            mode="next_bar_open",
            signal_timing="completed_bar_close",
            execution_price_field="Open",
            initial_cash=initial_cash,
            fees=fees,
            slippage=slippage,
            position_sizing=position_sizing,
            direction=direction,
            leverage=leverage,
            accumulate=accumulate,
            order_size=order_size,
            price_multiplier=price_multiplier,
            fixed_fee_per_contract_per_side=fixed_fee_per_contract_per_side,
            slippage_points=slippage_points,
            slippage_ticks=slippage_ticks,
            tick_size=tick_size,
        )

    @classmethod
    def same_bar_close(
        cls,
        *,
        initial_cash: float,
        fees: float,
        slippage: float,
        direction: PortfolioDirection,
        leverage: float,
        accumulate: bool,
        position_sizing: PositionSizing = "all_available_cash",
        order_size: float = float("inf"),
        price_multiplier: float = 1.0,
        fixed_fee_per_contract_per_side: float = 0.0,
        slippage_points: float = 0.0,
        slippage_ticks: float = 0.0,
        tick_size: float | None = None,
    ) -> "ExecutionConfig":
        return cls(
            mode="same_bar_close",
            signal_timing="completed_bar_close",
            execution_price_field="Close",
            initial_cash=initial_cash,
            fees=fees,
            slippage=slippage,
            position_sizing=position_sizing,
            direction=direction,
            leverage=leverage,
            accumulate=accumulate,
            order_size=order_size,
            price_multiplier=price_multiplier,
            fixed_fee_per_contract_per_side=fixed_fee_per_contract_per_side,
            slippage_points=slippage_points,
            slippage_ticks=slippage_ticks,
            tick_size=tick_size,
        )


@dataclass(frozen=True)
class ExperimentConfig:
    """Everything required to execute and rank one strategy experiment."""

    experiment_id: str
    strategy_id: str
    parameter_combinations: tuple[Mapping[str, Any], ...]
    market_data: MarketDataConfig
    execution: ExecutionConfig
    ranking_columns: tuple[str, ...]
    ranking_ascending: tuple[bool, ...]
    output_path: Path
    screening: ScreeningConfig = field(
        default_factory=ScreeningConfig.provisional_defaults
    )
    parameter_output_names: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must not be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if not self.parameter_combinations:
            raise ValueError("parameter_combinations must not be empty")
        if len(self.ranking_columns) != len(self.ranking_ascending):
            raise ValueError(
                "ranking_columns and ranking_ascending must have equal lengths"
            )

    @property
    def parameter_name_map(self) -> dict[str, str]:
        return dict(self.parameter_output_names)

    @property
    def initial_cash(self) -> float:
        return self.execution.initial_cash

    @property
    def fees(self) -> float:
        return self.execution.fees

    @property
    def slippage(self) -> float:
        return self.execution.slippage

    @property
    def direction(self) -> PortfolioDirection:
        return self.execution.direction

    @property
    def leverage(self) -> float:
        return self.execution.leverage

    @property
    def accumulate(self) -> bool:
        return self.execution.accumulate


@dataclass(frozen=True)
class RejectedParameters:
    parameters: dict[str, Any]
    error: str


@dataclass(frozen=True)
class ExperimentResult:
    ranked_results: pd.DataFrame
    passing_results: pd.DataFrame
    screened_out_results: pd.DataFrame
    experiment_id: str
    strategy_id: str
    strategy_name: str
    strategy_version: str
    normalized_parameters: tuple[dict[str, Any], ...]
    market_data_audit: DataAudit
    execution_assumptions: dict[str, Any]
    run_timestamp: str
    evaluated_combinations: int
    rejected_combinations: int
    rejections: tuple[RejectedParameters, ...]
    validation_results: tuple[ValidationResult, ...]
    screening_config: ScreeningConfig
    screening_results: tuple[ScreeningResult, ...]
    parameter_plan_summary: ParameterPlanSummary
