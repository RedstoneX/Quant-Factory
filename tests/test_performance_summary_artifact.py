"""performance_summary.json carries VectorBT's own All / Long / Short stats."""

import json
import math

import pandas as pd
import pytest

from orchestration.candidate_screening_artifacts import performance_summary, snapshot_screening_portfolio

pytestmark = pytest.mark.licensed_vectorbt

KEYS = {"net_profit", "gross_profit", "gross_loss", "profit_factor", "max_drawdown", "total_trades",
        "win_rate", "avg_trade", "avg_win", "avg_loss", "largest_win", "largest_loss",
        "avg_bars_in_trade", "commission_paid"}


def _portfolio():
    import vectorbtpro as vbt

    index = pd.date_range("2024-01-01", periods=12, freq="D", tz="UTC")
    close = pd.Series([10, 11, 12, 11, 10, 11, 12, 13, 12, 11, 12, 13.0], index=index)

    def mask(*at):
        return pd.Series([i in at for i in range(12)], index=index)

    return vbt.Portfolio.from_signals(
        close, entries=mask(0), exits=mask(2), short_entries=mask(3), short_exits=mask(4),
        fees=0.001, freq="1D")


def test_summary_has_all_long_short_with_json_safe_values():
    pf = _portfolio()
    summary = performance_summary(pf)
    assert set(summary) == {"all", "long", "short"}
    assert all(set(column) == KEYS for column in summary.values())
    assert summary["all"]["total_trades"] == 2
    assert summary["long"]["total_trades"] == summary["short"]["total_trades"] == 1
    assert summary["all"]["net_profit"] == pytest.approx(float(pf.trades.pnl.sum()))
    assert summary["all"]["net_profit"] == pytest.approx(
        summary["long"]["net_profit"] + summary["short"]["net_profit"])
    assert summary["all"]["avg_loss"] is None  # no losing trades: null, not NaN
    text = json.dumps(summary, allow_nan=False)
    assert not any(isinstance(v, float) and math.isnan(v) for c in summary.values() for v in c.values()) and text


def test_snapshot_keeps_summary_after_portfolio_is_released():
    assert snapshot_screening_portfolio(_portfolio()).performance["all"]["total_trades"] == 2
