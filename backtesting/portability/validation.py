"""Fail-closed validation for portable experiment profiles."""

from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from strategies.models import StrategySpecification

from backtesting.portability.models import (
    ExecutionProfile,
    ExperimentVariant,
    InstrumentProfile,
    SessionProfile,
    TimeframeProfile,
)

ASSET_CLASSES = frozenset({"equity", "etf", "futures", "crypto", "fx"})
APPROVAL_STATES = frozenset({"draft", "approved", "rejected"})


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required")


def _validate_timezone(value: str) -> None:
    _require_text(value, "timezone")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {value}") from exc


def _validate_approval(
    value: str, entry_name: str, *, require_approved: bool
) -> None:
    if value not in APPROVAL_STATES:
        raise ValueError(f"{entry_name}: invalid approval state {value!r}")
    if require_approved and value != "approved":
        raise ValueError(f"{entry_name}: entry is not approved")


def validate_instrument_profile(
    profile: InstrumentProfile, *, require_approved: bool = False
) -> None:
    if profile.asset_class not in ASSET_CLASSES:
        raise ValueError(f"Unknown asset class: {profile.asset_class}")
    _require_text(profile.symbol, "symbol")
    _require_text(profile.display_name, "display name")
    _require_text(profile.venue, "venue")
    _validate_timezone(profile.timezone)
    _require_text(profile.provider, "provider")
    _require_text(profile.provider_symbol, "provider symbol")
    _require_text(profile.session_profile_id, "session-profile reference")
    _require_text(profile.execution_profile_id, "execution-profile reference")
    if not profile.supported_intervals:
        raise ValueError(f"{profile.symbol}: supported intervals are required")
    if len(profile.supported_intervals) != len(set(profile.supported_intervals)):
        raise ValueError(f"{profile.symbol}: supported intervals must be unique")
    if profile.tick_size is not None and profile.tick_size <= 0:
        raise ValueError(f"{profile.symbol}: tick size must be positive")
    if profile.price_precision is not None and profile.price_precision < 0:
        raise ValueError(f"{profile.symbol}: price precision must be non-negative")
    if profile.asset_class == "futures":
        if profile.tick_size is None:
            raise ValueError(f"{profile.symbol}: futures require tick size")
        if profile.contract_multiplier is None or profile.contract_multiplier <= 0:
            raise ValueError(
                f"{profile.symbol}: futures require a positive contract multiplier"
            )
        if profile.point_value is None or profile.point_value <= 0:
            raise ValueError(f"{profile.symbol}: futures require a positive point value")
    if profile.asset_class in {"crypto", "fx"}:
        if not profile.base_currency or not profile.quote_currency:
            raise ValueError(
                f"{profile.symbol}: {profile.asset_class} requires base and quote currencies"
            )
    _validate_approval(
        profile.approval_state,
        f"instrument {profile.symbol}",
        require_approved=require_approved,
    )


def validate_session_profile(
    profile: SessionProfile, *, require_approved: bool = False
) -> None:
    _require_text(profile.session_id, "session ID")
    _require_text(profile.name, "session name")
    _validate_timezone(profile.timezone)
    _require_text(profile.trading_day_boundary, "trading-day boundary")
    _require_text(profile.rationale, "session rationale")
    if profile.designation not in {"regular", "extended", "synthetic"}:
        raise ValueError(f"{profile.session_id}: invalid session designation")
    if (profile.start is None) != (profile.end is None):
        raise ValueError(f"{profile.session_id}: start and end must be provided together")
    if not profile.continuous_market and (profile.start is None or profile.end is None):
        raise ValueError(f"{profile.session_id}: session start and end are required")
    if profile.start is not None and profile.start == profile.end:
        raise ValueError(f"{profile.session_id}: session start and end must differ")
    if profile.start is not None and profile.end is not None:
        crosses_midnight = profile.end < profile.start
        if profile.overnight != crosses_midnight:
            raise ValueError(
                f"{profile.session_id}: overnight flag conflicts with session times"
            )
    if profile.continuous_market and profile.anchor is None:
        raise ValueError(
            f"{profile.session_id}: continuous session-based market requires an explicit anchor"
        )
    _validate_approval(
        profile.approval_state,
        f"session {profile.session_id}",
        require_approved=require_approved,
    )


