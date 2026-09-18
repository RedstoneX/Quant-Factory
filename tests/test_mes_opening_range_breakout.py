from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backtesting.run_mes_orb import (
    ALL_IN_FEE_PER_CONTRACT_PER_SIDE,
    SCENARIO_SLIPPAGE_TICKS,
    _config,
)
from backtesting.experiments import ExecutionConfig
from backtesting.experiments.runner import align_signals_for_execution
from market_data import load_data_locations, load_dataset_manifest, verify_dataset_file
from strategies import get_strategy
from strategies.mes_opening_range_breakout import (
    ORB_OFFSET_TICKS,
    ORB_RANGE_MINUTES,
    build_parameter_grid,
    generate_orb_signal_bundle,
)


def _session(day: str, *, breakout: str = "long") -> pd.DataFrame:
    local = pd.date_range(f"{day} 09:30", f"{day} 16:00", freq="5min", tz="America/New_York")
    index = local.tz_convert("UTC")
    frame = pd.DataFrame(
        {"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0, "Volume": 10},
        index=index,
    )
    confirmation = pd.Timestamp(f"{day} 10:35", tz="America/New_York").tz_convert("UTC")
    if breakout == "long":
        frame.loc[confirmation, ["Open", "High", "Low", "Close"]] = [100.5, 101.5, 100.25, 101.25]
    elif breakout == "short":
        frame.loc[confirmation, ["Open", "High", "Low", "Close"]] = [99.5, 99.75, 98.5, 98.75]
    return frame


def _schedule(*days: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "market_open": [pd.Timestamp(f"{day} 09:30", tz="America/New_York").tz_convert("UTC") for day in days],
            "market_close": [pd.Timestamp(f"{day} 16:00", tz="America/New_York").tz_convert("UTC") for day in days],
        },
        index=pd.DatetimeIndex([pd.Timestamp(day) for day in days]),
    )


@pytest.mark.parametrize("minutes", ORB_RANGE_MINUTES)
def test_opening_range_uses_exact_completed_bars(minutes: int) -> None:
    data = _session("2025-01-15")
    bundle = generate_orb_signal_bundle(
        data,
        {"range_minutes": minutes, "breakout_offset_ticks": 0},
        direction="long",
        schedule=_schedule("2025-01-15"),
    )
    row = bundle.opening_ranges.iloc[0]
    assert row["range_end"] == pd.Timestamp("2025-01-15 09:30", tz="America/New_York").tz_convert("UTC") + pd.Timedelta(minutes=minutes)
    assert row["range_high"] == 100.5
    assert row["range_low"] == 99.5


@pytest.mark.parametrize("offset", ORB_OFFSET_TICKS)
def test_long_breakout_enters_next_bar_and_exits_at_session_close(offset: int) -> None:
    data = _session("2025-01-15")
    bundle = generate_orb_signal_bundle(
        data, {"range_minutes": 60, "breakout_offset_ticks": offset},
        direction="long", schedule=_schedule("2025-01-15")
    )
    execution = ExecutionConfig.next_bar_open(
        initial_cash=100_000, fees=0, slippage=0, direction="longonly",
        leverage=1, accumulate=False, position_sizing="fixed_units",
        order_size=1, price_multiplier=5,
    )
    aligned = align_signals_for_execution(bundle.signals, execution)
    assert aligned.entries[aligned.entries].index.tolist() == [pd.Timestamp("2025-01-15 10:40", tz="America/New_York").tz_convert("UTC")]
    assert aligned.exits[aligned.exits].index.tolist() == [pd.Timestamp("2025-01-15 16:00", tz="America/New_York").tz_convert("UTC")]


def test_short_variant_is_structurally_separate_and_one_trade_per_session() -> None:
    days = ("2025-01-15", "2025-01-16")
    data = pd.concat([_session(day, breakout="short") for day in days])
    bundle = generate_orb_signal_bundle(
        data, {"range_minutes": 60, "breakout_offset_ticks": 2},
        direction="short", schedule=_schedule(*days)
    )
    assert not bundle.signals.entries.any()
    assert bundle.signals.short_entries is not None
    assert int(bundle.signals.short_entries.sum()) == 2
    assert int(bundle.signals.short_exits.sum()) == 2


