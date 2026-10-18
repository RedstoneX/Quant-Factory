"""Read-only projection for the one-page "Idea report" (every idea, including failed and never-run ones).

A thin layer over the existing per-idea loaders: it renames the five tests, maps stored outcomes onto the
five agreed statuses, and reshapes stored account value, trades and settings with pandas. Nothing is invented:
a number the run did not save is reported as "not saved for this run", never as a dash or a made-up value.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from dashboard.idea_results_projection import (
    STAGES, TRADE_STAGES, load_idea, load_period_price, load_stage_detail, load_trade_view,
)
from dashboard.overview_projection import _validated_connection, configured_database_path
from dashboard.results_projection import oos_report_metrics

TEST_LABELS = {"screening": "Survives costs", "oos": "Unseen data", "walk_forward": "Holds over time", "robustness": "Stress test", "monte_carlo": "Luck test"}
PASSED, CLOSE_CALL, FAILED, CANT_TEST, CRASHED = "Passed", "Close call", "Failed", "Can't test", "Crashed"
STATUS_TONE = {PASSED: "green", CLOSE_CALL: "amber", FAILED: "red", CANT_TEST: "grey", CRASHED: "red"}
NOT_SAVED = "Not saved for this run."


def report_status(stage: str, stored_status: str | None, run_status: str | None) -> str:
    """One of the five agreed words for a test.

    Only the costs and unseen-data tests are pass marks; a weak score on the other three is a close call.
    A run that ended in failure without saving a verdict crashed; no run, or too little evidence, cannot be tested.
    """
    if stored_status == "passed":
        return PASSED
    if stored_status == "failed":
        return FAILED if stage in TRADE_STAGES else CLOSE_CALL
    if run_status == "failed":
        return CRASHED
    return CANT_TEST


def never_ran_card(idea: dict[str, Any], tests: list[dict[str, Any]]) -> dict[str, str]:
    """Why no account-value history exists, and the one thing to do about it (from stored run states only)."""
    states = {test["run_status"] for test in tests if test["run_status"]}
    if not states:
        return {"reason": "This idea was saved, but no test has been started for it.", "fix": "Send it for testing from New idea."}
    if "running" in states:
        return {"reason": "The first test is still running, so there is no history to draw yet.", "fix": "Check back when it finishes."}
    if "failed" in states and "succeeded" not in states:
        return {"reason": "The first test crashed before it saved any result.", "fix": "Test it again; if it crashes again the run log says why."}
    return {"reason": "The test finished but did not save an account-value history.", "fix": "Test it again so the history is saved."}


def _database(database: str | Path | None) -> Path:
    return Path(database) if database is not None else configured_database_path()


def _draft_head(database: Path, candidate_id: str | None) -> dict[str, Any]:
    """Title of an idea that has no test configuration yet."""
    connection, _error = _validated_connection(database)
    if connection is None or not candidate_id:
        return {}
    try:
        row = connection.execute(
            "SELECT COALESCE(json_extract(candidate_json, '$.candidate.title'), title) AS title FROM idea_drafts WHERE draft_id=?", [candidate_id],
        ).fetchone()
        return {"title": row["title"]} if row and row["title"] else {}
    except sqlite3.Error:
        return {}
    finally:
        connection.close()


def _tested_label(database: Path, run_id: str | None) -> str | None:
    connection, _error = _validated_connection(database)
    if connection is None or not run_id:
        return None
    try:
        row = connection.execute("SELECT created_at FROM experiment_runs WHERE run_id=?", [run_id]).fetchone()
        local = pd.Timestamp(row["created_at"]).tz_convert("America/New_York") if row and row["created_at"] else None
        return f"Tested {local.day} {local:%b}, {local.hour % 12 or 12}:{local:%M %p} ET" if local is not None else None
    except (sqlite3.Error, ValueError, TypeError):
        return None
    finally:
        connection.close()


def _series(rows: list[dict[str, Any]]) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(rows)
    return pd.Series(frame["value"].astype(float).to_numpy(), index=pd.to_datetime(frame["timestamp"]), dtype=float).sort_index()


def hero_series(screening_equity: list[dict[str, Any]], unseen_equity: list[dict[str, Any]]) -> dict[str, pd.Series]:
    """Built-on account value up to where the unseen period begins, then the unseen period joined on to it.

    The unseen test saves its own account value from its own start; it is scaled to continue from the last
    built-on value so the two read as one line. With no unseen history everything is built-on.
    """
    whole, unseen = _series(screening_equity), _series(unseen_equity)
    if unseen.empty:
        return {"built": whole, "unseen": unseen}
    built = whole[whole.index < unseen.index[0]]
    if built.empty:
        return {"built": built, "unseen": unseen}
    return {"built": built, "unseen": unseen / unseen.iloc[0] * built.iloc[-1]}


def drawdown(values: pd.Series) -> pd.Series:
    """Percent below the running peak (pandas cummax)."""
    return (values / values.cummax() - 1) * 100 if not values.empty else values


def monthly_returns(values: pd.Series) -> pd.DataFrame:
    """Percent change per calendar month, years down and months across (pandas resample + pivot)."""
    if values.empty:
        return pd.DataFrame()
    month_end = values.resample("ME").last()
    change = (month_end.pct_change().fillna(month_end / values.iloc[0] - 1) * 100).rename("pct")
    frame = change.to_frame().assign(year=change.index.year, month=change.index.month)
    return frame.pivot(index="year", columns="month", values="pct").reindex(columns=range(1, 13))


def settings_grid(rows: list[dict[str, Any]], chosen_row_id: str | None) -> dict[str, Any] | None:
    """Sharpe after costs for every setting tried, laid out on the first two settings that varied."""
    if not rows:
        return None
    frame = pd.DataFrame([{**{key: str(value) for key, value in (row.get("parameters") or {}).items()}, "sharpe": row.get("sharpe_ratio"), "row_id": row.get("row_id")} for row in rows])
    names = [name for name in frame.columns if name not in ("sharpe", "row_id") and frame[name].nunique() > 1] or [name for name in frame.columns if name not in ("sharpe", "row_id")][:1]
    if not names:
        return None
    down, across = (names[0], names[1]) if len(names) > 1 else (names[0], None)
    frame["across"] = frame[across] if across else "all"
    table = frame.pivot_table(index=down, columns="across", values="sharpe", aggfunc="mean")
    chosen = frame[frame["row_id"] == chosen_row_id]
    return {"down": down, "across": across or "", "rows": list(table.index), "columns": list(table.columns), "values": table.where(table.notna(), None).to_numpy().tolist(),
            "chosen": (str(chosen.iloc[0][down]), str(chosen.iloc[0]["across"])) if not chosen.empty else None, "count": len(frame)}


def _test_measure(stage: str, test: dict[str, Any], idea: dict[str, Any], detail: dict[str, Any], database: Path, built_return: float | None) -> dict[str, Any]:
    """The value shown on a test's bar, the bar's length and its pass line (None when no line was saved)."""
    out: dict[str, Any] = {"value": NOT_SAVED if test["run_id"] else "Not run", "fraction": None, "pass_line": None}
    if not test["run_id"]:
        return out
    if stage == "screening":
        total, survivors = int(idea.get("screening_count") or 0), int(idea.get("screening_count") or 0) - int(idea.get("screened_out_count") or 0)
        if total:
            out.update(value=f"{survivors:,} of {total:,} settings", fraction=survivors / total, pass_line=1 / total)
    elif stage == "oos":
        value = (oos_report_metrics(database=database, run_id=test["run_id"]) or {}).get("total_return")
        if value is not None:
            scale = max(abs(float(value)), abs(built_return or 0.0)) or 1.0  # both stored: unseen return and built-on return share one scale
            out.update(value=f"{float(value) * 100:+.1f}%", fraction=0.5 + float(value) / (2 * scale), pass_line=0.5)
    elif stage == "walk_forward":
        periods = detail["periods"]
        if periods:
            made = sum(1 for period in periods if (period["net_return"] or 0) > 0)
            out.update(value=f"{made} of {len(periods)} windows", fraction=made / len(periods))
    else:
        checks = detail["checks"]
        if checks:
            passed = sum(1 for check in checks if check["result"] == "Passed")
            out.update(value=f"{passed} of {len(checks)} checks", fraction=passed / len(checks), pass_line=1.0)
    return out


def load_report(candidate_id: str | None = None, *, run_id: str | None = None, database: str | Path | None = None) -> dict[str, Any]:
    """Everything one idea's report page draws, from stored results only."""
    path = _database(database)
    idea = load_idea(candidate_id, run_id=run_id, database=path)
    if not idea.get("available"):
        head = _draft_head(path, candidate_id)
        if not head:
            return {"available": False, "message": idea.get("message") or "This idea was not found."}
        idea = {**idea, "title": head["title"], "symbol": "", "tests": [], "runs": {}}
    runs = idea.get("runs") or {}
    tests = []
    for stage, _old_label in STAGES:
        stored = next((test for test in idea.get("tests") or [] if test["stage"] == stage), {})
        run = runs.get(stage) or {}
        detail = load_stage_detail(idea, stage, database=path) if stage in ("walk_forward", "robustness", "monte_carlo") and run else {"periods": [], "checks": []}
        stored_status = stored.get("status") if stored.get("status") in ("passed", "failed") else None
        tests.append({"stage": stage, "label": TEST_LABELS[stage], "run_id": run.get("run_id"), "run_status": run.get("status"),
                      "status": report_status(stage, stored_status, run.get("status")), "line": stored.get("line") or "This test has not run for this idea yet.", "detail": detail})
    screening_view = load_trade_view(idea, "screening", database=path) if "screening" in runs else {"available": False}
    unseen_view = load_trade_view(idea, "oos", database=path) if "oos" in runs else {"available": False}
    screening_equity = screening_view.get("equity") or [] if screening_view.get("available") else []
    unseen_equity = unseen_view.get("equity") or [] if unseen_view.get("available") else []
    series = hero_series(screening_equity, unseen_equity)
    whole = pd.concat([part for part in (series["built"], series["unseen"]) if not part.empty]) if not (series["built"].empty and series["unseen"].empty) else series["built"]
    built_return = float(series["built"].iloc[-1] / series["built"].iloc[0] - 1) if len(series["built"]) > 1 else None
    for test in tests:
        test.update(_test_measure(test["stage"], test, idea, test["detail"], path, built_return))
    hold = pd.Series(dtype=float)
    if not whole.empty and "screening" in runs:  # buy and hold from the saved price bars, started with the same money
        bars = pd.DataFrame(load_period_price(runs["screening"]["run_id"], None, database=path)["price"])
        if not bars.empty:
            close = pd.Series(bars["close"].astype(float).to_numpy(), index=pd.to_datetime(bars["timestamp"]))
            close = close[(close.index >= whole.index[0]) & (close.index <= whole.index[-1])]
            hold = close / close.iloc[0] * whole.iloc[0] if not close.empty else close
    trades = (screening_view.get("trades") if screening_view.get("available") else None) or (unseen_view.get("trades") if unseen_view.get("available") else None) or []
    has_chart = not whole.empty
    passed = sum(1 for test in tests if test["status"] == PASSED)
    failed_gate = next((test for test in tests if test["stage"] in TRADE_STAGES and test["status"] == FAILED), None)
    performance = ((unseen_view.get("performance") if unseen_equity else None) or screening_view.get("performance") or {}).get("performance", {}).get("all") or {}
    rows = idea.get("screening_rows") or []
    return {
        "available": True, "title": idea["title"], "symbol": idea.get("symbol") or "", "candidate_id": idea.get("candidate_id") or candidate_id,
        "verdict": f"Failed at: {failed_gate['label'].lower()}" if failed_gate else f"Passed {passed} of {len(tests)}", "verdict_tone": "red" if failed_gate else "green" if passed == len(tests) else "grey",
        "tested": _tested_label(path, (runs.get("screening") or {}).get("run_id")), "tests": tests,
        "hero": {"kind": "chart" if has_chart else "never_ran", **({} if has_chart else never_ran_card(idea, tests)),
                 "built": series["built"], "unseen": series["unseen"], "hold": hold, "drawdown": drawdown(whole), "unseen_label_note": "" if unseen_equity else NOT_SAVED},
        "performance": performance, "sharpe": next((row.get("sharpe_ratio") for row in rows if row.get("row_id") == screening_view.get("row_id")), None),
        "unseen_return": next((test for test in tests if test["stage"] == "oos"), {}).get("value"),
        "monthly": monthly_returns(whole), "trades": trades, "unseen_trades_saved": bool(unseen_view.get("trades")) if unseen_view.get("available") else False,
        "pnl": [float(trade["pnl"]) for trade in trades if trade.get("pnl") is not None],
        "grid": settings_grid(rows, screening_view.get("row_id")),
    }


__all__ = ["CANT_TEST", "CLOSE_CALL", "CRASHED", "FAILED", "NOT_SAVED", "PASSED", "STATUS_TONE", "TEST_LABELS", "drawdown", "hero_series", "load_report",
           "monthly_returns", "never_ran_card", "report_status", "settings_grid"]
