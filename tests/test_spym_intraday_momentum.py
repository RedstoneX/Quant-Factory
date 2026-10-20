"""SPYM intraday momentum: signal boundaries, exact mixed-price execution, and daily metrics."""

from __future__ import annotations

from dataclasses import replace

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


def _bundle(data: pd.DataFrame):
    return generate_intraday_momentum_signal_bundle(data, schedule=_schedule("2026-01-02", "2026-01-05", "2026-01-06"))


def test_boundary_extraction_preserves_long_short_and_zero_source_rule() -> None:
    bundle = _bundle(_data())

    assert [item.signal for item in bundle.eligible_sessions] == ["long", "short"]
    assert bundle.signals.entries.at[_time("2026-01-05", "15:30")]
    assert bundle.signals.short_entries.at[_time("2026-01-06", "15:30")]
    assert bundle.signals.metadata["zero_signal_count"] == 0

    zero = _bundle(_data(zero=True))
    assert zero.eligible_sessions[0].signal == "short"
    assert zero.signals.short_entries.at[_time("2026-01-05", "15:30")]
    assert zero.signals.metadata["zero_signal_count"] == 1


def test_missing_any_required_boundary_excludes_that_session_without_synthesis() -> None:
    bundle = _bundle(_data(missing="15:30"))

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


@pytest.mark.licensed_vectorbt
def test_mixed_price_adapter_uses_entry_open_exit_close_and_conservative_costs() -> None:
    data = _data()
    bundle = _bundle(data)
    portfolio = runner.build_mixed_price_portfolio(data, bundle)
    orders = portfolio.orders.records_readable.set_index("Fill Index")
    fills = orders["Price"]
    # Long: buys at the 15:30 open plus adverse slippage, sells at the 15:59 close minus it.
    assert fills.at[_time("2026-01-05", "15:30")] == pytest.approx(102.0 * (1 + runner.SLIPPAGE_RATE))
    assert fills.at[_time("2026-01-05", "15:59")] == pytest.approx(103.5 * (1 - runner.SLIPPAGE_RATE))
    # Short: sells at the 15:30 open minus slippage, covers at the 15:59 close plus it.
    assert fills.at[_time("2026-01-06", "15:30")] == pytest.approx(98.0 * (1 - runner.SLIPPAGE_RATE))
    assert fills.at[_time("2026-01-06", "15:59")] == pytest.approx(97.5 * (1 + runner.SLIPPAGE_RATE))
    assert runner.FEE_RATE == 0.0005 and runner.SLIPPAGE_RATE == 0.0002
    assert orders["Fees"].tolist() == pytest.approx((orders["Size"] * fills * runner.FEE_RATE).tolist())
    # size=inf, accumulate=False: the whole account is deployed exactly once per session.
    trades = portfolio.trades.records_readable
    assert len(trades) == 2 and trades["Status"].eq("Closed").all()
    assert orders["Size"].iloc[0] * fills.iloc[0] * (1 + runner.FEE_RATE) == pytest.approx(runner.INITIAL_CASH)


def test_candidate_adapter_fails_closed_on_unpaired_signals() -> None:
    data = _data()
    bundle = _bundle(data)
    broken = replace(bundle, signals=replace(bundle.signals, exits=bundle.signals.exits & False))
    with pytest.raises(RuntimeError, match="entries and exits must be paired"):
        runner.validate_candidate_execution(data, broken, runner.exact_execution_prices(data, broken.signals))


def test_readiness_measurement_is_fixed_and_fails_closed_on_drift() -> None:
    bundle = _bundle(_data())
    with pytest.raises(RuntimeError, match="session readiness"):
        runner.assert_readiness(bundle)
    approved = {
        "eligible_session_count": 133, "long_session_count": 70,
        "short_session_count": 63, "zero_signal_count": 0,
    }
    runner.assert_readiness(replace(bundle, signals=replace(bundle.signals, metadata=approved)))
    drifted = approved | {"short_session_count": 62}
    with pytest.raises(RuntimeError, match="session readiness"):
        runner.assert_readiness(replace(bundle, signals=replace(bundle.signals, metadata=drifted)))


@pytest.mark.licensed_vectorbt
def test_completed_trade_validation_requires_one_closed_trade_per_eligible_session() -> None:
    data = _data()
    bundle = _bundle(data)
    portfolio = runner.build_mixed_price_portfolio(data, bundle)
    validations = runner.validate_completed_trades(portfolio, bundle)
    assert validations[0]["completed_trade_count"] == 2
    assert validations[1] == {"gate_id": "mixed_price.completed_trade_directions", "status": "passed", "long_trade_count": 1, "short_trade_count": 1}
    assert validations[2]["filled_order_count"] == 4

    fewer_sessions = replace(bundle, eligible_sessions=bundle.eligible_sessions[:1])
    with pytest.raises(RuntimeError, match="does not match 1 eligible sessions"):
        runner.validate_completed_trades(portfolio, fewer_sessions)
    wrong_directions = replace(
        bundle, signals=replace(bundle.signals, metadata=bundle.signals.metadata | {"long_session_count": 2, "short_session_count": 0})
    )
    with pytest.raises(RuntimeError, match="trade directions do not match"):
        runner.validate_completed_trades(portfolio, wrong_directions)


@pytest.mark.licensed_vectorbt
def test_annualization_uses_only_eligible_daily_equity_and_252_zero_risk_free() -> None:
    data = _data()
    bundle = _bundle(data)
    portfolio = runner.build_mixed_price_portfolio(data, bundle)
    daily, returns = runner.daily_equity_and_returns(portfolio.value, bundle.eligible_sessions)

    # 2026-01-02 only supplies the prior 15:59 close; it is not an eligible session.
    assert len(daily) == len(returns) == 2
    assert [item.strftime("%Y-%m-%d") for item in daily.index] == ["2026-01-05", "2026-01-06"]
    assert daily.iloc[-1] == pytest.approx(float(portfolio.value.iloc[-1]))
    metrics = runner.daily_metrics(portfolio, bundle)
    total_return = daily.iloc[-1] / runner.INITIAL_CASH - 1.0
    assert metrics["total_return"] == pytest.approx(total_return)
    assert metrics["annualized_return"] == pytest.approx((1.0 + total_return) ** (252 / 2) - 1.0)
    assert metrics["number_of_trades"] == 2
    assert runner.execution_assumptions()["annualization"] == {
        "sessions_per_year": 252, "risk_free_rate": 0.0, "basis": "end-of-session strategy equity and daily returns",
    }
