"""Read-only projection for the Results workbench: one row per idea (or per setting tried), from stored results only.

Reuses the idea report's words, statuses and test labels; the per-idea test outcomes come from the same stored
runs and evidence the report reads. Nothing is invented: a figure the run did not save is left out, not filled in.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from dashboard.idea_report_projection import CANT_TEST, gates_chip, CLOSE_CALL, STATUS_TONE, TEST_LABELS, apply_campaign_verdict, campaign_row, report_status
from dashboard.idea_results_projection import STAGES, TRADE_STAGES, _check_name, _check_value, _evidence, _stage_runs, _test_card
from dashboard.overview_projection import TEST_TITLE_PATTERNS, _validated_connection, configured_database_path

STAGE_NAMES = [stage for stage, _label in STAGES]
# Submissions that only exercised the plumbing, not an idea: the shared throwaway-title patterns plus these notes in the attribution.
TEST_ATTRIBUTION_MARKERS = ("connection test", "test only", "usability test")
INTERVALS = {"1m": "1 min", "5m": "5 min", "15m": "15 min", "30m": "30 min", "60m": "60 min", "1h": "60 min", "1d": "daily"}
AT_MOST = ("maximum_", "worst_")  # checks where lower is better


def is_real_idea(title: str | None, attribution: str | None) -> bool:
    """True for an idea submitted by an agent or the owner; false for fixtures and connection or usability tests."""
    name, source = (title or "").strip().lower(), (attribution or "").lower()
    if any(name.startswith(pattern.rstrip("%")) for pattern in TEST_TITLE_PATTERNS):
        return False
    return not any(marker in source for marker in TEST_ATTRIBUTION_MARKERS)


def five_dots(statuses: list[str]) -> list[str]:
    """One tone per test, in test order: green passed, amber close call, red failed or crashed, grey not run or cannot test."""
    return [STATUS_TONE[status] for status in statuses]


def setting_text(parameters: dict[str, Any]) -> str:
    return " · ".join(f"{str(key).replace('_', ' ')} {value}" for key, value in parameters.items())


def newest_real_idea(ideas: pd.DataFrame) -> str | None:
    """Candidate id of the newest real idea (the workbench opens on it)."""
    return None if ideas.empty else str(ideas.sort_values("created_at", ascending=False).iloc[0]["candidate_id"])


def _database(database: str | Path | None) -> Path:
    return Path(database) if database is not None else configured_database_path()


def _metrics(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _pct(value: Any) -> float | None:
    return None if value is None else round(float(value) * 100, 2)


def _statuses(database: Path, connection: sqlite3.Connection, configuration_id: str, screening: dict[str, int], candidate_id: str | None = None) -> tuple[list[str], dict[str, Any]]:
    runs = _stage_runs(connection, configuration_id)
    out: list[str] = []
    for stage, label in STAGES:
        card = _test_card(database, stage, label, runs.get(stage), screening)
        stored = card["status"] if card["status"] in ("passed", "failed") else None
        out.append(report_status(stage, stored, (runs.get(stage) or {}).get("status")))
    row = connection.execute("SELECT state, reason_code, reason_detail FROM qf_campaign_admissions WHERE candidate_id=?", [candidate_id]).fetchone() if candidate_id else None
    return apply_campaign_verdict(out, (str(row[0]), str(row[1]), str(row[2] or "")) if row else None), runs


SHORT_STAGE = {"screening": "costs", "oos": "unseen", "walk_forward": "over time", "robustness": "stress", "monte_carlo": "luck"}


def overall_status(statuses: list[str], trades: Any = None, survivor: bool = False) -> str:
    """The one word the grid chip shows: Passed, Close call, Failed: <test>, Can't test, Crashed or No trades (no counts; the report keeps its long form)."""
    if trades is not None and not pd.isna(trades) and trades == 0:
        return "No trades"
    if survivor and gates_chip(statuses):  # scores are not gates: a survivor stays Passed the gates whatever its scores
        return "Passed" if all(status in ("Passed", "Not scored") for status in statuses) else gates_chip(statuses)
    failed = next((SHORT_STAGE[stage] for stage, status in zip(STAGE_NAMES, statuses) if status == "Failed"), None)
    if failed:
        return f"Failed: {failed}"
    if "Crashed" in statuses:
        return "Crashed"
    if "Close call" in statuses:
        return "Close call"
    return "Passed" if all(status == "Passed" for status in statuses) else "Can't test"


def chip_tone(text: str) -> str:
    """green passed, amber close call, red failed or crashed, grey can't test or no trades."""
    return "green" if text == "Passed" else "amber" if text == "Close call" or text.startswith("Passed the gates") else "red" if text.startswith("Failed") or text == "Crashed" else "grey"


