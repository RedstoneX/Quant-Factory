"""Read-only projection for the Today home screen: what needs the owner, the funnel, the scatter and the heatmap.

Everything is computed from the Results workbench's one-row-per-idea frame (which reuses the idea report's statuses and
test labels) plus one count of test runs per day. No number is stored or hard-coded; an empty answer is an empty frame.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from dashboard.idea_report_projection import CLOSE_CALL, PASSED, TEST_LABELS
from dashboard.overview_projection import _validated_connection, configured_database_path
from dashboard.results_workbench_projection import STAGE_NAMES, load_shortfall, load_workbench

SHORT_TO_STAGE = {"costs": "screening", "unseen": "oos", "over time": "walk_forward", "stress": "robustness", "luck": "monte_carlo"}
FUNNEL_LABELS = ["Submitted", *[TEST_LABELS[stage] for stage in STAGE_NAMES]]
CLOSE_CALL_LIMIT = 5


def funnel(ideas: pd.DataFrame) -> list[dict[str, Any]]:
    """How many ideas are still standing after each test, in test order. The two gates are cumulative (an idea counts only if it passed every gate up to it);
    the three scores after them count ideas that cleared both gates and whose own score Passed, so they are counts of scores, not of survivors."""
    total = len(ideas)
    standing = pd.Series(True, index=ideas.index)
    steps = [{"label": FUNNEL_LABELS[0], "count": total, "share": 1.0 if total else 0.0}]
    for index, label in enumerate(FUNNEL_LABELS[1:]):
        passed = ideas["dots"].map(lambda tones, i=index: tones[i] == "green")
        if index < 2:
            standing = standing & passed
        count = int(standing.sum()) if index < 2 else int((standing & passed).sum())
        steps.append({"label": label, "count": count, "share": count / total if total else 0.0})
    return steps


def biggest_failure(ideas: pd.DataFrame) -> dict[str, Any] | None:
    """The test that failed the most ideas outright (red 'Failed: <test>' results), with its count; None when nothing failed."""
    failed = ideas["result"][ideas["result"].str.startswith("Failed: ")].str.removeprefix("Failed: ") if not ideas.empty else pd.Series(dtype=str)
    if failed.empty:
        return None
    counts = failed.value_counts()
    return {"label": TEST_LABELS[SHORT_TO_STAGE[counts.index[0]]], "count": int(counts.iloc[0]), "total": len(ideas)}


def needs_owner(ideas: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Passed ideas awaiting a call, and close calls; each best Sharpe first (ideas with no Sharpe last)."""
    if ideas.empty:
        return {"passed": ideas, "close": ideas}
    ranked = ideas.sort_values("sharpe", ascending=False, na_position="last", kind="stable")
    return {"passed": ranked[ranked["result"].str.startswith(PASSED)], "close": ranked[ranked["result"] == CLOSE_CALL]}


def best_idea(ideas: pd.DataFrame) -> str | None:
    """Candidate id of the best idea: the passed idea with the highest Sharpe, else the best close call, else the highest Sharpe of any idea, else None."""
    waiting = needs_owner(ideas)
    for key in ("passed", "close"):
        if not waiting[key].empty:
            return str(waiting[key].iloc[0]["candidate_id"])
    scored = ideas.dropna(subset=["sharpe"]) if not ideas.empty else ideas
    return None if scored.empty else str(scored.sort_values("sharpe", ascending=False, kind="stable").iloc[0]["candidate_id"])


def scatter_points(ideas: pd.DataFrame) -> pd.DataFrame:
    """Every idea that made trades (zero-trade ideas left out): return and worst drop, with its result for colour."""
    if ideas.empty:
        return ideas
    made = ideas[ideas["result"] != "No trades"].dropna(subset=["total_return", "worst_drop"])
    return made[["candidate_id", "title", "total_return", "worst_drop", "result"]]


def heatmap(ideas: pd.DataFrame) -> pd.DataFrame:
    """Best Sharpe by market (rows) and strategy type (columns) over ideas that have a Sharpe (pandas pivot_table, max)."""
    scored = ideas.dropna(subset=["sharpe"]) if not ideas.empty else ideas
    return pd.DataFrame() if scored.empty else scored.pivot_table(index="market", columns="family", values="sharpe", aggfunc="max")


def close_calls(ideas: pd.DataFrame, database: str | Path | None = None, limit: int = CLOSE_CALL_LIMIT) -> list[dict[str, Any]]:
    """The best few close calls with the first test they missed and how far short (the saved shortfall of the first failed rule)."""
    rows = []
    for row in needs_owner(ideas)["close"].head(limit).to_dict("records"):
        shortfall = load_shortfall(row["candidate_id"], database) or {}
        item = (shortfall.get("items") or [None])[0]
        rows.append({"candidate_id": row["candidate_id"], "title": row["title"], "step": shortfall.get("label", ""), "check": (item or {}).get("check", ""),
                     "measured": (item or {}).get("measured", ""), "needed": (item or {}).get("needed", ""), "fraction": (item or {}).get("fraction")})
    return rows


def tests_per_day(database: str | Path | None = None, days: int = 14, today: pd.Timestamp | None = None) -> pd.Series:
    """Test runs started per calendar day (UTC) over the last `days` days, zero-filled; empty when the database has no runs in the window."""
    path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(path)
    if connection is None:
        return pd.Series(dtype=int)
    try:
        stamps = pd.to_datetime([row[0] for row in connection.execute("SELECT created_at FROM experiment_runs WHERE created_at IS NOT NULL")], utc=True, errors="coerce")
    except sqlite3.Error:
        return pd.Series(dtype=int)
    finally:
        connection.close()
    return daily_counts(stamps, days, today)


def daily_counts(stamps: pd.DatetimeIndex, days: int = 14, today: pd.Timestamp | None = None) -> pd.Series:
    """Count timestamps per UTC calendar day over the last `days` days (pandas groupby + reindex), zero-filled; empty when none fall in the window."""
    end = (today if today is not None else pd.Timestamp.now(tz="UTC")).normalize()
    window = pd.date_range(end - pd.Timedelta(days=days - 1), end, freq="D", tz="UTC")
    counts = pd.Series(1, index=stamps.dropna().normalize()).groupby(level=0).sum()
    series = counts.reindex(window, fill_value=0).astype(int)
    return series if series.sum() else pd.Series(dtype=int)


def load_today(database: str | Path | None = None) -> dict[str, Any]:
    """Everything the Today page draws."""
    ideas = load_workbench(database)["ideas"]
    return {"ideas": ideas, "funnel": funnel(ideas) if not ideas.empty else [], "failure": biggest_failure(ideas), "waiting": needs_owner(ideas), "best": best_idea(ideas),
            "scatter": scatter_points(ideas), "heatmap": heatmap(ideas), "close_calls": close_calls(ideas, database), "per_day": tests_per_day(database)}


__all__ = ["best_idea", "biggest_failure", "close_calls", "daily_counts", "funnel", "heatmap", "load_today", "needs_owner", "scatter_points", "tests_per_day"]
