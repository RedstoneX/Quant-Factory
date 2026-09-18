"""Mounted run-test and results callback ownership."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from dash import Dash, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.components.operator_context import (
    OperatorContextViewModel,
    operator_context,
)
from dashboard.components.configuration_summary import configuration_summary
from dashboard.application import (
    _active_route,
    _backtest_selector_label,
    _callback_triggered_id,
    _configuration_is_launchable,
    _detail_has_backtest_evidence,
    _operator_message,
    _preferred_backtest_id,
    _recent_events_panel,
    _recent_runs_panel,
    _run_action_availability,
    _run_detail_panel,
    _run_launch_summary,
    _results_operator_context,
    _selector_options,
)
from dashboard.run_adapter import ConfigurationReadinessView, SavedConfigurationView
from dashboard.callbacks.review_state import load_durable_review
from dashboard.run_detail_adapter import (
    ResultSummaryView,
    RunDetailDashboardAdapter,
    RunEvidenceView,
    SelectedRunDetailView,
)
from orchestration import FixtureRunService, RunServiceError, RunSummary


OWNED_STATE = {
    "selected_backtest": ("selected-run-selector.value", "selected-run-state.data"),
}


_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_MAX_RESULTS_QUERY_LENGTH = 2_048
_MAX_RUN_ID_LENGTH = 256


def _requested_results_run_id(search: str | None) -> tuple[bool, str | None]:
    """Return whether Results was asked to adopt one syntactically safe run ID."""

    if not search:
        return False, None
    query = search[1:] if search.startswith("?") else search
    if len(query) > _MAX_RESULTS_QUERY_LENGTH or _INVALID_PERCENT_ESCAPE.search(query):
        return True, None
    try:
        pairs = parse_qsl(
            query,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=20,
        )
    except (UnicodeDecodeError, ValueError):
        return True, None
    values = [value for key, value in pairs if key == "run_id"]
    if not values:
        return False, None
    if len(values) != 1:
        return True, None
    run_id = values[0]
    if (
        not run_id.strip()
        or len(run_id) > _MAX_RUN_ID_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in run_id)
    ):
        return True, None
    return True, run_id


def _callback_triggered_ids() -> frozenset[str]:
    """Return every component that triggered the current Dash callback."""

    try:
        component_ids = {
            component_id
            for component_id in ctx.triggered_prop_ids.values()
            if isinstance(component_id, str)
        }
    except Exception:
        component_ids = set()
    primary = _callback_triggered_id()
    if primary:
        component_ids.add(primary)
    return frozenset(component_ids)


def register_backtest_results_callbacks(
    app: Dash,
    *,
    runs: FixtureRunService,
    detail_adapter: RunDetailDashboardAdapter,
    configurations: tuple[SavedConfigurationView, ...],
    readiness_by_id: dict[str, ConfigurationReadinessView],
    dashboard_database: str | Path,
    artifact_root: Path,
) -> None:
    """Register Run test and Results callbacks within their page boundaries."""

    @app.callback(
        Output("run-configuration-preview", "children"),
        Output("launch-run", "disabled"),
        Output("launch-run", "title"),
        Input("selected-configuration-state", "data"),
    )
    def preview_configuration(configuration_id: str | None):
        readiness = readiness_by_id.get(configuration_id or "")
        summary = configuration_summary(
            readiness,
            component_id="run-configuration-preview-content",
        )
        if readiness is None:
            return (
                summary.children,
                True,
                "The selected saved configuration could not be found.",
            )
        return (
            summary.children,
            not readiness.ready,
            (
                "Launch this immutable saved configuration."
                if readiness.ready
                else "Resolve every preflight blocker before running this test."
            ),
        )

    @app.callback(
        Output("launch-message", "children"),
        Output("launch-message", "className"),
        Output("run-test-operator-context", "children"),
        Output("run-test-operator-context", "className"),
        Input("launch-run", "n_clicks"),
        State("selected-configuration-state", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def launch_saved_configuration(
        _: int,
        configuration_id: str | None,
        pathname: str | None = "/research/run-test",
    ):
        if not _active_route(pathname, "/research/run-test"):
            raise PreventUpdate
        selected = next(
            (
                configuration
                for configuration in configurations
                if configuration.configuration_id == configuration_id
            ),
            None,
        )
        if selected is None:
            empty_context = operator_context(component_id="run-test-operator-context")
            return (
                _operator_message(
                    "Run launch did not start.",
                    "The selected saved configuration could not be found.",
                    tone="error",
                ),
                "save-message error-state",
                empty_context.children,
                empty_context.className,
            )
        readiness = readiness_by_id.get(selected.configuration_id)
        if readiness is None or not readiness.ready:
            empty_context = operator_context(component_id="run-test-operator-context")
            return (
                _operator_message(
                    "Run launch did not start.",
                    "The selected saved configuration did not pass preflight. Resolve every blocker before retrying.",
                    tone="error",
                ),
                "save-message error-state",
                empty_context.children,
                empty_context.className,
            )

        try:
            result = runs.launch_fixture(
                configuration_id=selected.configuration_id,
            )
        except (KeyError, ValueError, RunServiceError) as exc:
            empty_context = operator_context(component_id="run-test-operator-context")
            return (
                _operator_message(
                    "Run launch did not start.",
                    str(exc),
                    tone="error",
                ),
                "save-message error-state",
                empty_context.children,
                empty_context.className,
            )

        status = result.run.status.replace("_", " ").title()
        next_action = (
            "Inspect evidence"
            if result.run.status == "succeeded"
            else "Wait for completion"
            if result.run.status in {"created", "queued", "running", "retrying"}
            else "Review failure"
            if result.run.status in {"failed", "cancelled", "timed_out"}
            else "No action available"
        )
        run_context = operator_context(
            OperatorContextViewModel(
                selected_run=True,
                run_status=status,
                evidence_outcome="Unavailable",
                human_decision="Unavailable",
                next_safe_action=next_action,
            ),
            component_id="run-test-operator-context",
        )
        return (
            _run_launch_summary(result.run),
            "save-message",
            run_context.children,
            run_context.className,
        )

    @app.callback(
        Output("historical-launch-message", "children"),
        Output("historical-launch-message", "className"),
        Input("launch-selected-run-configuration", "n_clicks"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def launch_selected_run_configuration(
        n_clicks: int | None,
        run_id: str | None,
        pathname: str | None = "/research/backtest-results",
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        if not n_clicks:
            return no_update, no_update
        if not run_id:
            return (
                _operator_message(
                    "Run launch did not start.",
                    "No historical run is selected.",
                    tone="error",
                ),
                "historical-launch-message error-state",
            )

        try:
            selected_run = runs.get_run(run_id)
        except (KeyError, ValueError, RunServiceError) as exc:
            return (
                _operator_message(
                    "Run lookup failed.",
                    str(exc),
                    tone="error",
                ),
                "historical-launch-message error-state",
            )

        if selected_run is None:
            return (
                _operator_message(
                    "Run launch did not start.",
                    f"Selected run {run_id} could not be found.",
                    tone="error",
                ),
                "historical-launch-message error-state",
            )
        if not _configuration_is_launchable(
            selected_run.configuration_id,
            configurations,
        ):
            return (
                _operator_message(
                    "Run launch did not start.",
                    "The selected run's saved configuration is unavailable "
                    "or not launchable.",
                    tone="error",
                ),
                "historical-launch-message error-state",
            )

        try:
            result = runs.launch_fixture(
                configuration_id=selected_run.configuration_id,
            )
        except (KeyError, ValueError, RunServiceError) as exc:
            return (
                _operator_message(
                    "New run launch did not start.",
                    str(exc),
                    tone="error",
                ),
                "historical-launch-message error-state",
            )

        return (
            _run_launch_summary(result.run),
            "historical-launch-message historical-launch-message-success",
        )

    @app.callback(
        Output("reproduction-message", "children"),
        Output("reproduction-message", "className"),
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
            return no_update, no_update
        if not run_id:
            return (
                "No persisted run is selected for reproduction.",
                "reproduction-message error-state",
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
        )

    @app.callback(
        Output("selected-run-state", "data"),
        Input("selected-run-selector", "value"),
        Input("run-history-grid", "selectedRows", allow_optional=True),
        Input("url", "search"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
    )
    def preserve_selected_run(
        selected_run_id: str | None,
        history_rows: list[dict[str, Any]] | None = None,
        search: str | None = None,
        stored_run_id: str | None = None,
        pathname: str | None = "/research/backtest-results",
    ):
        triggered_ids = _callback_triggered_ids()
        triggered_id = _callback_triggered_id()

        def stored_run_is_valid() -> bool:
            if not stored_run_id:
                return False
            try:
                return runs.get_run(stored_run_id) is not None
            except (KeyError, ValueError, RunServiceError):
                return False

        query_requested, requested_run_id = _requested_results_run_id(search)
        should_consider_query = triggered_id is None or "url" in triggered_ids
        if should_consider_query and not _active_route(
            pathname,
            "/research/backtest-results",
        ):
            return no_update
        if should_consider_query and query_requested:
            if requested_run_id:
                try:
                    requested_run = runs.get_run(requested_run_id)
                except (KeyError, ValueError, RunServiceError):
                    requested_run = None
                if (
                    requested_run is not None
                    and requested_run.run_id == requested_run_id
                ):
                    return requested_run_id
            return no_update if stored_run_id else None
        if triggered_id == "run-history-grid" and history_rows:
            return history_rows[0].get("run_id") or stored_run_id
        if triggered_id == "selected-run-selector" and selected_run_id:
            return selected_run_id
        if triggered_id is None and stored_run_is_valid():
            return no_update
        if selected_run_id:
            return selected_run_id
        return no_update if stored_run_id else None

    @app.callback(
        Output("launch-selected-run-configuration", "disabled"),
        Output("launch-selected-run-configuration", "title"),
        Output("reproduce-selected-run", "disabled"),
        Output("reproduce-selected-run", "title"),
        Output("cancel-selected-run", "disabled"),
        Output("cancel-selected-run", "title"),
        Input("selected-run-state", "data"),
        Input("refresh-runs", "n_clicks"),
        Input("cancellation-message", "children"),
        Input("stale-recovery-message", "children"),
    )
    def update_selected_run_actions(
        run_id: str | None,
        _: int,
        __: int,
        ___: int,
    ):
        run = runs.get_run(run_id) if run_id else None
        return _run_action_availability(
            run,
            (
                run is not None
                and _configuration_is_launchable(
                    run.configuration_id,
                    configurations,
                )
            ),
        )

    @app.callback(
        Output("recent-runs-monitor", "children"),
        Output("recent-events-monitor", "children"),
        Input("refresh-runs", "n_clicks"),
        Input("launch-message", "children"),
        Input("historical-launch-message", "children", allow_optional=True),
        Input("reproduction-message", "children", allow_optional=True),
        Input("cancellation-message", "children", allow_optional=True),
        Input("stale-recovery-message", "children"),
    )
    def refresh_run_monitor(
        _: int,
        __: int,
        ___: int,
        ____: int,
        _____: int,
        ______: int,
    ):
        recent_run_records = runs.recent_runs(limit=20)
        recent_event_records = runs.recent_events(limit=20)
        return (
            _recent_runs_panel(recent_run_records),
            _recent_events_panel(recent_event_records),
        )

    @app.callback(
        Output("run-history-grid", "rowData"),
        Input("refresh-runs", "n_clicks"),
        Input("launch-message", "children"),
        Input("historical-launch-message", "children", allow_optional=True),
        Input("reproduction-message", "children", allow_optional=True),
        Input("review-message", "children", allow_optional=True),
        Input("cancellation-message", "children", allow_optional=True),
        Input("stale-recovery-message", "children"),
    )
    def refresh_run_history(
        *_: object,
    ):
        if hasattr(runs, "all_history"):
            return list(runs.all_history(artifact_root=detail_adapter.artifact_root))
        return [
            {
                "run_id": run.run_id,
                "created_at": run.created_at,
                "instrument": "Not recorded",
                "strategy": f"{run.strategy_id} {run.strategy_version}",
                "stage": run.stage,
                "status": run.status,
                "review": "Not checked",
                "evidence": "Unverified",
                "metric_basis": "No persisted ranked result",
                "total_return": None,
                "annualized_return": None,
                "sharpe_ratio": None,
                "number_of_trades": None,
                "artifact_status": "Unverified",
                "reproducibility": "Unverified",
            }
            for run in runs.recent_runs(limit=20)
        ]

    @app.callback(
        Output("selected-run-selector", "options"),
        Output("selected-run-selector", "value"),
        Input("refresh-runs", "n_clicks"),
        Input("launch-message", "children"),
        Input("historical-launch-message", "children", allow_optional=True),
        Input("reproduction-message", "children", allow_optional=True),
        Input("selected-run-state", "data"),
        State("selected-run-selector", "value"),
        State("selected-run-selector", "options"),
    )
    def refresh_run_selectors_after_launch(
        _refresh_clicks: int,
        launch_message: object,
        historical_launch_message: object,
        reproduction_message: object,
        stored_run_id: str | None,
        selected_run_id: str | None,
        selected_options: list[dict[str, str]] | None,
    ):
        recent_run_records = runs.recent_runs(limit=20)
        recent_runs_by_id = {run.run_id: run for run in recent_run_records}
        triggered_id = _callback_triggered_id()

        looked_up_runs: dict[str, RunSummary | None] = {}

        def valid_run(run_id: str | None) -> RunSummary | None:
            if not run_id:
                return None
            if run_id in recent_runs_by_id:
                return recent_runs_by_id[run_id]
            if run_id not in looked_up_runs:
                try:
                    looked_up_runs[run_id] = runs.get_run(run_id)
                except (KeyError, ValueError, RunServiceError):
                    looked_up_runs[run_id] = None
            return looked_up_runs[run_id]

        selected_run = valid_run(selected_run_id)
        stored_run = valid_run(stored_run_id)
        completion_messages = {
            "launch-message": launch_message,
            "historical-launch-message": historical_launch_message,
            "reproduction-message": reproduction_message,
        }

        def message_run_id(message: object) -> str | None:
            if message is None:
                return None
            if isinstance(message, dict):
                props = message.get("props")
                if isinstance(props, dict):
                    run_id = props.get("data-run-id")
                    if isinstance(run_id, str) and run_id:
                        return run_id
                    return message_run_id(props.get("children"))
                return None
            if isinstance(message, (list, tuple)):
                for item in message:
                    run_id = message_run_id(item)
                    if run_id:
                        return run_id
                return None
            to_plotly_json = getattr(message, "to_plotly_json", None)
            if callable(to_plotly_json):
                return message_run_id(to_plotly_json())
            return None

        completed_run_id = (
            message_run_id(completion_messages[triggered_id])
            if triggered_id in completion_messages
            else None
        )
        completed_run = valid_run(completed_run_id)
        completed_run_id = completed_run.run_id if completed_run is not None else None
        stored_state_has_priority = (
            triggered_id in {None, "selected-run-state"} and stored_run is not None
        )
        stable_selected_run_id = (
            stored_run_id
            if stored_state_has_priority
            else selected_run_id
            if selected_run is not None
            else stored_run_id
            if stored_run is not None
            else None
        )
        # Resolving chart evidence is only needed for initial selection. A
        # refresh with a valid operator selection must not reconstruct every
        # candidate portfolio before returning unchanged selector values.
        preferred_backtest_id = (
            _preferred_backtest_id(recent_run_records, detail_adapter)
            if stable_selected_run_id is None and completed_run_id is None
            else None
        )
        selected_value = (
            completed_run_id
            if completed_run_id is not None
            else stable_selected_run_id
            if stable_selected_run_id is not None
            else preferred_backtest_id
            if preferred_backtest_id is not None
            else None
        )
        initial_selector_hydration = triggered_id is None and bool(selected_options)
        options = _selector_options(recent_run_records)
        option_values = {option["value"] for option in options}
        for run in (completed_run, selected_run, stored_run):
            if run is not None and run.run_id not in option_values:
                options.append(
                    {
                        "label": _backtest_selector_label(run),
                        "value": run.run_id,
                    }
                )
                option_values.add(run.run_id)
        selector_options: Any = (
            no_update
            if (initial_selector_hydration and not stored_state_has_priority)
            or options == (selected_options or [])
            else options
        )
        selector_value: Any = no_update if selected_value == selected_run_id else selected_value
        return selector_options, selector_value

    @app.callback(
        Output("selected-run-detail", "children"),
        Input("selected-run-state", "data"),
        Input("selected-run-selector", "value"),
        Input("refresh-runs", "n_clicks"),
        Input("launch-message", "children"),
        Input("cancellation-message", "children", allow_optional=True),
        Input("stale-recovery-message", "children"),
    )
    def inspect_run(
        stored_run_id: str | None,
        selected_run_id: str | None,
        _: int,
        __: int,
        ___: int,
        ____: int,
    ):
        run_id = stored_run_id or selected_run_id
        if not run_id:
            return _run_detail_panel(None)

        run = runs.get_run(run_id)
        if run is None:
            return html.Section(
                [
                    html.H2("Run not found"),
                    html.P(
                        (
                            "The selected run no longer exists in the "
                            "Quant Factory state database."
                        ),
                        className="error-state",
                    ),
                ],
                className="panel run-detail-panel",
            )

        detail_view: SelectedRunDetailView | None
        try:
            detail_view = detail_adapter.selected_run_detail(run_id)
        except (KeyError, RuntimeError, ValueError) as exc:
            detail_view = SelectedRunDetailView(
                configuration_fields=(),
                parameters=(),
                market_data=(),
                execution=(),
                ranking=(),
                screening=(),
                lineage_fields=(),
                manifest_fields=(),
                artifacts=(),
                result_summary=ResultSummaryView(
                    status="empty",
                    message="No persisted result summary is available for this run.",
                    rows=(),
                ),
                evidence=RunEvidenceView(
                    notices=(),
                    metrics=(),
                    trades=(),
                    orders=(),
                    equity_curve=(),
                    drawdown_curve=(),
                    validation=(),
                    provenance=(),
                    warnings=(),
                ),
                warnings=(f"Run detail retrieval failed: {exc}",),
            )

        return _run_detail_panel(
            run,
            runs.events_for_run(run_id),
            detail=detail_view,
        )

    @app.callback(
        Output("results-operator-context", "children"),
        Output("results-operator-context", "className"),
        Input("selected-run-state", "data"),
        Input("refresh-runs", "n_clicks"),
        Input("review-message", "children"),
        Input("stale-recovery-message", "children"),
    )
    def update_results_operator_context(
        run_id: str | None,
        _refresh_clicks: int,
        _review_message: object,
        _stale_recovery_message: object = None,
    ):
        if not run_id:
            context = _results_operator_context(None)
            return context.children, context.className
        try:
            run = runs.get_run(run_id)
        except (KeyError, ValueError, RunServiceError):
            run = None
        if run is None:
            context = _results_operator_context(None)
            return context.children, context.className
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
        )
        return context.children, context.className

    @app.callback(
        Output("cancellation-message", "children"),
        Output("cancellation-message", "className"),
        Input("cancel-selected-run", "n_clicks"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def request_selected_run_cancellation(
        n_clicks: int | None,
        run_id: str | None,
        pathname: str | None = "/research/backtest-results",
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        if not n_clicks:
            return no_update, no_update
        if not run_id:
            return (
                "No run is selected for cancellation.",
                "cancellation-message error-state",
            )

        try:
            run = runs.request_fixture_cancellation(run_id)
        except (KeyError, ValueError, RunServiceError) as exc:
            return (
                f"Cancellation request failed: {exc}",
                "cancellation-message error-state",
            )

        if run.status == "running":
            return (
                (
                    "Cancellation requested. The run remains active while "
                    "waiting for fixture acknowledgement."
                ),
                "cancellation-message cancellation-message-pending",
            )

        return (
            (
                f"Run is already {run.status}; no cancellation request "
                "was applied."
            ),
            "cancellation-message",
        )

    @app.callback(
        Output("stale-recovery-message", "children"),
        Output("stale-recovery-message", "className"),
        Input("recover-stale-runs", "n_clicks"),
        State("stale-before-input", "value"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def recover_stale_runs(
        _: int,
        stale_before: str | None,
        pathname: str | None = "/research/backtest-results",
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        cutoff = (stale_before or "").strip()
        if not cutoff:
            return (
                "Enter an explicit UTC cutoff before requesting recovery.",
                "stale-recovery-message error-state",
            )

        try:
            recovered = runs.recover_stale_fixture_runs(
                stale_before=cutoff,
            )
        except (ValueError, RuntimeError, RunServiceError) as exc:
            return (
                f"Stale-run recovery failed: {exc}",
                "stale-recovery-message error-state",
            )

        if not recovered:
            return (
                "No stale fixture runs matched the supplied cutoff.",
                "stale-recovery-message",
            )

        return (
            html.Div(
                [
                    html.Strong(
                        f"Recovered {len(recovered)} stale fixture "
                        f"{'run' if len(recovered) == 1 else 'runs'}."
                    ),
                    html.Ul(
                        [
                            html.Li(
                                (
                                    f"{run.run_id}: failed - "
                                    f"{run.error_summary or 'stale recovery'}"
                                )
                            )
                            for run in recovered
                        ]
                    ),
                ]
            ),
            "stale-recovery-message stale-recovery-message-success",
        )
