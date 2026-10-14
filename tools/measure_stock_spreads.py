"""Measure each universe symbol's median SIP bid/ask spread for backtest slippage.

Usage (credentials come from the environment and are never printed):
    QF_ALPACA_API_KEY=... QF_ALPACA_SECRET_KEY=... \\
        python tools/measure_stock_spreads.py --out data/costs/alpaca_sip_spreads.json

Method: for each of the last 20 complete regular NYSE sessions, every SIP quote in the
one minute starting 10:00, 12:00 and 15:30 New York time (a sample after an early
close is skipped). Per valid quote (bid > 0, ask > bid): (ask - bid) / mid in basis
points. The symbol's figure is the median over all its valid quotes; the median
midpoint (ask+bid)/2 over the same quotes is recorded as median_mid_price.
"""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, time as clock, timedelta
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from market_data.alpaca_sip_universe import UNIVERSE  # noqa: E402

QUOTES_URL = "https://data.alpaca.markets/v2/stocks/{symbol}/quotes"
NEW_YORK = ZoneInfo("America/New_York")
SAMPLE_TIMES = (clock(10, 0), clock(12, 0), clock(15, 30))
SESSION_COUNT = 20
PAGE_LIMIT = 10_000
# Alpaca market-data request limit stated in the dispatch brief (2026-10-14); see
# https://docs.alpaca.markets/docs/about-market-data-api
REQUESTS_PER_MINUTE = 200

Get = Callable[..., Any]


class RateLimiter:
    """At most ``limit`` calls in any rolling 60 seconds."""

    def __init__(self, limit: int = REQUESTS_PER_MINUTE, *, clock_fn: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.limit, self.clock_fn, self.sleep = limit, clock_fn, sleep
        self.calls: deque[float] = deque()

    def wait(self) -> None:
        now = self.clock_fn()
        while self.calls and now - self.calls[0] >= 60.0:
            self.calls.popleft()
        if len(self.calls) >= self.limit:
            self.sleep(60.0 - (now - self.calls[0]))
            self.calls.popleft()
        self.calls.append(self.clock_fn())


def spread_bps(quote: Mapping[str, Any]) -> float | None:
    """(ask - bid) / mid in basis points; None for a quote that is not two-sided and valid."""
    bid, ask = float(quote.get("bp") or 0.0), float(quote.get("ap") or 0.0)
    if bid <= 0 or ask <= bid:
        return None
    return (ask - bid) / ((ask + bid) / 2.0) * 10_000.0


def recent_sessions(today: datetime, count: int = SESSION_COUNT) -> list[tuple[datetime, datetime]]:
    """The last ``count`` complete regular sessions before ``today``: (open, close) in UTC."""
    import pandas_market_calendars as mcal

    end = today.astimezone(NEW_YORK).date() - timedelta(days=1)
    schedule = mcal.get_calendar("NYSE").schedule(start_date=end - timedelta(days=count * 2 + 14), end_date=end)
    rows = schedule.tail(count)
    return [(row.market_open.to_pydatetime(), row.market_close.to_pydatetime()) for row in rows.itertuples()]


def sample_windows(sessions: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    windows = []
    for market_open, market_close in sessions:
        day = market_open.astimezone(NEW_YORK).date()
        for at in SAMPLE_TIMES:
            start = datetime.combine(day, at, tzinfo=NEW_YORK)
            if start + timedelta(minutes=1) <= market_close:
                windows.append((start, start + timedelta(minutes=1)))
    return windows


def window_quotes(symbol: str, start: datetime, end: datetime, *, get: Get, headers: Mapping[str, str],
                  limiter: RateLimiter) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        params: dict[str, Any] = {
            "feed": "sip", "limit": PAGE_LIMIT, "start": _rfc3339(start), "end": _rfc3339(end),
        }
        if token:
            params["page_token"] = token
        limiter.wait()
        response = get(QUOTES_URL.format(symbol=symbol), params=params, headers=headers, timeout=30)
        response.raise_for_status()
        body = response.json()
        quotes.extend(body.get("quotes") or [])
        token = body.get("next_page_token")
        if not token:
            return quotes


def measure(symbols: Sequence[str], sessions: Sequence[tuple[datetime, datetime]], *, get: Get,
            headers: Mapping[str, str], limiter: RateLimiter) -> dict[str, dict[str, Any]]:
    windows = sample_windows(sessions)
    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        values: list[float] = []
        mids: list[float] = []
        for start, end in windows:
            quotes = window_quotes(symbol, start, end, get=get, headers=headers, limiter=limiter)
            for quote in quotes:
                value = spread_bps(quote)
                if value is not None:
                    values.append(value)
                    mids.append((float(quote["ap"]) + float(quote["bp"])) / 2.0)
        if not values:
            raise RuntimeError(f"{symbol}: no valid two-sided SIP quotes in any sampled minute")
        result[symbol] = {
            "median_spread_bps": statistics.median(values), "median_mid_price": statistics.median(mids),
            "samples": len(values), "sessions": len(sessions),
        }
    return result


def document(spreads: Mapping[str, Any], sessions: Sequence[tuple[datetime, datetime]],
             measured_at: datetime) -> dict[str, Any]:
    first = sessions[0][0].astimezone(NEW_YORK).date().isoformat()
    last = sessions[-1][0].astimezone(NEW_YORK).date().isoformat()
    return {
        "measured_at": _rfc3339(measured_at),
        "method": (
            f"Median of (ask-bid)/mid in bps over every valid SIP quote (bid>0, ask>bid) in the one minute "
            f"starting 10:00, 12:00 and 15:30 New York time on each of {len(sessions)} complete regular "
            f"sessions {first} to {last}; slippage per side = half this median. median_mid_price = "
            f"median (ask+bid)/2 over the same quotes, used to turn the per-share FINRA TAF into a fraction."
        ),
        "source": "Alpaca market data /v2/stocks/{symbol}/quotes, feed=sip",
        "symbols": dict(spreads),
    }


def _rfc3339(moment: datetime) -> str:
    return moment.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--symbols", nargs="*", default=list(UNIVERSE))
    args = parser.parse_args(argv)
    key, secret = os.environ.get("QF_ALPACA_API_KEY"), os.environ.get("QF_ALPACA_SECRET_KEY")
    if not key or not secret:
        parser.error("QF_ALPACA_API_KEY and QF_ALPACA_SECRET_KEY must be set in the environment")
    import requests

    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    now = datetime.now(tz=ZoneInfo("UTC"))
    sessions = recent_sessions(now)
    spreads = measure(args.symbols, sessions, get=requests.get, headers=headers, limiter=RateLimiter())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document(spreads, sessions, now), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(spreads)} symbols to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
