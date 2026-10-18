"""Zero-trade ideas are told plainly that the entry rule never fired."""

from dataclasses import replace

from backtesting.screening.models import ScreeningConfig
from backtesting.screening.rules import evaluate_rules
from dashboard.plain_labels import plain_rejection_reasons

def _cfg(**kw):
    return replace(ScreeningConfig.provisional_defaults(), **kw)


NAN = float("nan")
ZERO_TRADES = {
    "number_of_trades": 0,
    "total_return": 0.0,
    "annualized_return": 0.0,
    "sharpe_ratio": NAN,
    "max_drawdown": 0.0,
    "win_rate": NAN,
}


def _failed(metrics, config):
    return [r for r in evaluate_rules(dict(metrics), config) if r.status == "failed"]


def test_zero_trades_still_rejected_with_plain_first_reason():
    failed = _failed(ZERO_TRADES, _cfg(minimum_win_rate=0.4))
    assert {r.rule_id for r in failed} >= {"metrics.finite", "trades.minimum"}
    assert failed[0].message == "no trades: the entry rule never fired in this period"
    assert all("observed {" not in r.message for r in failed)


def test_zero_trades_with_finite_metrics_uses_plain_reason():
    failed = _failed({**ZERO_TRADES, "sharpe_ratio": 0.0}, _cfg())
    assert failed[0].rule_id == "trades.minimum"
    assert "entry rule never fired" in failed[0].message


def test_nonzero_trades_wording_unchanged():
    failed = _failed({**ZERO_TRADES, "number_of_trades": 1}, _cfg())
    assert failed[0].message.startswith("required_metrics failed: expected all available")


def test_plain_rejection_reasons_handles_no_trades():
    text = " | ".join(r.message for r in _failed(ZERO_TRADES, _cfg()))
    assert plain_rejection_reasons(text)[0] == "No trades: the entry rule never fired in this period"