def _build(database: Path) -> dict[str, pd.DataFrame]:
    connection, _error = _validated_connection(database)
    if connection is None:
        return {"ideas": pd.DataFrame(), "settings": pd.DataFrame()}
    try:
        heads = connection.execute(
            "SELECT d.draft_id AS candidate_id, COALESCE(json_extract(d.candidate_json, '$.candidate.title'), d.title) AS title, d.created_at, d.attribution, d.configuration_id, "
            "COALESCE(json_extract(d.candidate_json, '$.candidate.family'), 'other') AS family, "
            "COALESCE(json_extract(c.canonical_config_json, '$.market_data.symbol'), json_extract(c.canonical_config_json, '$.market_data.dataset_id'), 'Unrecorded') AS market, "
            "json_extract(c.canonical_config_json, '$.market_data.interval') AS interval, json_extract(c.canonical_config_json, '$.screening.minimum_sharpe_ratio') AS sharpe_line "
            "FROM idea_drafts d JOIN experiment_configurations c ON c.configuration_id=d.configuration_id WHERE d.candidate_json<>'' ORDER BY d.draft_id",
        ).fetchall()
        ideas, settings, seen = [], [], set()
        for head in heads:
            if head["configuration_id"] in seen or not is_real_idea(head["title"], head["attribution"]):
                continue  # one row per idea: the first draft of a configuration, like the idea report
            seen.add(head["configuration_id"])
            rows = []
            runs = _stage_runs(connection, head["configuration_id"])
            if "screening" in runs:
                rows = connection.execute("SELECT row_id, normalized_parameters_json, metrics_json, ranking_position, screening_status FROM parameter_results WHERE run_id=? ORDER BY ranking_position, row_id",
                                          [runs["screening"]["run_id"]]).fetchall()
            screening = {"screening_count": len(rows), "screened_out_count": sum(1 for row in rows if row["screening_status"] == "screened_out")}
            statuses, _ = _statuses(database, connection, head["configuration_id"], screening, head["candidate_id"])
            row = connection.execute("SELECT state FROM qf_campaign_admissions WHERE candidate_id=?", [head["candidate_id"]]).fetchone()
            survivor = bool(row and row[0] == "survivor")
            best = _metrics(rows[0]["metrics_json"]) if rows else {}
            common = {"candidate_id": head["candidate_id"], "title": head["title"], "market": head["market"], "timeframe": INTERVALS.get(head["interval"], head["interval"] or ""),
                      "family": str(head["family"]).replace("_", " ").capitalize(), "sharpe_line": head["sharpe_line"], "created_at": head["created_at"], "result": overall_status(statuses, survivor=survivor), "dots": five_dots(statuses)}
            ideas.append({**common, "sharpe": best.get("sharpe_ratio"), "total_return": _pct(best.get("total_return")), "worst_drop": _pct(best.get("max_drawdown")),
                          "trades": best.get("number_of_trades"), "settings_tried": len(rows)})
            for row in rows:
                metrics = _metrics(row["metrics_json"])
                settings.append({**common, "row_id": f"{head['candidate_id']}:{row['row_id']}", "setting": setting_text(_metrics(row["normalized_parameters_json"])), "sharpe": metrics.get("sharpe_ratio"),
                                 "total_return": _pct(metrics.get("total_return")), "worst_drop": _pct(metrics.get("max_drawdown")), "trades": metrics.get("number_of_trades"),
                                 "kept": row["screening_status"] != "screened_out"})
    except sqlite3.Error:
        return {"ideas": pd.DataFrame(), "settings": pd.DataFrame()}
    finally:
        connection.close()
    return {"ideas": _without_empty_metrics(pd.DataFrame(ideas).sort_values("created_at", ascending=False).reset_index(drop=True)) if ideas else pd.DataFrame(),
            "settings": _without_empty_metrics(pd.DataFrame(settings).sort_values("created_at", ascending=False, kind="stable").reset_index(drop=True)) if settings else pd.DataFrame()}


def _without_empty_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """An idea or setting that made no trades has no Sharpe, return or drop to show: those are cleared so they read as unknown, not as zero."""
    frame.loc[frame["trades"].fillna(0) == 0, ["sharpe", "total_return", "worst_drop"]] = None
    return frame


@lru_cache(maxsize=4)
def _cached(path: str, modified: int) -> dict[str, pd.DataFrame]:
    return _build(Path(path))


def load_workbench(database: str | Path | None = None) -> dict[str, pd.DataFrame]:
    """{'ideas': one row per idea, 'settings': one row per setting tried}, newest first. Cached until the database file changes."""
    path = _database(database)
    return _cached(str(path), path.stat().st_mtime_ns if path.exists() else 0)


