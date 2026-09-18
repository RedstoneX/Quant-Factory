"""Strategy Review page callback ownership."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import Dash, Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate

from backtesting.validation.evidence_decision_artifacts import (
    EVIDENCE_DECISION_LOGICAL_NAME,
)
from dashboard.application import (
    REVIEWER,
    REVIEW_CONTEXT_UNAVAILABLE_MESSAGE,
    _active_route,
    _dashboard_persistence,
    _decision_summary,
    _detail_fields,
    _detail_subsection,
    _operator_message,
    _review_artifact_summary,
    _review_context_failure_message,
    _review_context_unavailable_notice,
    _review_metric_cards,
    _review_result_rows,
    _review_run_options,
    _review_summary,
)
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService
from persistence import ArtifactType, ReviewState
from persistence.evidence_service import ValidationEvidenceArtifactService


OWNED_STATE = {
    "review_selection": (
        "review-run-selector.value",
        "selected-review-identity.data",
        "selected-parameters.data",
        "review-status.value",
        "review-note.value",
    ),
}


def register_strategy_review_callbacks(
    app: Dash,
    *,
    runs: FixtureRunService,
    detail_adapter: RunDetailDashboardAdapter,
    dashboard_database: str | Path,
    artifact_root: Path,
) -> None:
    """Register callbacks owned by the Strategy Review route."""

    @app.callback(
        Output("review-run-selector", "options"),
        Output("review-run-selector", "value"),
        Input("refresh-experiments", "n_clicks"),
        State("review-run-selector", "value"),
        State("review-run-selector", "options"),
    )
    def refresh_experiment_selector(
        _: int,
        selected_run_id: str | None,
        current_options: list[dict[str, str]] | None,
    ):
        recent = runs.recent_runs(limit=20)
        options = _review_run_options(recent)
        run_ids = {option["value"] for option in options}
        value = (
            selected_run_id
            if selected_run_id in run_ids
            else options[0]["value"]
            if options
            else None
        )
        options_output: Any = no_update if options == (current_options or []) else options
        return options_output, value

    @app.callback(
        Output("metric-cards", "children"),
        Output("ranked-table", "rowData"),
        Output("selected-parameter-display", "children"),
        Output("provenance", "children"),
        Output("assumptions", "children"),
        Output("selected-review-identity", "data"),
        Output("selected-parameters", "data"),
        Input("review-run-selector", "value"),
    )
    def select_row(run_id: str | None):
        if not run_id:
            empty = html.Div(
                "No persisted backtest is selected for durable review.",
                className="empty-state-copy",
            )
            return (
                _review_metric_cards(None, None),
                [],
                empty,
                empty,
                empty,
                None,
                {},
            )
        run = runs.get_run(run_id)
        if run is None:
            raise ValueError(f"Selected run {run_id} is unavailable")
        try:
            detail = detail_adapter.selected_run_detail(run_id)
        except (KeyError, RuntimeError, ValueError) as exc:
            raise ValueError(f"Selected run evidence is unavailable: {exc}") from exc
        return (
            _review_metric_cards(run, detail),
            _review_result_rows(detail),
            _review_summary(run, detail),
            _review_artifact_summary(detail),
            html.Div(
                [
                    _detail_subsection(
                        "Trading assumptions",
                        _detail_fields(
                            detail.execution,
                            empty="No trading assumptions are recorded.",
                        ),
                    ),
                    _detail_subsection(
                        "Research History",
                        _detail_fields(
                            detail.lineage_fields,
                            empty="No research history fields are recorded.",
                        ),
                    ),
                ],
                className="experiment-lineage-summary",
            ),
            run_id,
            {"run_id": run_id, "configuration_id": run.configuration_id},
        )

    @app.callback(
        Output("review-status", "value"),
        Output("review-note", "value"),
        Input("selected-review-identity", "data"),
    )
    def load_review(identity: str | None):
        if not identity:
            return ReviewState.UNREVIEWED.value, REVIEW_CONTEXT_UNAVAILABLE_MESSAGE
        with _dashboard_persistence(dashboard_database) as service:
            evidence = ValidationEvidenceArtifactService(service)
            existing = tuple(
                artifact
                for artifact in service.list_run_artifacts(identity)
                if artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
                and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
            )
            try:
                gate = evidence.evaluate_persisted_review_context(
                    identity,
                    artifact_root=artifact_root,
                )
                if existing:
                    decision = evidence.retrieve_evidence_decision(
                        identity,
                        artifact_root=artifact_root,
                        expected_gate=gate,
                    )
            except (KeyError, RuntimeError, ValueError) as exc:
                message = _review_context_failure_message(exc)
                if existing:
                    return (
                        ReviewState.UNREVIEWED.value,
                        f"Durable decision exists but cannot be displayed: {message}",
                    )
                return ReviewState.UNREVIEWED.value, message
            if existing:
                review = decision.document["decision"]["review"]
                return str(review["state"]), str(review.get("reason", ""))
        return ReviewState.UNREVIEWED.value, ""

    @app.callback(
        Output("save-review", "disabled"),
        Output("save-review", "title"),
        Output("review-message", "children", allow_duplicate=True),
        Input("selected-review-identity", "data"),
        prevent_initial_call=True,
    )
    def refresh_review_context_availability(identity: str | None):
        if not identity:
            return True, REVIEW_CONTEXT_UNAVAILABLE_MESSAGE, _review_context_unavailable_notice()
        with _dashboard_persistence(dashboard_database) as service:
            try:
                ValidationEvidenceArtifactService(
                    service
                ).evaluate_persisted_review_context(
                    identity,
                    artifact_root=artifact_root,
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                message = _review_context_failure_message(exc)
                return True, message, _operator_message(message, tone="warning")
        return (
            False,
            "Persist a durable evidence decision for the selected review context.",
            "",
        )

    @app.callback(
        Output("review-message", "children"),
        Input("save-review", "n_clicks"),
        State("selected-review-identity", "data"),
        State("selected-parameters", "data"),
        State("review-status", "value"),
        State("review-note", "value"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def save_review(
        _: int,
        identity: str,
        parameters: dict[str, Any],
        status: str,
        note: str | None,
        pathname: str | None = "/research/strategy-review",
    ) -> html.Div:
        if not _active_route(pathname, "/research/strategy-review"):
            raise PreventUpdate
        if not identity:
            raise ValueError("No persisted backtest is selected")
        try:
            ReviewState(status)
        except ValueError as exc:
            raise ValueError(f"Unsupported review status: {status}") from exc
        _ = parameters, note
        reason = (note or "").strip()
        if not reason:
            raise ValueError("A review reason is required")
        with _dashboard_persistence(dashboard_database) as service:
            evidence = ValidationEvidenceArtifactService(service)
            try:
                gate = evidence.evaluate_persisted_review_context(
                    identity,
                    artifact_root=artifact_root,
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                return _operator_message(
                    _review_context_failure_message(exc),
                    tone="warning",
                )
            decision = evidence.persist_evidence_decision(
                run_id=identity,
                gate_result=gate,
                review_state=ReviewState(status),
                review_reason=reason,
                reviewer=REVIEWER,
                artifact_root=artifact_root,
            )
        return _decision_summary(decision)
