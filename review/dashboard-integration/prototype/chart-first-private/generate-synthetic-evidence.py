#!/usr/bin/env python3
"""Generate deterministic synthetic data for the standalone review preview.

This creates no trading evidence. It exists only because the byte-for-byte
preview JavaScript expects 53,528 synthetic bars and 366 trade-shaped rows.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path


PRICE_COUNT = 53_528
TRADE_COUNT = 366
TRADE_FIELDS = (
    "Exit Trade Id",
    "Entry Index",
    "Exit Index",
    "Avg Entry Price",
    "Avg Exit Price",
    "Direction",
    "Size",
    "Entry Fees",
    "Exit Fees",
    "PnL",
    "Return",
    "Status",
)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def build_document() -> dict[str, object]:
    start = datetime(2040, 1, 1, tzinfo=timezone.utc)
    prices: list[list[object]] = []
    closes: list[float] = []
    previous = 80.0
    for index in range(PRICE_COUNT):
        drift = index * 0.00004
        wave = math.sin(index / 113.0) * 0.18 + math.sin(index / 19.0) * 0.035
        close = round(80.0 + drift + wave, 4)
        open_price = previous
        high = round(max(open_price, close) + 0.025, 4)
        low = round(min(open_price, close) - 0.025, 4)
        prices.append([iso(start + timedelta(minutes=index)), open_price, high, low, close])
        closes.append(close)
        previous = close

    trades: list[list[object]] = []
    pnl_values: list[float] = []
    stride = (PRICE_COUNT - 20) // TRADE_COUNT
    for index in range(TRADE_COUNT):
        entry_index = 5 + index * stride
        exit_index = min(entry_index + 8 + index % 17, PRICE_COUNT - 1)
        direction = "Long" if index % 3 else "Short"
        entry = closes[entry_index]
        exit_price = closes[exit_index]
        gross = exit_price - entry if direction == "Long" else entry - exit_price
        pnl = round(gross - 0.02, 4)
        pnl_values.append(pnl)
        trades.append(
            [
                index + 1,
                prices[entry_index][0],
                prices[exit_index][0],
                entry,
                exit_price,
                direction,
                1.0,
                0.01,
                0.01,
                pnl,
                round(pnl / entry, 8),
                "Closed",
            ]
        )

    winners = sum(value > 0 for value in pnl_values)
    return {
        "schema_version": 1,
        "synthetic_review_only": True,
        "fixture": "synthetic-review-not-trading-evidence",
        "instrument": "SYNTHETIC",
        "timeframe": "1m",
        "run_id": "synthetic-review-not-a-real-run",
        "completed_at": iso(start + timedelta(minutes=PRICE_COUNT - 1)),
        "metric_fields": ["total_return", "max_drawdown", "win_rate", "number_of_trades"],
        "trade_fields": list(TRADE_FIELDS),
        "metrics": {
            "total_return": round(sum(pnl_values) / 10_000, 8),
            "max_drawdown": -0.01,
            "win_rate": round(winners / TRADE_COUNT, 8),
            "number_of_trades": TRADE_COUNT,
        },
        "price_series": prices,
        "trades": trades,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("synthetic-review-evidence.json"),
    )
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(build_document(), separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote synthetic review data to {args.output}")


if __name__ == "__main__":
    main()
