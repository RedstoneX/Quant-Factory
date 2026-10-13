"""Read-only Results workspace projection over persisted run evidence."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from dashboard.overview_projection import _validated_connection, configured_database_path
from dashboard.results_model import group_trade_rows, prepare_interval
from dashboard.run_detail_adapter import RunDetailDashboardAdapter, _candidate_trade_rows


PRICE_LIMIT = 2_000
TRADE_LIMIT = 500
EQUITY_LIMIT = 2_000


def _artifact_root(database: Path) -> Path:
    return database.parent.parent if database.parent.name == "state" else database.parent


def _fields(items: Any) -> list[dict[str, str]]:
    return [{"label": str(item.label), "value": str(item.value)} for item in items]


def _percent(value: Any, *, absolute: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    number = abs(number) if absolute else number
    return number * 100 if abs(number) <= 1 else number


def _screening_rows(connection: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT row_id, normalized_parameters_json, metrics_json, ranking_position,
               screening_status, rejection_reasons
        FROM parameter_results
        WHERE run_id=?
        ORDER BY ranking_position, row_id
        """,
        [run_id],
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            parameters = json.loads(str(row["normalized_parameters_json"] or "{}"))
            metrics = json.loads(str(row["metrics_json"] or "{}"))
        except (json.JSONDecodeError, TypeError):
            parameters, metrics = {}, {}
        result.append({
            "row_id": str(row["row_id"]),
            "rank": int(row["ranking_position"]),
            "run_length": parameters.get("run_length"),
            "minimum_ticks_per_bar": parameters.get("minimum_ticks_per_bar"),
            "total_return": _percent(metrics.get("total_return")),
            "annualized_return": _percent(metrics.get("annualized_return")),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": _percent(metrics.get("max_drawdown"), absolute=True),
            "number_of_trades": metrics.get("number_of_trades"),
            "win_rate": _percent(metrics.get("win_rate")),
            "screening_status": str(row["screening_status"]),
            "rejection_reasons": str(row["rejection_reasons"] or ""),
        })
    return result


