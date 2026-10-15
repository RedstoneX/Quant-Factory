"""Read-only projection of the recorded scores (rolling test, stress test, luck, overfitting).

Values are read from persisted evidence artifacts. The only arithmetic is the
share of profitable folds and the mean fold Sharpe, plain summaries of the fold
results already stored in the rolling-test evidence.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from dashboard.overview_projection import BASE_CTE, _base_params, _validated_connection, configured_database_path
from dashboard.results_projection import _artifact_document

SHORTLIST_LIMIT = 200
STRESS_STAGES = ("robustness", "monte_carlo")
EMPTY_SCORES: dict[str, Any] = {
    "folds_total": None, "folds_profitable": None, "folds_share": None, "fold_sharpe": None,
    "rolling_status": None, "stress_status": None, "luck": None, "overfitting": None,
}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value else None


def _evidence(database: Path, connection: sqlite3.Connection, configuration_id: str, stage: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT run_id FROM experiment_runs WHERE configuration_id=? AND stage=? AND status='succeeded' "
        "ORDER BY created_at DESC, run_id DESC LIMIT 1", (configuration_id, stage),
    ).fetchone()
    document = _artifact_document(database=database, run_id=str(row[0]), logical_name=f"{stage}_evidence") if row else None
    return (document or {}).get("evidence") or None


def _status(evidence: dict[str, Any] | None) -> str | None:
    status = ((evidence or {}).get("normalized_evidence") or {}).get("status")
    return str(status) if status else None


def _scores(database: Path, connection: sqlite3.Connection, configuration_id: str | None) -> dict[str, Any]:
    scores = dict(EMPTY_SCORES)
    if not configuration_id:
        return scores
    try:
        rolling = _evidence(database, connection, configuration_id, "walk_forward")
        if rolling:
            folds = [f for f in rolling.get("folds") or [] if f.get("test_metrics")]
            returns = [v for v in (_number(f["test_metrics"].get("total_return")) for f in folds) if v is not None]
            sharpes = [v for v in (_number(f["test_metrics"].get("sharpe_ratio")) for f in folds) if v is not None]
            total = len(rolling.get("folds") or [])
            scores.update(
                folds_total=total, rolling_status=_status(rolling),
                folds_profitable=sum(v > 0 for v in returns) if returns else None,
                folds_share=sum(v > 0 for v in returns) / total if returns and total else None,
                fold_sharpe=sum(sharpes) / len(sharpes) if sharpes else None,
            )
            overfit = rolling.get("idea_overfitting") or {}
            scores["luck"] = _number((overfit.get("deflated_sharpe") or {}).get("probability"))
            scores["overfitting"] = _number((overfit.get("overfitting_pbo") or {}).get("probability"))
        statuses = [s for s in (_status(_evidence(database, connection, configuration_id, stage)) for stage in STRESS_STAGES) if s]
        scores["stress_status"] = ("failed" if "failed" in statuses else "passed" if "passed" in statuses else statuses[0]) if statuses else None
    except (sqlite3.Error, ValueError, TypeError, KeyError, AttributeError):
        return dict(EMPTY_SCORES)
    return scores


def load_run_scores(run_id: str | None, *, database: str | Path | None = None) -> dict[str, Any]:
    """Scores for the idea that a Results run belongs to."""
    database_path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(database_path)
    if connection is None or not run_id:
        return dict(EMPTY_SCORES)
    try:
        row = connection.execute("SELECT configuration_id FROM experiment_runs WHERE run_id=?", (run_id,)).fetchone()
        return _scores(database_path, connection, row[0] if row else None)
    except sqlite3.Error:
        return dict(EMPTY_SCORES)
    finally:
        connection.close()


def load_shortlist(*, database: str | Path | None = None) -> list[dict[str, Any]]:
    """Ideas that cleared the costs screen and the unseen-data test, best unseen-data Sharpe first."""
    database_path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(database_path)
    if connection is None:
        return []
    try:
        rows = connection.execute(
            BASE_CTE + " SELECT candidate_id, title, symbol, configuration_id, run_id, "
            "CAST(json_extract(oos_metrics_json,'$.sharpe_ratio') AS REAL) AS sharpe "
            "FROM candidates WHERE oos_metrics_json IS NOT NULL AND configuration_id IS NOT NULL "
            "ORDER BY sharpe DESC, candidate_id LIMIT ?", _base_params() + [SHORTLIST_LIMIT],
        ).fetchall()
        return [
            {"candidate_id": str(r["candidate_id"]), "title": str(r["title"] or "Untitled idea"), "symbol": str(r["symbol"] or ""),
             "run_id": r["run_id"], "rank": index + 1, "sharpe": _number(r["sharpe"]),
             **_scores(database_path, connection, str(r["configuration_id"]))}
            for index, r in enumerate(rows)
        ]
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def load_waiting_for_you(*, database: str | Path | None = None) -> dict[str, int]:
    """Counts of ideas that wait on an owner step (campaign state survivor / exception_hold)."""
    database_path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(database_path)
    if connection is None:
        return {"review": 0, "decision": 0}
    try:
        rows = connection.execute(
            "SELECT state, COUNT(*) FROM qf_campaign_admissions WHERE state IN ('survivor','exception_hold') GROUP BY state"
        ).fetchall()
        found = {str(state): int(count) for state, count in rows}
        return {"review": found.get("survivor", 0), "decision": found.get("exception_hold", 0)}
    except sqlite3.Error:
        return {"review": 0, "decision": 0}
    finally:
        connection.close()


def waiting_banner_text(counts: dict[str, int]) -> str | None:
    parts = []
    if counts.get("review"):
        n = counts["review"]
        parts.append(f"{n:,} idea{'s' if n != 1 else ''} passed every test and need{'s' if n == 1 else ''} your review")
    if counts.get("decision"):
        n = counts["decision"]
        parts.append(f"{n:,} idea{'s' if n != 1 else ''} on hold for your decision")
    return "Waiting for you: " + "; ".join(parts) if parts else None


__all__ = ["load_run_scores", "load_shortlist", "load_waiting_for_you", "waiting_banner_text"]
