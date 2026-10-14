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
from datetime import datetime, time as clock, timedelta
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from market_data.alpaca_sip_universe import UNIVERSE  # noqa: E402

NEW_YORK = ZoneInfo("America/New_York")
SAMPLE_TIMES = (clock(10, 0), clock(12, 0), clock(15, 30))
SESSION_COUNT = 20
FEED = "sip"

Pull = Callable[..., Any]


def spread_bps(bid: pd.Series, ask: pd.Series) -> tuple[list[float], list[float]]:
    """Per valid quote (bid > 0, ask > bid): (ask - bid) / mid in basis points, and the mid; others dropped."""
    bid, ask = bid.to_numpy(float), ask.to_numpy(float)
    valid = (bid > 0) & (ask > bid)
    bid, ask = bid[valid], ask[valid]
    mid = (ask + bid) / 2.0
    return ((ask - bid) / mid * 10_000.0).tolist(), mid.tolist()


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


def measure(symbols: Sequence[str], sessions: Sequence[tuple[datetime, datetime]], *, pull: Pull,
            client_config: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """One ``vbt.AlpacaData.pull`` per sampled minute (all symbols); paging and 429 retry are alpaca-py's."""
    values: dict[str, list[float]] = {symbol: [] for symbol in symbols}
    mids: dict[str, list[float]] = {symbol: [] for symbol in symbols}
    for start, end in sample_windows(sessions):
        data = pull(list(symbols), data_type="quotes", start=start, end=end, feed=FEED,
                    client_config=dict(client_config))
        for symbol in symbols:
            quotes = data.data.get(symbol)
            if quotes is None or quotes.empty:
                continue
            spreads, window_mids = spread_bps(quotes["Bid price"], quotes["Ask price"])
            values[symbol].extend(spreads)
            mids[symbol].extend(window_mids)
    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        if not values[symbol]:
            raise RuntimeError(f"{symbol}: no valid two-sided SIP quotes in any sampled minute")
        result[symbol] = {
            "median_spread_bps": statistics.median(values[symbol]), "median_mid_price": statistics.median(mids[symbol]),
            "samples": len(values[symbol]), "sessions": len(sessions),
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
    import vectorbtpro as vbt  # licensed; imported here so the helpers load without it

    now = datetime.now(tz=ZoneInfo("UTC"))
    sessions = recent_sessions(now)
    spreads = measure(args.symbols, sessions, pull=vbt.AlpacaData.pull,
                      client_config=dict(api_key=key, secret_key=secret))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document(spreads, sessions, now), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(spreads)} symbols to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
