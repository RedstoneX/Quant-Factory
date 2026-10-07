"""Shared helpers for assertions over deferred Results tab content."""

from dashboard.application import _results_report_tab_content
from dashboard.run_detail_adapter import SelectedRunDetailView


def render_results_tabs(detail: SelectedRunDetailView | None) -> str:
    return "".join(
        str(_results_report_tab_content(tab, detail))
        for tab in ("metrics", "trades", "variants", "evidence", "assumptions")
    )
