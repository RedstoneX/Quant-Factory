"""Alpaca SIP CLI, nightly scheduling, universe and compose wiring."""

from __future__ import annotations

from datetime import UTC, datetime, time as dt_time
from pathlib import Path

import pytest
import yaml

from market_data.alpaca_sip_cli import (
    parse_args,
    resolve_symbols,
    run_daily,
    run_top_up,
    seconds_until,
)
from market_data.alpaca_sip_universe import UNIVERSE, UNIVERSE_GROUPS, asset_type

ROOT = Path(__file__).resolve().parents[1]


def test_universe_has_45_unique_symbols_in_labelled_groups():
    assert len(UNIVERSE) == 45
    assert len(set(UNIVERSE)) == 45
    assert {group: len(symbols) for group, symbols in UNIVERSE_GROUPS.items()} == {
        "market_reference": 3, "funds": 11, "stocks": 31,
    }
    assert asset_type("IBIT") == "ETF"
    assert asset_type("XLE") == "ETF"
    assert asset_type("KO") == "stock"


def test_all_and_symbols_selection():
    assert resolve_symbols(parse_args(["--all"])) == list(UNIVERSE)
    assert resolve_symbols(parse_args(["--symbols", "spy", "NVDA"])) == ["SPY", "NVDA"]
    with pytest.raises(ValueError, match="Not in the universe"):
        resolve_symbols(parse_args(["--symbols", "ZZZZ"]))
    with pytest.raises(SystemExit):
        parse_args(["--all", "--symbols", "SPY"])


def test_missing_credentials_stop_before_any_download(capsys):
    def never_built(**_: object):
        raise AssertionError("provider must not be built without credentials")

    code = run_top_up(["SPY"], since="2016-01-01", environ={}, provider_factory=never_built)
    assert code == 2
    assert "Missing Alpaca credentials" in capsys.readouterr().out


def test_seconds_until_next_daily_run():
    now = datetime(2026, 10, 14, 1, 0, tzinfo=UTC)
    assert seconds_until(now, dt_time(2, 0)) == 3600
    assert seconds_until(datetime(2026, 10, 14, 2, 0, tzinfo=UTC), dt_time(2, 0)) == 86400


def test_daily_loop_runs_job_each_day_and_survives_failures():
    clock = [datetime(2026, 10, 14, 1, 0, tzinfo=UTC)]
    sleeps: list[float] = []
    codes = iter([1, 0])

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] = clock[0].fromtimestamp(clock[0].timestamp() + seconds, UTC)

    assert run_daily(dt_time(2, 0), lambda: next(codes), clock=lambda: clock[0], sleep=sleep, max_runs=2) == 0
    assert sleeps == [3600, 86400]


def test_compose_mounts_market_data_writable_only_for_topup_service():
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    topup = services["market-data-topup"]
    assert topup["entrypoint"] == ["python", "-m", "market_data.alpaca_sip_cli"]
    assert topup["command"][:1] == ["--all"]
    assert topup["environment"]["QF_ALPACA_API_KEY"] == "${QF_ALPACA_API_KEY:-}"
    assert topup["environment"]["QF_ALPACA_SECRET_KEY"] == "${QF_ALPACA_SECRET_KEY:-}"
    for name, service in services.items():
        for volume in service.get("volumes", []):
            if "/market-data:" not in volume:
                continue
            if name == "market-data-topup":
                assert volume.endswith(":rw")
            else:
                assert volume.endswith(":ro"), (name, volume)
