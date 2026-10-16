"""Read-only projection for the one-page-per-idea Results view.

Picks the newest run of each test stage for one idea, says in plain words how
each test went, and loads the whole-period trades, account value and price
bars that the page draws. Nothing is computed here that a run did not save,
apart from pandas sums, cumulative sums and thinning for display.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import sqlite3
from typing import Any

import pandas as pd

from dashboard.formatting import format_metric, format_percent
from dashboard.overview_projection import _validated_connection, configured_database_path
from dashboard.results_model import group_trade_rows, prepare_interval
from dashboard.results_projection import (
    EQUITY_LIMIT, OOS_REPORT_LOGICAL_NAME, PRICE_LIMIT, _artifact_document, _shared_price_rows, _trade_row,
    load_results_record, oos_report_metrics,
)
from dashboard.run_detail_adapter import _candidate_trade_rows
from dashboard.time_display import eastern_plot_timestamp

STAGES = (
    ("screening", "Costs test"), ("oos", "Unseen data"), ("walk_forward", "Rolling test"),
    ("robustness", "Stress test"), ("monte_carlo", "Shuffle test"),
)
TRADE_STAGES = ("screening", "oos")
STATUS_WORDS = {"passed": "Passed", "failed": "Failed", "insufficient_evidence": "Too few trades", None: "Not run yet", "not_reached": "Not reached"}
STATUS_COLORS = {"passed": "teal", "failed": "red", "insufficient_evidence": "yellow", None: "gray", "not_reached": "gray"}
REJECTION = re.compile(r"(\w+) failed: expected ([<>]=?) ?(-?\d+(?:\.\d+)?(?:e-?\d+)?).*?observed (-?\d+(?:\.\d+)?(?:e-?\d+)?)")
MARKET_WORDS = {"bearish": "Falling market", "bullish": "Rising market", "neutral": "Flat market",
                "high_volatility": "big swings", "low_volatility": "small swings"}
CHECK_WORDS = {
    "minimum_return": "Return at least", "minimum_sharpe": "Return per unit of risk at least",
    "maximum_drawdown": "Drop from peak at most", "minimum_observations": "Bars seen at least",
    "minimum_valid_neighbors": "Nearby settings tested", "required_pass_proportion": "Share of nearby settings that pass",
    "degradation_proportion": "Share that hold up with worse costs", "worst_drawdown": "Worst drop from peak",
    "locked_point": "Chosen setting checked",
}
REASON_WORDS = (
    (r"training screening produced no passing candidates.*", "No setting passed on the training years, so this period was skipped."),
    (r"selection screening produced no passing candidates.*", "No setting passed on the checking years, so this period was skipped."),
    (r"requires at least (\d+) observations; received (\d+)", r"Needs at least \1 results to shuffle; it had \2."),
)


def plain_reason(text: Any) -> str:
    text = str(text or "").strip()
    for pattern, words in REASON_WORDS:
        if re.fullmatch(pattern, text):
            return re.sub(pattern, words, text)
    return text[:1].upper() + text[1:] if text else ""


CHECK_KINDS = {  # check key -> how its numbers read: percent, ratio (return per unit of risk) or count
    "minimum_return": "percent", "maximum_drawdown": "percent", "worst_drawdown": "percent", "required_pass_proportion": "percent",
    "degradation_proportion": "percent", "locked_point": "percent", "minimum_sharpe": "ratio",
    "minimum_observations": "count", "minimum_valid_neighbors": "count",
}


def _check_value(threshold_id: str, value: Any) -> str:
    """A check's measured or needed number in the unit its check uses."""
    kind = CHECK_KINDS.get(str(threshold_id).rpartition(":")[2])
    if value is None or kind is None:
        return "—" if value is None else format_metric("", value)
    return format_percent(value) if kind == "percent" else format_metric("sharpe_ratio" if kind == "ratio" else "number_of_trades", value)


def _check_name(threshold_id: str) -> str:
    market, _, check = str(threshold_id).rpartition(":")
    words = CHECK_WORDS.get(check, check.replace("_", " ").capitalize())
    if not market:
        return words
    trend, _, swings = market.partition("|")
    return f"{MARKET_WORDS.get(trend, trend)}, {MARKET_WORDS.get(swings, swings)}: {words[:1].lower() + words[1:]}"


def _database(database: str | Path | None) -> Path:
    return Path(database) if database is not None else configured_database_path()


