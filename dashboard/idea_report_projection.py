"""Read-only projection for the one-page "Idea report" (every idea, including failed and never-run ones).

A thin layer over the existing per-idea loaders: it renames the five tests, maps stored outcomes onto the
five agreed statuses, and reshapes stored account value, trades and settings with pandas. Nothing is invented:
a number the run did not save is reported as "not saved for this run", never as a dash or a made-up value.
"""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any

import pandas as pd

from dashboard.idea_results_projection import (
    STAGES, TRADE_STAGES, load_idea, load_period_price, load_stage_detail, load_trade_view, shuffle_result_line,
)
from dashboard.overview_projection import _validated_connection, configured_database_path
from dashboard.score_projection import load_run_scores
from dashboard.plain_labels import OUR_SIDE_WORDS, is_our_side_mismatch, plain_unseen_reason, unseen_loss_text
from dashboard.results_model import ResultsDataError
from dashboard.results_projection import oos_report_metrics

UNSEEN_RULE = "Passes if it made money on years it never saw, after costs"  # owner ruling 19 Oct 2026
SHUFFLE_RULE = "Passes if shuffled trades still made money"  # the Shuffle test (stage 5) rule; the card's line below it carries the measured numbers
RULES = {  # one "Passes if…" line per test, so every card reads the same way (design review 21 Oct 2026)
    "screening": "Passes if at least one setting clears the cost screen: enough trades and enough return after costs",
    "oos": UNSEEN_RULE,
    "walk_forward": "Passes if it kept making money window by window on rolling periods",
    "robustness": "Passes if every stress check holds: nearby settings and worse costs",
    "monte_carlo": SHUFFLE_RULE,
}


UNSAVED_UNSEEN_NOTE = "The unseen-period chart and trades weren't saved for this run; its result is in test 2 below."


def _slice_score(name: str, metrics: dict[str, Any]) -> tuple[str, str | None]:
    """One recorded-score line for a slice: its name, and its Sharpe after costs as text (a score, not a gate), or None when not saved."""
    sharpe = metrics.get("sharpe_ratio")
    return name, None if sharpe is None else f"{float(sharpe):.2f}"


TEST_LABELS = {"screening": "Survives costs", "oos": "Unseen data", "walk_forward": "Holds over time", "robustness": "Stress test", "monte_carlo": "Shuffle test"}
PASSED, CLOSE_CALL, FAILED, CANT_TEST, CRASHED = "Passed", "Close call", "Failed", "Can't test", "Crashed"
NOT_SCORED = "Not scored"  # a score stage of a gateway survivor with no usable result; shown in the grey Can't test style
STATUS_TONE = {PASSED: "green", CLOSE_CALL: "amber", FAILED: "red", CANT_TEST: "grey", CRASHED: "red", NOT_SCORED: "grey"}
NOT_SAVED = "Not saved for this run."
GATES_CHIP = ("Passed the gates", "green")
TOO_FEW_WINDOWS = "Too few windows"  # log wording only; never a stage status on the Report
NOT_ENOUGH = "Not scored — not enough data"  # the one phrase for an unscored Shuffle test, everywhere
SCORE_STAGES = ("walk_forward", "robustness", "monte_carlo")


def report_status(stage: str, stored_status: str | None, run_status: str | None) -> str:
    """One of the five agreed words for a test.

    The recorded normalized status wins: a recorded "failed" is Failed on every test, never upgraded to a close call.
    A run that ended in failure without saving a verdict crashed; no run, or too little evidence, cannot be tested.
    """
    if stored_status == "passed":
        return PASSED
    if stored_status == "failed":
        return FAILED
    if run_status == "failed":
        return CRASHED
    return CANT_TEST


_NEEDS = re.compile(r"Needs at least (?P<needed>\d+)\D.*?had (?P<had>\d+)", re.S)


