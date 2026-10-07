"""Explicit presentation boundary for Results-owned dashboard callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ResultsViewServices:
    """Rendering collaborators supplied by the dashboard composition root."""

    backtest_selector_label: Callable[..., Any]
    configuration_is_launchable: Callable[..., Any]
    operator_message: Callable[..., Any]
    parameter_variant_selection: Callable[..., Any]
    empty_price_marker_figure: Callable[..., Any]
    price_marker_figure: Callable[..., Any]
    preferred_backtest_id: Callable[..., Any]
    recent_events_panel: Callable[..., Any]
    recent_runs_panel: Callable[..., Any]
    run_detail_panel: Callable[..., Any]
    results_report_tabs: Callable[..., Any]
    results_supporting_charts: Callable[..., Any]
    results_operator_context: Callable[..., Any]
    selector_options: Callable[..., Any]
