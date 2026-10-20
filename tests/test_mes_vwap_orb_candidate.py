from __future__ import annotations

import pandas as pd
import pytest

from backtesting.experiments import ExecutionConfig, ExperimentConfig
from backtesting.screening import ScreeningConfig
from market_data import MarketDataConfig
from backtesting.experiments.runner import (
    _construct_portfolio,
    align_signals_for_execution,
)
from strategies import get_strategy
from strategies.mes_vwap_orb_candidate import (
    CANDIDATE_ID,
    CANDIDATE_VERSION,
    STRATEGY_ID,
    STRATEGY_VERSION,
    generate_candidate_signals,
)


def _session(day: str = "2025-01-15") -> pd.DataFrame:
    index = pd.date_range(
        f"{day} 09:30",
        f"{day} 16:00",
        freq="5min",
        inclusive="left",
        tz="America/New_York",
    ).tz_convert("UTC")
    return pd.DataFrame(
        {
            "Open": 100.0,
            "High": 100.5,
            "Low": 99.5,
            "Close": 100.0,
            "Volume": 10.0,
        },
        index=index,
    )


def _schedule(day: str = "2025-01-15") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market_open": [
                pd.Timestamp(f"{day} 09:30", tz="America/New_York").tz_convert("UTC")
            ],
            "market_close": [
                pd.Timestamp(f"{day} 16:00", tz="America/New_York").tz_convert("UTC")
            ],
        },
        index=pd.DatetimeIndex([pd.Timestamp(day)]),
    )


def _execution() -> ExecutionConfig:
    return ExecutionConfig.next_bar_open(
        initial_cash=100_000,
        fees=0,
        slippage=0,
        direction="both",
        leverage=1,
        accumulate=False,
        position_sizing="fixed_units",
        order_size=1,
        price_multiplier=5,
    )


def test_registered_candidate_uses_exact_fixed_contract_and_long_filters() -> None:
    data = _session()
    signal_time = pd.Timestamp("2025-01-15 10:00", tz="America/New_York").tz_convert("UTC")
    next_time = signal_time + pd.Timedelta(minutes=5)
    data.loc[signal_time, ["Open", "High", "Low", "Close"]] = [100.5, 101.6, 100.3, 101.5]
    data.loc[next_time, "Open"] = 101.5

    bundle = generate_candidate_signals(data, schedule=_schedule())

    assert get_strategy(STRATEGY_ID).spec.identity.version == STRATEGY_VERSION
    assert CANDIDATE_ID in get_strategy(STRATEGY_ID).spec.source
    assert CANDIDATE_VERSION in get_strategy(STRATEGY_ID).spec.source
    assert bundle.calendar_session_count == 1
    assert bundle.eligible_session_count == 1
    assert bundle.signals.entries.at[signal_time]
    assert not bundle.signals.short_entries.any()
    assert bundle.signals.exits.at[
        pd.Timestamp("2025-01-15 15:50", tz="America/New_York").tz_convert("UTC")
    ]
    assert bundle.signals.stop_loss.at[signal_time] == pytest.approx(2.0 / 101.5)
    assert bundle.signals.take_profit.at[signal_time] == pytest.approx(3.0 / 101.5)

    aligned = align_signals_for_execution(bundle.signals, _execution())
    assert aligned.entries.at[next_time]
    assert aligned.stop_loss.at[next_time] == pytest.approx(2.0 / 101.5)
    assert aligned.take_profit.at[next_time] == pytest.approx(3.0 / 101.5)
    assert aligned.exits.at[
        pd.Timestamp("2025-01-15 15:55", tz="America/New_York").tz_convert("UTC")
    ]


def test_short_breakout_uses_vwap_and_body_confirmation() -> None:
    data = _session()
    signal_time = pd.Timestamp("2025-01-15 10:00", tz="America/New_York").tz_convert("UTC")
    data.loc[signal_time, ["Open", "High", "Low", "Close"]] = [99.5, 99.7, 98.3, 98.5]

    bundle = generate_candidate_signals(data, schedule=_schedule())

    assert bundle.signals.short_entries.at[signal_time]
    assert not bundle.signals.entries.any()
    assert bundle.signals.stop_loss.at[signal_time] > 0
    assert bundle.signals.take_profit.at[signal_time] == pytest.approx(
        bundle.signals.stop_loss.at[signal_time] * 1.5
    )


def test_weak_body_and_unusable_volume_do_not_create_a_trade() -> None:
    data = _session()
    signal_time = pd.Timestamp("2025-01-15 10:00", tz="America/New_York").tz_convert("UTC")
    data.loc[signal_time, ["Open", "High", "Low", "Close"]] = [100.5, 102.0, 100.0, 101.5]

    weak_body = generate_candidate_signals(data, schedule=_schedule())
    assert not weak_body.signals.entries.any()

    volume_time = pd.Timestamp("2025-01-15 09:55", tz="America/New_York").tz_convert("UTC")
    data.loc[volume_time, "Volume"] = 0
    bad_volume = generate_candidate_signals(data, schedule=_schedule())
    assert not bad_volume.signals.entries.any()
    assert bad_volume.issues[0].reason == "missing or unusable volume"


@pytest.mark.licensed_vectorbt
def test_stop_orders_use_ohlc_and_conservative_stop_fill(tmp_path) -> None:
    data = _session()
    signal_time = pd.Timestamp("2025-01-15 10:00", tz="America/New_York").tz_convert("UTC")
    data.loc[signal_time, ["Open", "High", "Low", "Close"]] = [100.5, 101.6, 100.3, 101.5]
    data.loc[signal_time + pd.Timedelta(minutes=5), "Open"] = 101.5
    signals = generate_candidate_signals(data, schedule=_schedule()).signals
    aligned = align_signals_for_execution(signals, _execution())
    config = ExperimentConfig(
        experiment_id="orb-stop", strategy_id=STRATEGY_ID, parameter_combinations=({},),
        market_data=MarketDataConfig(
            symbol="MES", provider="Databento", provider_implementation="fixture", interval="5m",
            requested_start="2025-01-15", end_date_policy="fixed", adjusted=False,
            exchange_calendar="NYSE", market_timezone="America/New_York", cache_path=tmp_path / "MES.parquet",
        ),
        execution=_execution(), ranking_columns=("total_return",), ranking_ascending=(False,),
        output_path=tmp_path / "unused.csv", screening=ScreeningConfig.provisional_defaults(),
    )
    portfolio = _construct_portfolio(data, aligned, config)

    entry_bar = signal_time + pd.Timedelta(minutes=5)
    stop_fraction = float(aligned.stop_loss.at[entry_bar])
    trades = portfolio.trades.records_readable
    orders = portfolio.orders.records_readable
    assert len(trades) == 1 and trades.at[0, "Direction"] == "Long"
    # Entry fills at the next bar's open in dollar-per-contract units.
    assert trades.at[0, "Entry Index"] == entry_bar
    assert trades.at[0, "Avg Entry Price"] == pytest.approx(101.5 * 5)
    # The stop is hit on the first bar whose low reaches the opening-range boundary, and it
    # fills at the stop level (not the close), so the loss is exactly the signalled risk.
    assert orders["Stop Type"].tolist() == [None, "SL"]
    assert trades.at[0, "Avg Exit Price"] == pytest.approx(101.5 * 5 * (1 - stop_fraction))
    assert trades.at[0, "Avg Exit Price"] == pytest.approx(99.5 * 5)
    assert trades.at[0, "Exit Index"] == entry_bar + pd.Timedelta(minutes=5)
    assert trades.at[0, "Return"] == pytest.approx(-stop_fraction)
