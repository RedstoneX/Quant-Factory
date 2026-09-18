"""Compare Backtests page callback ownership."""

from __future__ import annotations

from pathlib import Path

from dash import Dash, Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.application import (
    _active_route,
    _backtest_selector_label,
    _comparison_backtest_cards,
    _dashboard_persistence,
    _results_operator_context,
    _run_comparison_panel,
    _selector_options,
)
from dashboard.callbacks.review_state import load_durable_review
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService, RunServiceError


OWNED_STATE = {
    "comparison_selection": "comparison-run-selector.value",
}


def register_compare_backtests_callbacks(
    app: Dash,
    *,
    runs: FixtureRunService,
    detail_adapter: RunDetailDashboardAdapter,
    dashboard_database: str | Path,
    artifact_root: Path,
) -> None:
    """Register callbacks owned by the Compare Backtests route."""

    @app.callback(
        Output("comparison-run-selector", "options"),
        Input("refresh-comparisons", "n_clicks"),
        Input("refresh-runs", "n_clicks"),
    )
    def refresh_comparison_selector_options(_: int, __: int):
        return _selector_options(runs.recent_runs(limit=20))

    @app.callback(
        Output("comparison-selected-cards", "children"),
        Input("comparison-run-selector", "value"),
        Input("refresh-comparisons", "n_clicks"),
    )
    def refresh_comparison_selected_cards(
        run_ids: list[str] | tuple[str, ...] | None,
        _: int,
    ):
        recent_run_records = runs.recent_runs(limit=20)
        return _comparison_backtest_cards(
            recent_run_records,
            [str(run_id) for run_id in (run_ids or ())],
        )

    @app.callback(
        Output("comparison-operator-contexts", "children"),
        Input("comparison-run-selector", "value"),
        Input("refresh-comparisons", "n_clicks"),
        Input("review-message", "children"),
    )
    def refresh_comparison_operator_contexts(
        run_ids: list[str] | tuple[str, ...] | None,
        _refresh_clicks: int,
        _review_message: object,
    ):
        selected = [str(run_id) for run_id in (run_ids or ())]
        if not selected:
            return html.Div(
                "Select persisted backtests to inspect each run's context.",
                className="empty-state-copy",
            )

        contexts = []
        for index, run_id in enumerate(selected, start=1):
            try:
                run = runs.get_run(run_id)
            except (KeyError, ValueError, RunServiceError):
                run = None
            if run is None:
                contexts.append(
                    html.Article(
                        [
                            html.H3(f"Backtest {index}"),
                            html.P(run_id, className="comparison-trace-id"),
                            html.Div(
                                "This persisted backtest is unavailable.",
                                className="error-state",
                            ),
                        ],
                        className="comparison-run-context",
                        **{"data-run-id": run_id},
                    )
                )
                continue

            try:
                detail = detail_adapter.selected_run_detail(run_id)
            except (KeyError, RuntimeError, ValueError):
                detail = None
            try:
                review = load_durable_review(
                    dashboard_database,
                    artifact_root,
                    run_id,
                )
                human_decision = review.display_state
            except (KeyError, RuntimeError, ValueError):
                human_decision = "Unavailable"
            context = _results_operator_context(
                run,
                detail,
                human_decision=human_decision,
                component_id=f"compare-operator-context-{index}",
            )
            contexts.append(
                html.Article(
                    [
                        html.H3(_backtest_selector_label(run)),
                        html.P(run_id, className="comparison-trace-id"),
                        context,
                    ],
                    className="comparison-run-context",
                    **{"data-run-id": run_id},
                )
            )
        return contexts

    @app.callback(
        Output("run-comparison-output", "children"),
        Output("run-comparison-output", "className"),
        Input("compare-selected-runs", "n_clicks"),
        State("comparison-run-selector", "value"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def compare_selected_runs(
        _: int,
        run_ids: list[str] | tuple[str, ...] | None,
        pathname: str | None = "/research/compare-backtests",
    ):
        if not _active_route(pathname, "/research/compare-backtests"):
            raise PreventUpdate
        try:
            with _dashboard_persistence(dashboard_database) as service:
                comparison = service.compare_runs(tuple(run_ids or ()))
        except (KeyError, TypeError, RuntimeError) as exc:
            return (
                html.Div(
                    f"Backtest comparison failed: {exc}",
                    className="error-state",
                ),
                "run-comparison-output",
            )
        except ValueError as exc:
            detail = str(exc)
            if "at least two" in detail.lower():
                return (
                    html.Div(
                        "Select at least two persisted backtests before comparing.",
                        className="error-state",
                    ),
                    "run-comparison-output",
                )
            return (
                html.Div(
                    f"Backtest comparison failed: {detail}",
                    className="error-state",
                ),
                "run-comparison-output",
            )
        return _run_comparison_panel(comparison), "run-comparison-output"

    @app.callback(
        Output("reproduction-message", "children"),
        Output("reproduction-message", "className"),
        Output("run-comparison-output", "children", allow_duplicate=True),
        Output("run-comparison-output", "className", allow_duplicate=True),
        Output("comparison-run-selector", "value", allow_duplicate=True),
        Input("reproduce-selected-run", "n_clicks"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def reproduce_selected_run(
        n_clicks: int | None,
        run_id: str | None,
        pathname: str | None = "/research/backtest-results",
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        if not n_clicks:
            return no_update, no_update, no_update, no_update, no_update
        if not run_id:
            return (
                "No persisted run is selected for reproduction.",
                "reproduction-message error-state",
                html.Div(
                    "Run reproduction failed: no persisted run is selected.",
                    className="error-state",
                ),
                "run-comparison-output",
                no_update,
            )

        try:
            result = runs.reproduce_fixture_run(
                run_id,
                artifact_root=artifact_root,
            )
        except (KeyError, ValueError, RuntimeError, RunServiceError) as exc:
            return (
                f"Run reproduction failed: {exc}",
                "reproduction-message error-state",
                html.Div(
                    f"Run reproduction failed: {exc}",
                    className="error-state",
                ),
                "run-comparison-output",
                no_update,
            )

        notes = html.Ul([html.Li(note) for note in result.notes])
        return (
            html.Div(
                [
                    html.Strong(
                        (
                            f"Reproduced {result.original.run_id} as "
                            f"{result.reproduction.run_id}."
                        )
                    ),
                    notes,
                ],
                **{"data-run-id": result.reproduction.run_id},
            ),
            "reproduction-message reproduction-message-success",
            _run_comparison_panel(result.comparison),
            "run-comparison-output",
            [result.original.run_id, result.reproduction.run_id],
        )
