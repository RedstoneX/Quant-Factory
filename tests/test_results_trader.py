"""Trader-facing Results page: money, profit factor, labels, score notes, unseen-data chart target."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dashboard import results_projection as projection
from dashboard.formatting import format_money, profit_factor
from dashboard.ui import results as page


def test_money_has_two_decimals_and_sign() -> None:
    assert format_money(64.43739053687545) == "$64.44"
    assert format_money(-18.980367106125634) == "-$18.98"
    assert format_money(1234.5) == "$1,234.50"
    assert format_money(-0.001) == "$0.00"
    assert format_money(None) == "—"


def test_profit_factor_is_gross_profit_over_gross_loss() -> None:
    assert profit_factor([10.0, -5.0, 5.0, -5.0]) == 1.5
    assert profit_factor([10.0, 5.0]) is None
    assert profit_factor([]) is None


def test_profit_factor_tile_is_filled_from_trades_when_not_recorded() -> None:
    metrics = [{"label": "Profit Factor", "value": "—"}, {"label": "Win Rate", "value": "42.00%"}]
    filled = projection._with_profit_factor(metrics, [30.0, -10.0])
    assert {"label": "Profit Factor", "value": "3.00"} in filled
    assert sum(item["label"] == "Profit Factor" for item in filled) == 1
    recorded = [{"label": "Profit Factor", "value": "1.20"}]
    assert projection._with_profit_factor(recorded, [30.0, -10.0]) == recorded


def test_trade_ledger_formats_money_and_uses_trader_term() -> None:
    pnl = next(column for column in page.TRADE_COLUMNS if column["field"] == "pnl")
    assert pnl["valueFormatter"]["function"] == page.MONEY_JS
    assert "Biggest drop" not in json.dumps(page.METRIC_COLUMNS)
    assert any(column.get("headerName") == "Max drawdown" for column in page.METRIC_COLUMNS)


def _text(components) -> str:
    return json.dumps([item.to_plotly_json() if hasattr(item, "to_plotly_json") else item for item in components], default=lambda item: item.to_plotly_json(), ensure_ascii=False)


def test_every_score_tile_has_a_plain_line_and_weak_passed_idea_gets_reminder_once() -> None:
    weak = {"rolling_status": "failed", "folds_profitable": 5, "folds_total": 18, "folds_share": 0.28, "fold_sharpe": 0.1,
            "stress_status": "failed", "luck": 0.2, "overfitting": 0.7}
    text = _text(page.explained_score_cards(weak, passed=True))
    assert all(note in text for note in page.SCORE_NOTES)
    assert text.count(page.SCORES_NOTE) == 1
    assert page.SCORES_NOTE not in _text(page.explained_score_cards(weak, passed=False))
    strong = {**weak, "rolling_status": "passed", "stress_status": "passed", "luck": 0.9, "overfitting": 0.1}
    assert page.SCORES_NOTE not in _text(page.explained_score_cards(strong, passed=True))


def test_unavailable_chart_message_has_no_developer_text() -> None:
    assert "/" not in page.CHART_UNAVAILABLE and "toml" not in page.CHART_UNAVAILABLE.lower()


def _database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE experiment_runs (run_id TEXT, environment_json TEXT)")
    connection.execute("CREATE TABLE parameter_results (run_id TEXT, row_id TEXT, normalized_parameters_json TEXT)")
    connection.execute("INSERT INTO experiment_runs VALUES ('oos', ?)", [json.dumps({"filter_handoff": {"source_run_id": "scr"}})])
    connection.executemany("INSERT INTO parameter_results VALUES ('scr', ?, ?)", [("a", '{"trail":15}'), ("b", '{"trail":20}')])
    return connection


def test_unseen_data_run_maps_to_the_first_check_setting_and_test_dates(tmp_path: Path, monkeypatch) -> None:
    report = {"shortlist_parameters": [{"trail": 20}], "split": {"test": {"start": "2024-10-08", "end": "2026-02-13"}}}
    monkeypatch.setattr(projection, "_artifact_document", lambda **_: report)
    monkeypatch.setattr(projection, "_validated_connection", lambda _db: (_database(), None))
    target = projection.oos_chart_target(database=tmp_path / "x.sqlite3", run_id="oos")
    assert target == {"source_run_id": "scr", "row_id": "b", "start": "2024-10-08", "end": "2026-02-13"}


def test_unseen_data_run_without_report_has_no_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(projection, "_artifact_document", lambda **_: None)
    assert projection.oos_chart_target(database=tmp_path / "x.sqlite3", run_id="oos") is None


def test_settings_line_never_says_all_screened_out_for_a_passed_run() -> None:
    assert page.settings_tried_line(3, 3) == "3 settings tried · all screened out"
    assert page.settings_tried_line(3, 1) == "3 settings tried · 2 passed, 1 screened out"
    assert "screened out" not in page.settings_tried_line(3, 0)


def test_trade_grid_fits_by_flex_keeps_dates_whole_and_shows_running_total(monkeypatch) -> None:
    columns = {column["field"]: column for column in page.TRADE_COLUMNS}
    assert columns["entry_display"]["minWidth"] >= 220 and columns["exit_display"]["minWidth"] >= 220
    assert all("flex" in column for column in columns.values())
    assert columns["cum_pnl"]["headerName"] == "Running total"
    monkeypatch.setattr(page, "_resolve", lambda search: (FAKE_IDEA, "oos"))
    monkeypatch.setattr(page, "top_line", lambda idea: [])
    layout = json.dumps(page.results_layout().to_plotly_json(), default=lambda item: item.to_plotly_json())
    main_grid = layout.split('"id": "results-trade-grid"')[1].split('"id": "results-trade-count"')[0]
    assert '"columnSize"' not in main_grid
    assert "results-linked-trade-grid" not in layout
    assert "charAt(0).toUpperCase()" in json.dumps(page.METRIC_COLUMNS)


def test_equity_figure_gives_drawdown_its_own_axis_and_a_date_axis_that_suits_years() -> None:
    rows = [{"timestamp": f"2024-0{month}-01T00:00:00", "value": value} for month, value in ((1, 100.0), (2, 110.0), (3, 99.0))]
    figure = page._equity_figure(rows, "none")
    assert len(figure.data) == 2 and figure.data[0].yaxis != figure.data[1].yaxis
    assert [round(float(v), 6) for v in figure.data[1].y] == [0.0, 0.0, -10.0]  # value / cummax - 1, in percent
    assert not figure.layout.xaxis.tickformat and figure.layout.xaxis.tickformatstops


FAKE_IDEA = {
    "available": True, "title": "MES idea", "symbol": "MES", "verdict": "Passed the costs and unseen-data tests", "verdict_color": "teal",
    "runs": {}, "screening_rows": [], "screened_out_count": 0,
    "tests": [{"stage": stage, "label": label, "run_id": f"run_{stage}", "status": "passed", "status_text": "Passed", "color": "teal", "line": "fine"}
              for stage, label in page.STAGES],
}


def test_results_is_one_page_per_idea_with_a_test_strip_and_strategy_tester_tabs(monkeypatch) -> None:
    monkeypatch.setattr(page, "_resolve", lambda search: (FAKE_IDEA, "oos"))
    monkeypatch.setattr(page, "top_line", lambda idea: [])
    layout = json.dumps(page.results_layout("?candidate_id=c1").to_plotly_json(), default=lambda item: item.to_plotly_json())
    for words in ("Costs test", "Unseen data", "Rolling test", "Stress test", "Shuffle test", "Overview", "Performance summary",
                  "Price chart and trades", "Settings tried", "MES idea"):
        assert words in layout
    assert '"id": "results-test"' in layout and '"id": "results-settings-grid"' in layout


def test_price_chart_reacts_to_zoom_and_has_range_buttons() -> None:
    assert page.relayout_window({"xaxis.autorange": True}) == "all"
    assert page.relayout_window({"autosize": True}) is None
    start, end = page.relayout_window({"xaxis.range[0]": "2026-01-01 09:30", "xaxis.range[1]": "2026-01-08 16:00"})
    assert (str(start), str(end)) == ("2026-01-01 09:30:00", "2026-01-08 16:00:00")
    price = [{"timestamp": f"2026-01-0{day}T10:00:00", "open": 1, "high": 2, "low": .5, "close": 1.5} for day in range(1, 9)]
    trades = [{"trade_id": n, "direction": "Long", "outcome": "Win", "pnl": 1, "entry_timestamp": "2026-01-02T10:00:00", "entry_price": 1,
               "exit_timestamp": "2026-01-02T11:00:00", "exit_price": 1.5} for n in range(page.TRADE_MARKER_LIMIT + 1)]
    crowded = page.trades_figure(price, trades, None, None, "r", window=("2026-01-01", "2026-01-08"))
    assert [trace.type for trace in crowded.data] == ["candlestick"]  # too many to read: no markers
    readable = page.trades_figure(price, trades[:3], None, None, "r", window=("2026-01-01", "2026-01-08"))
    assert len(readable.data) > 1 and readable.layout.dragmode == "pan" and readable.layout.uirevision == "r"
    assert [button.label for button in readable.layout.xaxis.rangeselector.buttons] == ["1W", "1M", "1Y", "All"]
    assert page._GRAPH_CONFIG["scrollZoom"] is True


def test_page_opens_on_the_furthest_test_the_idea_reached(monkeypatch) -> None:
    monkeypatch.setattr(page, "load_idea", lambda candidate_id, run_id=None: {**FAKE_IDEA, "open_test": "screening"})
    assert page._resolve("?candidate_id=c1")[1] == "screening"


def test_old_run_link_opens_its_idea_with_that_test_selected(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(page, "idea_for_run", lambda run_id: {"candidate_id": "c1", "stage": "walk_forward"})
    monkeypatch.setattr(page, "load_idea", lambda candidate_id, run_id=None: calls.append((candidate_id, run_id)) or FAKE_IDEA)
    assert page._resolve("?run_id=r9") == (FAKE_IDEA, "walk_forward")
    assert calls == [("c1", "r9")]


def test_performance_summary_is_read_from_the_saved_file_never_computed() -> None:
    assert page.performance_table({}).children == page.SUMMARY_MISSING
    document = {"performance": {"all": {"net_profit": 12.5, "win_rate": 0.5, "total_trades": 4}, "long": {"net_profit": -3}, "short": {}}}
    grid = page.performance_table({"performance": document})
    rows = {row["measure"]: row for row in grid.rowData}
    assert rows["Net profit"] == {"measure": "Net profit", "all": "$12.50", "long": "-$3.00", "short": "—"}
    assert rows["Win rate"]["all"] == "50.00%" and rows["Trades"]["all"] == "4"


def test_a_test_without_trades_shows_its_own_detail_not_an_empty_chart(monkeypatch) -> None:
    monkeypatch.setattr(page, "load_stage_detail", lambda idea, stage: {"periods": [], "checks": [{"check": "Worst drop from peak", "result": "Passed", "measured": .01, "needed": .35}], "reasons": []})
    monkeypatch.setattr(page, "load_run_scores", lambda run_id: {})
    detail = json.dumps(page.score_detail(FAKE_IDEA, "robustness")[0].to_plotly_json(), default=lambda item: item.to_plotly_json())
    assert "results-check-grid" in detail and "Worst drop from peak" in detail and "Graph" not in detail


def test_equity_from_trades_is_starting_cash_plus_cumulative_pnl_at_exit_time() -> None:
    from dashboard.results_projection import equity_from_trades

    trades = [
        {"exit_timestamp": "2024-01-03T10:00:00", "pnl": -5.0},
        {"exit_timestamp": "2024-01-02T10:00:00", "pnl": 10.0},
        {"exit_timestamp": None, "pnl": 99.0},
    ]
    assert [row["value"] for row in equity_from_trades(trades, starting_cash=100.0)] == [110.0, 105.0]
    assert equity_from_trades([], starting_cash=100.0) == []
    assert equity_from_trades(trades, starting_cash=None) == []  # no saved starting cash: no curve, no guess