def idea_for_run(run_id: str | None, *, database: str | Path | None = None) -> dict[str, Any] | None:
    """The idea (candidate id, or its configuration when no idea row exists) and stage of one run."""
    connection, _error = _validated_connection(_database(database))
    if connection is None or not run_id:
        return None
    try:
        row = connection.execute(
            "SELECT r.configuration_id, r.stage, (SELECT d.draft_id FROM idea_drafts d WHERE d.configuration_id=r.configuration_id "
            "AND d.candidate_json<>'' ORDER BY d.draft_id LIMIT 1) AS candidate_id FROM experiment_runs r WHERE r.run_id=?", [run_id],
        ).fetchone()
        return {"configuration_id": str(row["configuration_id"]), "stage": str(row["stage"]), "candidate_id": row["candidate_id"]} if row else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def _stage_runs(connection: sqlite3.Connection, configuration_id: str) -> dict[str, dict[str, Any]]:
    """The newest campaign: the newest costs-test run, then each later run handed off from the one before it.

    Each stage records the run it was handed from (environment_json filter_handoff.source_run_id), so runs
    from older campaigns are never mixed in. Without a costs-test run, the newest run of each stage is used.
    """
    rows = [dict(row) for row in connection.execute(
        "SELECT run_id, stage, status, json_extract(environment_json, '$.filter_handoff.source_run_id') AS source "
        "FROM experiment_runs WHERE configuration_id=? ORDER BY (status='succeeded') DESC, created_at DESC, run_id DESC", [configuration_id],
    )]
    head = next((row for row in rows if row["stage"] == "screening"), None)
    runs: dict[str, dict[str, Any]] = {}
    if head is None:
        for row in rows:
            runs.setdefault(str(row["stage"]), {"run_id": str(row["run_id"]), "status": str(row["status"])})
        return runs
    previous = str(head["run_id"])
    runs["screening"] = {"run_id": previous, "status": str(head["status"])}
    for stage, _label in STAGES[1:]:
        found = next((row for row in rows if row["stage"] == stage and row["source"] == previous), None)
        if found is None:
            break
        previous = str(found["run_id"])
        runs[stage] = {"run_id": previous, "status": str(found["status"])}
    return runs


def failure_score(report: dict[str, Any]) -> str:
    """'scored 0.48, needed 0.50' from the best training result's saved rejection reason; '' when none was saved."""
    results = [item for item in report.get("training_results") or [] if isinstance(item, dict)]
    best = max(results, key=lambda item: float(item.get("sharpe_ratio") or float("-inf")), default={})
    match = REJECTION.search(str(best.get("screening_rejection_reasons") or ""))
    return f"scored {float(match.group(4)):.2f}, needed {float(match.group(3)):.2f}" if match else ""


def _evidence(database: Path, run_id: str | None, stage: str) -> dict[str, Any]:
    document = _artifact_document(database=database, run_id=run_id, logical_name=f"{stage}_evidence") if run_id else None
    return (document or {}).get("evidence") or {}


