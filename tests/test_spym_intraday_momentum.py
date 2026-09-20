"""Focused contract coverage for the fixed Decision-296 SPYM screen."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

import backtesting.run_spym_intraday_momentum as runner
from strategies.spym_intraday_momentum import generate_intraday_momentum_signal_bundle


def _time(day: str, value: str) -> pd.Timestamp:
    return pd.Timestamp(f"{day} {value}", tz="America/New_York").tz_convert("UTC")


def _schedule(*days: str) -> pd.DataFrame:
    return pd.DataFrame(index=pd.DatetimeIndex(days))


def _data(*, zero: bool = False, missing: str | None = None) -> pd.DataFrame:
    rows = [
        (_time("2026-01-02", "15:59"), 100.0, 100.0),
        (_time("2026-01-05", "09:59"), 101.0 if not zero else 100.0, 101.0 if not zero else 100.0),
        (_time("2026-01-05", "15:30"), 102.0, 102.5),
        (_time("2026-01-05", "15:59"), 103.0, 103.5),
        (_time("2026-01-06", "09:59"), 99.0, 99.0),
        (_time("2026-01-06", "15:30"), 98.0, 98.5),
        (_time("2026-01-06", "15:59"), 97.0, 97.5),
    ]
    if missing is not None:
        rows = [row for row in rows if row[0] != _time("2026-01-06", missing)]
    index = pd.DatetimeIndex([row[0] for row in rows])
    return pd.DataFrame({"Open": [row[1] for row in rows], "Close": [row[2] for row in rows]}, index=index)


def test_boundary_extraction_preserves_long_short_and_zero_source_rule() -> None:
    bundle = generate_intraday_momentum_signal_bundle(_data(), schedule=_schedule("2026-01-02", "2026-01-05", "2026-01-06"))

    assert [item.signal for item in bundle.eligible_sessions] == ["long", "short"]
    assert bundle.signals.entries.at[_time("2026-01-05", "15:30")]
    assert bundle.signals.short_entries.at[_time("2026-01-06", "15:30")]
    assert bundle.signals.metadata["zero_signal_count"] == 0

    zero = generate_intraday_momentum_signal_bundle(_data(zero=True), schedule=_schedule("2026-01-02", "2026-01-05", "2026-01-06"))
    assert zero.eligible_sessions[0].signal == "short"
    assert zero.signals.short_entries.at[_time("2026-01-05", "15:30")]
    assert zero.signals.metadata["zero_signal_count"] == 1


def test_missing_any_required_boundary_excludes_that_session_without_synthesis() -> None:
    bundle = generate_intraday_momentum_signal_bundle(_data(missing="15:30"), schedule=_schedule("2026-01-02", "2026-01-05", "2026-01-06"))

    assert [item.session_date for item in bundle.eligible_sessions] == ["2026-01-05"]
    assert bundle.excluded_sessions[-1]["session_date"] == "2026-01-06"
    assert "15:30" in bundle.excluded_sessions[-1]["reason"]


def test_prior_early_close_without_1559_excludes_next_scheduled_session() -> None:
    schedule = _schedule("2025-11-28", "2025-12-01")
    current_boundaries = [
        (_time("2025-12-01", "09:59"), 101.0, 101.0),
        (_time("2025-12-01", "15:30"), 102.0, 102.5),
        (_time("2025-12-01", "15:59"), 103.0, 103.5),
    ]
    data = pd.DataFrame(
        {"Open": [row[1] for row in current_boundaries], "Close": [row[2] for row in current_boundaries]},
        index=pd.DatetimeIndex([row[0] for row in current_boundaries]),
    )
    bundle = generate_intraday_momentum_signal_bundle(data, schedule=schedule)

    exclusion = next(item for item in bundle.excluded_sessions if item["session_date"] == "2025-12-01")
    assert "prior regular-session 15:59 (2025-11-28)" in exclusion["reason"]
    assert not bundle.signals.entries.any()
    assert not bundle.signals.short_entries.any()


def test_mixed_price_adapter_uses_entry_open_exit_close_and_conservative_costs(monkeypatch) -> None:
    data = _data()
    bundle = generate_intraday_momentum_signal_bundle(data, schedule=_schedule("2026-01-02", "2026-01-05", "2026-01-06"))
    captured = {}

    class Portfolio:
        @staticmethod
        def from_signals(**kwargs):
            captured.update(kwargs)
            return "portfolio"

    monkeypatch.setattr(runner, "require_vectorbtpro", lambda: SimpleNamespace(Portfolio=Portfolio))
    assert runner.build_mixed_price_portfolio(data, bundle) == "portfolio"
    prices = captured["price"]
    assert prices.at[_time("2026-01-05", "15:30")] == 102.0
    assert prices.at[_time("2026-01-05", "15:59")] == 103.5
    assert prices.at[_time("2026-01-06", "15:30")] == 98.0
    assert prices.at[_time("2026-01-06", "15:59")] == 97.5
    assert captured["fees"] == 0.0005
    assert captured["slippage"] == 0.0002
    assert captured["size"] == float("inf")
    assert captured["accumulate"] is False


def test_candidate_adapter_fails_closed_on_unpaired_signals() -> None:
    data = _data()
    bundle = generate_intraday_momentum_signal_bundle(data, schedule=_schedule("2026-01-02", "2026-01-05", "2026-01-06"))
    broken = SimpleNamespace(signals=SimpleNamespace(**{**bundle.signals.__dict__, "exits": bundle.signals.exits & False}), eligible_sessions=bundle.eligible_sessions)
    with pytest.raises(RuntimeError, match="entries and exits must be paired"):
        runner.validate_candidate_execution(data, broken, runner.exact_execution_prices(data, broken.signals))


def test_readiness_measurement_is_fixed_and_fails_closed_on_drift() -> None:
    bundle = SimpleNamespace(signals=SimpleNamespace(metadata={
        "eligible_session_count": 133, "long_session_count": 70,
        "short_session_count": 63, "zero_signal_count": 0,
    }))
    runner.assert_readiness(bundle)
    bundle.signals.metadata["short_session_count"] = 62
    with pytest.raises(RuntimeError, match="session readiness"):
        runner.assert_readiness(bundle)


def test_completed_trade_validation_requires_one_closed_trade_per_eligible_session() -> None:
    bundle = SimpleNamespace(
        eligible_sessions=tuple(range(133)),
        signals=SimpleNamespace(metadata={"long_session_count": 70, "short_session_count": 63}),
    )
    trades = pd.DataFrame({"Status": ["Closed"] * 133, "Direction": ["Long"] * 70 + ["Short"] * 63})
    orders = pd.DataFrame({"Timestamp": ["2026-01-01"] * 266, "Price": [100.0] * 266})
    portfolio = SimpleNamespace(trades=SimpleNamespace(records_readable=trades), orders=SimpleNamespace(records_readable=orders))
    validations = runner.validate_completed_trades(portfolio, bundle)
    assert validations[0]["completed_trade_count"] == 133
    assert validations[1] == {"gate_id": "mixed_price.completed_trade_directions", "status": "passed", "long_trade_count": 70, "short_trade_count": 63}
    assert validations[2]["filled_order_count"] == 266

    bad_portfolio = SimpleNamespace(trades=SimpleNamespace(records_readable=trades.iloc[:2]), orders=SimpleNamespace(records_readable=orders))
    with pytest.raises(RuntimeError, match="does not match 133 eligible sessions"):
        runner.validate_completed_trades(bad_portfolio, bundle)
    missing_direction = SimpleNamespace(
        trades=SimpleNamespace(records_readable=trades.drop(columns="Direction")),
        orders=SimpleNamespace(records_readable=orders),
    )
    with pytest.raises(RuntimeError, match="must expose Direction"):
        runner.validate_completed_trades(missing_direction, bundle)


def test_annualization_uses_only_eligible_daily_equity_and_252_zero_risk_free() -> None:
    index = pd.DatetimeIndex([
        _time("2026-01-05", "15:59"), _time("2026-01-06", "15:59"), _time("2026-01-07", "15:59"),
    ])
    equity = pd.Series([10_100.0, 50_000.0, 10_201.0], index=index)
    eligible = (SimpleNamespace(session_date="2026-01-05"), SimpleNamespace(session_date="2026-01-07"))
    daily, returns = runner.daily_equity_and_returns(equity, eligible)

    assert len(daily) == len(returns) == 2
    assert daily.tolist() == [10_100.0, 10_201.0]
    portfolio = SimpleNamespace(value=equity, trades=SimpleNamespace(count=lambda: 2, win_rate=0.5))
    metrics = runner.daily_metrics(portfolio, SimpleNamespace(eligible_sessions=eligible))
    assert metrics["annualized_return"] == pytest.approx((1.0201 ** (252 / 2)) - 1.0)
    assert runner.execution_assumptions()["annualization"] == {
        "sessions_per_year": 252, "risk_free_rate": 0.0, "basis": "end-of-session strategy equity and daily returns",
    }
