"""Shared helpers for assertions over deferred Results tab content."""

from dashboard.application import _results_report_tab_content
from dashboard.run_detail_adapter import SelectedRunDetailView


def render_results_tabs(detail: SelectedRunDetailView | None) -> str:
    return "".join(
        str(_results_report_tab_content(tab, detail))
        for tab in ("metrics", "trades", "variants", "evidence", "assumptions")
    )


def render_selected_results(app, callback_lookup, run_id: str, inspect_args: tuple) -> str:
    inspect = callback_lookup(app, "selected-run-detail")
    load_tab = callback_lookup(app, "results-report-tab-content")
    return str(inspect(*inspect_args)) + "".join(
        str(load_tab(tab, run_id, "/research/backtest-results", None))
        for tab in ("metrics", "trades", "variants", "evidence", "assumptions")
    )
