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

# The universe's share-price floor ($5, owner's selection criterion recorded in
# market_data/alpaca_sip_universe.py).
TAF_PRICE_FLOOR = 5.0

# The engine charges one fractional fee on every fill; it cannot charge a per-share fee
# on sells only. Conservative model: both regulatory fees on BOTH sides, and the TAF as
# a fraction of value at the $5 floor (per-share fee / price is largest at the lowest
# price), ignoring the per-trade cap (which only lowers it). This overstates the real
# cost of every trade at a real share price of $5 or more. Not modelled: Consolidated
# Audit Trail fees (no published per-trade rate was retrieved).
REGULATORY_FEE_FRACTION_PER_SIDE = SEC_SECTION_31_RATE + FINRA_TAF_PER_SHARE / TAF_PRICE_FLOOR

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


def half_spread_fraction(symbol: str, spreads_path: Path = SPREADS_PATH) -> float:
    """Half the symbol's measured median bid/ask spread, as a fraction of price."""
    if not spreads_path.is_file():
        raise StockCostsUnavailable(
            f"No measured spreads file at {spreads_path.name}; run tools/measure_stock_spreads.py"
        )
    symbols = json.loads(spreads_path.read_text(encoding="utf-8")).get("symbols") or {}
    entry = symbols.get(symbol)
    if entry is None:
        raise StockCostsUnavailable(f"No measured bid/ask spread for {symbol} in {spreads_path.name}")
    bps = float(entry["median_spread_bps"])
    if not math.isfinite(bps) or bps <= 0:
        raise StockCostsUnavailable(f"The measured spread for {symbol} is not a positive number: {bps!r}")
    return bps / 2.0 / 10_000.0


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
    dataset_id = dataset_id_for(symbol)
    folder = manifest_dir if manifest_dir is not None else manifest_dir_for(dataset_id, load_data_locations())
    manifest = json.loads((folder / f"{dataset_id}.json").read_text(encoding="utf-8"))
    latest = str(manifest["latest_timestamp"])
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
        "fees": REGULATORY_FEE_FRACTION_PER_SIDE,
        "slippage": slippage,
        "stress_slippage": slippage * STRESS_SLIPPAGE_MULTIPLIER,
    }