def test_missing_range_bar_excludes_and_reports_session() -> None:
    days = ("2025-01-15", "2025-01-16")
    data = pd.concat([_session(day) for day in days])
    missing = pd.Timestamp("2025-01-15 09:40", tz="America/New_York").tz_convert("UTC")
    data = data.drop(missing)
    bundle = generate_orb_signal_bundle(
        data, {"range_minutes": 15, "breakout_offset_ticks": 0},
        direction="long", schedule=_schedule(*days)
    )
    assert bundle.eligible_session_count == 1
    assert bundle.issues[0].session_date == "2025-01-15"
    assert "opening range missing" in bundle.issues[0].reason


def test_gap_after_confirmation_prevents_fill_and_no_overnight_exit() -> None:
    data = _session("2025-01-15")
    next_bar = pd.Timestamp("2025-01-15 10:40", tz="America/New_York").tz_convert("UTC")
    data = data.drop(next_bar)
    bundle = generate_orb_signal_bundle(
        data, {"range_minutes": 60, "breakout_offset_ticks": 0},
        direction="long", schedule=_schedule("2025-01-15")
    )
    assert not bundle.signals.entries.any()
    assert not bundle.signals.exits.any()


def test_winter_and_summer_anchors_resolve_to_0930_new_york() -> None:
    days = ("2025-01-15", "2025-07-15")
    data = pd.concat([_session(day) for day in days])
    bundle = generate_orb_signal_bundle(
        data, {"range_minutes": 5, "breakout_offset_ticks": 0},
        direction="long", schedule=_schedule(*days)
    )
    opens = pd.DatetimeIndex(bundle.opening_ranges["session_open"])
    assert opens[0].hour == 14
    assert opens[1].hour == 13
    assert set(opens.tz_convert("America/New_York").hour) == {9}


def test_post_confirmation_prices_do_not_change_signal_time() -> None:
    data = _session("2025-01-15")
    changed = data.copy()
    changed.loc[changed.index > pd.Timestamp("2025-01-15 10:35", tz="America/New_York").tz_convert("UTC"), "Close"] = 150.0
    kwargs = dict(parameters={"range_minutes": 60, "breakout_offset_ticks": 0}, direction="long", schedule=_schedule("2025-01-15"))
    left = generate_orb_signal_bundle(data, **kwargs).signals.entries
    right = generate_orb_signal_bundle(changed, **kwargs).signals.entries
    pd.testing.assert_series_equal(left, right)


def test_grid_and_registry_have_exact_30_structural_variants() -> None:
    assert len(build_parameter_grid()) == 15
    assert len(build_parameter_grid()) * 2 == 30
    assert get_strategy("mes_opening_range_breakout_long").spec.identity.direction == "long"
    assert get_strategy("mes_opening_range_breakout_short").spec.identity.direction == "short"


def test_cataloged_mes_file_matches_committed_manifest() -> None:
    manifest = load_dataset_manifest("futures_MES_5m_databento")
    path = verify_dataset_file(manifest, load_data_locations())
    assert path.name == "MES_5m_databento.parquet"
    assert manifest.row_count == 476_042


@pytest.mark.parametrize("scenario,ticks", SCENARIO_SLIPPAGE_TICKS.items())
def test_mes_cost_scenarios_are_futures_native(
    scenario: str, ticks: float
) -> None:
    execution = _config("longonly", scenario).execution
    assert execution.fees == 0.0
    assert execution.slippage == 0.0
    assert execution.fixed_fee_per_contract_per_side == ALL_IN_FEE_PER_CONTRACT_PER_SIDE
    assert execution.slippage_ticks == ticks
    assert execution.absolute_slippage_points == ticks * 0.25
    assert execution.order_size == 1.0
    assert execution.price_multiplier == 5.0
