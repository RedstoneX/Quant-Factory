"""Zero-trade fixed-rule stress reports plainly that the entry rule never fired."""

from backtesting.robustness.fixed_rule import non_finite_metrics_reason


def test_zero_trades_says_entry_rule_never_fired() -> None:
    reason = non_finite_metrics_reason(0)
    assert reason == "made no trades: the entry rule never fired under the stressed costs"
    assert "non-finite" not in reason


def test_non_finite_metrics_with_trades_keeps_existing_message() -> None:
    assert non_finite_metrics_reason(3) == "stressed trade metrics are missing or non-finite"
