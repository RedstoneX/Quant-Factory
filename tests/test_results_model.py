"""Portable data-contract tests for the chart-first selected-run Results model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dashboard.results_model import (
    ResultsDataError,
    TradeEvent,
    group_trade_rows,
    map_event_to_bar,
    prepare_interval,
    validate_ohlc_rows,
)
from dashboard.run_detail_adapter import _validated_series_rows


def _row(timestamp: str, open_: float, high: float, low: float, close: float):
    return {
        "timestamp": timestamp,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }


def test_ohlc_validation_requires_ordered_unique_timezone_aware_finite_rows() -> None:
    valid = validate_ohlc_rows(
        (
            _row("2026-01-01T09:30:00-05:00", 10, 12, 9, 11),
            _row("2026-01-01T14:31:00Z", 11, 13, 10, 12),
        )
    )
    assert [bar.timestamp.isoformat() for bar in valid] == [
        "2026-01-01T14:30:00+00:00",
        "2026-01-01T14:31:00+00:00",
    ]

    invalid_cases = (
        (_row("2026-01-01T14:30:00", 10, 12, 9, 11), "timezone_required"),
        (
            (
                _row("2026-01-01T14:31:00Z", 10, 12, 9, 11),
                _row("2026-01-01T14:30:00Z", 11, 13, 10, 12),
            ),
            "unordered_timestamp",
        ),
        (
            (
                _row("2026-01-01T14:30:00Z", 10, 12, 9, 11),
                _row("2026-01-01T14:30:00+00:00", 11, 13, 10, 12),
            ),
            "unordered_timestamp",
        ),
        (_row("2026-01-01T14:30:00Z", 10, float("inf"), 9, 11), "nonfinite_number"),
        (_row("2026-01-01T14:30:00Z", 10, 10.5, 9, 11), "inconsistent_ohlc"),
        (
            _row("2026-01-01T14:30:00.001Z", 10, 12, 9, 11),
            "misaligned_source_bar",
        ),
        (
            (
                _row("2026-01-01T14:30:00Z", 10, 12, 9, 11),
                _row("2026-01-01T14:30:30Z", 11, 13, 10, 12),
            ),
            "duplicate_source_bucket",
        ),
    )
    for source, code in invalid_cases:
        rows = source if isinstance(source, tuple) else (source,)
        with pytest.raises(ResultsDataError) as caught:
            validate_ohlc_rows(rows)
        assert caught.value.code == code


def test_aggregation_uses_epoch_left_ohlc_rules_and_does_not_fill_gaps() -> None:
    rows = (
        _row("2026-01-01T14:31:00Z", 10, 12, 9, 11),
        _row("2026-01-01T14:34:00Z", 11, 14, 10, 13),
        _row("2026-01-01T14:41:00Z", 20, 22, 19, 21),
    )

    five_minute = prepare_interval(rows, "5m")

    assert five_minute.available is True
    assert [bar.timestamp.isoformat() for bar in five_minute.bars] == [
        "2026-01-01T14:30:00+00:00",
        "2026-01-01T14:40:00+00:00",
    ]
    assert five_minute.bars[0].open == 10
    assert five_minute.bars[0].high == 14
    assert five_minute.bars[0].low == 9
    assert five_minute.bars[0].close == 13
    assert five_minute.bars[0].source_count == 2
    assert five_minute.bars[1].source_count == 1
    fifteen_minute = prepare_interval(rows, "15m")
    assert len(fifteen_minute.bars) == 1
    assert fifteen_minute.bars[0].source_count == 3


def test_source_minute_boundary_accepts_adjacent_epoch_left_bars() -> None:
    bars = validate_ohlc_rows(
        (
            _row("2026-01-01T09:30:00-05:00", 10, 12, 9, 11),
            _row("2026-01-01T14:31:00Z", 11, 13, 10, 12),
        )
    )

    assert [bar.timestamp.minute for bar in bars] == [30, 31]


def test_daily_aggregation_uses_utc_epoch_buckets() -> None:
    daily = prepare_interval(
        (
            _row("2026-01-01T23:59:00-05:00", 10, 11, 9, 10.5),
            _row("2026-01-02T05:01:00Z", 10.5, 12, 10, 11.5),
        ),
        "1D",
    )

    assert daily.available is True
    assert len(daily.bars) == 1
    assert daily.bars[0].timestamp.isoformat() == "2026-01-02T00:00:00+00:00"
    assert daily.bars[0].open == 10
    assert daily.bars[0].close == 11.5


def test_intervals_report_explicit_unsupported_and_unavailable_reasons() -> None:
    unsupported = prepare_interval((), "30m")
    empty = prepare_interval((), "5m")
    wrong_source = prepare_interval((), "5m", source_interval="5m")

    assert unsupported.available is False
    assert "not supported" in unsupported.reason
    assert empty.available is False
    assert empty.reason == "No persisted OHLC bars are available for this run."
    assert wrong_source.available is False
    assert "requires persisted 1m OHLC" in wrong_source.reason


def test_trade_event_mapping_preserves_exact_event_and_uses_containing_bar() -> None:
    interval = prepare_interval(
        (
            _row("2026-01-01T14:30:00Z", 10, 11, 9, 10.5),
            _row("2026-01-01T14:31:00Z", 10.5, 12, 10, 11.5),
        ),
        "5m",
    )
    event = TradeEvent(
        trade_id="7",
        leg="entry",
        timestamp=datetime(2026, 1, 1, 14, 31, 42, tzinfo=timezone.utc),
        price=10.75,
    )

    mapping = map_event_to_bar(event, interval)

    assert mapping.available is True
    assert mapping.event is event
    assert mapping.event.timestamp.isoformat() == "2026-01-01T14:31:42+00:00"
    assert mapping.event.price == 10.75
    assert mapping.bar_timestamp.isoformat() == "2026-01-01T14:30:00+00:00"


def test_trade_event_mapping_does_not_fabricate_marker_in_empty_bucket() -> None:
    interval = prepare_interval(
        (_row("2026-01-01T14:30:00Z", 10, 11, 9, 10.5),), "5m"
    )
    event = TradeEvent(
        trade_id="7",
        leg="exit",
        timestamp=datetime(2026, 1, 1, 14, 41, tzinfo=timezone.utc),
        price=10.9,
    )

    mapping = map_event_to_bar(event, interval)

    assert mapping.available is False
    assert mapping.bar_timestamp is None
    assert "no persisted OHLC bar" in mapping.reason


def test_trade_groups_keep_closed_open_and_unconfirmed_evidence_truthful() -> None:
    grouped = group_trade_rows(
        (
            {
                "Exit Trade Id": 1,
                "Status": "Closed",
                "Direction": "Long",
                "Entry Index": "2026-01-01T14:30:15Z",
                "Avg Entry Price": 10.0,
                "Exit Index": "2026-01-01T14:34:45Z",
                "Avg Exit Price": 11.0,
                "PnL": 1.0,
                "Return": 0.1,
            },
            {
                "Exit Trade Id": 2,
                "Status": "Open",
                "Direction": "Long",
                "Entry Index": "2026-01-01T14:40:00Z",
                "Avg Entry Price": 12.0,
                "Exit Index": "2026-01-01T14:45:00Z",
                "Avg Exit Price": 12.5,
                "PnL": 0.5,
            },
            {
                "Exit Trade Id": 3,
                "Status": "Closed",
                "Entry Index": "2026-01-01T14:50:00Z",
                "Avg Entry Price": 13.0,
                "PnL": 2.0,
            },
            {
                "Exit Trade Id": 4,
                "Status": "Closed",
                "Entry Index": "2026-01-01T15:00:00Z",
                "Avg Entry Price": 14.0,
                "Exit Index": "2026-01-01T15:05:00Z",
                "Avg Exit Price": 13.5,
                "PnL": -0.5,
            },
            {
                "Exit Trade Id": 5,
                "Status": "Closed",
                "Entry Index": "2026-01-01T15:10:00Z",
                "Avg Entry Price": 14.0,
                "Exit Index": "2026-01-01T15:09:59Z",
                "Avg Exit Price": 15.0,
                "PnL": 1.0,
            },
        )
    )

    assert grouped.closed_count == 2
    assert grouped.open_count == 1
    assert grouped.unconfirmed_count == 2
    assert grouped.profitable_closed_count == 1
    assert grouped.groups[0].outcome == "win"
    assert grouped.groups[1].exit is None
    assert grouped.groups[1].outcome is None
    assert grouped.groups[1].pnl is None
    assert grouped.groups[1].valuation_price == 12.5
    assert grouped.groups[1].valuation_timestamp is not None
    assert grouped.groups[1].valuation_timestamp.isoformat() == "2026-01-01T14:45:00+00:00"
    assert grouped.groups[2].exit is None
    assert grouped.groups[2].outcome is None
    assert "lacks complete persisted entry and exit" in " ".join(
        grouped.groups[2].unavailable_reasons
    )
    assert grouped.groups[3].outcome == "loss"
    assert grouped.groups[4].status == "unconfirmed"
    assert grouped.groups[4].exit is None
    assert grouped.groups[4].outcome is None
    assert "exit timestamp precedes" in " ".join(
        grouped.groups[4].unavailable_reasons
    )


@pytest.mark.parametrize(
    ("valuation_fields", "reason_fragment"),
    (
        ({"Exit Index": "2026-01-01T14:45:00Z"}, "not both recorded"),
        ({"Avg Exit Price": 12.5}, "not both recorded"),
        (
            {
                "Exit Index": "not-a-timestamp",
                "Avg Exit Price": 12.5,
            },
            "not a valid ISO-8601 timestamp",
        ),
        (
            {
                "Exit Index": "2026-01-01T14:45:00Z",
                "Avg Exit Price": float("inf"),
            },
            "must be finite",
        ),
    ),
)
def test_open_trade_partial_or_invalid_vectorbt_valuation_is_unavailable(
    valuation_fields, reason_fragment: str
) -> None:
    grouped = group_trade_rows(
        (
            {
                "Exit Trade Id": 6,
                "Status": "Open",
                "Entry Index": "2026-01-01T14:40:00Z",
                "Avg Entry Price": 12.0,
                **valuation_fields,
            },
        )
    )

    trade = grouped.groups[0]
    assert trade.status == "open"
    assert trade.exit is None
    assert trade.outcome is None
    assert trade.pnl is None
    assert trade.valuation_timestamp is None
    assert trade.valuation_price is None
    assert reason_fragment in " ".join(trade.unavailable_reasons)


def test_adapter_price_validation_uses_strict_results_contract() -> None:
    warnings: list[str] = []
    rows = _validated_series_rows(
        {
            "price_series": [
                _row("2026-01-01T14:31:00Z", 10, 12, 9, 11),
                _row("2026-01-01T14:30:00Z", 11, 13, 10, 12),
            ]
        },
        "price_series",
        numeric_fields=("open", "high", "low", "close"),
        warnings=warnings,
    )

    assert rows == ()
    assert "timestamps must be unique and increasing" in warnings[0]
