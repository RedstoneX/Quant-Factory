"""Read-only Results workspace projection over persisted run evidence."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from dashboard.overview_projection import _validated_connection, configured_database_path
from dashboard.results_model import group_trade_rows, prepare_interval
from dashboard.formatting import format_metric, profit_factor
from dashboard.run_detail_adapter import RunDetailDashboardAdapter, _candidate_trade_rows
from dashboard.time_display import eastern_label, eastern_plot_timestamp, eastern_session


PRICE_LIMIT = 2_000
TRADE_LIMIT = 500
EQUITY_LIMIT = 2_000


def _trade_row(group: Any) -> dict[str, Any]:
    """One grid/chart row for a grouped trade, in Eastern wall time."""
    return {
        "trade_id": group.trade_id,
        "direction": (group.direction or "Unrecorded").title(),
        "entry_timestamp": eastern_plot_timestamp(group.entry.timestamp) if group.entry else None,
        "entry_display": eastern_label(group.entry.timestamp) if group.entry else "—",
        "entry_price": group.entry.price if group.entry else None,
        "exit_timestamp": eastern_plot_timestamp(group.exit.timestamp) if group.exit else None,
        "exit_display": eastern_label(group.exit.timestamp) if group.exit else "—",
        "exit_price": group.exit.price if group.exit else None,
        "duration": (
            f"{int((group.exit.timestamp - group.entry.timestamp).total_seconds() // 60)}m"
            if group.entry and group.exit else "—"
        ),
        "pnl": None if group.pnl is None else round(float(group.pnl), 2),
        "outcome": (group.outcome or group.status).replace("_", " ").title(),
        "status": group.status,
    }


def _saved_initial_cash(detail: Any) -> float | None:
    """The run's own saved starting cash (its execution assumptions), or None when it was not saved."""
    for field in detail.execution:
        if field.label == "Initial Cash":
            try:
                return float(field.value)
            except (TypeError, ValueError):
                return None
    return None


def equity_from_trades(trades: list[dict[str, Any]], *, starting_cash: float | None) -> list[dict[str, Any]]:
    """Account value after each closed trade: starting cash plus cumulative P&L (pandas cumsum) at exit time."""
    if starting_cash is None:
        return []
    closed = pd.DataFrame([t for t in trades if t.get("exit_timestamp") and t.get("pnl") is not None])
    if closed.empty:
        return []
    closed = closed.sort_values("exit_timestamp")
    values = starting_cash + closed["pnl"].cumsum()
    return [{"timestamp": ts, "value": float(v)} for ts, v in zip(closed["exit_timestamp"], values)]


def load_screening_configuration_trades(
    run_id: str | None, parameter_row_id: str | None, *, database: str | Path | None = None,
) -> dict[str, Any]:
    """Every saved trade of one first-check setting (newest bounded set), for the Trades list."""
    if not run_id or not parameter_row_id:
        return {"trades": [], "trade_count": 0}
    database_path = Path(database) if database is not None else configured_database_path()
    document = _artifact_document(
        database=database_path, run_id=run_id,
        logical_name=f"screening_configuration/{parameter_row_id}/trades_and_orders",
    )
    if not document:
        return {"trades": [], "trade_count": 0}
    grouped = group_trade_rows(_candidate_trade_rows(document))
    return {"trades": [_trade_row(g) for g in grouped.groups[-TRADE_LIMIT:]], "trade_count": len(grouped.groups)}


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
            "parameters": parameters,
            "run_length": parameters.get("run_length"),
            "minimum_ticks_per_bar": parameters.get("minimum_ticks_per_bar"),
            "range_minutes": parameters.get("range_minutes"),
            "breakout_offset_ticks": parameters.get("breakout_offset_ticks"),
            "direction_variant": parameters.get("direction_variant"),
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


