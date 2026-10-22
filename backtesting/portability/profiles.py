"""Approved compatibility profiles for the existing SPY daily RSI experiment."""

from datetime import time, timedelta

from backtesting.portability.models import (
    ExecutionProfile,
    InstrumentProfile,
    SessionProfile,
    TimeframeProfile,
)

US_EQUITY_RTH_SESSION = SessionProfile(
    session_id="us_equity_rth",
    name="US equity regular trading session",
    timezone="America/New_York",
    anchor=time(9, 30),
    start=time(9, 30),
    end=time(16, 0),
    trading_day_boundary="NYSE exchange session",
    designation="regular",
    overnight=False,
    calendar_reference="NYSE",
    continuous_market=False,
    rationale="Preserve the approved exchange-aware daily US equity session.",
    approval_state="approved",
)

SPY_DAILY_TIMEFRAME = TimeframeProfile(
    interval="1 day",
    bar_duration=timedelta(days=1),
    timezone="America/New_York",
    kind="native",
    resampling_origin=None,
    resampling_offset=None,
    incomplete_bar_policy="Exclude incomplete current exchange session",
    required_source_resolution=timedelta(days=1),
    available_source_resolution=timedelta(days=1),
    approval_state="approved",
)

SPY_RSI_EXECUTION_PROFILE = ExecutionProfile(
    profile_id="spy_rsi_daily_next_open",
    fee_rate=0.0005,
    commission_per_order=0.0,
    slippage_rate=0.0002,
    spread_rate=0.0,
    order_timing="completed-bar signal; next available session",
    fill_convention="next session open",
    minimum_tick=0.01,
    contract_multiplier=1.0,
    point_value=1.0,
    sizing="all available cash, one long position",
    leverage=1.0,
    shorting_available=False,
    liquidity_assumptions=(
        "Research assumptions only; no production provider or broker calibration."
    ),
    approval_state="approved",
)

SPY_DAILY_INSTRUMENT = InstrumentProfile(
    symbol="SPY",
    display_name="SPDR S&P 500 ETF Trust",
    asset_class="etf",
    venue="NYSE Arca",
    base_currency="USD",
    quote_currency=None,
    timezone="America/New_York",
    trading_calendar="NYSE",
    tick_size=0.01,
    price_precision=2,
    contract_multiplier=1.0,
    point_value=1.0,
    continuous_market=False,
    supported_intervals=("1 day",),
    provider="Yahoo Finance",
    provider_symbol="SPY",
    adjusted_prices_required=True,
    session_profile_id=US_EQUITY_RTH_SESSION.session_id,
    execution_profile_id=SPY_RSI_EXECUTION_PROFILE.profile_id,
    approval_state="approved",
)