def _test_card(database: Path, stage: str, label: str, run: dict[str, Any] | None, screening: dict[str, Any]) -> dict[str, Any]:
    run_id = (run or {}).get("run_id")
    status: str | None = None
    line = "This test has not run for this idea yet."
    if run_id and stage == "screening":
        total, out = int(screening.get("screening_count") or 0), int(screening.get("screened_out_count") or 0)
        status = "passed" if total > out else "failed"
        line = f"{total - out:,} of {total:,} settings still made money after costs."
    elif run_id and stage == "oos":
        report = oos_report_metrics(database=database, run_id=run_id) or {}
        status = report.get("_test_status")
        value = report.get("total_return")
        line = "No unseen-data result was saved." if value is None else f"{'Made' if value >= 0 else 'Lost'} {abs(float(value)) * 100:.2f}% on data it never saw."
        saved = _artifact_document(database=database, run_id=run_id, logical_name=OOS_REPORT_LOGICAL_NAME) or {}
        if value is None and saved.get("failure_stage"):  # stopped before the unseen data: the run's own saved failure
            failure = failure_score(saved)
            return {"stage": stage, "label": label, "run_id": run_id, "status": "failed", "status_text": "Failed", "color": "red",
                    "line": f"No setting passed the training years{f' (best {failure})' if failure else ''}, so it never traded unseen data.",
                    "failure": failure, "has_result": False}
    elif run_id:
        evidence = _evidence(database, run_id, stage)
        normalized = evidence.get("normalized_evidence") or {}
        status = normalized.get("status")
        if stage == "walk_forward":
            folds = evidence.get("folds") or []
            made = sum(1 for fold in folds if isinstance(fold.get("test_metrics"), dict) and (fold["test_metrics"].get("total_return") or 0) > 0)
            line = f"{made} of {len(folds)} rolling periods made money." if folds else "No rolling periods were saved."
        elif stage == "robustness":
            checks = normalized.get("threshold_results") or []
            failed = sum(1 for check in checks if check.get("status") == "failed")
            line = f"{failed} of {len(checks)} checks failed." if failed else f"All {len(checks)} checks passed."
        else:
            reasons = normalized.get("reasons") or []
            line = plain_reason(reasons[0]) if reasons else "Shuffled trades still made money." if status == "passed" else "No detail was saved."
        if not evidence:
            status, line = (run or {}).get("status") if (run or {}).get("status") == "failed" else None, "No result was saved for this test."
    score = stage not in TRADE_STAGES and status == "failed"  # a weak score is amber, never red
    return {"stage": stage, "label": label, "run_id": run_id, "status": status,
            "status_text": "Weak" if score else STATUS_WORDS.get(status, str(status).replace("_", " ").capitalize()),
            "color": "yellow" if score else STATUS_COLORS.get(status, "gray"), "line": line}


def _verdict(tests: list[dict[str, Any]]) -> tuple[str, str]:
    """Only the costs and unseen-data tests are pass marks; the other three are scores (see dashboard/ui/scores.py)."""
    gates = [test for test in tests if test["stage"] in TRADE_STAGES]
    failed = next((test for test in gates if test["status"] == "failed"), None)
    if failed:
        return f"Failed at: {failed['label'].lower()}" + (f" — {failed['failure']}" if failed.get("failure") else ""), "red"
    if all(test["status"] == "passed" for test in gates):
        return "Passed the costs and unseen-data tests", "teal"
    return "Still being tested", "blue"


def load_idea(candidate_id: str | None = None, *, run_id: str | None = None, database: str | Path | None = None) -> dict[str, Any]:
    """One idea: name, market, verdict, the newest run of each test, and the costs-test settings."""
    database_path = _database(database)
    connection, _error = _validated_connection(database_path)
    if connection is None:
        return {"available": False, "message": "The results database is not available."}
    try:
        if candidate_id:
            row = connection.execute("SELECT configuration_id FROM idea_drafts WHERE draft_id=?", [candidate_id]).fetchone()
            configuration_id = str(row[0]) if row and row[0] else None
        else:
            found = connection.execute("SELECT configuration_id FROM experiment_runs WHERE run_id=?", [run_id]).fetchone() if run_id else None
            configuration_id = str(found[0]) if found else None
        if not configuration_id:
            return {"available": False, "message": "This idea has no saved test results yet."}
        head = connection.execute(
            "SELECT COALESCE(json_extract(c.canonical_config_json, '$.market_data.symbol'), json_extract(c.canonical_config_json, '$.market_data.dataset_id'), 'Unrecorded') AS symbol, "
            "c.experiment_id, (SELECT COALESCE(json_extract(d.candidate_json, '$.candidate.title'), d.title) FROM idea_drafts d WHERE d.configuration_id=c.configuration_id "
            "AND d.candidate_json<>'' ORDER BY d.draft_id LIMIT 1) AS title FROM experiment_configurations c WHERE c.configuration_id=?", [configuration_id],
        ).fetchone()
        runs = _stage_runs(connection, configuration_id)
    except sqlite3.Error:
        return {"available": False, "message": "Saved results for this idea could not be loaded."}
    finally:
        connection.close()
    if run_id and idea_for_run(run_id, database=database_path):  # an old link keeps showing the exact run it named
        stage = idea_for_run(run_id, database=database_path)["stage"]
        runs[stage] = {"run_id": run_id, "status": runs.get(stage, {}).get("status", "succeeded")}
    screening = load_results_record(runs["screening"]["run_id"], database=database_path) if "screening" in runs else {}
    tests = [_test_card(database_path, stage, label, runs.get(stage), screening) for stage, label in STAGES]
    stopped = next((index for index, test in enumerate(tests) if test["stage"] in TRADE_STAGES and test["status"] == "failed"), len(tests))
    for test in tests[stopped + 1:]:
        if not test["run_id"]:
            test.update(status="not_reached", status_text=STATUS_WORDS["not_reached"], color="gray", line="It stopped at an earlier test, so this never ran.")
    reached = [test["stage"] for test in tests if test["run_id"] and test.get("has_result", True)]
    verdict, color = _verdict(tests)
    title = (head["title"] if head else None) or str((head["experiment_id"] if head else None) or "Untitled idea").replace("_", " ").title()
    return {
        "available": True, "candidate_id": candidate_id or idea_for_run(run_id, database=database_path).get("candidate_id"),
        "configuration_id": configuration_id, "title": title, "symbol": str(head["symbol"]) if head else "Unrecorded",
        "verdict": verdict, "verdict_color": color, "tests": tests, "runs": runs, "open_test": reached[-1] if reached else "screening",
        "screening_rows": screening.get("screening_rows") or [], "screening_count": screening.get("screening_count") or 0,
        "screened_out_count": screening.get("screened_out_count") or 0,
    }