def too_few_phrase(line: Any) -> str:
    """The one phrase for an unscored Shuffle test, from the recorded numbers: 'Not scored — not enough data (5 of 10 needed)'."""
    found = _NEEDS.search(str(line or ""))
    return NOT_ENOUGH + (f" ({found['had']} of {found['needed']} needed)" if found else "")


def score_statuses(candidate_id: str | None, database: str | Path | None = None, run_id: str | None = None) -> dict[str, str]:
    """The Report page's status word for the three recorded scores (Holds over time, Stress test, Shuffle test), from the same stored stage results the Report reads; {} when none are available.
    `run_id` (a screening run) scopes it to that test's stage runs, as the Report does; a Shuffle test with too few results gets the too_few_phrase."""
    idea = load_idea(candidate_id, run_id=run_id, database=_database(database))
    if not idea.get("available"):
        return {}
    runs = idea.get("runs") or {}
    out = {}
    for stage in ("walk_forward", "robustness", "monte_carlo"):
        stored = next((test for test in idea.get("tests") or [] if test["stage"] == stage), {})
        stored_status = stored.get("status") if stored.get("status") in ("passed", "failed") else None
        out[stage] = report_status(stage, stored_status, (runs.get(stage) or {}).get("status"))
        if stage == "monte_carlo" and stored.get("status") == "insufficient_evidence" and str(stored.get("line") or "").startswith("Needs at least"):
            out[stage] = too_few_phrase(stored.get("line"))  # the recorded Monte Carlo reason: too few observations to shuffle (PR 287)
    return out


def campaign_row(database: Path, candidate_id: str | None) -> tuple[str, str, str] | None:
    """The factory's latest verdict for an idea: (state, reason_code, reason_detail) from the campaign events (the read-only qf_campaign_admissions table); None when it has none."""
    connection, _error = _validated_connection(database)
    if connection is None or not candidate_id:
        return None
    try:
        row = connection.execute("SELECT state, reason_code, reason_detail FROM qf_campaign_admissions WHERE candidate_id=?", [candidate_id]).fetchone()
        return (str(row[0]), str(row[1]), str(row[2] or "")) if row else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def apply_campaign_verdict(statuses: list[str], row: tuple[str, ...] | None) -> list[str]:
    """Five test statuses, overridden by the factory's own verdict when it has one.

    screened_out at a test: the tests before it Passed, that test Failed, the rest Can't test. survivor: each gate Passed unless a result is recorded for it (the recorded result stands), the three scores keep their own status (Not scored when none).
    screened_out because our own settings did not match (plain_labels.is_our_side_mismatch): that test and the rest Can't test, never Failed.
    failed (run_error): no card is painted Crashed (each card crashes only from its own stage run; the header chip says Crashed when none did). Any other state (queued, running, duplicate, blocked) is no verdict, and the research-DB statuses stand.
    """
    if row is None:
        return statuses
    state, reason, detail = (*row, "")[:3]
    stages = [stage for stage, _label in STAGES]
    if state == "survivor":  # the two gates passed; the three scores keep their own recorded status (owner ruling 15 Oct)
        gates = [PASSED if status == CANT_TEST else status for status in statuses[:len(TRADE_STAGES)]]  # a recorded result is never overwritten; Passed only where none is recorded
        return gates + [NOT_SCORED if status == CANT_TEST else status for status in statuses[len(gates):]]
    if state == "screened_out" and reason in stages:
        at = stages.index(reason)
        if is_our_side_mismatch(detail):
            return [PASSED] * at + [CANT_TEST] * (len(stages) - at)
        return [PASSED] * at + [FAILED] + [CANT_TEST] * (len(stages) - at - 1)
    return statuses


SCORE_DETAIL_WORDS = {"walk_forward": "made money", "robustness": "passed", "monte_carlo": "passed"}


