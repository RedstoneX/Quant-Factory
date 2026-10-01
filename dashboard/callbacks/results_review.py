"""Durable review callbacks owned by the Results page."""

from __future__ import annotations

from pathlib import Path

from dash import Dash, Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.components.messages import operator_message as _operator_message
from dashboard.components.results_review import (
    DASHBOARD_REVIEWER as REVIEWER,
    REVIEW_CONTEXT_UNAVAILABLE_MESSAGE,
    dashboard_persistence as _dashboard_persistence,
    decision_summary as _decision_summary,
    review_context_failure_message as _review_context_failure_message,
    review_context_unavailable_notice as _review_context_unavailable_notice,
)
from dashboard.callbacks.review_state import (
    DurableReviewSnapshot,
    load_durable_review,
    persist_screening_rejection_review,
    screening_rejection_available,
)
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from dashboard.routing import active_route as _active_route
from orchestration import FixtureRunService
from persistence import ReviewState
from persistence.evidence_service import ValidationEvidenceArtifactService


OWNED_STATE = {
    "review_form": (
        "selected-run-state.data",
        "review-status.value",
        "review-note.value",
        "review-message.children",
        "review-history.children",
    ),
}


def _state_label(value: object | None) -> str:
    if value in (None, ""):
        return "Unreviewed"
    return str(value).replace("_", " ").capitalize()


def _review_history(snapshot: DurableReviewSnapshot) -> html.Div | html.Ol:
    if not snapshot.history:
        return html.Div(
            "No durable decision has been recorded for the selected run.",
            className="empty-state-copy",
        )
    return html.Ol(
        [
            html.Li(
                [
                    html.Strong(
                        f"{_state_label(event.get('prior_state'))} → "
                        f"{_state_label(event.get('new_state'))}"
                    ),
                    html.P(str(event.get("note") or "No rationale recorded.")),
                    html.Small(
                        f"{event.get('created_at', 'Time unavailable')} · "
                        f"{event.get('operator', 'Operator unavailable')}"
                    ),
                ]
            )
            for event in snapshot.history
        ],
        className="review-history-list",
    )


def register_results_review_callbacks(
    app: Dash,
    *,
    runs: FixtureRunService,
    detail_adapter: RunDetailDashboardAdapter,
    dashboard_database: str | Path,
    artifact_root: Path,
) -> None:
    """Register durable-review behavior against the Results selection."""

    _ = runs, detail_adapter

    @app.callback(
        Output("review-status", "value"),
        Output("review-note", "value"),
        Output("review-history", "children"),
        Input("selected-run-state", "data"),
    )
    def load_review(identity: str | None):
        if not identity:
            empty = DurableReviewSnapshot(
                state=ReviewState.UNREVIEWED,
                note="",
                operator=None,
                updated_at=None,
                history=(),
                decision_identity=None,
            )
            return ReviewState.UNREVIEWED.value, "", _review_history(empty)
        try:
            snapshot = load_durable_review(
                dashboard_database,
                artifact_root,
                identity,
            )
        except (KeyError, RuntimeError, ValueError) as exc:
            message = _review_context_failure_message(exc)
            return (
                ReviewState.UNREVIEWED.value,
                "",
                _operator_message(message, tone="warning"),
            )
        return snapshot.state.value, snapshot.note, _review_history(snapshot)

    @app.callback(
        Output("save-review", "disabled"),
        Output("save-review", "title"),
        Output("review-message", "children", allow_duplicate=True),
        Input("selected-run-state", "data"),
        prevent_initial_call=True,
    )
    def refresh_review_context_availability(identity: str | None):
        if not identity:
            return (
                True,
                REVIEW_CONTEXT_UNAVAILABLE_MESSAGE,
                _review_context_unavailable_notice(),
            )
        with _dashboard_persistence(dashboard_database) as service:
            try:
                ValidationEvidenceArtifactService(
                    service
                ).evaluate_persisted_review_context(
                    identity,
                    artifact_root=artifact_root,
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                try:
                    screening_rejection_available(
                        service, identity, artifact_root=artifact_root
                    )
                except (KeyError, RuntimeError, ValueError):
                    message = _review_context_failure_message(exc)
                    return True, message, _operator_message(message, tone="warning")
                return (
                    False,
                    "This terminal screening outcome may only be recorded as Reject.",
                    _operator_message(
                        "Terminal screening rejection verified.",
                        "Record Reject with a durable rationale; advancement decisions remain gated.",
                        tone="warning",
                    ),
                )
        return (
            False,
            "Persist a durable evidence decision for the selected run.",
            "",
        )

    @app.callback(
        Output("review-message", "children"),
        Output("review-history", "children", allow_duplicate=True),
        Input("save-review", "n_clicks"),
        State("selected-run-state", "data"),
        State("review-status", "value"),
        State("review-note", "value"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def save_review(
        _: int,
        identity: str,
        status: str,
        note: str | None,
        pathname: str | None = "/research/backtest-results",
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        if not identity:
            raise ValueError("No persisted backtest is selected")
        try:
            review_state = ReviewState(status)
        except ValueError as exc:
            raise ValueError(f"Unsupported review status: {status}") from exc
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
                decision = evidence.persist_evidence_decision(
                    run_id=identity,
                    gate_result=gate,
                    review_state=review_state,
                    review_reason=reason,
                    reviewer=REVIEWER,
                    artifact_root=artifact_root,
                )
            except (KeyError, RuntimeError, ValueError) as gate_exc:
                if review_state == ReviewState.REJECT:
                    try:
                        decision = persist_screening_rejection_review(
                            service,
                            run_id=identity,
                            review_reason=reason,
                            reviewer=REVIEWER,
                            artifact_root=artifact_root,
                        )
                    except (KeyError, RuntimeError, ValueError) as exc:
                        failure = exc
                    else:
                        failure = None
                else:
                    failure = gate_exc
                if failure is None:
                    pass
                else:
                    return (
                        _operator_message(
                            _review_context_failure_message(failure),
                            (
                                "No review change was saved. Refresh the selected run and "
                                "inspect its existing decision before retrying."
                            ),
                            tone="warning",
                        ),
                        no_update,
                    )
        snapshot = load_durable_review(
            dashboard_database,
            artifact_root,
            identity,
        )
        if "lockbox_gate" in decision.document["decision"]:
            summary = _decision_summary(decision)
        else:
            summary = _operator_message(
                "Terminal screening rejection saved.",
                f"Decision identity: {decision.decision_identity}",
                tone="warning",
            )
        return summary, _review_history(snapshot)
