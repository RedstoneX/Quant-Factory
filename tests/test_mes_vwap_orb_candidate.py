from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from backtesting.experiments import ExecutionConfig
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


def test_stop_orders_use_ohlc_and_conservative_stop_fill(monkeypatch) -> None:
    import backtesting.experiments.runner as runner

    data = _session()
    signal_time = pd.Timestamp("2025-01-15 10:00", tz="America/New_York").tz_convert("UTC")
    data.loc[signal_time, ["Open", "High", "Low", "Close"]] = [100.5, 101.6, 100.3, 101.5]
    data.loc[signal_time + pd.Timedelta(minutes=5), "Open"] = 101.5
    signals = generate_candidate_signals(data, schedule=_schedule()).signals
    aligned = align_signals_for_execution(signals, _execution())
    captured: dict[str, object] = {}

    class Portfolio:
        @staticmethod
        def from_signals(**kwargs):
            captured.update(kwargs)
            return "portfolio"

    monkeypatch.setattr(runner, "require_vectorbtpro", lambda: SimpleNamespace(Portfolio=Portfolio))
    result = _construct_portfolio(data, aligned, SimpleNamespace(execution=_execution()))

    assert result == "portfolio"
    assert captured["stop_exit_price"] == "Stop"
    assert captured["stop_entry_price"] == "Open"
    assert captured["sl_stop"] is aligned.stop_loss
    assert captured["tp_stop"] is aligned.take_profit
    assert captured["high"].equals(data["High"] * 5)
    assert captured["low"].equals(data["Low"] * 5)