def gates_chip(statuses: list[str], values: dict[str, str] | None = None) -> str | None:
    """'Passed the gates' plus a mark in words for each failed score ('Passed the gates · Holds over time: failed (3 of 18 windows made money) · Stress test: failed'); None unless both gates Passed.
    `values` maps stage to its stored measure ('3 of 18 windows'), added when saved. Scores never remove a survivor from review."""
    if list(statuses[:len(TRADE_STAGES)]) != [PASSED] * len(TRADE_STAGES):
        return None
    values = values or {}
    marks = [f" · {TEST_LABELS[stage]}: {'close call' if status == CLOSE_CALL else 'failed'}" + (f" ({values[stage]} {SCORE_DETAIL_WORDS[stage]})" if values.get(stage) else "")
             for stage, status in zip(SCORE_STAGES, statuses[len(TRADE_STAGES):]) if status in (FAILED, CLOSE_CALL)]
    return GATES_CHIP[0] + "".join(marks)


def gates_line(tests: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """The survivor's header line as (text, tone) parts: 'Passed the gates' green, each failed score red with its stored measure, each unscored score grey."""
    parts = [(GATES_CHIP[0], "green")]
    for test in tests:
        if test["stage"] not in SCORE_STAGES:
            continue
        if test["status"] in (FAILED, CLOSE_CALL):
            measure = f" ({test['value']} {SCORE_DETAIL_WORDS[test['stage']]})" if test.get("fraction") is not None else ""
            parts.append((f" · {test['label']}: {'close call' if test['status'] == CLOSE_CALL else 'failed'}{measure}", "red"))
        elif test["status"] in (NOT_SCORED, CANT_TEST):
            phrase = str(test.get("value")) if str(test.get("value")).startswith(NOT_ENOUGH) else "Not scored"
            parts.append((f" · {test['label']}: {phrase[0].lower()}{phrase[1:]}", "grey"))
    return parts


def overall_chip(tests: list[dict[str, Any]]) -> tuple[str, str]:
    """Header chip text and tone: the overall status from the five-status set, plus a count when mixed."""
    if not any(test["run_id"] for test in tests):
        return "Not tested yet", "grey"
    gate = next((test for test in tests if test["stage"] in TRADE_STAGES and test["status"] == FAILED), None)
    if gate:
        return f"Failed at {gate['label']}", "red"
    if all(test["status"] == PASSED for test in tests):
        return PASSED, "green"
    counts = [(word, sum(1 for test in tests if test["status"] == word)) for word in (PASSED, CLOSE_CALL, CRASHED)]
    counts += [(CANT_TEST, sum(1 for test in tests if test["status"] == CANT_TEST and test["run_id"])),  # something recorded stopped it
               ("Not run", sum(1 for test in tests if test["status"] == CANT_TEST and not test["run_id"]))]
    return " · ".join(f"{count} {word.lower()}" for word, count in counts if count), "red" if any(t["status"] == CRASHED for t in tests) else "grey"


def summary_strip(row: dict[str, Any], trades: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return, worst drop, Sharpe after costs and trades from the shown setting's saved cost-screen row (the same numbers the Results list shows), win rate from its trades; anything not saved is left out."""
    items: list[tuple[str, str]] = []
    if row.get("total_return") is not None:
        items.append(("Return", f"{float(row['total_return']):+.1f}%"))
    if row.get("max_drawdown") is not None:
        items.append(("Worst drop", f"{-abs(float(row['max_drawdown'])):.1f}%"))
    if row.get("sharpe_ratio") is not None:
        items.append(("Sharpe after costs", f"{float(row['sharpe_ratio']):.2f}"))
    if row.get("number_of_trades") is not None:
        items.append(("Trades", f"{int(row['number_of_trades']):,}"))
    pnl = pd.Series([trade["pnl"] for trade in trades if trade.get("pnl") is not None], dtype=float)
    if not pnl.empty:
        items.append(("Win rate", f"{(pnl > 0).mean() * 100:.0f}%"))
    return items


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


def hero_series(screening_equity: list[dict[str, Any]], unseen_start: str | None) -> dict[str, pd.Series]:
    """The one saved whole-window account value of the shown setting, split at the unseen-data start date: built-on before, unseen from that date on.

    One curve, two colours; nothing from another run is stitched on. Without a known unseen start everything is built-on.
    """
    whole = _series(screening_equity)
    if not unseen_start or whole.empty:
        return {"built": whole, "unseen": pd.Series(dtype=float)}
    start = pd.Timestamp(unseen_start)
    start = start.tz_localize(whole.index.tz) if start.tzinfo is None and whole.index.tz is not None else start.tz_convert(whole.index.tz) if whole.index.tz is not None else start.tz_localize(None)
    return {"built": whole[whole.index < start], "unseen": whole[whole.index >= start]}


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


def locked_row_id(rows: list[dict[str, Any]], locked: dict[str, Any]) -> str | None:
    """The cost-screen row whose setting equals the unseen test's locked parameters (compared as text); None when nothing was locked or no row matches."""
    if not locked:
        return None
    wanted = {str(key): str(value) for key, value in locked.items()}
    return next((row["row_id"] for row in rows if {str(k): str(v) for k, v in (row.get("parameters") or {}).items()} == wanted), None)


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
    out: dict[str, Any] = {"value": NOT_SAVED if test["run_id"] else "Not run", "fraction": None, "pass_line": None, "rule": RULES[stage], "scores": []}
    if not test["run_id"]:
        return out
    if stage == "screening":
        total, survivors = int(idea.get("screening_count") or 0), int(idea.get("screening_count") or 0) - int(idea.get("screened_out_count") or 0)
        if total:
            out.update(value=f"{survivors:,} of {total:,} settings", fraction=survivors / total, pass_line=1 / total)
    elif stage == "oos":
        metrics = oos_report_metrics(database=database, run_id=test["run_id"]) or {}
        value = metrics.get("total_return")
        if metrics:
            out["scores"] = [_slice_score("Built-on years", metrics.get("_training_metrics") or {}), _slice_score("Unseen years", metrics)]
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
                      "status": report_status(stage, stored_status, run.get("status")), "line": (stored.get("line") or "") if run.get("run_id") and stage != "oos" else "", "detail": detail})
    campaign = campaign_row(path, idea.get("candidate_id") or candidate_id)
    verdict = apply_campaign_verdict([test["status"] for test in tests], campaign)
    for test, status in zip(tests, verdict):
        test["status"] = status
    unseen_report = oos_report_metrics(database=path, run_id=(runs.get("oos") or {}).get("run_id")) or {}
    locked_row = locked_row_id(idea.get("screening_rows") or [], unseen_report.get("_locked_parameters") or {})  # every Report number is the locked setting; only the settings bars show the others
    screening_view = load_trade_view(idea, "screening", locked_row, database=path) if "screening" in runs else {"available": False}
    screening_equity = screening_view.get("equity") or [] if screening_view.get("available") else []
    series = hero_series(screening_equity, unseen_report.get("_unseen_start"))  # one saved curve, coloured built-on / unseen at the unseen-data start
    whole = pd.concat([part for part in (series["built"], series["unseen"]) if not part.empty]) if not (series["built"].empty and series["unseen"].empty) else series["built"]
    built_return = float(series["built"].iloc[-1] / series["built"].iloc[0] - 1) if len(series["built"]) > 1 else None
    for test in tests:
        test.update(_test_measure(test["stage"], test, idea, test["detail"], path, built_return))
        stored = next((t for t in idea.get("tests") or [] if t["stage"] == test["stage"]), {})
        if test["stage"] == "monte_carlo" and stored.get("status") == "insufficient_evidence" and str(stored.get("line") or "").startswith("Needs at least"):
            test.update(value=too_few_phrase(stored.get("line")), line="")  # one phrase, from the recorded numbers
        elif test["stage"] == "monte_carlo" and test["detail"]["checks"]:
            test["line"] = shuffle_result_line(test["detail"]["checks"])  # the measured result, never the rule repeated
    luck = load_run_scores((runs.get("monte_carlo") or {}).get("run_id"), database=path).get("luck") if runs.get("monte_carlo") else None
    crash_chip = ("Crashed", "red") if campaign and campaign[0] == "failed" and not any(t["status"] == CRASHED for t in tests) else overall_chip(tests)  # a crash no stage run carries shows in the header only
    survivor_chip = gates_chip(verdict, {test["stage"]: test.get("value") for test in tests}) if campaign and campaign[0] == "survivor" else None  # the gateway's survivor means only the two gates (costs, unseen data) were cleared
    if campaign and campaign[0] == "screened_out" and campaign[1] == "oos":  # the unseen-data reason in words, never the stored source-lock text
        unseen_test = next(test for test in tests if test["stage"] == "oos")
        if is_our_side_mismatch(campaign[2]):
            unseen_test["line"] = OUR_SIDE_WORDS + "."
        elif "test did not pass" in campaign[2]:
            unseen_test["line"] = f"{idea['title']} {unseen_loss_text(oos_report_metrics(database=path, run_id=(runs.get('oos') or {}).get('run_id')))}."
        elif plain_unseen_reason(campaign[2]):
            unseen_test["line"] = plain_unseen_reason(campaign[2]) + "."
    hold = pd.Series(dtype=float)
    if not whole.empty and "screening" in runs:  # buy and hold from the saved price bars, started with the same money
        try:
            bars = pd.DataFrame(load_period_price(runs["screening"]["run_id"], None, database=path)["price"])
        except ResultsDataError:  # saved bars that fail validation: the optional buy-and-hold comparison is left out, the report still draws
            bars = pd.DataFrame()
        if not bars.empty:
            close = pd.Series(bars["close"].astype(float).to_numpy(), index=pd.to_datetime(bars["timestamp"]))
            close = close[(close.index >= whole.index[0]) & (close.index <= whole.index[-1])]
            hold = close / close.iloc[0] * whole.iloc[0] if not close.empty else close
    trades = (screening_view.get("trades") if screening_view.get("available") else None) or []
    has_chart = not whole.empty
    performance = (screening_view.get("performance") or {}).get("performance", {}).get("all") or {}
    rows = idea.get("screening_rows") or []
    shown = next((row for row in rows if row.get("row_id") == screening_view.get("row_id")), {})  # the shown setting's saved row: the single source the Results list reads too
    has_unseen = not series["unseen"].empty
    return {
        "available": True, "title": idea["title"], "symbol": idea.get("symbol") or "", "candidate_id": idea.get("candidate_id") or candidate_id,
        "verdict": survivor_chip or crash_chip[0], "verdict_line": gates_line(tests) if survivor_chip else None, "verdict_tone": GATES_CHIP[1] if survivor_chip else crash_chip[1], "strip": [] if not has_chart else summary_strip(shown, trades),
        "tested": _tested_label(path, (runs.get("screening") or {}).get("run_id")), "tests": tests,
        "hero": {"kind": "chart" if has_chart else "never_ran", **({} if has_chart else never_ran_card(idea, tests)),
                 "built": series["built"], "unseen": series["unseen"], "hold": hold, "drawdown": drawdown(whole), "unseen_label_note": "" if has_unseen else NOT_SAVED},
        "performance": performance, "sharpe": shown.get("sharpe_ratio"),
        "unseen_return": next((test for test in tests if test["stage"] == "oos"), {}).get("value"),
        "luck": luck, "monthly": monthly_returns(whole), "trades": trades, "unseen_trades_saved": has_unseen,
        "pnl": [float(trade["pnl"]) for trade in trades if trade.get("pnl") is not None],
        "grid": settings_grid(rows, screening_view.get("row_id")),
    }


__all__ = ["apply_campaign_verdict", "campaign_row", "score_statuses", "CANT_TEST", "NOT_SCORED", "gates_chip", "CLOSE_CALL", "CRASHED", "FAILED", "NOT_SAVED", "PASSED", "STATUS_TONE", "TEST_LABELS", "drawdown", "hero_series", "load_report",
           "monthly_returns", "never_ran_card", "overall_chip", "report_status", "summary_strip", "settings_grid"]
