"""Compare Backtests page layout."""

from __future__ import annotations

from dash import html

from orchestration import RunSummary


def layout(*, recent_runs: tuple[RunSummary, ...] = ()) -> html.Div:
    from dashboard.application import _comparisons_page

    return _comparisons_page(recent_runs=recent_runs)