def _artifact_document(*, database: Path, run_id: str, logical_name: str) -> dict[str, Any] | None:
    root = _artifact_root(database).resolve()
    connection, _error = _validated_connection(database)
    if connection is None:
        return None
    try:
        artifact = connection.execute(
            """
            SELECT location, checksum, size_bytes, availability
            FROM artifact_references
            WHERE run_id=? AND logical_name=?
            """,
            [run_id, logical_name],
        ).fetchone()
        if artifact is None or str(artifact["availability"]) != "available":
            return None
        path = (root / str(artifact["location"])).resolve()
        if path != root and root not in path.parents:
            return None
        content = path.read_bytes()
        if len(content) != int(artifact["size_bytes"]):
            return None
        if hashlib.sha256(content).hexdigest() != str(artifact["checksum"]):
            return None
        document = json.loads(content)
        return document if isinstance(document, dict) else None
    except (sqlite3.Error, OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    finally:
        connection.close()


def load_screening_configuration_evidence(
    run_id: str | None,
    parameter_row_id: str | None,
    *,
    interval: str = "15m",
    database: str | Path | None = None,
) -> dict[str, Any]:
    """Load bounded, exact artifacts for one persisted screening configuration."""
    if not run_id or not parameter_row_id:
        return {"available": False, "message": "Select a persisted configuration."}
    database_path = Path(database) if database is not None else configured_database_path()
    namespace = f"screening_configuration/{parameter_row_id}"
    trades_document = _artifact_document(
        database=database_path, run_id=run_id,
        logical_name=f"{namespace}/trades_and_orders",
    )
    equity_document = _artifact_document(
        database=database_path, run_id=run_id,
        logical_name=f"{namespace}/equity_curve",
    )
    price_document = (
        equity_document
        if equity_document and equity_document.get("price_series")
        else _artifact_document(
            database=database_path, run_id=run_id, logical_name="screening_price_series"
        )
    )
    metrics_document = _artifact_document(
        database=database_path, run_id=run_id,
        logical_name=f"{namespace}/metrics",
    )
    if not all((price_document, trades_document, equity_document, metrics_document)):
        return {
            "available": False,
            "message": "This historical configuration retained aggregate metrics only; chart and trade evidence were not persisted.",
            "run_id": run_id,
            "parameter_row_id": parameter_row_id,
        }
    source_interval = str(price_document.get("source_interval") or "5m")
    prepared = prepare_interval(
        price_document.get("price_series") or [], interval,
        source_interval=source_interval,
    )
    grouped = group_trade_rows(_candidate_trade_rows(trades_document))
    trades = [
        {
            "trade_id": group.trade_id,
            "direction": (group.direction or "Unrecorded").title(),
            "entry_timestamp": group.entry.timestamp.isoformat() if group.entry else None,
            "entry_price": group.entry.price if group.entry else None,
            "exit_timestamp": group.exit.timestamp.isoformat() if group.exit else None,
            "exit_price": group.exit.price if group.exit else None,
            "duration": (
                f"{int((group.exit.timestamp - group.entry.timestamp).total_seconds() // 60)}m"
                if group.entry and group.exit else "—"
            ),
            "pnl": group.pnl,
            "outcome": (group.outcome or group.status).replace("_", " ").title(),
            "status": group.status,
        }
        # Results investigates the newest retained evidence.  Keep the bounded
        # trade cohort aligned with the newest persisted price window so entry
        # and exit markers cannot silently disappear when a configuration has
        # more trades than the UI limit.
        for group in grouped.groups[-TRADE_LIMIT:]
    ]
    equity = [row for row in equity_document.get("equity_curve") or [] if isinstance(row, dict)]
    prepared_rows = [
        {"timestamp": bar.timestamp.isoformat(), "open": bar.open, "high": bar.high,
         "low": bar.low, "close": bar.close, "source_count": bar.source_count}
        for bar in prepared.bars
    ] if prepared.available else []
    if prepared_rows and trades:
        focus = str(trades[-1].get("entry_timestamp") or prepared_rows[-1]["timestamp"])
        position = bisect_left([str(row["timestamp"]) for row in prepared_rows], focus)
        prepared_rows = prepared_rows[max(0, position - 30):position + 60]
    else:
        prepared_rows = prepared_rows[-PRICE_LIMIT:]
    return {
        "available": bool(prepared.available),
        "message": (
            "Exact persisted configuration evidence loaded."
            if prepared.available else prepared.reason or "No persisted price bars are available."
        ),
        "run_id": run_id,
        "parameter_row_id": parameter_row_id,
        "interval": interval,
        "source_interval": source_interval,
        "price": prepared_rows,
        "price_available": prepared.available,
        "price_reason": prepared.reason,
        "trades": trades,
        "trade_count": len(grouped.groups),
        "trade_limit": TRADE_LIMIT,
        "equity": equity[-EQUITY_LIMIT:],
        "metrics": metrics_document.get("metrics") or {},
    }


def list_results_runs(*, database: str | Path | None = None) -> list[dict[str, Any]]:
    """Return bounded newest-first run choices without mutating persistence."""
    database_path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(database_path)
    if connection is None:
        return []
    try:
        rows = connection.execute(
            """
            SELECT r.run_id, r.status, r.stage, r.created_at, r.completed_at,
                   c.experiment_id, c.strategy_id,
                   COALESCE(json_extract(c.canonical_config_json, '$.market_data.symbol'),
                            json_extract(c.canonical_config_json, '$.market_data.dataset_id'),
                            'Unrecorded') AS symbol,
                   d.draft_id AS candidate_id,
                   COALESCE(json_extract(d.candidate_json, '$.candidate.title'), d.title) AS candidate_title
            FROM experiment_runs r
            JOIN experiment_configurations c ON c.configuration_id=r.configuration_id
            LEFT JOIN idea_drafts d ON d.configuration_id=r.configuration_id AND d.candidate_json<>''
            ORDER BY COALESCE(r.completed_at, r.created_at) DESC, r.run_id DESC
            LIMIT 100
            """
        ).fetchall()
        return [
            {
                "run_id": str(row["run_id"]),
                "status": str(row["status"]),
                "stage": str(row["stage"]),
                "created_at": str(row["created_at"]),
                "completed_at": str(row["completed_at"] or ""),
                "experiment_id": str(row["experiment_id"] or "Unrecorded experiment"),
                "strategy_id": str(row["strategy_id"] or "Unrecorded strategy"),
                "symbol": str(row["symbol"] or "Unrecorded"),
                "candidate_id": str(row["candidate_id"]) if row["candidate_id"] else None,
                "title": (
                    str(row["candidate_title"])
                    if row["candidate_title"]
                    else str(row["experiment_id"] or row["strategy_id"] or row["run_id"]).replace("_", " ").title()
                ),
            }
            for row in rows
        ]
    except (sqlite3.Error, ValueError, TypeError):
        return []
    finally:
        connection.close()


def _run_choice(run_id: str | None, runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if run_id:
        exact = next((row for row in runs if row["run_id"] == run_id), None)
        if exact:
            return exact
    return next((row for row in runs if row["status"] == "succeeded"), runs[0] if runs else None)


def load_results_record(
    run_id: str | None = None,
    *,
    interval: str = "15m",
    database: str | Path | None = None,
) -> dict[str, Any]:
    """Hydrate one exact run and bounded chart/ledger evidence."""
    database_path = Path(database) if database is not None else configured_database_path()
    runs = list_results_runs(database=database_path)
    run = _run_choice(run_id, runs)
    if run is None:
        return {"available": False, "message": "No persisted Results run is available.", "runs": []}
    screening_rows: list[dict[str, Any]] = []
    connection, _error = _validated_connection(database_path)
    if connection is not None:
        try:
            screening_rows = _screening_rows(connection, run["run_id"])
        except (sqlite3.Error, ValueError, TypeError):
            screening_rows = []
        finally:
            connection.close()
    try:
        detail = RunDetailDashboardAdapter(
            database_path, artifact_root=_artifact_root(database_path)
        ).selected_run_detail(run["run_id"])
        evidence = detail.evidence
        prepared = prepare_interval(
            evidence.price_series,
            interval,
            source_interval=evidence.source_interval,
        )
        price = [
            {
                "timestamp": bar.timestamp.isoformat(), "open": bar.open, "high": bar.high,
                "low": bar.low, "close": bar.close, "source_count": bar.source_count,
            }
            for bar in prepared.bars[-PRICE_LIMIT:]
        ] if prepared.available else []
        grouped = group_trade_rows(evidence.trades)
        trades = [
            {
                "trade_id": group.trade_id,
                "direction": (group.direction or "Unrecorded").title(),
                "entry_timestamp": group.entry.timestamp.isoformat() if group.entry else None,
                "entry_price": group.entry.price if group.entry else None,
                "exit_timestamp": group.exit.timestamp.isoformat() if group.exit else None,
                "exit_price": group.exit.price if group.exit else None,
                "duration": (
                    f"{int((group.exit.timestamp - group.entry.timestamp).total_seconds() // 60)}m"
                    if group.entry and group.exit else "—"
                ),
                "pnl": group.pnl,
                "outcome": (group.outcome or group.status).replace("_", " ").title(),
                "status": group.status,
            }
            for group in grouped.groups[:TRADE_LIMIT]
        ]
        return {
            "available": True,
            "message": "Persisted run evidence loaded read-only.",
            "run": run,
            "runs": runs,
            "metrics": _fields(evidence.metrics),
            "trades": trades,
            "trade_count": len(grouped.groups),
            "trade_limit": TRADE_LIMIT,
            "price": price,
            "price_available": prepared.available,
            "price_reason": prepared.reason,
            "source_interval": evidence.source_interval,
            "interval": interval,
            "equity": [dict(row) for row in evidence.equity_curve[-EQUITY_LIMIT:]],
            "drawdown": [dict(row) for row in evidence.drawdown_curve[-EQUITY_LIMIT:]],
            "validation": _fields(evidence.validation_outcome or evidence.validation),
            "provenance": _fields(evidence.provenance),
            "lineage": _fields(detail.lineage_fields),
            "artifacts": [asdict(item) for item in detail.artifacts],
            "notices": list(evidence.notices),
            "warnings": list(detail.warnings),
            "result_status": detail.result_summary.status,
            "result_message": detail.result_summary.message,
            "evidence_classification": evidence.evidence_classification,
            "promotion_eligible": evidence.promotion_eligible,
            "screening_rows": screening_rows,
            "screening_count": len(screening_rows),
            "screened_out_count": sum(row["screening_status"] == "screened_out" for row in screening_rows),
        }
    except (KeyError, RuntimeError, ValueError, OSError) as exc:
        return {
            "available": False,
            "message": f"Persisted Results evidence is unavailable: {exc}",
            "run": run,
            "runs": runs,
            "screening_rows": screening_rows,
            "screening_count": len(screening_rows),
            "screened_out_count": sum(row["screening_status"] == "screened_out" for row in screening_rows),
        }


__all__ = ["list_results_runs", "load_results_record", "load_screening_configuration_evidence"]
