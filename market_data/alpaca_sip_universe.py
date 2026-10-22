"""The one place that lists the Alpaca SIP one-minute backtest universe."""

from __future__ import annotations

UNIVERSE_NAME = "us_day_trading_liquid_v4"
UNIVERSE_AS_OF = "2026-10-14"
HISTORY_START = "2016-01-01"

# Owner's criteria: low spreads, high volume, whole shares affordable. Measured
# 2026-10-14 from three months of Alpaca daily bars plus SIP quotes on three
# recent sessions: price $5-$250, at least 10M shares/day, and a median
# bid/ask spread no wider than 1% of the stock's average daily high-low range.
# SPY, QQQ and IWM are kept as market reference even though they cost more.
# Exact mirrors dropped (one-year daily and one-month 15-minute returns move
# together at |r| >= 0.99): SQQQ (inverse TQQQ), SOXS (inverse SOXL), KORU (3x EWY).
# MUU and SNXX stay: they are the whole-share way to trade Micron and SanDisk.
UNIVERSE_GROUPS: dict[str, tuple[str, ...]] = {
    "market_reference": ("SPY", "QQQ", "IWM"),
    "funds": (
        "TQQQ", "SOXL", "EWY", "DRAM", "IBIT", "GDX", "XLE", "KRE", "SLV", "SNXX", "MUU",
    ),
    "stocks": (
        "NVDA", "SPCX", "INTC", "PLTR", "SKHY", "ORCL", "MSTR", "NFLX", "WMT", "CRWV", "HOOD",
        "CSCO", "KLAC", "IREN", "SMCI", "KO", "RKLB", "C", "UBER", "WFC", "HPE", "FCX", "IONQ",
        "BMNR", "ASTS", "BMY", "SLB", "CIFR", "APLD", "DVN", "RIOT",
    ),
}
FUND_GROUPS = frozenset({"market_reference", "funds"})
UNIVERSE = tuple(symbol for symbols in UNIVERSE_GROUPS.values() for symbol in symbols)

SURVIVORSHIP_NOTE = (
    f"Selected in Oct 2026 ({UNIVERSE_AS_OF}) by recent spread, volume and share price. "
    "Names that were liquid in the past but faded, merged or were delisted are absent, "
    "so backtests on it carry survivorship bias and overstate what was knowable at the time."
)


def universe_group(symbol: str) -> str:
    """Return the config group of a universe symbol; fail plainly for anything else."""
    for group, symbols in UNIVERSE_GROUPS.items():
        if symbol in symbols:
            return group
    raise ValueError(f"{symbol!r} is not in the Alpaca SIP universe")


def asset_type(symbol: str) -> str:
    """Return ETF or stock for a universe symbol."""
    return "ETF" if universe_group(symbol) in FUND_GROUPS else "stock"
