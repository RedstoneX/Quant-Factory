"""Narrow contracts for the reused selected-run Results beta workspace."""

from __future__ import annotations

from pathlib import Path

from dashboard.application import (
    _price_marker_figure,
    _price_marker_panel,
    _results_report_tabs,
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
        ),
        warnings=(),
    )


def test_price_workspace_reuses_plotly_with_independent_bars_and_view_controls() -> None:
    figure, availability = _price_marker_figure(_detail())

    candlesticks = [trace for trace in figure.data if trace.type == "candlestick"]
    assert [trace.name for trace in candlesticks] == [
        "Observed TEST (1m)",
        "Observed TEST (5m)",
        "Observed TEST (15m)",
        "Observed TEST (1D)",
    ]
    assert [len(trace.x) for trace in candlesticks] == [6, 2, 1, 1]
    assert availability == "All persisted display intervals are available."
    assert figure.layout.dragmode == "pan"

    bars_menu, view_menu = figure.layout.updatemenus
    assert [button.label for button in bars_menu.buttons] == ["1m", "5m", "15m", "1D"]
    assert {button.method for button in bars_menu.buttons} == {"restyle"}
    assert [button.label for button in view_menu.buttons] == ["Full run", "1D", "1W", "1M"]
    assert {button.method for button in view_menu.buttons} == {"relayout"}
    assert all("xaxis" not in str(button.args) for button in bars_menu.buttons)
    assert all("visible" not in str(button.args) for button in view_menu.buttons)

    graph = _price_marker_panel(_detail()).children[0]
    assert graph.config["scrollZoom"] is True


def test_results_report_reuses_existing_metrics_and_trade_explorer() -> None:
    report = _results_report_tabs(_detail())
    rendered = str(report)

    assert [tab.label for tab in report.children] == ["Metrics", "Trades"]
    assert rendered.count("id='selected-trade-grid'") == 1
    assert rendered.count("id='trade-explorer-summary'") == 1


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
    for forbidden in ("interval =", "view =", "selectedTrade", "results-report-tabs"):
        assert forbidden not in source
