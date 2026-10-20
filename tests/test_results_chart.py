"""Results price chart: drawn from saved bars and saved trades, never from a backtest rebuild."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from dashboard import results_projection as projection
from dashboard.ui import results as page
from persistence import ArtifactType, PersistenceService
from tests.test_artifact_contracts import _service_with_run


def register_price_copy(service: PersistenceService, run_id: str, path: Path, root: Path) -> None:
    """Register a per-run price copy the way older runs saved it (a checksummed sqlite3 artifact)."""
    service.register_artifact(
        run_id=run_id, artifact_type=ArtifactType.GENERIC_FIXTURE_EVIDENCE, logical_name="screening_price_series",
        media_type="application/vnd.sqlite3", format="sqlite3", location=str(path.relative_to(root)),
        content=path.read_bytes(),
    )


def _price_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "bars.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE price_bars (timestamp TEXT, open REAL, high REAL, low REAL, close REAL)")
    stamps = pd.date_range("2025-01-02 14:30", periods=78, freq="5min", tz="UTC").append(
        pd.date_range("2025-01-03 14:30", periods=78, freq="5min", tz="UTC"))
    connection.executemany("INSERT INTO price_bars VALUES (?, 100, 101, 99, 100.5)", [[stamp.isoformat()] for stamp in stamps])
    connection.commit(); connection.close()
    service = _service_with_run(tmp_path, "scr")
    try:
        register_price_copy(service, "scr", path, tmp_path)
    finally:
        service.close()
    return tmp_path / "state" / "artifacts.sqlite3"


def test_session_price_reads_one_eastern_day_of_saved_bars(tmp_path: Path) -> None:
    database = _price_artifact(tmp_path)
    bars = projection.load_session_price("scr", "2025-01-03", interval="15m", database=database)
    assert len(bars["price"]) == 26 and all(row["timestamp"].startswith("2025-01-03") for row in bars["price"])
    assert projection.load_session_price("scr", None, database=database)["price"] == []


TRADES = [
    {"trade_id": 1, "direction": "Long", "outcome": "Win", "pnl": 5.0, "entry_timestamp": "2025-01-03T09:45:00", "entry_price": 100.0, "exit_timestamp": "2025-01-03T10:30:00", "exit_price": 101.0},
    {"trade_id": 2, "direction": "Long", "outcome": "Loss", "pnl": -3.0, "entry_timestamp": "2025-01-03T11:00:00", "entry_price": 100.5, "exit_timestamp": "2025-01-03T11:20:00", "exit_price": 99.5},
]
PRICE = [{"timestamp": f"2025-01-03T{hour:02d}:00:00", "open": 100, "high": 101, "low": 99, "close": 100.5} for hour in range(9, 16)]


def test_chart_has_candles_and_entry_and_exit_markers() -> None:
    figure = page.trades_figure(PRICE, TRADES, None, None, 0)
    names = [trace.name for trace in figure.data]
    assert names == ["Price", "Entry", "Exit · win", "Exit · loss"]


def test_picking_a_trade_zooms_to_it() -> None:
    figure = page.trades_figure(PRICE, TRADES, TRADES[1], None, 0)
    start, end = (pd.Timestamp(value) for value in figure.layout.xaxis.range)
    assert start < pd.Timestamp("2025-01-03T11:00") and end > pd.Timestamp("2025-01-03T11:20")
    assert end - start < pd.Timedelta(hours=3)


def test_no_bars_shows_plain_message() -> None:
    figure = page.trades_figure([], TRADES, None, "No price bars were saved for 2025-01-04.", 0)
    assert figure.layout.annotations[0].text == "No price bars were saved for 2025-01-04."


def test_chart_day_follows_picked_trade_then_session_then_last_trade() -> None:
    assert page._chart_session("all", TRADES[0], TRADES) == "2025-01-03"
    assert page._chart_session("2025-01-02", None, TRADES) == "2025-01-02"
    assert page._chart_session("all", None, TRADES) == "2025-01-03"


def test_results_page_does_not_need_vectorbt() -> None:
    assert not hasattr(page, "rebuild_setting") and not hasattr(page, "window_figure")
