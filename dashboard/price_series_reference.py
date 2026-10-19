"""A run's price bars: its own saved copy (older runs) or a hashed reference to the shared market data.

New runs record which bars of the shared market-data store they used instead
of copying them. The bars are reloaded through ``load_market_data`` and shown
only when their hash still matches; otherwise the chart gets a plain reason.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from typing import Any, Callable

import pandas as pd

from market_data import DatasetUnavailableError, MarketDataConfig, load_market_data
from orchestration.candidate_screening_artifacts import SCREENING_PRICE_REFERENCE, screening_bars_hash

PRICE_DATA_CHANGED = (
    "The market data this test used has changed since it ran, so its price chart is not shown."
)
PRICE_DATA_MISSING = "The market data this test used is no longer available, so its price chart is not shown."


def _utc_window(session: str | None, period: tuple[str, str] | None) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    if not (session or period):
        return None
    first, last = period or (session, session)
    start = pd.Timestamp(first, tz="America/New_York")
    end = pd.Timestamp(last, tz="America/New_York") + pd.Timedelta(days=1)
    return start.tz_convert("UTC"), end.tz_convert("UTC")


def _referenced_price_rows(
    *, database: Path, run_id: str, session: str | None, period: tuple[str, str] | None,
    artifact_reference: Callable[..., Any], artifact_document: Callable[..., Any],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Reload a run's bars from the shared market-data store and prove they are the bars it used."""
    document = artifact_document(database=database, run_id=run_id, logical_name=SCREENING_PRICE_REFERENCE)
    if document is None:
        return None, None
    try:
        request = dict(document["market_data"])
        request["cache_path"] = Path(request["cache_path"])
        request["legacy_cache_paths"] = tuple(Path(item) for item in request.get("legacy_cache_paths") or ())
        loaded = load_market_data(MarketDataConfig(**request), allow_download=False).data
        bars = loaded.loc[pd.Timestamp(document["start"]):pd.Timestamp(document["end"])]
        if len(bars) != int(document["row_count"]) or screening_bars_hash(bars) != str(document["bars_sha256"]):
            return None, PRICE_DATA_CHANGED
    except (DatasetUnavailableError, OSError):
        return None, PRICE_DATA_MISSING
    except (ValueError, TypeError, KeyError):
        return None, PRICE_DATA_CHANGED
    window = _utc_window(session, period)
    utc = bars.tz_convert("UTC") if bars.index.tz is not None else bars
    if window is not None:
        utc = utc[(utc.index >= window[0]) & (utc.index < window[1])]
    return [
        {"timestamp": index.isoformat(), "open": float(row.Open), "high": float(row.High),
         "low": float(row.Low), "close": float(row.Close)}
        for index, row in utc.loc[:, ["Open", "High", "Low", "Close"]].iterrows()
    ], None


def shared_price_source(
    *, database: Path, run_id: str, session: str | None, period: tuple[str, str] | None = None,
    artifact_reference: Callable[..., Any], artifact_document: Callable[..., Any],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """A run's bars and, when they cannot be shown faithfully, the plain reason why.

    Older runs keep their own copy and are read from it; newer runs record a
    reference to the shared market-data store instead.
    """
    helpers = {"artifact_reference": artifact_reference, "artifact_document": artifact_document}
    rows = _copied_price_rows(database=database, run_id=run_id, session=session, period=period, **helpers)
    if rows is not None:
        return rows, None
    return _referenced_price_rows(database=database, run_id=run_id, session=session, period=period, **helpers)


def _copied_price_rows(
    *, database: Path, run_id: str, session: str | None, period: tuple[str, str] | None = None,
    artifact_reference: Callable[..., Any], artifact_document: Callable[..., Any],
) -> list[dict[str, Any]] | None:
    """Bars from a run's own price copy (runs saved before references replaced copies)."""
    reference = artifact_reference(
        database=database, run_id=run_id, logical_name="screening_price_series"
    )
    if reference is None:
        return None
    path, artifact = reference
    if str(artifact["format"]) != "sqlite3":
        return None
    try:
        content = path.read_bytes()
        if len(content) != int(artifact["size_bytes"]):
            return None
        if hashlib.sha256(content).hexdigest() != str(artifact["checksum"]):
            return None
        query = "SELECT timestamp, open, high, low, close FROM price_bars"
        parameters: list[str] = []
        window = _utc_window(session, period)
        if window is not None:
            query += " WHERE timestamp>=? AND timestamp<?"
            parameters = [window[0].isoformat(), window[1].isoformat()]
        query += " ORDER BY timestamp"
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = connection.execute(query, parameters).fetchall()
        finally:
            connection.close()
        return [
            {
                "timestamp": str(row[0]),
                "open": float(row[1]), "high": float(row[2]),
                "low": float(row[3]), "close": float(row[4]),
            }
            for row in rows
        ]
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        return None
