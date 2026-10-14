"""The one place that lists the Alpaca SIP one-minute backtest universe."""

from __future__ import annotations

UNIVERSE_NAME = "us_day_trading_liquid_v2"
UNIVERSE_AS_OF = "2026-10-14"
HISTORY_START = "2016-01-01"

# Chosen by the owner for day-trading liquidity and affordable share prices,
# measured from three months of Alpaca daily bars.
UNIVERSE_GROUPS: dict[str, tuple[str, ...]] = {
    "index_funds": ("SPY", "QQQ", "IWM", "TQQQ", "SQQQ", "SOXL", "IBIT", "GDX"),
    "sector_funds": ("XLF", "XLE", "XLK", "XLV", "XLU", "XLP", "XLI", "XLB", "XLY", "XLC"),
    "large_caps": (
        "NVDA", "AAPL", "TSLA", "MSFT", "META", "AMD", "AMZN", "GOOGL", "AVGO",
        "ORCL", "NFLX", "WMT", "JPM", "XOM", "CRM", "V", "UNH", "BAC",
    ),
    "active_growth": ("MU", "PLTR", "INTC", "MRVL", "HOOD", "COIN", "MSTR", "SMCI", "CSCO"),
    "affordable_high_volume": (
        "T", "F", "SOFI", "PFE", "AAL", "NU", "WBD", "CMCSA", "PCG", "MARA", "NOK", "VALE",
        "RKT", "IREN",
    ),
}
FUND_GROUPS = frozenset({"index_funds", "sector_funds"})
UNIVERSE = tuple(symbol for symbols in UNIVERSE_GROUPS.values() for symbol in symbols)

SURVIVORSHIP_NOTE = (
    f"Selected in Oct 2026 ({UNIVERSE_AS_OF}) by recent liquidity and share price. "
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
