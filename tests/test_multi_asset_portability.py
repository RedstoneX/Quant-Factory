"""Focused tests for typed multi-asset experiment planning."""

from dataclasses import replace
from datetime import time, timedelta

import pytest

import backtesting.run_rsi_demo as demo
from backtesting.portability import (
    ExecutionProfile,
    InstrumentProfile,
    SPY_DAILY_INSTRUMENT,
    SPY_DAILY_TIMEFRAME,
    SPY_RSI_EXECUTION_PROFILE,
    SessionProfile,
    TimeframeProfile,
    US_EQUITY_RTH_SESSION,
    summarize_experiment_matrix,
    validate_experiment_variant,
    validate_instrument_profile,
    validate_session_profile,
    validate_timeframe_profile,
)
from strategies.parameter_governance import summarize_parameter_plan
from strategies.rsi_mean_reversion import (
    ENTRY_THRESHOLDS,
    EXIT_THRESHOLDS,
    RSI_MEAN_REVERSION_SPEC,
    RSI_WINDOWS,
    build_parameter_grid,
)


def _equity(symbol: str = "MSFT", asset_class: str = "equity") -> InstrumentProfile:
    return replace(
        SPY_DAILY_INSTRUMENT,
        symbol=symbol,
        display_name=symbol,
        asset_class=asset_class,  # type: ignore[arg-type]
        provider_symbol=symbol,
    )


def _futures() -> InstrumentProfile:
    return InstrumentProfile(
        symbol="MES",
        display_name="Micro E-mini S&P 500",
        asset_class="futures",
        venue="CME",
        base_currency="USD",
        quote_currency=None,
        timezone="America/Chicago",
        trading_calendar="CME",
        tick_size=0.25,
        price_precision=2,
        contract_multiplier=5.0,
        point_value=5.0,
        continuous_market=False,
        supported_intervals=("1 minute",),
        provider="Databento",
        provider_symbol="MES.c.0",
        adjusted_prices_required=False,
        session_profile_id="cme_globex",
        execution_profile_id="mes_research",
        approval_state="approved",
    )


def _currency_instrument(asset_class: str) -> InstrumentProfile:
    symbol = "BTC/USD" if asset_class == "crypto" else "EUR/USD"
    return InstrumentProfile(
        symbol=symbol,
        display_name=symbol,
        asset_class=asset_class,  # type: ignore[arg-type]
        venue="approved venue",
        base_currency=symbol[:3],
        quote_currency="USD",
        timezone="UTC",
        trading_calendar=None,
        tick_size=0.01,
        price_precision=2,
        contract_multiplier=None,
        point_value=None,
        continuous_market=True,
        supported_intervals=("1 hour",),
        provider="approved provider",
        provider_symbol=symbol,
        adjusted_prices_required=False,
        session_profile_id=f"{asset_class}_utc",
        execution_profile_id=f"{asset_class}_research",
        approval_state="approved",
    )


@pytest.mark.parametrize(
    "profile",
    [
        _equity(),
        _equity("SPY", "etf"),
        _futures(),
        _currency_instrument("crypto"),
        _currency_instrument("fx"),
    ],
)
def test_supported_asset_profiles_are_valid(profile: InstrumentProfile) -> None:
    validate_instrument_profile(profile, require_approved=True)


def test_unknown_asset_class_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown asset class"):
        validate_instrument_profile(_equity(asset_class="option"))


def test_missing_timezone_and_provider_symbol_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone is required"):
        validate_instrument_profile(replace(SPY_DAILY_INSTRUMENT, timezone=""))
    with pytest.raises(ValueError, match="provider symbol is required"):
        validate_instrument_profile(replace(SPY_DAILY_INSTRUMENT, provider_symbol=""))


@pytest.mark.parametrize("asset_class", ["crypto", "fx"])
def test_currency_pairs_require_base_and_quote(asset_class: str) -> None:
    profile = replace(_currency_instrument(asset_class), base_currency=None)
    with pytest.raises(ValueError, match="requires base and quote currencies"):
        validate_instrument_profile(profile)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("tick_size", "require tick size"),
        ("contract_multiplier", "require a positive contract multiplier"),
        ("point_value", "require a positive point value"),
    ],
)
def test_futures_require_contract_metadata(field: str, message: str) -> None:
    profile = replace(_futures(), **{field: None})
    with pytest.raises(ValueError, match=message):
        validate_instrument_profile(profile)


def test_continuous_session_requires_anchor() -> None:
    session = SessionProfile(
        session_id="crypto_utc",
        name="Crypto UTC day",
        timezone="UTC",
        anchor=None,
        start=None,
        end=None,
        trading_day_boundary="UTC day",
        designation="synthetic",
        overnight=False,
        calendar_reference=None,
        continuous_market=True,
        rationale="Synthetic session for a session-based hypothesis.",
        approval_state="approved",
    )
    with pytest.raises(ValueError, match="requires an explicit anchor"):
        validate_session_profile(session)


def test_invalid_session_times_are_rejected() -> None:
    with pytest.raises(ValueError, match="start and end must differ"):
        validate_session_profile(
            replace(US_EQUITY_RTH_SESSION, end=time(9, 30))
        )
    with pytest.raises(ValueError, match="overnight flag conflicts"):
        validate_session_profile(
            replace(US_EQUITY_RTH_SESSION, start=time(18), end=time(17))
        )


