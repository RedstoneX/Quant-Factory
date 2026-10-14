"""Dataset identity and trading costs for the Alpaca SIP one-minute stock/ETF datasets.

Every cost below is a published rate (citation and effective date), a committed
measurement (data/costs/alpaca_sip_spreads.json) or an owner fact. Nothing defaults:
a symbol without a measured spread has no profile.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from market_data.alpaca_sip_universe import UNIVERSE
from market_data.catalog import load_data_locations, manifest_dir_for

STOCK_INTERVAL = "1m"
SPREADS_PATH = Path(__file__).resolve().parents[1] / "data" / "costs" / "alpaca_sip_spreads.json"

# Owner fact: the owner's own trading account is about $9.7k (measured 2026-10), so
# stock results are sized to an account of that scale rather than to a fund.
INITIAL_CASH = 10_000.0

# Commission $0: "no commission charges for Alpaca self-directed individual cash
# brokerage accounts" trading U.S.-listed securities through the API.
# https://alpaca.markets/disclosures (fee schedule:
# https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf), read 2026-10-14.
COMMISSION_PER_SIDE = 0.0

# SEC Section 31 fee: $20.60 per million dollars of sales, effective 2026-04-04.
# https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2
SEC_SECTION_31_RATE = 20.60 / 1_000_000

# FINRA Trading Activity Fee, covered equity sales: $0.000195 per share sold, at most
# $9.79 per trade, effective 2026-01-01.
# https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule
FINRA_TAF_PER_SHARE = 0.000195



def regulatory_fee_fraction_per_side(median_mid_price: float) -> float:
    """SEC + FINRA sell-side fees as one fraction of traded value per side.

    The engine charges one fractional fee on every fill, buys and sells alike. Both fees
    are sell-only, so each is halved and charged on both sides: a round trip pays one
    sell's worth. The per-share TAF becomes a fraction at the symbol's measured median
    quote midpoint; its per-trade cap (which only lowers it) is ignored. On
    split-adjusted history the real share price differed, so the TAF fraction is exact
    only near the measurement date. Not modelled: Consolidated Audit Trail fees (no
    published per-trade rate was retrieved).
    """
    return (SEC_SECTION_31_RATE + FINRA_TAF_PER_SHARE / median_mid_price) / 2.0

# Same stress multiplier as the MES profile (orchestration/auto_campaign.py,
# _PROFILES[("MES", "5m")]: slippage_ticks=1.0 -> stress_slippage_ticks=2.0).
STRESS_SLIPPAGE_MULTIPLIER = 2.0

# US stocks quote in whole cents at $1 and above (Reg NMS Rule 612, 17 CFR 242.612).
TICK_SIZE = 0.01

# 252 sessions a year x 390 regular-session minutes (09:30-16:00 New York).
ANNUALIZATION_FACTOR = 252.0 * 390.0


class StockCostsUnavailable(ValueError):
    """A stock has no committed measured spread, so it has no honest cost model."""


def dataset_id_for(symbol: str) -> str:
    return f"equities_{symbol}_1m_alpaca_sip"


def _measured(symbol: str, field: str, spreads_path: Path) -> float:
    if not spreads_path.is_file():
        raise StockCostsUnavailable(
            f"No measured spreads file at {spreads_path.name}; run tools/measure_stock_spreads.py"
        )
    symbols = json.loads(spreads_path.read_text(encoding="utf-8")).get("symbols") or {}
    entry = symbols.get(symbol)
    if entry is None:
        raise StockCostsUnavailable(f"No measured bid/ask spread for {symbol} in {spreads_path.name}")
    if entry.get(field) is None:
        raise StockCostsUnavailable(f"No measured {field} for {symbol} in {spreads_path.name}")
    value = float(entry[field])
    if not math.isfinite(value) or value <= 0:
        raise StockCostsUnavailable(f"The measured {field} for {symbol} is not a positive number: {value!r}")
    return value


def half_spread_fraction(symbol: str, spreads_path: Path = SPREADS_PATH) -> float:
    """Half the symbol's measured median bid/ask spread, as a fraction of price."""
    return _measured(symbol, "median_spread_bps", spreads_path) / 2.0 / 10_000.0


def median_mid_price(symbol: str, spreads_path: Path = SPREADS_PATH) -> float:
    """The symbol's measured median quote midpoint over the same samples, in dollars."""
    return _measured(symbol, "median_mid_price", spreads_path)


def _completed_end(latest_bar: str) -> str:
    """The latest bar, or the last completed NYSE close if that bar is mid-session.

    Nightly and intraday top-ups can stop inside a session; a backtest must end on a
    completed one. A one-minute bar labelled at its open is observed through +1 minute.
    """
    import pandas_market_calendars as mcal

    latest = pd.Timestamp(latest_bar)
    observed_through = latest + pd.Timedelta(STOCK_INTERVAL.replace("m", "min"))
    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=(latest - pd.Timedelta(days=14)).date(), end_date=latest.date()
    )
    closes = schedule.loc[schedule["market_close"] <= observed_through, "market_close"]
    if closes.empty:
        raise ValueError(f"no completed NYSE session ends by {latest_bar}")
    end = min(closes.iloc[-1], latest)
    return latest_bar if end == latest else end.isoformat().replace("+00:00", "Z")


def stock_profile_fields(
    symbol: str, *, manifest_dir: Path | None = None, spreads_path: Path = SPREADS_PATH
) -> dict[str, Any]:
    """DatasetProfile fields for one universe symbol, read from its manifest now.

    The manifest's latest bar is recorded as the dataset end, so a rerun of the saved
    setup reads exactly the same bars even after nightly top-ups.
    """
    if symbol not in UNIVERSE:
        raise ValueError(f"{symbol!r} is not in the Alpaca SIP universe")
    slippage = half_spread_fraction(symbol, spreads_path)
    fees = regulatory_fee_fraction_per_side(median_mid_price(symbol, spreads_path))
    dataset_id = dataset_id_for(symbol)
    folder = manifest_dir if manifest_dir is not None else manifest_dir_for(dataset_id, load_data_locations())
    manifest = json.loads((folder / f"{dataset_id}.json").read_text(encoding="utf-8"))
    latest = _completed_end(str(manifest["latest_timestamp"]))
    return {
        "dataset_id": dataset_id,
        "symbol": symbol,
        "interval": STOCK_INTERVAL,
        "dataset_end": latest,
        "requested_start": str(manifest["first_available_bar"]),
        "end_date_policy": f"fixed manifest end {latest} recorded when the campaign was created",
        "cache_path": Path(str(manifest["canonical_relative_path"])),
        "fixed_fee_per_contract_per_side": COMMISSION_PER_SIDE,
        "slippage_ticks": 0.0,
        "tick_size": TICK_SIZE,
        "price_multiplier": 1.0,
        "stress_fee_per_contract_per_side": COMMISSION_PER_SIDE,
        "stress_slippage_ticks": 0.0,
        "annualization_factor": ANNUALIZATION_FACTOR,
        # The catalog loader checks provider identity against the manifest ("alpaca").
        "provider": str(manifest["provider"]),
        "adjusted": True,
        "initial_cash": INITIAL_CASH,
        "position_sizing": "all_cash_whole_shares",
        "order_size": 1.0,  # all available cash, in whole shares
        "fees": fees,
        "slippage": slippage,
        "stress_slippage": slippage * STRESS_SLIPPAGE_MULTIPLIER,
    }
