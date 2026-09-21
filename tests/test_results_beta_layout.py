"""Narrow contracts for the reused selected-run Results beta workspace."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dashboard.application import (
    _bounded_curve_rows,
    _price_marker_figure,
    _price_marker_panel,
    _result_summary,
    _results_report_tabs,
)
from dashboard.components.trade_explorer import (
    layout as trade_explorer_layout,
    normalize_trade_rows,
)
from dashboard.run_detail_adapter import (
    DetailField,
    ResultSummaryView,
    RunEvidenceView,
    SelectedRunDetailView,
)


def _detail() -> SelectedRunDetailView:
    prices = tuple(
        {
            "timestamp": f"2026-01-02T14:3{minute}:00+00:00",
            "open": 100.0 + minute,
            "high": 101.0 + minute,
            "low": 99.0 + minute,
            "close": 100.5 + minute,
        }
        for minute in range(6)
    )
    return SelectedRunDetailView(
        configuration_fields=(),
        parameters=(),
        market_data=(DetailField("Symbol", "TEST"), DetailField("Timeframe", "1m")),
        execution=(),
        ranking=(),
        screening=(),
        lineage_fields=(),
        manifest_fields=(),
        artifacts=(),
        result_summary=ResultSummaryView(status="available", message="", rows=()),
        evidence=RunEvidenceView(
            notices=(),
            metrics=(),
            trades=(
                {
                    "Status": "Closed",
                    "Direction": "Long",
                    "Entry Index": "2026-01-02T14:31:00+00:00",
                    "Exit Index": "2026-01-02T14:34:00+00:00",
                    "Avg Entry Price": 101.0,
                    "Avg Exit Price": 104.0,
                    "Size": 2.0,
                },
            ),
            orders=(),
            equity_curve=(),
            drawdown_curve=(),
            validation=(),
            provenance=(),
            warnings=(),
            price_series=prices,
            benchmark={"instrument": "TEST"},
            source_interval="1m",
            price_unit="currency",
            pnl_unit="USD",
        ),
        warnings=(),
    )


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = (children,)
    for child in children:
        yield from _walk(child)


def test_price_workspace_reuses_plotly_with_independent_bars_and_view_controls() -> None:
    figure, availability = _price_marker_figure(_detail())

    candlesticks = [trace for trace in figure.data if trace.type == "candlestick"]
    assert [trace.name for trace in candlesticks] == ["Observed TEST (1m)"]
    assert len(candlesticks[0].x) == 6
    assert "Showing 6 of 6 actual 1m bars for 1D" in availability
    assert figure.layout.dragmode == "pan"
    marker_traces = [trace for trace in figure.data if trace.type == "scatter"]
    assert marker_traces
    assert all(trace.customdata[0][0] == 1 for trace in marker_traces)

    five_minute, _ = _price_marker_figure(_detail(), interval="5m", view="Full run")
    assert [trace.name for trace in five_minute.data if trace.type == "candlestick"] == [
        "Observed TEST (5m)"
    ]
    assert len(five_minute.data[0].x) == 2

    panel = _price_marker_panel(_detail())
    graph = next(component for component in _walk(panel) if getattr(component, "id", None) == "price-marker-chart")
    bars = next(component for component in _walk(panel) if getattr(component, "id", None) == "price-chart-bars")
    view = next(component for component in _walk(panel) if getattr(component, "id", None) == "price-chart-view")
    assert [option["value"] for option in bars.options] == ["1m", "5m", "15m", "1D"]
    assert [option["value"] for option in view.options] == ["Full run", "1D", "1W", "1M"]
    assert bars.value == "1m"
    assert view.value == "1D"
    assert graph.config["scrollZoom"] is True


def test_large_results_series_are_bounded_for_the_browser_without_changing_evidence() -> None:
    rows = tuple(
        {"timestamp": f"2026-01-{1 + (index // 1440):02d}T00:00:00+00:00", "value": float(index)}
        for index in range(10_000)
    )

    displayed, sampled = _bounded_curve_rows(rows, y_field="value")

    assert sampled is True
    assert len(displayed) == 1_500
    assert displayed[0] == rows[0]
    assert displayed[-1] == rows[-1]
    assert len(rows) == 10_000


def test_representative_drawdown_display_retains_the_worst_observation() -> None:
    rows = tuple(
        {
            "timestamp": f"2026-01-{1 + (index // 1440):02d}T00:00:00+00:00",
            "drawdown": -0.9 if index == 4_321 else -(index % 17) / 100,
        }
        for index in range(10_000)
    )

    displayed, sampled = _bounded_curve_rows(rows, y_field="drawdown")

    assert sampled is True
    assert min(row["drawdown"] for row in displayed) == -0.9


def test_selected_long_trade_expands_the_view_to_keep_both_markers_visible() -> None:
    base = _detail()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prices = tuple(
        {
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
        }
        for index in range(4_320)
    )
    entry_time = prices[100]["timestamp"]
    exit_time = prices[4_000]["timestamp"]
    trade = {
        "Status": "Closed",
        "Direction": "Long",
        "Entry Index": entry_time,
        "Exit Index": exit_time,
        "Avg Entry Price": 100.0,
        "Avg Exit Price": 100.5,
        "Size": 1.0,
    }
    detail = replace(
        base,
        evidence=replace(
            base.evidence,
            price_series=prices,
            trades=(trade,),
        ),
    )

    figure, _ = _price_marker_figure(
        detail,
        interval="1m",
        view="1D",
        selected_trade_index=1,
    )
    exact_event_times = {
        item[1]
        for trace in figure.data
        if trace.type == "scatter"
        for item in trace.customdata
    }

    assert exact_event_times == {entry_time, exit_time}
    assert len(figure.data[0].x) > 1_440


def test_mes_workspace_keeps_native_five_minute_bars_and_index_point_prices() -> None:
    base = _detail()
    prices = tuple(
        {
            "timestamp": f"2026-01-02T14:{30 + (index * 5):02d}:00+00:00",
            "open": 6000.0 + index,
            "high": 6002.0 + index,
            "low": 5999.0 + index,
            "close": 6001.0 + index,
        }
        for index in range(6)
    )
    detail = SelectedRunDetailView(
        **{
            **base.__dict__,
            "market_data": (
                DetailField("Symbol", "MES"),
                DetailField("Timeframe", "5m"),
            ),
            "evidence": RunEvidenceView(
                **{
                    **base.evidence.__dict__,
                    "trades": (),
                    "price_series": prices,
                    "benchmark": None,
                    "source_interval": "5m",
                    "price_unit": "index_points",
                }
            ),
        }
    )

    figure, availability = _price_marker_figure(detail)
    candlesticks = [trace for trace in figure.data if trace.type == "candlestick"]

    assert [trace.name for trace in candlesticks] == ["Observed MES (5m)"]
    assert figure.layout.yaxis.tickformat == ",.2f"
    assert figure.layout.yaxis.title.text == "MES price (index points)"
    assert "index points" in candlesticks[0].hovertemplate
    assert "$" not in candlesticks[0].hovertemplate
    assert "actual 5m bars for 1W" in availability

    unavailable, reason = _price_marker_figure(detail, interval="1m", view="1D")
    assert not unavailable.data
    assert "finer than the persisted 5m source" in reason
    panel = _price_marker_panel(detail)
    bars = next(component for component in _walk(panel) if getattr(component, "id", None) == "price-chart-bars")
    assert bars.options[0]["disabled"] is True
    assert "1m: Bars interval 1m is finer than the persisted 5m source" in str(panel)


def test_ranked_result_summary_exposes_all_fifteen_rows_in_existing_grid() -> None:
    table_rows = tuple(
        {
            "ranking_position": rank,
            "range_minutes": 5 * rank,
            "breakout_offset_ticks": rank % 3,
            "total_return": rank / 100,
            "screening_status": "screened_out",
            "screening_reason": f"Rejected by rule {rank}",
        }
        for rank in range(1, 16)
    )
    summary = ResultSummaryView(
        status="available",
        message="Persisted ranked screening results.",
        rows=((DetailField("Rank", "1"),),),
        table_rows=table_rows,
    )

    rendered = _result_summary(summary)
    grid = next(component for component in _walk(rendered) if hasattr(component, "rowData"))

    assert len(grid.rowData) == 15
    assert grid.rowData[0]["screening_reason"] == "Rejected by rule 1"
    assert grid.rowData[-1]["screening_reason"] == "Rejected by rule 15"
    assert grid.dashGridOptions["paginationPageSize"] == 15
    assert grid.dashGridOptions["domLayout"] == "autoHeight"
    assert grid.style == {"width": "100%"}


def test_results_report_reuses_existing_metrics_and_trade_explorer() -> None:
    report = _results_report_tabs(_detail())
    rendered = str(report)

    assert [tab.label for tab in report.children] == ["Metrics", "Trades"]
    assert rendered.count("id='selected-trade-grid'") == 1
    assert rendered.count("id='trade-explorer-summary'") == 1


def test_trade_selection_linkage_is_scoped_and_grid_uses_normal_page_flow() -> None:
    explorer = trade_explorer_layout()
    grid = next(
        component
        for component in _walk(explorer)
        if getattr(component, "id", None) == "selected-trade-grid"
    )
    assert grid.dashGridOptions["domLayout"] == "autoHeight"
    assert grid.dashGridOptions["paginationPageSize"] == 12
    assert grid.style == {"width": "100%"}
    assert "results-chart-focus-status" in str(explorer)

    normalized = normalize_trade_rows(_detail().evidence.trades, run_id="run-test")
    assert normalized[0]["__trade_index"] == 1


def test_reset_layout_asset_changes_dimensions_only() -> None:
    source = (
        Path(__file__).parents[1]
        / "dashboard"
        / "assets"
        / "results_beta_resize.js"
    ).read_text(encoding="utf-8")

    assert "--qf-results-chart-height" in source
    assert "--qf-results-report-min-height" in source
    assert "removeProperty" in source
    assert "qfResults.focusTrade" in source
    assert "graph.data" in source
    assert "Plotly.restyle" in source
    assert "Plotly.relayout" not in source
    assert "without changing Bars or View" in source
    assert "Plotly.react" not in source
    assert "Plotly.newPlot" not in source
    for forbidden in ("interval =", "view =", "selectedTrade", "results-report-tabs"):
        assert forbidden not in source


def test_results_layout_contract_runs_in_portable_ci() -> None:
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "test.yml"
    ).read_text(encoding="utf-8")

    assert "tests/test_results_beta_layout.py" in workflow