def _artifact_reference(*, database: Path, run_id: str, logical_name: str) -> tuple[Path, sqlite3.Row] | None:
    root = _artifact_root(database).resolve()
    connection, _error = _validated_connection(database)
    if connection is None:
        return None
    try:
        artifact = connection.execute(
            """
            SELECT location, checksum, size_bytes, availability, format
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
        return path, artifact
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return None
    finally:
        connection.close()


def _artifact_document(*, database: Path, run_id: str, logical_name: str) -> dict[str, Any] | None:
    reference = _artifact_reference(database=database, run_id=run_id, logical_name=logical_name)
    if reference is None:
        return None
    path, artifact = reference
    try:
        content = path.read_bytes()
        if len(content) != int(artifact["size_bytes"]):
            return None
        if hashlib.sha256(content).hexdigest() != str(artifact["checksum"]):
            return None
        document = json.loads(content)
        return document if isinstance(document, dict) else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


OOS_REPORT_LOGICAL_NAME = "source_lock_evidence:out_of_sample"


def oos_report_metrics(*, database: Path, run_id: str | None) -> dict[str, Any] | None:
    """Unseen-data metrics the pipeline saves in the OOS report (it writes no parameter rows)."""
    if not run_id:
        return None
    report = _artifact_document(database=database, run_id=run_id, logical_name=OOS_REPORT_LOGICAL_NAME)
    metrics = (report or {}).get("metrics")
    if not report or report.get("artifact_kind") != "out_of_sample" or not isinstance(metrics, dict) or not metrics:
        return None
    return {**metrics, "_test_status": report.get("test_status")}


def _shared_price_rows(
    *, database: Path, run_id: str, session: str | None, period: tuple[str, str] | None = None,
) -> list[dict[str, Any]] | None:
    """Saved bars for one Eastern session, or for a whole Eastern date range (start and end days inclusive)."""
    reference = _artifact_reference(
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
        if session or period:
            first, last = period or (session, session)
            start = pd.Timestamp(first, tz="America/New_York")
            end = pd.Timestamp(last, tz="America/New_York") + pd.Timedelta(days=1)
            query += " WHERE timestamp>=? AND timestamp<?"
            parameters = [start.tz_convert("UTC").isoformat(), end.tz_convert("UTC").isoformat()]
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


def load_session_price(
    run_id: str | None, session: str | None, *, interval: str = "15m", database: str | Path | None = None,
) -> dict[str, Any]:
    """One Eastern session of the bars a first-check run saved (checksummed), grouped to the chosen bar size.

    An unseen-data run reads the bars of the first-check run it came from; no
    backtest engine is needed to draw them.
    """
    if not run_id or not session:
        return {"price": [], "reason": "No price bars were saved for this run."}
    database_path = Path(database) if database is not None else configured_database_path()
    rows = _shared_price_rows(database=database_path, run_id=run_id, session=session)
    if not rows:
        return {"price": [], "reason": f"No price bars were saved for {session}."}
    prepared = prepare_interval(rows, interval, source_interval="5m")
    return {
        "price": [
            {"timestamp": eastern_plot_timestamp(bar.timestamp), "open": bar.open, "high": bar.high,
             "low": bar.low, "close": bar.close, "source_count": bar.source_count}
            for bar in prepared.bars[-PRICE_LIMIT:]
        ] if prepared.available else [],
        "reason": prepared.reason,
    }


def list_screening_configuration_sessions(
    run_id: str | None, parameter_row_id: str | None, *, database: str | Path | None = None,
) -> list[str]:
    if not run_id or not parameter_row_id:
        return []
    database_path = Path(database) if database is not None else configured_database_path()
    document = _artifact_document(
        database=database_path, run_id=run_id,
        logical_name=f"screening_configuration/{parameter_row_id}/trades_and_orders",
    )
    if not document:
        return []
    grouped = group_trade_rows(_candidate_trade_rows(document))
    return sorted({eastern_session(group.entry.timestamp) for group in grouped.groups if group.entry})


def load_screening_configuration_evidence(
    run_id: str | None,
    parameter_row_id: str | None,
    *,
    interval: str = "15m",
    session: str | None = None,
    database: str | Path | None = None,
) -> dict[str, Any]:
    """Load bounded, exact artifacts for one persisted screening configuration."""
    if not run_id or not parameter_row_id:
        return {"available": False, "message": "Select a saved setting."}
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
    sessions = list_screening_configuration_sessions(
        run_id, parameter_row_id, database=database_path,
    )
    selected_session = session if session in sessions else (sessions[-1] if sessions else None)
    shared_price = _shared_price_rows(
        database=database_path, run_id=run_id, session=selected_session,
    )
    price_document = (
        {"source_interval": equity_document.get("source_interval", "5m"), "price_series": shared_price}
        if shared_price is not None and equity_document
        else equity_document
        if equity_document and equity_document.get("price_series")
        else None
    )
    metrics_document = _artifact_document(
        database=database_path, run_id=run_id,
        logical_name=f"{namespace}/metrics",
    )
    if not all((price_document, trades_document, equity_document, metrics_document)):
        return {
            "available": False,
            "message": "This historical configuration retained aggregate metrics only; no price chart or trades were saved.",
            "run_id": run_id,
            "parameter_row_id": parameter_row_id,
        }
    source_interval = str(price_document.get("source_interval") or "5m")
    prepared = prepare_interval(
        price_document.get("price_series") or [], interval,
        source_interval=source_interval,
    )
    grouped = group_trade_rows(_candidate_trade_rows(trades_document))
    groups = [group for group in grouped.groups if not selected_session or (
        group.entry and eastern_session(group.entry.timestamp) == selected_session
    )]
    trades = [
        _trade_row(group)
        # Keep the bounded trade cohort aligned with the selected session so
        # entry and exit markers cannot silently disappear from its chart.
        for group in groups[-TRADE_LIMIT:]
    ]
    equity = [row for row in equity_document.get("equity_curve") or [] if isinstance(row, dict)]
    prepared_rows = [
        {"timestamp": eastern_plot_timestamp(bar.timestamp), "open": bar.open, "high": bar.high,
         "low": bar.low, "close": bar.close, "source_count": bar.source_count}
        for bar in prepared.bars
    ] if prepared.available else []
    prepared_rows = prepared_rows[-PRICE_LIMIT:]
    return {
        "available": bool(prepared.available),
        "message": (
            "Saved results for this setting loaded."
            if prepared.available else prepared.reason or "No price chart was saved for this run."
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
        "equity": [
            {**row, "timestamp": eastern_plot_timestamp(row["timestamp"])}
            for row in equity[-EQUITY_LIMIT:] if row.get("timestamp")
        ],
        "metrics": metrics_document.get("metrics") or {},
        "sessions": sessions,
        "selected_session": selected_session,
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


def _oos_metric_fields(database: Path, run: dict[str, Any]) -> list[dict[str, str]]:
    if run.get("stage") != "oos":
        return []
    metrics = oos_report_metrics(database=database, run_id=run["run_id"]) or {}
    names = ("total_return", "annualized_return", "sharpe_ratio", "max_drawdown", "number_of_trades", "win_rate")
    return [
        {"label": name.replace("_", " ").title(), "value": format_metric(name, metrics[name])}
        for name in names if metrics.get(name) is not None
    ]


def oos_chart_target(*, database: Path, run_id: str | None) -> dict[str, Any] | None:
    """The first-check setting an unseen-data run traded, and its test dates, so the chart can be rebuilt."""
    if not run_id:
        return None
    report = _artifact_document(database=database, run_id=run_id, logical_name=OOS_REPORT_LOGICAL_NAME)
    shortlist = (report or {}).get("shortlist_parameters")
    test = ((report or {}).get("split") or {}).get("test") or {}
    connection, _error = _validated_connection(database)
    if connection is None or not shortlist or not test.get("start") or not test.get("end"):
        return None
    try:
        source = connection.execute(
            "SELECT json_extract(environment_json, '$.filter_handoff.source_run_id') FROM experiment_runs WHERE run_id=?",
            [run_id],
        ).fetchone()
        if not source or not source[0]:
            return None
        for row in connection.execute(
            "SELECT row_id, normalized_parameters_json FROM parameter_results WHERE run_id=?", [source[0]]
        ):
            if json.loads(row["normalized_parameters_json"]) == shortlist[0]:
                return {"source_run_id": source[0], "row_id": row["row_id"], "start": test["start"], "end": test["end"]}
    except (sqlite3.Error, ValueError, TypeError):
        return None
    finally:
        connection.close()
    return None


def _with_profit_factor(metrics: list[dict[str, str]], pnls: list[Any]) -> list[dict[str, str]]:
    """Add Profit Factor from the trades shown when the run did not record one."""
    if any(item["label"] == "Profit Factor" and item["value"] != "—" for item in metrics):
        return metrics
    factor = profit_factor(pnls)
    if factor is None:
        return metrics
    return [item for item in metrics if item["label"] != "Profit Factor"] + [{"label": "Profit Factor", "value": f"{factor:.2f}"}]


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
        return {"available": False, "message": "No saved test run is available.", "runs": []}
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
                "timestamp": eastern_plot_timestamp(bar.timestamp), "open": bar.open, "high": bar.high,
                "low": bar.low, "close": bar.close, "source_count": bar.source_count,
            }
            for bar in prepared.bars[-PRICE_LIMIT:]
        ] if prepared.available else []
        grouped = group_trade_rows(evidence.trades)
        trades = [
            _trade_row(group)
            for group in grouped.groups[:TRADE_LIMIT]
        ]
        equity = [
            {**dict(row), "timestamp": eastern_plot_timestamp(row["timestamp"])}
            for row in evidence.equity_curve[-EQUITY_LIMIT:] if row.get("timestamp")
        ]
        equity_from_saved_trades = not equity and bool(grouped.groups) and _saved_initial_cash(detail) is not None
        if equity_from_saved_trades:  # no saved curve: rebuild it from every saved trade
            equity = equity_from_trades([_trade_row(group) for group in grouped.groups], starting_cash=_saved_initial_cash(detail))[-EQUITY_LIMIT:]
        return {
            "available": True,
            "message": "Saved results for this run loaded.",
            "run": run,
            "runs": runs,
            "metrics": _with_profit_factor(
                _fields(evidence.metrics) or _oos_metric_fields(database_path, run),
                [group.pnl for group in grouped.groups],
            ),
            "oos_chart": oos_chart_target(database=database_path, run_id=run["run_id"]) if run.get("stage") == "oos" else None,
            "trades": trades,
            "trade_count": len(grouped.groups),
            "trade_limit": TRADE_LIMIT,
            "price": price,
            "price_available": prepared.available,
            "price_reason": prepared.reason,
            "source_interval": evidence.source_interval,
            "interval": interval,
            "equity": equity,
            "equity_from_trades": equity_from_saved_trades,
            "drawdown": [
                {**dict(row), "timestamp": eastern_plot_timestamp(row["timestamp"])}
                for row in evidence.drawdown_curve[-EQUITY_LIMIT:] if row.get("timestamp")
            ],
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
            "message": "Saved results for this run could not be loaded.",
            "run": run,
            "runs": runs,
            "screening_rows": screening_rows,
            "screening_count": len(screening_rows),
            "screened_out_count": sum(row["screening_status"] == "screened_out" for row in screening_rows),
        }


__all__ = [
    "list_results_runs", "equity_from_trades", "load_screening_configuration_trades", "list_screening_configuration_sessions", "load_session_price",
    "load_results_record", "load_screening_configuration_evidence",
]
