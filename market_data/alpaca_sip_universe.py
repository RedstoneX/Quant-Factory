"""The one place that lists the Alpaca SIP one-minute backtest universe."""

from __future__ import annotations

UNIVERSE_NAME = "us_large_cap_and_index_etfs_v1"
UNIVERSE_AS_OF = "2026-10-14"
HISTORY_START = "2016-01-01"

INDEX_ETFS = ("SPY", "QQQ", "IWM", "DIA")
SECTOR_ETFS = (
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
)
LARGE_CAP_STOCKS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "AVGO", "TSLA", "JPM",
    "LLY", "V", "UNH", "XOM", "MA", "COST", "HD", "PG", "JNJ", "WMT",
    "NFLX", "ABBV", "BAC", "KO", "CVX", "MRK", "ORCL", "AMD", "CRM", "PEP",
)
UNIVERSE = INDEX_ETFS + SECTOR_ETFS + LARGE_CAP_STOCKS

SURVIVORSHIP_NOTE = (
    f"The stock list is today's ({UNIVERSE_AS_OF}) large-cap list chosen with hindsight. "
    "Companies that shrank, merged or were delisted since 2016 are absent, so backtests "
    "on it carry survivorship bias and overstate what was knowable at the time."
)


def asset_type(symbol: str) -> str:
    """Return ETF or stock for a universe symbol; fail plainly for anything else."""
    if symbol in INDEX_ETFS or symbol in SECTOR_ETFS:
        return "ETF"
    if symbol in LARGE_CAP_STOCKS:
        return "stock"
    raise ValueError(f"{symbol!r} is not in the Alpaca SIP universe")