def shortfall_items(label: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How far each failed rule fell short: the measured and needed numbers as saved, and a 0-1 bar length (1 = the pass line)."""
    items = []
    for result in results:
        if result.get("status") != "failed" or result.get("observed") is None or result.get("threshold") is None:
            continue
        measured, needed = float(result["observed"]), float(result["threshold"])
        lower_is_better = str(result.get("threshold_id", "")).rpartition(":")[2].startswith(AT_MOST)
        if lower_is_better:
            fraction = abs(needed) / abs(measured) if measured else 1.0
        else:
            fraction = measured / needed if needed > 0 and measured > 0 else 0.0
        items.append({"label": label, "check": _check_name(result["threshold_id"]), "measured": _check_value(result["threshold_id"], measured),
                      "needed": _check_value(result["threshold_id"], needed), "fraction": max(0.0, min(1.0, fraction))})
    return items


def load_shortfall(candidate_id: str, database: str | Path | None = None) -> dict[str, Any] | None:
    """For a close-call idea: the first test that fell short and its failed rules (from the saved evidence). None when it is not a close call."""
    path = _database(database)
    ideas = load_workbench(path)["ideas"]
    row = ideas[ideas["candidate_id"] == candidate_id] if not ideas.empty else ideas
    if row.empty:
        return None
    dots = row.iloc[0]["dots"]
    index = next((i for i, tone in enumerate(dots) if tone == "amber"), None)
    if index is None:
        return None
    stage = STAGE_NAMES[index]
    connection, _error = _validated_connection(path)
    if connection is None:
        return None
    try:
        configuration = connection.execute("SELECT configuration_id FROM idea_drafts WHERE draft_id=?", [candidate_id]).fetchone()
        runs = _stage_runs(connection, configuration[0]) if configuration else {}
    finally:
        connection.close()
    results = ((_evidence(path, (runs.get(stage) or {}).get("run_id"), stage).get("normalized_evidence") or {}).get("threshold_results")) or []
    return {"candidate_id": candidate_id, "title": row.iloc[0]["title"], "stage": stage, "number": index + 1, "label": TEST_LABELS[stage], "items": shortfall_items(TEST_LABELS[stage], results)}


COMPARES = {"equals": "==", "notEqual": "!=", "greaterThan": ">", "greaterThanOrEqual": ">=", "lessThan": "<", "lessThanOrEqual": "<="}


def _mask(column: pd.Series, condition: dict[str, Any]) -> pd.Series:
    kind, value = condition.get("type"), condition.get("filter")
    if condition.get("filterType") == "number":
        if kind == "inRange":
            return column.between(value, condition.get("filterTo"))
        return column.eq(value) if kind == "equals" else column.ne(value) if kind == "notEqual" else column.gt(value) if kind == "greaterThan" else column.ge(value) if kind == "greaterThanOrEqual" else column.lt(value) if kind == "lessThan" else column.le(value)
    text = column.astype(str).str.lower()
    needle = str(value or "").lower()
    return {"contains": text.str.contains(needle, regex=False), "notContains": ~text.str.contains(needle, regex=False), "equals": text.eq(needle),
            "notEqual": text.ne(needle), "startsWith": text.str.startswith(needle), "endsWith": text.str.endswith(needle)}.get(kind, text.str.contains(needle, regex=False))


def page_of_settings(frame: pd.DataFrame, request: dict[str, Any]) -> dict[str, Any]:
    """Answer one AG Grid infinite-row-model request (startRow, endRow, sortModel, filterModel) with a pandas filter, sort and slice."""
    for field, model in (request.get("filterModel") or {}).items():
        if field not in frame:
            continue
        conditions = model.get("conditions") or [model]
        masks = [_mask(frame[field], {**condition, "filterType": condition.get("filterType") or model.get("filterType")}) for condition in conditions]
        frame = frame[pd.concat(masks, axis=1).any(axis=1) if model.get("operator") == "OR" else pd.concat(masks, axis=1).all(axis=1)]
    sorts = [item for item in request.get("sortModel") or [] if item.get("colId") in frame]
    if sorts:
        frame = frame.sort_values([item["colId"] for item in sorts], ascending=[item["sort"] == "asc" for item in sorts], kind="stable")
    start, end = int(request.get("startRow") or 0), int(request.get("endRow") or 100)
    return {"rowData": frame.iloc[start:end].to_dict("records"), "rowCount": len(frame)}


__all__ = ["CANT_TEST", "CLOSE_CALL", "chip_tone", "five_dots", "overall_status", "is_real_idea", "load_shortfall", "load_workbench", "newest_real_idea", "page_of_settings", "setting_text", "shortfall_items"]
