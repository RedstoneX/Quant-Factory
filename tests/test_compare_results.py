"""Focused rendering and callback contracts for persisted-run Compare."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import Dash, dcc, html
from dash.exceptions import PreventUpdate
import pytest

from dashboard.callbacks.compare_backtests import register_compare_backtests_callbacks
from dashboard.compare_adapter import (
    ComparabilityFinding,
    CompareDifferenceField,
    CompareDifferenceGroup,
    CompareDifferenceValue,
    CompareMetricRow,
    CompareMetricValue,
    CompareRunIdentity,
    CompareSeries,
    CompareSeriesPoint,
    CompareViewModel,
)
from dashboard.components.compare_results import (
    compare_empty,
    compare_failure,
    compare_loading,
    compare_results,
)
from dashboard.pages.compare_backtests import layout as compare_page


def _run(position: int, run_id: str, *, available: bool = True) -> CompareRunIdentity:
    return CompareRunIdentity(
        position=position,
        run_id=run_id,
        available=available,
        results_href=f"/research/backtest-results?run_id={run_id}",
        strategy=f"Fixture {position}@1.0.0",
        instrument="SPY" if available else "Unavailable",
        timeframe="1d" if available else "Unavailable",
        requested_period="2024-01-01/2024-01-03",
        actual_period="2024-01-01/2024-01-03" if available else "Unavailable",
        run_status="Succeeded" if available else "Unavailable",
        evidence_outcome="Passed" if available else "Not run",
        human_review="Unreviewed" if position == 1 else "Watchlist",
        omissions=() if available else ("Data provenance is unavailable.",),
        errors=() if available else ("Persisted run is unavailable.",),
    )


def _model(*, blocked: bool = False, partial: bool = False) -> CompareViewModel:
    runs = (_run(1, "run-a"), _run(2, "run-b", available=not partial))
    metrics = (
        CompareMetricRow(
            key="total_return",
            label="Total return",
            state="changed" if not partial else "missing",
            values=(
                CompareMetricValue(
                    "run-a",
                    0.1,
                    "10.00%",
                    "Rank 1 persisted parameter result; screening passed",
                ),
                CompareMetricValue(
                    "run-b",
                    None if partial else 0.2,
                    "Unavailable" if partial else "20.00%",
                    (
                        "No persisted ranked result"
                        if partial
                        else "Rank 1 persisted parameter result; screening passed"
                    ),
                    "Metric is absent from the persisted ranked result."
                    if partial
                    else None,
                ),
            ),
            basis_warning=(
                "Headline metric bases differ or are unavailable."
                if partial
                else None
            ),
        ),
    )
    first_points = (
        CompareSeriesPoint("2024-01-01T00:00:00Z", 100.0),
        CompareSeriesPoint("2024-01-02T00:00:00Z", 105.0),
    )
    second_points = () if partial else (
        CompareSeriesPoint("2024-01-01T00:00:00Z", 100.0),
        CompareSeriesPoint("2024-01-02T00:00:00Z", 97.0),
    )
    equity = (
        CompareSeries("run-a", "Fixture 1 · SPY · 1d", "Start = 100", first_points),
        CompareSeries(
            "run-b",
            "Fixture 2 · SPY · 1d",
            "Start = 100",
            second_points,
            "No validated persisted equity curve is available." if partial else None,
        ),
    )
    drawdown = (
        CompareSeries(
            "run-a",
            "Fixture 1 · SPY · 1d",
            "Peak-relative drawdown",
            (
                CompareSeriesPoint("2024-01-01T00:00:00Z", 0.0),
                CompareSeriesPoint("2024-01-02T00:00:00Z", 0.0),
            ),
        ),
        CompareSeries(
            "run-b",
            "Fixture 2 · SPY · 1d",
            "Peak-relative drawdown",
            () if partial else (
                CompareSeriesPoint("2024-01-01T00:00:00Z", 0.0),
                CompareSeriesPoint("2024-01-02T00:00:00Z", -0.03),
            ),
            "No validated persisted equity curve is available." if partial else None,
        ),
    )
    differences = (
        CompareDifferenceGroup(
            "parameters",
            "Parameters",
            (
                CompareDifferenceField(
                    "window",
                    "Window",
                    "changed",
                    (
                        CompareDifferenceValue("run-a", "10", True),
                        CompareDifferenceValue("run-b", "20", True),
                    ),
                ),
            ),
        ),
        CompareDifferenceGroup(
            "data",
            "Data, provider and period",
            (
                CompareDifferenceField(
                    "provider",
                    "Provider",
                    "equal" if not partial else "missing",
                    (
                        CompareDifferenceValue("run-a", "fixture", True),
                        CompareDifferenceValue(
                            "run-b",
                            "Unavailable" if partial else "fixture",
                            not partial,
                            "Persisted value is unavailable." if partial else None,
                        ),
                    ),
                ),
            ),
        ),
        CompareDifferenceGroup("execution", "Execution and costs", ()),
        CompareDifferenceGroup("evidence", "Evidence", ()),
        CompareDifferenceGroup("review", "Human review", ()),
    )
    findings = (
        ComparabilityFinding(
            "actual_period" if blocked else "review_differences",
            "blocking" if blocked else "warning",
            (
                "Selected runs use different data windows."
                if blocked
                else "Selected runs have different human review values."
            ),
            ("run-a", "run-b"),
        ),
    )
    if partial:
        findings += (
            ComparabilityFinding(
                "equity_unavailable",
                "blocking",
                "Normalized equity and drawdown cannot be compared for every selected run.",
                ("run-b",),
            ),
        )
    return CompareViewModel(
        requested_run_ids=("run-a", "run-b"),
        runs=runs,
        metric_rows=metrics,
        equity_series=equity,
        drawdown_series=drawdown,
        difference_groups=differences,
        findings=findings,
        directly_comparable=not blocked and not partial,
    )


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def _text(component: Any) -> str:
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, str):
            values.append(value)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                collect(item)
            return
        if hasattr(value, "to_plotly_json"):
            collect(getattr(value, "children", None))

    collect(component)
    return " ".join(values)


def _by_id(component: Any, component_id: str):
    return next(item for item in _walk(component) if getattr(item, "id", None) == component_id)


def test_compare_results_renders_identities_quartets_warnings_before_charts_and_links() -> None:
    rendered = compare_results(_model(blocked=True))
    text = _text(rendered)

    assert rendered.to_plotly_json()["props"]["data-directly-comparable"] == "false"
    assert text.count("Run status") == 2
    assert text.count("Evidence outcome") == 2
    assert text.count("Human decision") == 2
    assert text.count("Next safe action") == 2
    assert "Record decision" in text
    assert "No action available" in text
    assert "Direct comparison is blocked" in text
    assert "Selected runs use different data windows." in text
    assert "Aligned headline metrics" in text
    assert "Basis: Rank 1 persisted parameter result; screening passed" in text
    assert "Parameters" in text
    assert "Data, provider and period" in text

    children = rendered.children
    findings_index = next(
        index for index, child in enumerate(children) if getattr(child, "id", None) == "comparison-findings"
    )
    chart_index = next(
        index
        for index, child in enumerate(children)
        if "compare-chart-section" in str(getattr(child, "className", ""))
    )
    assert findings_index < chart_index

    cards = [
        item
        for item in _walk(rendered)
        if "compare-run-card" in str(getattr(item, "className", ""))
    ]
    assert [card.to_plotly_json()["props"]["data-run-id"] for card in cards] == [
        "run-a",
        "run-b",
    ]
    links = [item for item in _walk(rendered) if isinstance(item, dcc.Link)]
    assert [link.href for link in links] == [
        "/research/backtest-results?run_id=run-a",
        "/research/backtest-results?run_id=run-b",
    ]


def test_compare_charts_use_only_persisted_points_and_label_every_trace() -> None:
    rendered = compare_results(_model())
    equity = _by_id(rendered, "comparison-equity-chart").figure
    drawdown = _by_id(rendered, "comparison-drawdown-chart").figure

    assert len(equity.data) == 2
    assert list(equity.data[0].x) == [
        "2024-01-01T00:00:00Z",
        "2024-01-02T00:00:00Z",
    ]
    assert list(equity.data[0].y) == [100.0, 105.0]
    assert list(equity.data[1].y) == [100.0, 97.0]
    assert "run-a" in equity.data[0].name
    assert "run-b" in equity.data[1].name
    assert list(drawdown.data[1].y) == [0.0, -0.03]
    assert all(trace.connectgaps is False for trace in (*equity.data, *drawdown.data))


def test_partial_evidence_omits_unsupported_trace_and_labels_every_gap() -> None:
    rendered = compare_results(_model(partial=True))
    text = _text(rendered)
    equity = _by_id(rendered, "comparison-equity-chart").figure

    assert len(equity.data) == 1
    assert equity.data[0].name.endswith("run-a")
    assert "run-b: No validated persisted equity curve is available." in text
    assert "Unavailable" in text
    assert "Persisted value is unavailable." in text
    assert "This persisted test is unavailable." in text
    assert "Persisted run is unavailable." in text
    assert "Comparison is blocked" in text


def test_loading_empty_and_failure_states_keep_safe_read_only_guidance() -> None:
    loading = compare_loading(("run-a", "run-b"))
    empty = compare_empty()
    failure = compare_failure(("run-a", "run-b"), "database unavailable")

    assert loading.to_plotly_json()["props"]["aria-busy"] == "true"
    assert "run-a" in _text(loading)
    assert "No test will run or change" in _text(loading)
    assert "Select at least two saved tests" in _text(empty)
    assert "selected tests are unchanged" in _text(failure)
    assert "Choose Refresh to retry reading" in _text(failure)
    assert "database unavailable" in _text(failure)


def test_compare_page_persists_only_its_selection_in_session() -> None:
    page = compare_page()
    selector = _by_id(page, "find-compare-grid")

    assert selector.selectedRows == []
    assert selector.dashGridOptions["rowSelection"]["mode"] == "multiRow"
    assert selector.columnSize == "responsiveSizeToFit"
    assert selector.persistence is True
    assert selector.persistence_type == "session"
    assert selector.persisted_props == ["filterModel", "columnState"]
    assert _by_id(page, "find-compare-search").persistence is True
    assert _by_id(page, "find-compare-reset-view") is not None
    assert _by_id(page, "find-compare-grid-count") is not None
    assert [column["field"] for column in selector.columnDefs if not column.get("hide")] == [
        "created_at",
        "instrument",
        "interval",
        "strategy",
        "evidence",
        "total_return",
        "max_drawdown",
        "win_rate",
        "sharpe_ratio",
        "number_of_trades",
    ]
    labels_by_field = {
        column["field"]: column["headerName"] for column in selector.columnDefs
    }
    assert labels_by_field["total_return"] == "Total return"
    assert labels_by_field["max_drawdown"] == "Max drawdown"
    assert labels_by_field["win_rate"] == "Win rate"
    assert _by_id(page, "comparison-loading") is not None
    assert "Each row is one saved test" in _text(page)


class _CompareAdapter:
    def __init__(self, model: CompareViewModel | None = None, error: Exception | None = None):
        self.model = model
        self.error = error
        self.reads: list[tuple[str, ...]] = []

    def compare(self, run_ids):
        selected = tuple(run_ids)
        self.reads.append(selected)
        if self.error:
            raise self.error
        assert self.model is not None
        return self.model


class _RunService:
    def __init__(self) -> None:
        self.recent_reads = 0

    def all_history(self, *, artifact_root=None):
        self.recent_reads += 1
        return ()

    def reproduce_fixture_run(self, run_id: str, *, artifact_root: Path):
        raise AssertionError("Compare must not reproduce a run")


class _DetailAdapter:
    artifact_root = Path(".")


def _callback(app: Dash, output_fragment: str, input_id: str):
    entry = next(
        value
        for key, value in app.callback_map.items()
        if output_fragment in key
        and any(item["id"] == input_id for item in value.get("inputs", ()))
    )
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def _callback_app(adapter: _CompareAdapter) -> tuple[Dash, _RunService]:
    app = Dash(__name__, suppress_callback_exceptions=True)
    runs = _RunService()
    register_compare_backtests_callbacks(
        app,
        runs=runs,
        detail_adapter=_DetailAdapter(),
        dashboard_database=Path("unused.sqlite3"),
        artifact_root=Path("."),
        compare_adapter=adapter,
    )
    return app, runs


def test_compare_callback_is_route_gated_and_refresh_retries_only_the_read() -> None:
    adapter = _CompareAdapter(_model())
    app, runs = _callback_app(adapter)
    compare = _callback(app, "run-comparison-output", "refresh-comparisons")
    options = _callback(app, "find-compare-grid.rowData", "refresh-comparisons")
    option_inputs = {
        (item["id"], item["property"])
        for item in app.callback_map["find-compare-grid.rowData"]["inputs"]
    }
    comparison_output = next(
        value
        for key, value in app.callback_map.items()
        if "run-comparison-output.children" in key
    )
    comparison_inputs = {
        (item["id"], item["property"])
        for item in comparison_output["inputs"]
    }

    assert option_inputs == {
        ("refresh-comparisons", "n_clicks"),
        ("url", "pathname"),
        ("url", "search"),
    }
    assert comparison_inputs == {
        ("refresh-comparisons", "n_clicks"),
        ("url", "pathname"),
        ("url", "search"),
    }
    assert all("reproduction-message" not in key for key in app.callback_map)

    with pytest.raises(PreventUpdate):
        compare(0, "/research/setup", "?run_id=run-a&run_id=run-b")
    assert adapter.reads == []

    first, first_class = compare(
        0,
        "/research/compare-backtests",
        "?run_id=run-a&run_id=run-b",
    )
    refreshed, refreshed_class = compare(
        1,
        "/research/compare-backtests",
        "?run_id=run-a&run_id=run-b",
    )
    assert first_class == refreshed_class == "run-comparison-output"
    assert _by_id(first, "comparison-equity-chart") is not None
    assert _by_id(refreshed, "comparison-equity-chart") is not None
    assert adapter.reads == [("run-a", "run-b"), ("run-a", "run-b")]

    with pytest.raises(PreventUpdate):
        options(0, "/", None)
    assert options(1, "/research/compare-backtests", None) == []
    assert runs.recent_reads == 1


def test_compare_callback_retains_identities_on_read_failure() -> None:
    adapter = _CompareAdapter(error=RuntimeError("persisted store unavailable"))
    app, _ = _callback_app(adapter)
    compare = _callback(app, "run-comparison-output", "refresh-comparisons")

    rendered, class_name = compare(
        0,
        "/research/compare-backtests",
        "?run_id=run-a&run_id=run-b",
    )

    assert class_name == "run-comparison-output"
    assert "run-a" in _text(rendered)
    assert "run-b" in _text(rendered)
    assert "Choose Refresh to retry reading" in _text(rendered)
    assert "persisted store unavailable" in _text(rendered)
