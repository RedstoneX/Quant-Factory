"""Typed profiles for portable, multi-asset experiment planning."""

from dataclasses import dataclass
from datetime import time, timedelta
from typing import Literal

from strategies.models import ApprovalState

AssetClass = Literal["equity", "etf", "futures", "crypto", "fx"]
SessionDesignation = Literal["regular", "extended", "synthetic"]
TimeframeKind = Literal["native", "resampled"]


@dataclass(frozen=True)
class InstrumentProfile:
    symbol: str
    display_name: str
    asset_class: AssetClass
    venue: str
    base_currency: str | None
    quote_currency: str | None
    timezone: str
    trading_calendar: str | None
    tick_size: float | None
    price_precision: int | None
    contract_multiplier: float | None
    point_value: float | None
    continuous_market: bool
    supported_intervals: tuple[str, ...]
    provider: str
    provider_symbol: str
    adjusted_prices_required: bool
    session_profile_id: str
    execution_profile_id: str
    approval_state: ApprovalState


@dataclass(frozen=True)
class SessionProfile:
    session_id: str
    name: str
    timezone: str
    anchor: time | None
    start: time | None
    end: time | None
    trading_day_boundary: str
    designation: SessionDesignation
    overnight: bool
    calendar_reference: str | None
    continuous_market: bool
    rationale: str
    approval_state: ApprovalState


@dataclass(frozen=True)
class TimeframeProfile:
    interval: str
    bar_duration: timedelta
    timezone: str
    kind: TimeframeKind
    resampling_origin: str | None
    resampling_offset: timedelta | None
    incomplete_bar_policy: str
    required_source_resolution: timedelta
    approval_state: ApprovalState
    available_source_resolution: timedelta | None = None


@dataclass(frozen=True)
class ExecutionProfile:
    profile_id: str
    fee_rate: float
    commission_per_order: float
    slippage_rate: float
    spread_rate: float
    order_timing: str
    fill_convention: str
    minimum_tick: float | None
    contract_multiplier: float | None
    point_value: float | None
    sizing: str
    leverage: float
    shorting_available: bool
    liquidity_assumptions: str
    approval_state: ApprovalState


@dataclass(frozen=True)
class ExperimentVariant:
    strategy_id: str
    instrument_symbol: str
    provider_symbol: str
    timeframe_interval: str
    session_id: str
    execution_profile_id: str
    adjusted_prices: bool
    approval_state: ApprovalState

    @property
    def identity(self) -> tuple[str, str, str, str, str, str, bool]:
        return (
            self.strategy_id,
            self.instrument_symbol,
            self.provider_symbol,
            self.timeframe_interval,
            self.session_id,
            self.execution_profile_id,
            self.adjusted_prices,
        )


@dataclass(frozen=True)
class UnsupportedCombination:
    instrument_symbol: str
    timeframe_interval: str
    reason: str


@dataclass(frozen=True)
class ExperimentMatrixSummary:
    instrument_count: int
    timeframe_count: int
    session_count: int
    execution_profile_count: int
    experiment_variant_count: int
    parameter_combinations: int
    total_planned_simulations: int
    variants: tuple[ExperimentVariant, ...]
    unsupported_combinations: tuple[UnsupportedCombination, ...]
    warnings: tuple[str, ...]
