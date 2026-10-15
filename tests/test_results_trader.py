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
