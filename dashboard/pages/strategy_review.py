"""Strategy Review page layout."""

from __future__ import annotations

from dash import html

from dashboard.application import DashboardContext
from orchestration import RunSummary


def layout(
    context: DashboardContext | None,
    *,
    recent_runs: tuple[RunSummary, ...] = (),
) -> html.Div:
    from dashboard.application import create_review_page

    return create_review_page(context, recent_runs=recent_runs)
