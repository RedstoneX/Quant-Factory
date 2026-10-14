"""Download or top up the Alpaca SIP one-minute bar library.

Full backfill (first run) or top-up (later runs) for the whole universe:
    python -m market_data.alpaca_sip_cli --all
Selected symbols, with a custom first-download start date:
    python -m market_data.alpaca_sip_cli --symbols SPY AAPL --since 2020-01-01
Nightly top-up that stays running and fires once a day at a UTC time:
    python -m market_data.alpaca_sip_cli --all --daily-at 02:00

Credentials come from QF_ALPACA_API_KEY and QF_ALPACA_SECRET_KEY.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, time as dt_time, timedelta
import os
from pathlib import Path
import time

import requests

from market_data.alpaca_sip_universe import HISTORY_START, UNIVERSE
from market_data.catalog import DEFAULT_CONFIG_PATH, DataLocations, load_data_locations
from market_data.providers.alpaca_sip import (
    AlpacaSipError,
    AlpacaSipProvider,
    credentials_from_environment,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_LOCATIONS_VARIABLE = "QUANT_FACTORY_DATA_LOCATIONS"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpaca SIP one-minute bar library")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--symbols", nargs="+", help="symbols from the universe")
    which.add_argument("--all", action="store_true", help="every universe symbol")
    parser.add_argument(
        "--since",
        default=HISTORY_START,
        help="first date for symbols with no stored file yet (default %(default)s)",
    )
    parser.add_argument("--daily-at", help="stay running and top up daily at HH:MM UTC")
    parser.add_argument("--data-locations", help="path to data_locations.local.toml")
    return parser.parse_args(argv)


def resolve_symbols(args: argparse.Namespace) -> list[str]:
    if args.all:
        return list(UNIVERSE)
    symbols = [symbol.upper() for symbol in args.symbols]
    unknown = [symbol for symbol in symbols if symbol not in UNIVERSE]
    if unknown:
        raise ValueError(f"Not in the universe (edit market_data/alpaca_sip_universe.py): {unknown}")
    return symbols


def _locations(path_arg: str | None, environ: Mapping[str, str]) -> DataLocations:
    path = Path(path_arg or environ.get(DATA_LOCATIONS_VARIABLE) or DEFAULT_CONFIG_PATH)
    locations = load_data_locations(path)
    root = locations.root.resolve()
    if root == PROJECT_ROOT or PROJECT_ROOT in root.parents:
        raise ValueError("Configured market-data root is inside the repository; refusing to write")
    return locations


def run_top_up(
    symbols: Sequence[str],
    *,
    since: str,
    data_locations: str | None = None,
    environ: Mapping[str, str] | None = None,
    provider_factory: Callable[..., AlpacaSipProvider] = AlpacaSipProvider,
) -> int:
    """Top up each symbol; one symbol's failure never stops the others."""
    values = os.environ if environ is None else environ
    try:
        credentials = credentials_from_environment(values)
        locations = _locations(data_locations, values)
    except (AlpacaSipError, FileNotFoundError, ValueError) as exc:
        print(f"Alpaca SIP top-up cannot start: {exc}", flush=True)
        return 2
    provider = provider_factory(credentials=credentials, locations=locations)
    failures = 0
    for symbol in symbols:
        try:
            result = provider.top_up(symbol, since=since)
        except (AlpacaSipError, requests.RequestException, OSError, ValueError) as exc:
            failures += 1
            print(f"{symbol}: FAILED: {exc}", flush=True)
            continue
        print(
            f"{symbol}: {result.status}; {result.new_rows} new bars; {result.row_count} stored",
            flush=True,
        )
    print(f"Done: {len(symbols) - failures} ok, {failures} failed", flush=True)
    return 1 if failures else 0


def seconds_until(now: datetime, at: dt_time) -> float:
    """Seconds from ``now`` to the next occurrence of ``at`` (same tz as ``now``)."""
    target = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_daily(
    at: dt_time,
    job: Callable[[], int],
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    max_runs: int | None = None,
) -> int:
    """Run ``job`` once a day at ``at`` UTC; a failed run is logged and the loop continues."""
    runs = 0
    while max_runs is None or runs < max_runs:
        wait = seconds_until(clock(), at)
        print(f"Next Alpaca SIP top-up in {wait / 3600:.2f} h", flush=True)
        sleep(wait)
        code = job()
        print(f"Alpaca SIP top-up finished at {clock().isoformat()} with exit code {code}", flush=True)
        runs += 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        symbols = resolve_symbols(args)
        daily_at = dt_time.fromisoformat(args.daily_at) if args.daily_at else None
    except ValueError as exc:
        print(f"Invalid arguments: {exc}", flush=True)
        return 2

    def job() -> int:
        return run_top_up(symbols, since=args.since, data_locations=args.data_locations)

    if daily_at is None:
        return job()
    return run_daily(daily_at, job)


if __name__ == "__main__":
    raise SystemExit(main())
