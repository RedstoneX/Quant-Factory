"""Deterministic product proof for the one-study parameter-variant explorer."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dash import Dash

from dashboard.application import (
    _parameter_variant_selection,
    _parameter_variants_explorer,
    _results_report_tabs,
    _results_view_services,
)
from dashboard.callbacks.backtest_results import (
    _requested_results_parameter_row_id,
    register_backtest_results_callbacks,
)
from dashboard.run_detail_adapter import DetailField, ResultSummaryView
from orchestration import DurableResearchLaunchService


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = (children,)
    for child in children:
        yield from _walk(child)


def _row(index: int, *, run_id: str = "run-many") -> dict[str, Any]:
    row_id = f"row-{index:04d}"
    parameters = {
        "entry_window": 5 + index % 30,
        "stop_ticks": 2 + index % 12,
    }
    metrics = {
        "total_return": (index - 1_000) / 100_000,
        "max_drawdown": -(index % 250) / 10_000,
        "sharpe_ratio": (index % 80) / 20,
        "number_of_trades": 40 + index % 400,
    }
    status = "passed" if index % 7 == 0 else "screened_out"
    reason = "" if status == "passed" else f"Fixed rule rejected row {index}"
    return {
        "variant_key": f"{run_id}:{row_id}",
        "parameter_row_id": row_id,
        "__run_id": run_id,
        "__parameters": parameters,
        "__metrics": metrics,
        "ranking_position": index + 1,
        **parameters,
        **metrics,
        "screening_status": status,
        "screening_reason": reason,
    }


def _summary(count: int = 2_000) -> ResultSummaryView:
    rows = tuple(_row(index) for index in range(count))
    return ResultSummaryView(
        status="available",
        message="Artifact-validated ranked screening results.",
        rows=((DetailField("Rank", "1"),),),
        table_rows=rows,
    )


def _callback(app: Dash, output_fragment: str):
    entry = next(
        value
        for key, value in app.callback_map.items()
        if output_fragment in key and "callback" in value
    )
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def test_explorer_keeps_all_two_thousand_rows_in_one_bounded_grid() -> None:
    rendered = _parameter_variants_explorer(
        _summary(), selected_parameter_row_id="row-1999"
    )
    grid = next(
        item
        for item in _walk(rendered)
        if getattr(item, "id", None) == "parameter-results-grid"
    )

    assert len(grid.rowData) == 2_000
    assert grid.rowData[0]["ranking_position"] == 1
    assert grid.rowData[-1]["ranking_position"] == 2_000
    assert grid.selectedRows == [grid.rowData[-1]]
    assert grid.getRowId == "params.data.variant_key"
    assert grid.dashGridOptions["paginationPageSize"] == 50
    assert grid.dashGridOptions["rowSelection"]["mode"] == "multiRow"
    assert "domLayout" not in grid.dashGridOptions
    assert grid.style == {"height": "520px", "width": "100%"}
    displayed_fields = {definition["field"] for definition in grid.columnDefs}
    assert "parameter_row_id" not in displayed_fields
    assert "variant_key" not in displayed_fields
    assert {
        "entry_window",
        "stop_ticks",
        "total_return",
        "max_drawdown",
        "sharpe_ratio",
        "number_of_trades",
        "screening_status",
        "screening_reason",
    }.issubset(displayed_fields)


def test_exact_variant_request_opens_variants_tab() -> None:
    assert _results_report_tabs(None).children[0].value == "metrics"
    assert (
        _results_report_tabs(
            None, selected_parameter_row_id="row-0001"
        ).children[0].value
        == "variants"
    )


def test_variant_selection_is_exact_bounded_and_links_to_the_same_run_row() -> None:
    rows = tuple(_row(index) for index in range(5))
    one = str(_parameter_variant_selection(rows[:1]))
    four = str(_parameter_variant_selection(rows[:4]))
    five = str(_parameter_variant_selection(rows))

    assert "Rank 1" in one
    assert "entry window" in one.lower()
    assert "run_id=run-many" in one
    assert "parameter_row_id=row-0000" in one
    assert "run-level chart, trades, and equity" in four
    assert "Select up to four variants" in five


def test_parameter_variant_query_parser_fails_closed() -> None:
    assert _requested_results_parameter_row_id(None) == (False, None)
    assert _requested_results_parameter_row_id("?run_id=run-a") == (False, None)
    assert _requested_results_parameter_row_id(
        "?run_id=run-a&parameter_row_id=row%3Aone"
    ) == (True, "row:one")
    for search in (
        "?parameter_row_id=",
        "?parameter_row_id=row-a&parameter_row_id=row-b",
        "?parameter_row_id=bad%0Arow",
        "?parameter_row_id=%GG",
    ):
        assert _requested_results_parameter_row_id(search) == (True, None)


def test_variant_callbacks_count_reset_and_reject_cross_run_selection(
    tmp_path: Path,
) -> None:
    summary = _summary(12)

    class DetailAdapter:
        artifact_root = tmp_path

        def selected_run_detail(self, run_id: str):
            assert run_id == "run-many"
            return SimpleNamespace(result_summary=summary)

    app = Dash(__name__, suppress_callback_exceptions=True)
    register_backtest_results_callbacks(
        app,
        runs=SimpleNamespace(),
        detail_adapter=DetailAdapter(),
        configurations=(),
        readiness_by_id={},
        dashboard_database=tmp_path / "state.sqlite3",
        artifact_root=tmp_path,
        view=_results_view_services(),
        research_launches=DurableResearchLaunchService(
            database=tmp_path / "state.sqlite3"
        ),
    )

    counts = _callback(app, "parameter-variant-grid-count")
    reset = _callback(app, "parameter-variant-search.value")
    inspect = _callback(app, "parameter-variant-selection-detail")

    assert counts(list(summary.table_rows[:3]), list(summary.table_rows), [summary.table_rows[0]]) == (
        "3 matched · 1 selected"
    )
    assert reset(1) == ("", {}, True)
    assert "Rank 1" in str(
        inspect(
            [
                {
                    "parameter_row_id": "row-0000",
                    "__run_id": "run-many",
                    "variant_key": "run-many:row-0000",
                }
            ],
            "run-many",
            "/research/backtest-results",
        )
    )
    stale = str(
        inspect(
            [
                {
                    "parameter_row_id": "row-0000",
                    "__run_id": "another-run",
                    "variant_key": "another-run:row-0000",
                }
            ],
            "run-many",
            "/research/backtest-results",
        )
    )
    assert "No stale or cross-run row was substituted" in stale
