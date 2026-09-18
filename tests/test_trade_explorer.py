"""Focused tests for the Backtest Results trade explorer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from dash.exceptions import PreventUpdate

from dashboard.app import (
    DashboardContext,
    _trade_pnl_chart,
    _trade_review_summary,
    create_app,
)
from dashboard.components.trade_explorer import (
    DATE_BASIS_LABEL,
    filter_trade_rows,
    normalize_trade_rows,
    selected_trade_detail,
)
from dashboard.run_detail_adapter import (
    DetailField,
    ResultSummaryView,
    RunEvidenceView,
    SelectedRunDetailView,
)
from market_data import DataAudit
from orchestration import RunSummary


def _walk_components(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk_components(child)
    elif children is not None:
        yield from _walk_components(children)


def _component_text(component) -> str:
    return " ".join(
        str(item) for item in _walk_components(component) if isinstance(item, str)
    )


def _component_ids(component) -> set[str]:
    return {
        str(component_id)
        for item in _walk_components(component)
        if (component_id := getattr(item, "id", None)) is not None
    }


def _callback_function(app, output_fragment: str):
    entry = next(
        value for key, value in app.callback_map.items() if output_fragment in key
    )
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def _data() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=3, freq="D")
    return pd.DataFrame({"Open": [1.0, 2.0, 3.0], "Close": [1.0, 2.0, 3.0]}, index=index)


def _audit(data: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Test",
        provider_implementation="fixture",
        interval="1 day",
        requested_start="2026-01-01",
        requested_dynamic_end_policy="test",
        latest_completed_exchange_session="2026-01-03",
        prices_adjusted=True,
        adjustment_verification="test",
        download_time="2026-01-03T21:00:00+00:00",
        download_timezone="UTC",
        actual_first_row_date="2026-01-01",
        actual_last_row_date="2026-01-03",
        row_count=len(data),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
    )


def _detail(trades: tuple[dict[str, Any], ...] = ()) -> SelectedRunDetailView:
    return SelectedRunDetailView(
        configuration_fields=(),
        parameters=(),
        market_data=(),
        execution=(
            DetailField("Signal Timing", "completed_bar_close"),
            DetailField("Execution Timing", "next_observed_databento_bar_open"),
            DetailField("Execution Price", "Open"),
            DetailField("Position Sizing", "fixed_units"),
            DetailField("Order Size", "1.0"),
            DetailField("Fees", "0.0"),
            DetailField("Slippage", "0.0"),
        ),
        ranking=(),
        screening=(),
        lineage_fields=(),
        manifest_fields=(),
        artifacts=(),
        result_summary=ResultSummaryView(
            status="empty",
            message="No persisted parameter result summary is available for this run.",
            rows=(),
        ),
        evidence=RunEvidenceView(
            notices=(),
            metrics=(),
            trades=trades,
            orders=(),
            equity_curve=(),
            drawdown_curve=(),
            validation=(),
            provenance=(),
            warnings=(),
        ),
        warnings=(),
    )


class _RunService:
    def __init__(self, runs: tuple[RunSummary, ...] = ()) -> None:
        self._runs = runs

    def recent_runs(self, limit: int = 20):
        return self._runs[:limit]

    def all_runs(self):
        return self._runs

    def all_history(self, *, artifact_root: Path):
        return ()

    def recent_events(self, limit: int = 20):
        return ()

    def get_run(self, run_id: str | None):
        return next((run for run in self._runs if run.run_id == run_id), None)

    def events_for_run(self, run_id: str):
        return ()


class _DetailAdapter:
    artifact_root = Path(".")

    def __init__(self, details: dict[str, SelectedRunDetailView] | Exception) -> None:
        self.details = details
        self.requests: list[str] = []

    def selected_run_detail(self, run_id: str):
        self.requests.append(run_id)
        if isinstance(self.details, Exception):
            raise self.details
        return self.details[run_id]


def _run(run_id: str) -> RunSummary:
    return RunSummary(
        run_id=run_id,
        configuration_id="c" * 64,
        strategy_id="spym_rsi_mean_reversion",
        strategy_version="1.0.0",
        stage="backtest",
        status="succeeded",
        created_at="2026-01-01T00:00:00+00:00",
        started_at="2026-01-01T00:00:01+00:00",
        completed_at="2026-01-01T00:00:02+00:00",
        prefect_flow_run_id=None,
        prefect_api_url=None,
        attempt_count=1,
        error_summary=None,
    )


def test_trade_rows_normalize_vectorbt_readable_fields_without_fabrication() -> None:
    rows = normalize_trade_rows(
        (
            {
                "Avg Entry Price": 80.32,
                "Avg Exit Price": 80.45,
                "Direction": "Long",
                "Entry Fees": 0.01,
                "Exit Fees": 0.02,
                "Entry Index": "2025-10-31T14:05:00+00:00",
                "Exit Index": "2025-10-31T14:39:00+00:00",
                "Exit Trade Id": 12,
                "PnL": 0.13,
                "Return": 0.0016,
                "Size": 1.0,
                "Status": "Closed",
            },
        ),
        run_id="run-a",
    )

    assert rows[0]["__trade_key"] == "run-a:1:12"
    assert rows[0]["Outcome"] == "Win"
    assert rows[0]["Status"] == "Closed"
    assert rows[0]["Direction"] == "Long"
    assert rows[0]["Fees"] == pytest.approx(0.03)
    assert rows[0]["__basis_date"] == "2025-10-31"
    assert rows[0]["Entry timestamp"] == "2025-10-31T14:05:00+00:00"


def test_trade_rows_keep_open_and_unknown_values_truthful() -> None:
    rows = normalize_trade_rows(
        (
            {
                "Entry Index": "bad-date",
                "Exit Index": "",
                "Direction": "mystery",
                "PnL": 2.5,
                "Status": "Open",
            },
            {
                "Exit Index": "2026-01-04T15:00:00Z",
                "PnL": True,
                "Entry Fees": 0.01,
            },
        ),
        run_id="run-a",
    )

    assert rows[0]["Outcome"] == "Open"
    assert rows[0]["Status"] == "Open"
    assert rows[0]["Direction"] == "Unknown"
    assert rows[0]["Entry timestamp"] == "Not recorded"
    assert rows[0]["Exit/valuation timestamp"] == "Not recorded"
    assert rows[0]["__date_status"] == "open"
    assert rows[1]["Outcome"] == "Unknown"
    assert rows[1]["Status"] == "Unknown"
    assert rows[1]["P&L"] is None
    assert rows[1]["Fees"] is None
    assert rows[1]["__basis_date"] == ""
    assert rows[1]["__date_status"] == "open"


def test_trade_filters_cover_outcome_direction_date_and_invalid_date_summary() -> None:
    rows = normalize_trade_rows(
        (
            {"Exit Index": "2026-01-02T15:00:00Z", "Direction": "Long", "PnL": 5, "Status": "Closed"},
            {"Exit Index": "2026-01-03T15:00:00Z", "Direction": "Short", "PnL": -1, "Status": "Closed"},
            {"Exit Index": "", "Direction": "Long", "PnL": 1, "Status": "Open"},
        ),
        run_id="run-a",
    )

    filtered, summary = filter_trade_rows(
        rows,
        outcomes=["Loss"],
        directions=["Short"],
        start_date="2026-01-03",
        end_date="2026-01-03",
    )

    assert [row["Trade"] for row in filtered] == ["Trade 2"]
    assert DATE_BASIS_LABEL in summary
    assert "1 open, unconfirmed or undated trades" in summary

    filtered, summary = filter_trade_rows(
        rows,
        outcomes=None,
        directions=None,
        start_date="not-a-date",
        end_date=None,
    )
    assert len(filtered) == 3
    assert "could not be read" in summary


def test_selected_trade_detail_rejects_stale_row_from_different_run() -> None:
    row = normalize_trade_rows(
        ({"Exit Index": "2026-01-02T15:00:00Z", "Direction": "Long", "PnL": 5},),
        run_id="old-run",
    )[0]

    detail = selected_trade_detail(
        [row],
        run_id="new-run",
        execution_fields=(),
        visible_rows=[row],
    )

    assert "currently selected backtest" in _component_text(detail)


def test_selected_trade_detail_shows_trade_identity() -> None:
    row = normalize_trade_rows(
        (
            {
                "Exit Trade Id": 77,
                "Exit Index": "2026-01-02T15:00:00Z",
                "Direction": "Long",
                "PnL": 5,
                "Status": "Closed",
            },
        ),
        run_id="run-a",
    )[0]

    detail = selected_trade_detail(
        [row],
        run_id="run-a",
        execution_fields=(DetailField("Slippage", "0.0"),),
        visible_rows=[row],
    )

    rendered = _component_text(detail)
    assert "Trade Trade 1" in rendered
    assert "Selected trade detail" in rendered


def test_aggregate_trade_summary_counts_only_confirmed_closed_outcomes() -> None:
    summary = _trade_review_summary(
        (
            {"Exit Index": "2026-01-02T15:00:00Z", "PnL": 10.0, "Status": "Closed"},
            {"Exit Index": "2026-01-03T15:00:00Z", "PnL": -2.0, "Status": "Closed"},
            {"Exit Index": "2026-01-04T15:00:00Z", "PnL": 0.0, "Status": "Closed"},
            {"Exit Index": "2026-01-05T15:00:00Z", "PnL": 3.0, "Status": "Open"},
            {"Exit Index": "2026-01-06T15:00:00Z", "PnL": -9.0},
        )
    )

    rendered = _component_text(summary)
    assert "Closed trades 3" in rendered
    assert "Wins 1" in rendered
    assert "Losses 1" in rendered
    assert "Flat/unknown 1" in rendered
    assert "Open/unconfirmed 2" in rendered


def test_aggregate_trade_pnl_chart_uses_only_closed_rows_with_aligned_hover() -> None:
    chart = _trade_pnl_chart(
        (
            {"Exit Index": "2026-01-02T15:00:00Z", "PnL": 10.0, "Return": 0.01, "Status": "Closed"},
            {"Exit Index": "2026-01-03T15:00:00Z", "PnL": 7.0, "Return": 0.007, "Status": "Open"},
            {"Exit Index": "2026-01-04T15:00:00Z", "PnL": -2.0, "Return": -0.002, "Status": "Closed"},
            {"Exit Index": "2026-01-05T15:00:00Z", "PnL": -5.0, "Return": -0.005},
        ),
        mode="cumulative",
    )
    trace = chart.figure.data[0]

    assert list(trace.y) == [10.0, 8.0]
    assert list(trace.marker.color) == ["#16a34a", "#ef4444"]
    assert trace.customdata[0][1] == "2026-01-02T15:00:00+00:00"
    assert trace.customdata[1][1] == "2026-01-04T15:00:00+00:00"


def test_aggregate_trade_pnl_chart_reports_no_closed_pnl_for_open_rows() -> None:
    chart = _trade_pnl_chart(
        ({"Exit Index": "2026-01-03T15:00:00Z", "PnL": 7.0, "Status": "Open"},),
        mode="cumulative",
    )

    assert "closed trades" in _component_text(chart)


def test_selected_trade_detail_empty_current_view_is_neutral() -> None:
    detail = selected_trade_detail(
        [],
        run_id="run-a",
        execution_fields=(),
        visible_rows=[],
    )

    rendered = _component_text(detail)
    assert "No trade rows are available" in rendered
    assert "filters" not in rendered


def test_trade_explorer_outputs_exist_in_empty_database_layout(tmp_path: Path) -> None:
    data = _data()
    app = create_app(
        DashboardContext(pd.DataFrame(), data, _audit(data)),
        tmp_path / "empty.sqlite3",
        run_service=_RunService(),
        run_detail_adapter=_DetailAdapter({}),
    )
    layout = app.validation_layout
    ids = _component_ids(layout)

    assert {
        "trade-outcome-filter",
        "trade-direction-filter",
        "trade-date-range",
        "trade-explorer-summary",
        "selected-trade-grid",
        "selected-trade-detail",
    }.issubset(ids)
    assert any("selected-trade-grid" in key for key in app.callback_map)
    assert any("selected-trade-detail" in key for key in app.callback_map)


def test_trade_callback_filters_rows_and_clears_selection_on_run_change(
    tmp_path: Path,
) -> None:
    data = _data()
    adapter = _DetailAdapter(
        {
            "run-a": _detail(
                (
                    {"Exit Index": "2026-01-02T15:00:00Z", "Direction": "Long", "PnL": 5, "Status": "Closed"},
                    {"Exit Index": "2026-01-03T15:00:00Z", "Direction": "Short", "PnL": -1, "Status": "Closed"},
                )
            ),
            "run-b": _detail(
                ({"Exit Index": "2026-02-02T15:00:00Z", "Direction": "Long", "PnL": 1},)
            ),
        }
    )
    app = create_app(
        DashboardContext(pd.DataFrame(), data, _audit(data)),
        tmp_path / "state.sqlite3",
        run_service=_RunService((_run("run-a"), _run("run-b"))),
        run_detail_adapter=adapter,
    )
    refresh_rows = _callback_function(app, "selected-trade-grid.rowData")

    rows, summary, selected = refresh_rows(
        "run-a",
        ["Loss"],
        ["Short"],
        "2026-01-03",
        "2026-01-03",
        0,
        "/research/backtest-results",
    )

    assert len(rows) == 1
    assert rows[0]["Outcome"] == "Loss"
    assert rows[0]["Direction"] == "Short"
    assert "Showing 1 of 2" in summary
    assert selected == []

    rows, _, selected = refresh_rows(
        "run-b",
        [],
        [],
        None,
        None,
        0,
        "/research/backtest-results",
    )
    assert [row["__run_id"] for row in rows] == ["run-b"]
    assert selected == []

    with pytest.raises(PreventUpdate):
        refresh_rows("run-a", [], [], None, None, 0, "/")