def validate_timeframe_profile(
    profile: TimeframeProfile, *, require_approved: bool = False
) -> None:
    _require_text(profile.interval, "interval")
    _validate_timezone(profile.timezone)
    _require_text(profile.incomplete_bar_policy, "incomplete-bar policy")
    if profile.kind not in {"native", "resampled"}:
        raise ValueError(f"{profile.interval}: invalid timeframe kind")
    if profile.bar_duration <= timedelta(0):
        raise ValueError(f"{profile.interval}: bar duration must be positive")
    if profile.required_source_resolution <= timedelta(0):
        raise ValueError(
            f"{profile.interval}: required source resolution must be positive"
        )
    if profile.required_source_resolution > profile.bar_duration:
        raise ValueError(
            f"{profile.interval}: required source data is too coarse for the timeframe"
        )
    if (
        profile.available_source_resolution is not None
        and profile.available_source_resolution > profile.required_source_resolution
    ):
        raise ValueError(
            f"{profile.interval}: available source data is too coarse; "
            f"requires {profile.required_source_resolution} or finer"
        )
    if profile.kind == "resampled" and not profile.resampling_origin:
        raise ValueError(f"{profile.interval}: resampled timeframe requires an origin")
    if profile.kind == "native" and (
        profile.resampling_origin is not None or profile.resampling_offset is not None
    ):
        raise ValueError(
            f"{profile.interval}: native timeframe cannot define resampling settings"
        )
    _validate_approval(
        profile.approval_state,
        f"timeframe {profile.interval}",
        require_approved=require_approved,
    )


def validate_execution_profile(
    profile: ExecutionProfile, *, require_approved: bool = False
) -> None:
    _require_text(profile.profile_id, "execution profile ID")
    _require_text(profile.order_timing, "order timing")
    _require_text(profile.fill_convention, "fill convention")
    _require_text(profile.sizing, "sizing")
    _require_text(profile.liquidity_assumptions, "liquidity assumptions")
    for name, value in (
        ("fee rate", profile.fee_rate),
        ("commission", profile.commission_per_order),
        ("slippage", profile.slippage_rate),
        ("spread", profile.spread_rate),
    ):
        if value < 0:
            raise ValueError(f"{profile.profile_id}: {name} must be non-negative")
    if profile.minimum_tick is not None and profile.minimum_tick <= 0:
        raise ValueError(f"{profile.profile_id}: minimum tick must be positive")
    if profile.contract_multiplier is not None and profile.contract_multiplier <= 0:
        raise ValueError(f"{profile.profile_id}: contract multiplier must be positive")
    if profile.point_value is not None and profile.point_value <= 0:
        raise ValueError(f"{profile.profile_id}: point value must be positive")
    if profile.leverage <= 0:
        raise ValueError(f"{profile.profile_id}: leverage must be positive")
    _validate_approval(
        profile.approval_state,
        f"execution profile {profile.profile_id}",
        require_approved=require_approved,
    )


def validate_experiment_variant(
    variant: ExperimentVariant,
    *,
    instrument: InstrumentProfile,
    timeframe: TimeframeProfile,
    session: SessionProfile,
    execution: ExecutionProfile,
    strategy: StrategySpecification,
    require_approved: bool = False,
) -> None:
    if variant.strategy_id != strategy.identity.strategy_id:
        raise ValueError("Experiment strategy does not match its specification")
    if variant.instrument_symbol != instrument.symbol:
        raise ValueError("Experiment instrument does not match its profile")
    if variant.provider_symbol != instrument.provider_symbol:
        raise ValueError(
            f"{instrument.symbol}: provider-symbol substitution is not allowed"
        )
    if variant.timeframe_interval != timeframe.interval:
        raise ValueError("Experiment timeframe does not match its profile")
    if variant.session_id != instrument.session_profile_id or (
        session.session_id != variant.session_id
    ):
        raise ValueError(f"{instrument.symbol}: session profile does not match")
    if variant.execution_profile_id != instrument.execution_profile_id or (
        execution.profile_id != variant.execution_profile_id
    ):
        raise ValueError(f"{instrument.symbol}: execution profile does not match")
    if instrument.asset_class not in strategy.data.asset_classes:
        raise ValueError(
            f"{instrument.symbol}: strategy does not support asset class "
            f"{instrument.asset_class}"
        )
    if timeframe.interval not in strategy.data.supported_intervals:
        raise ValueError(
            f"{instrument.symbol}: strategy does not support interval "
            f"{timeframe.interval}"
        )
    if timeframe.interval not in instrument.supported_intervals:
        raise ValueError(
            f"{instrument.symbol}: instrument does not support interval "
            f"{timeframe.interval}"
        )
    if variant.adjusted_prices != instrument.adjusted_prices_required or (
        variant.adjusted_prices != strategy.data.adjusted_prices
    ):
        raise ValueError(f"{instrument.symbol}: adjusted-price requirements conflict")
    if instrument.continuous_market and session.anchor is None:
        raise ValueError(
            f"{instrument.symbol}: continuous session-based experiment requires an anchor"
        )
    if execution.minimum_tick is not None and instrument.tick_size is not None:
        if execution.minimum_tick != instrument.tick_size:
            raise ValueError(f"{instrument.symbol}: execution minimum tick conflicts")
    if instrument.asset_class == "futures":
        if execution.contract_multiplier != instrument.contract_multiplier:
            raise ValueError(
                f"{instrument.symbol}: execution contract multiplier conflicts"
            )
        if execution.point_value != instrument.point_value:
            raise ValueError(f"{instrument.symbol}: execution point value conflicts")
    _validate_approval(
        variant.approval_state,
        "experiment variant",
        require_approved=require_approved,
    )
