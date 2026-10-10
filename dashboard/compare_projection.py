"""Bounded, read-only projection for exact survivor comparison."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from dashboard.candidates_projection import _candidate_grid_row, _candidate_source
from dashboard.compare_query import parse_compare_search
from dashboard.overview_projection import BASE_CTE, _base_params, _validated_connection, configured_database_path
from dashboard.results_projection import load_results_record


def load_compare_records(search: str | None, *, database: str | Path | None = None) -> dict[str, Any]:
    """Load two-to-four exact survivor runs and bounded persisted evidence."""

    request = parse_compare_search(search)
    if not request.requested:
        return {"available": False, "message": "Select two qualified survivors in Candidates to compare them.", "records": []}
    if not request.valid:
        return {"available": False, "message": request.error, "records": [], "tokens": list(request.visible_tokens)}
    database_path = Path(database) if database is not None else configured_database_path()
    connection, error = _validated_connection(database_path)
    if connection is None:
        return {"available": False, "message": error, "records": []}
    try:
        source = BASE_CTE + ", candidate_records AS (" + _candidate_source() + ")"
        records = []
        for run_id in request.run_ids:
            row = connection.execute(source + " SELECT * FROM candidate_records WHERE run_id=? AND lifecycle='survivor'", _base_params() + [run_id]).fetchone()
            if row is None:
                return {"available": False, "message": f"Run {run_id} is not an exact qualified survivor.", "records": []}
            candidate = _candidate_grid_row(row)
            evidence = load_results_record(run_id, database=database_path)
            records.append({**candidate, "evidence": evidence})
        return {"available": True, "message": "Exact persisted survivors loaded read-only.", "records": records, "shared_period": _shared_period(records)}
    except (sqlite3.Error, ValueError, TypeError) as exc:
        return {"available": False, "message": f"Comparison could not be projected safely: {exc}", "records": []}
    finally:
        connection.close()


def comparison_series(record: dict[str, Any], view: str) -> tuple[list[Any], list[float]]:
    """Return a normalized bounded evidence series suitable for Plotly."""

    evidence = record.get("evidence") or {}
    rows = evidence.get("drawdown" if view == "drawdown" else "equity") or []
    x_values, values = [], []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        raw = next((row.get(key) for key in ("drawdown", "drawdown_pct", "value") if row.get(key) is not None), None) if view == "drawdown" else next((row.get(key) for key in ("equity", "portfolio_value", "value", "cumulative_return") if row.get(key) is not None), None)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        x_values.append(next((row.get(key) for key in ("timestamp", "date", "datetime", "index") if row.get(key) is not None), index))
        values.append(value)
    if view != "drawdown" and values and values[0] != 0:
        base = values[0]
        values = [100.0 * value / base for value in values]
    return x_values, values


def _shared_period(records: list[dict[str, Any]]) -> str:
    ranges = []
    for record in records:
        x_values, _ = comparison_series(record, "equity")
        if x_values:
            ranges.append((str(x_values[0]), str(x_values[-1])))
    if len(ranges) != len(records):
        return "Shared period unavailable"
    start = max(item[0] for item in ranges); end = min(item[1] for item in ranges)
    return f"{start} → {end}" if start <= end else "No shared persisted period"


__all__ = ["comparison_series", "load_compare_records"]