def test_source_resolution_too_coarse_is_rejected() -> None:
    timeframe = replace(
        SPY_DAILY_TIMEFRAME,
        interval="1 hour",
        bar_duration=timedelta(hours=1),
        required_source_resolution=timedelta(minutes=5),
        available_source_resolution=timedelta(days=1),
    )
    with pytest.raises(ValueError, match="available source data is too coarse"):
        validate_timeframe_profile(timeframe)


def _summary(
    *,
    instruments: tuple[InstrumentProfile, ...] = (SPY_DAILY_INSTRUMENT,),
    timeframes: tuple[TimeframeProfile, ...] = (SPY_DAILY_TIMEFRAME,),
    sessions: tuple[SessionProfile, ...] = (US_EQUITY_RTH_SESSION,),
    executions: tuple[ExecutionProfile, ...] = (SPY_RSI_EXECUTION_PROFILE,),
):
    return summarize_experiment_matrix(
        instruments=instruments,
        timeframes=timeframes,
        sessions=sessions,
        execution_profiles=executions,
        strategy=RSI_MEAN_REVERSION_SPEC,
        parameter_plan=summarize_parameter_plan(
            RSI_MEAN_REVERSION_SPEC, require_approved=True
        ),
    )


def test_unsupported_interval_and_asset_class_are_excluded() -> None:
    hourly = replace(
        SPY_DAILY_TIMEFRAME,
        interval="1 hour",
        bar_duration=timedelta(hours=1),
        required_source_resolution=timedelta(hours=1),
        available_source_resolution=timedelta(hours=1),
    )
    interval_result = _summary(timeframes=(hourly,))
    assert interval_result.experiment_variant_count == 0
    assert "does not support interval" in interval_result.unsupported_combinations[0].reason

    crypto = replace(
        _currency_instrument("crypto"),
        session_profile_id=US_EQUITY_RTH_SESSION.session_id,
        execution_profile_id=SPY_RSI_EXECUTION_PROFILE.profile_id,
    )
    asset_result = _summary(instruments=(crypto,))
    assert asset_result.experiment_variant_count == 0
    assert "does not support asset class" in asset_result.unsupported_combinations[0].reason


def test_missing_execution_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing execution profile"):
        _summary(executions=())


def test_provider_symbol_substitution_is_rejected() -> None:
    variant = replace(_summary().variants[0], provider_symbol="SPY.US")
    with pytest.raises(ValueError, match="substitution is not allowed"):
        validate_experiment_variant(
            variant,
            instrument=SPY_DAILY_INSTRUMENT,
            timeframe=SPY_DAILY_TIMEFRAME,
            session=US_EQUITY_RTH_SESSION,
            execution=SPY_RSI_EXECUTION_PROFILE,
            strategy=RSI_MEAN_REVERSION_SPEC,
            require_approved=True,
        )


def test_adjusted_price_conflict_is_unsupported() -> None:
    unadjusted = replace(SPY_DAILY_INSTRUMENT, adjusted_prices_required=False)
    result = _summary(instruments=(unadjusted,))
    assert result.experiment_variant_count == 0
    assert "adjusted-price requirements conflict" in result.unsupported_combinations[0].reason


def test_duplicate_combinations_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate experiment combinations"):
        _summary(instruments=(SPY_DAILY_INSTRUMENT, SPY_DAILY_INSTRUMENT))


def test_variant_and_parameter_grid_counts_are_deterministic() -> None:
    result = _summary(instruments=(SPY_DAILY_INSTRUMENT, _equity()))
    assert result.instrument_count == 2
    assert result.timeframe_count == 1
    assert result.session_count == 1
    assert result.execution_profile_count == 1
    assert result.experiment_variant_count == 2
    assert result.parameter_combinations == 27
    assert result.total_planned_simulations == 54
    assert result.unsupported_combinations == ()
    assert result == _summary(instruments=(SPY_DAILY_INSTRUMENT, _equity()))


def test_unapproved_entries_are_rejected() -> None:
    draft = replace(SPY_DAILY_INSTRUMENT, approval_state="draft")
    with pytest.raises(ValueError, match="entry is not approved"):
        _summary(instruments=(draft,))


def test_spy_rsi_profile_preserves_existing_experiment() -> None:
    assert SPY_DAILY_INSTRUMENT.asset_class == "etf"
    assert SPY_DAILY_INSTRUMENT.provider_symbol == demo.DATA_CONFIG.symbol == "SPY"
    assert SPY_DAILY_INSTRUMENT.adjusted_prices_required is demo.DATA_CONFIG.adjusted
    assert SPY_DAILY_TIMEFRAME.interval == demo.DATA_CONFIG.interval == "1 day"
    assert SPY_RSI_EXECUTION_PROFILE.fee_rate == demo.EXPERIMENT_CONFIG.fees
    assert SPY_RSI_EXECUTION_PROFILE.slippage_rate == demo.EXPERIMENT_CONFIG.slippage
    assert SPY_RSI_EXECUTION_PROFILE.leverage == demo.EXPERIMENT_CONFIG.leverage
    assert RSI_MEAN_REVERSION_SPEC.data.asset_classes == ("equity", "etf")
    assert RSI_WINDOWS == (7, 14, 21)
    assert ENTRY_THRESHOLDS == (20, 25, 30)
    assert EXIT_THRESHOLDS == (50, 55, 60)
    assert len(build_parameter_grid()) == len(demo.PARAMETER_COMBINATIONS) == 27
