"""Tests for tools/measure_stock_spreads.py with ``vbt.AlpacaData.pull`` faked (no network)."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import sys

import pandas as pd
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "measure_stock_spreads", Path(__file__).resolve().parents[1] / "tools" / "measure_stock_spreads.py"
)
spreads_tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(spreads_tool)

SESSIONS = [(datetime(2026, 10, 13, 13, 30, tzinfo=timezone.utc), datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc))]


def _quotes(rows: list[tuple[float, float]]) -> pd.DataFrame:
    index = pd.DatetimeIndex(["2026-10-13T14:00:00Z"] * len(rows), name="Open time")
    return pd.DataFrame({"Bid price": [r[0] for r in rows], "Ask price": [r[1] for r in rows]}, index=index)


def test_spread_bps_drops_invalid_quotes() -> None:
    spreads, mids = spreads_tool.spread_bps(pd.Series([99.99, 0.0, 1.0]), pd.Series([100.01, 1.0, 1.0]))
    assert spreads == [pytest.approx(2.0)] and mids == [pytest.approx(100.0)]


def test_measure_uses_vbt_pull_sip_quotes_and_medians() -> None:
    calls: list[dict] = []

    def pull(symbols, **kwargs):
        calls.append({"symbols": symbols, **kwargs})
        return SimpleNamespace(data={"SPY": _quotes([(99.99, 100.01), (0, 5), (49.99, 50.01), (9.99, 10.01)])})

    result = spreads_tool.measure(["SPY"], SESSIONS, pull=pull, client_config={"api_key": "k", "secret_key": "s"})
    # 3 windows x (2.0, 4.0, 20.0) bps -> median 4.0 over 9 valid quotes.
    assert result == {"SPY": {"median_spread_bps": pytest.approx(4.0), "median_mid_price": pytest.approx(50.0),
                              "samples": 9, "sessions": 1}}
    assert len(calls) == 3
    assert calls[0]["feed"] == "sip" and calls[0]["data_type"] == "quotes" and calls[0]["symbols"] == ["SPY"]
    assert calls[0]["start"] == datetime(2026, 10, 13, 10, 0, tzinfo=spreads_tool.NEW_YORK)
    doc = spreads_tool.document(result, SESSIONS, SESSIONS[0][0])
    assert set(doc) == {"measured_at", "method", "source", "symbols"}


def test_symbol_without_valid_quotes_fails_plainly() -> None:
    def pull(symbols, **kwargs):
        return SimpleNamespace(data={"SPY": _quotes([(0, 1)])})

    with pytest.raises(RuntimeError, match="SPY: no valid two-sided SIP quotes"):
        spreads_tool.measure(["SPY"], SESSIONS, pull=pull, client_config={})


def test_early_close_skips_late_sample() -> None:
    open_utc = datetime(2026, 11, 27, 14, 30, tzinfo=timezone.utc)
    windows = spreads_tool.sample_windows([(open_utc, datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc))])
    assert len(windows) == 2


def test_main_wires_env_credentials_into_vbt_pull(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict = {}

    def pull(symbols, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(data={s: _quotes([(99.99, 100.01)]) for s in symbols})

    fake_vbt = SimpleNamespace(AlpacaData=SimpleNamespace(pull=pull))
    monkeypatch.setitem(sys.modules, "vectorbtpro", fake_vbt)
    monkeypatch.setattr(spreads_tool, "recent_sessions", lambda now: SESSIONS)
    monkeypatch.setenv("QF_ALPACA_API_KEY", "k")
    monkeypatch.setenv("QF_ALPACA_SECRET_KEY", "s")
    out = tmp_path / "out.json"
    assert spreads_tool.main(["--out", str(out), "--symbols", "SPY"]) == 0
    assert seen["client_config"] == {"api_key": "k", "secret_key": "s"} and seen["feed"] == "sip"
    assert '"SPY"' in out.read_text()
