"""Read-only Results workspace projection over persisted run evidence."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sqlite3
from typing import Any

from dashboard.overview_projection import _validated_connection, configured_database_path
from dashboard.results_model import group_trade_rows, prepare_interval
from dashboard.run_detail_adapter import RunDetailDashboardAdapter


PRICE_LIMIT = 2_000
TRADE_LIMIT = 500
EQUITY_LIMIT = 2_000


def _artifact_root(database: Path) -> Path:
    return database.parent.parent if database.parent.name == "state" else database.parent


def _fields(items: Any) -> list[dict[str, str]]:
    return [{"label": str(item.label), "value": str(item.value)} for item in items]


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
        }
    except (KeyError, RuntimeError, ValueError, OSError) as exc:
        return {
            "available": False,
            "message": f"Persisted Results evidence is unavailable: {exc}",
            "run": run,
            "runs": runs,
        }


__all__ = ["list_results_runs", "load_results_record"]
