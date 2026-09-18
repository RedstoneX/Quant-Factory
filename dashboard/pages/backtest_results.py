"""Backtest Results page layout."""

from __future__ import annotations

from typing import Any

from dash import html

from dashboard.run_adapter import SavedConfigurationView
from orchestration import RunEvent, RunSummary


def layout(
    *,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    recent_runs: tuple[RunSummary, ...] = (),
    recent_events: tuple[RunEvent, ...] = (),
    selected_run_panel: Any | None = None,
    selected_run_id: str | None = None,
    all_runs: tuple[RunSummary, ...] = (),
    history_rows: tuple[dict[str, object], ...] = (),
) -> html.Div:
    from dashboard.application import _runs_page

    return _runs_page(
        configurations=configurations,
        recent_runs=recent_runs,
        recent_events=recent_events,
        selected_run_panel=selected_run_panel,
        selected_run_id=selected_run_id,
        all_runs=all_runs,
        history_rows=history_rows,
    )
