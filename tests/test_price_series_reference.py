"""New runs record a reference to the shared market data, not a copy of it."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from pandas.testing import assert_frame_equal

from dashboard import price_series_reference as reference
from dashboard import results_projection as projection
from market_data import MarketDataConfig
from orchestration.candidate_screening_artifacts import persist_screening_price_series
from tests.test_artifact_contracts import _service_with_run

RUN = "artifact-run"
REQUEST = MarketDataConfig(
    symbol="SPYM", provider="Alpaca", provider_implementation="verified_local_catalog:test",
    interval="5m", requested_start="2025-01-02", end_date_policy="fixed", adjusted=False,
    exchange_calendar="NYSE", market_timezone="America/New_York", cache_path=Path("unused.parquet"),
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2025-01-02 14:30", periods=78, freq="5min", tz="UTC").append(
        pd.date_range("2025-01-03 14:30", periods=78, freq="5min", tz="UTC"))
    close = pd.Series(range(len(index)), index=index, dtype="float64") / 10 + 100
    return pd.DataFrame({"Open": close - 0.1, "High": close + 0.5, "Low": close - 0.5,
                         "Close": close, "Volume": 1_000.0})


def _persist(tmp_path: Path) -> Path:
    service = _service_with_run(tmp_path, RUN)
    try:
        persist_screening_price_series(
            persistence=service, artifact_root=tmp_path, run_id=RUN, data=_bars(), market_data=REQUEST,
        )
    finally:
        service.close()
    return tmp_path / "state" / "artifacts.sqlite3"


def _serve(monkeypatch, frame: pd.DataFrame, calls: list | None = None) -> None:
    def loader(config, now=None, *, allow_download=True):
        if calls is not None:
            calls.append((config, allow_download))
        return SimpleNamespace(data=frame)
    monkeypatch.setattr(reference, "load_market_data", loader)


def _old_copy(tmp_path: Path) -> tuple[Path, dict]:
    """The per-run copy older runs saved (same table the old writer produced)."""
    path = tmp_path / "copy.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE price_bars (timestamp TEXT PRIMARY KEY, open REAL NOT NULL, "
                       "high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL) WITHOUT ROWID")
    connection.executemany("INSERT INTO price_bars VALUES (?, ?, ?, ?, ?)", [
        (stamp.isoformat(), row.Open, row.High, row.Low, row.Close) for stamp, row in _bars().iterrows()])
    connection.commit(); connection.close()
    content = path.read_bytes()
    return path, {"format": "sqlite3", "size_bytes": len(content), "checksum": hashlib.sha256(content).hexdigest()}


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).set_index("timestamp")


def test_new_runs_write_a_reference_and_no_price_copy(tmp_path: Path) -> None:
    _persist(tmp_path)
    assert not list(tmp_path.rglob("screening_price_series.sqlite3"))
    assert (tmp_path / "state" / "artifacts" / RUN / "screening_price_series_reference.json").is_file()


def test_bars_loaded_by_reference_equal_the_old_copy(tmp_path: Path, monkeypatch) -> None:
    database = _persist(tmp_path)
    calls: list = []
    _serve(monkeypatch, _bars(), calls)
    by_reference, problem = projection._price_source(database=database, run_id=RUN, session=None)
    assert problem is None and calls == [(REQUEST, False)]
    path, row = _old_copy(tmp_path)
    monkeypatch.setattr(projection, "_artifact_reference",
                        lambda **kw: (path, row) if kw["logical_name"] == "screening_price_series" else None)
    from_copy, _ = projection._price_source(database=database, run_id=RUN, session=None)
    assert_frame_equal(_frame(by_reference), _frame(from_copy))


def test_session_chart_reads_one_day_by_reference(tmp_path: Path, monkeypatch) -> None:
    database = _persist(tmp_path)
    _serve(monkeypatch, _bars())
    bars = projection.load_session_price(RUN, "2025-01-03", interval="15m", database=database)
    assert len(bars["price"]) == 26 and all(row["timestamp"].startswith("2025-01-03") for row in bars["price"])


def test_changed_market_data_says_so_instead_of_drawing_other_bars(tmp_path: Path, monkeypatch) -> None:
    database = _persist(tmp_path)
    changed = _bars()
    changed.iloc[5, changed.columns.get_loc("Close")] += 0.25
    _serve(monkeypatch, changed)
    bars = projection.load_session_price(RUN, "2025-01-02", database=database)
    assert bars == {"price": [], "reason": reference.PRICE_DATA_CHANGED}


def test_reference_records_the_loader_request(tmp_path: Path, monkeypatch) -> None:
    database = _persist(tmp_path)
    calls: list = []
    _serve(monkeypatch, _bars(), calls)
    projection._price_source(database=database, run_id=RUN, session="2025-01-02")
    assert calls[0][0] == REQUEST and calls[0][0] != replace(REQUEST, symbol="SPY")
