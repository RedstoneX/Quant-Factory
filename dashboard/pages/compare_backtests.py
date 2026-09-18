"""Read-only Compare page for persisted research runs."""

from __future__ import annotations

from dash import dcc, html

from dashboard.components.compare_results import compare_empty, compare_loading
from orchestration import RunSummary


def comparison_selector_options(
    recent_runs: tuple[RunSummary, ...],
) -> list[dict[str, str]]:
    """Give otherwise-identical persisted tests a stable readable identity."""

    from dashboard.application import _backtest_selector_label, _ordered_backtests

    return [
        {
            "label": f"{_backtest_selector_label(run)} · Test {run.run_id}",
            "value": run.run_id,
        }
        for run in _ordered_backtests(recent_runs)
    ]


def layout(*, recent_runs: tuple[RunSummary, ...] = ()) -> html.Div:
    """Mount Compare controls and stable output regions once."""

    from dashboard.application import (
        _default_comparison_values,
        _strategy_research_path,
    )

    selected_values = _default_comparison_values(recent_runs)
    initial_state = (
        compare_loading(selected_values) if selected_values else compare_empty()
    )
    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P("RESEARCH / COMPARE", className="page-eyebrow"),
                            html.H1("Compare results", className="page-title"),
                            html.P(
                                "Compare persisted tests without hiding evidence, "
                                "review, data, or assumption differences.",
                                className="page-description",
                            ),
                        ]
                    ),
                    html.Button(
                        "Refresh",
                        id="refresh-comparisons",
                        n_clicks=0,
                        className="secondary-action page-action",
                        title=(
                            "Retry reading persisted comparison evidence. "
                            "No test will run or change."
                        ),
                    ),
                ],
                className="page-heading page-heading-with-actions",
            ),
            _strategy_research_path("/research/compare-backtests"),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Selection", className="section-kicker"),
                            html.H2("Choose persisted tests"),
                            html.P(
                                "Select two or more saved tests, then read their "
                                "recorded evidence. This selection is independent of Results.",
                                className="section-description",
                            ),
                        ],
                        className="section-heading-row",
                    ),
                    html.Div(
                        [
                            html.Label(
                                "Selected tests",
                                htmlFor="comparison-run-selector",
                                className="field-label",
                            ),
                            dcc.Dropdown(
                                id="comparison-run-selector",
                                options=comparison_selector_options(recent_runs),
                                value=selected_values,
                                multi=True,
                                placeholder="Select at least two persisted tests",
                                persistence=True,
                                persistence_type="session",
                            ),
                            html.P(
                                "Your Compare selection is kept for this browser session.",
                                className="field-help compact-field-help",
                            ),
                        ],
                        className="comparison-selector-control",
                    ),
                    html.Button(
                        "Compare selected tests",
                        id="compare-selected-runs",
                        n_clicks=0,
                        className="primary-action page-action",
                        title="Read immutable persisted evidence for the selected tests.",
                    ),
                ],
                className="comparison-setup-panel",
            ),
            html.Div(
                dcc.Loading(
                    html.Div(
                        initial_state,
                        id="run-comparison-output",
                        className="run-comparison-output",
                    ),
                    id="comparison-loading",
                    type="circle",
                ),
                id="comparison-operator-contexts",
                className="comparison-operator-contexts",
            ),
        ],
        className="page-container comparison-page",
    )


__all__ = ["comparison_selector_options", "layout"]