def _with_cumulative(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add running profit or loss in trade order (pandas cumsum)."""
    if not trades:
        return []
    frame = pd.DataFrame(trades)
    frame["trade_id"] = [str(number) for number in range(1, len(frame) + 1)]  # numbered from 1, oldest first
    frame["cum_pnl"] = frame["pnl"].fillna(0).cumsum().round(2)
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


def _thin(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every n-th point (pandas iloc) plus the last, so the whole period fits the chart limit."""
    if len(rows) <= EQUITY_LIMIT:
        return rows
    frame = pd.DataFrame(rows)
    step = -(-len(frame) // EQUITY_LIMIT)
    return pd.concat([frame.iloc[::step], frame.iloc[[-1]]]).drop_duplicates().to_dict("records")


def _performance(database: Path, run_id: str, namespace: str = "") -> dict[str, Any] | None:
    document = _artifact_document(database=database, run_id=run_id, logical_name=f"{namespace}performance_summary")
    performance = (document or {}).get("performance")
    return document if isinstance(performance, dict) and performance else None


def load_trade_view(idea: dict[str, Any] | None, stage: str, row_id: str | None = None, *, database: str | Path | None = None) -> dict[str, Any]:
    """Whole-period trades, account value and performance summary for the unseen-data test or one costs-test setting."""
    database_path = _database(database)
    run_id = ((idea or {}).get("runs") or {}).get(stage, {}).get("run_id")
    if not run_id or stage not in TRADE_STAGES:
        return {"available": False, "message": "This test has not run for this idea yet."}
    if stage == "oos":
        record = load_results_record(run_id, database=database_path)
        target = record.get("oos_chart") or {}
        trades = record.get("trades") or []
        return {
            "available": True, "stage": stage, "run_id": run_id, "trades": _with_cumulative(trades), "trade_count": int(record.get("trade_count") or 0),
            "equity": _thin(record.get("equity") or []), "equity_from_trades": bool(record.get("equity_from_trades")),
            "price_run_id": target.get("source_run_id"), "period": [target["start"], target["end"]] if target else None,
            "performance": _performance(database_path, run_id), "label": "Unseen-data test",
        }
    rows = (idea or {}).get("screening_rows") or []
    row = next((item for item in rows if item.get("row_id") == row_id), rows[0] if rows else None)
    if row is None:
        return {"available": False, "message": "The costs test saved no settings."}
    namespace = f"screening_configuration/{row['row_id']}/"
    document = _artifact_document(database=database_path, run_id=run_id, logical_name=f"{namespace}trades_and_orders")
    equity_document = _artifact_document(database=database_path, run_id=run_id, logical_name=f"{namespace}equity_curve") or {}
    if not document:
        return {"available": False, "message": "This setting kept its scores only; its trades were not saved."}
    groups = group_trade_rows(_candidate_trade_rows(document)).groups
    trades = [_trade_row(group) for group in groups]
    equity = [{**item, "timestamp": eastern_plot_timestamp(item["timestamp"])} for item in equity_document.get("equity_curve") or [] if isinstance(item, dict) and item.get("timestamp")]
    return {
        "available": True, "stage": stage, "run_id": run_id, "row_id": row["row_id"], "trades": _with_cumulative(trades), "trade_count": len(trades),
        "equity": _thin(equity), "equity_from_trades": False, "price_run_id": run_id, "period": None,
        "performance": _performance(database_path, run_id, namespace) or _performance(database_path, run_id), "label": f"Costs test · setting {row.get('rank')}",
    }


def _auto_interval(row_count: int) -> str:
    """The finest saved bar size whose bar count fits the chart limit (source bars are 5 minutes)."""
    if row_count <= PRICE_LIMIT:
        return "5m"
    if row_count / 3 <= PRICE_LIMIT:
        return "15m"
    if row_count / 12 <= PRICE_LIMIT:
        return "1h"
    return "1D"


def _coarsen(bars: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Weekly, then monthly OHLC bars (pandas resample) until the whole history fits the chart limit."""
    frame = pd.DataFrame(bars).assign(timestamp=lambda data: pd.to_datetime(data["timestamp"])).set_index("timestamp")
    for interval, rule in (("1W", "W"), ("1M", "MS")):
        coarse = frame.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        if len(coarse) <= PRICE_LIMIT:
            break
    coarse.index = coarse.index.strftime("%Y-%m-%dT%H:%M:%S")
    return interval, coarse.reset_index().to_dict("records")


@lru_cache(maxsize=8)
def _period_price(database: str, run_id: str, start: str | None, end: str | None) -> tuple[str, tuple[dict[str, Any], ...], str | None]:
    rows = _shared_price_rows(database=Path(database), run_id=run_id, session=None, period=(start, end) if start and end else None)
    if not rows:
        return "", (), "No price bars were saved for this period."
    interval = _auto_interval(len(rows))
    prepared = prepare_interval(rows, interval, source_interval="5m")
    bars = [
        {"timestamp": eastern_plot_timestamp(bar.timestamp), "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close}
        for bar in prepared.bars
    ] if prepared.available else []
    if len(bars) > PRICE_LIMIT:  # a window too long for daily bars: coarser bars keep the full history
        interval, bars = _coarsen(bars)
    return interval, tuple(bars), prepared.reason


def load_period_price(run_id: str | None, period: list[str] | None, *, database: str | Path | None = None) -> dict[str, Any]:
    """The whole test period's saved bars, at a bar size chosen so the chart can draw them."""
    if not run_id:
        return {"price": [], "interval": "", "reason": "No price bars were saved for this test."}
    start, end = (period or [None, None])[:2]
    interval, bars, reason = _period_price(str(_database(database)), run_id, start, end)
    return {"price": list(bars), "interval": interval, "reason": reason}


def load_stage_detail(idea: dict[str, Any] | None, stage: str, *, database: str | Path | None = None) -> dict[str, Any]:
    """The rolling, stress or shuffle test's own saved detail: periods or checks, and plain reasons."""
    run_id = ((idea or {}).get("runs") or {}).get(stage, {}).get("run_id")
    evidence = _evidence(_database(database), run_id, stage)
    normalized = evidence.get("normalized_evidence") or {}
    periods = []
    for fold in evidence.get("folds") or []:
        test = fold.get("test") or {}
        metrics = fold.get("test_metrics") if isinstance(fold.get("test_metrics"), dict) else {}
        periods.append({
            "period": f"{str(test.get('start') or '?')[:10]} to {str(test.get('end') or '?')[:10]}",
            "result": "Traded" if fold.get("status") == "successful" else "Skipped",
            "trades": metrics.get("number_of_trades"),
            "net_return": None if metrics.get("total_return") is None else round(float(metrics["total_return"]) * 100, 2),
            "note": plain_reason(fold.get("failure_reason")) if fold.get("failure_reason") else "",
        })
    checks = [
        {"check": _check_name(item.get("threshold_id")), "result": STATUS_WORDS.get(item.get("status"), str(item.get("status")).capitalize()),
         "measured": _check_value(item.get("threshold_id"), item.get("observed")), "needed": _check_value(item.get("threshold_id"), item.get("threshold"))}
        for item in normalized.get("threshold_results") or []
    ]
    reasons = [] if checks or periods else [plain_reason(reason) for reason in (normalized.get("reasons") or [])][:12]  # periods and checks already say why
    return {"run_id": run_id, "status": normalized.get("status"), "periods": periods, "checks": checks, "reasons": reasons}


__all__ = ["STAGES", "TRADE_STAGES", "failure_score", "idea_for_run", "load_idea", "load_period_price", "load_stage_detail", "load_trade_view", "plain_reason"]
