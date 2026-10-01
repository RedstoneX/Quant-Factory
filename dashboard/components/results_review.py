"""Results-review presentation and callback-local persistence boundary."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from dash import html

from dashboard.components.messages import operator_message
from persistence import PersistenceService


DASHBOARD_REVIEWER = "dashboard-operator"
REVIEW_CONTEXT_UNAVAILABLE_MESSAGE = (
    "Durable decision unavailable: this backtest has no persisted review context "
    "linking out-of-sample, walk-forward, Monte Carlo and robustness evidence."
)


@contextmanager
def dashboard_persistence(database: str | Path) -> Iterator[PersistenceService]:
    """Open a callback-local connection safe for Dash worker threads."""

    service = PersistenceService(database)
    try:
        yield service
    finally:
        service.close()


def review_context_unavailable_notice() -> html.Div:
    return operator_message(
        REVIEW_CONTEXT_UNAVAILABLE_MESSAGE,
        tone="warning",
    )


def review_context_failure_message(exc: BaseException) -> str:
    message = str(exc) or REVIEW_CONTEXT_UNAVAILABLE_MESSAGE
    if "review context artifact is missing" in message:
        return REVIEW_CONTEXT_UNAVAILABLE_MESSAGE
    return message


def decision_summary(decision: Any) -> html.Div:
    review = decision.document["decision"]["review"]
    gate = decision.document["decision"]["lockbox_gate"]
    references = gate.get("referenced_artifacts", ())
    return html.Div(
        [
            html.Strong("Evidence decision artifact validated."),
            html.Dl(
                [
                    html.Div([html.Dt("Status"), html.Dd(review.get("state", "—"))]),
                    html.Div([html.Dt("Reviewer"), html.Dd(review.get("reviewer", "—"))]),
                    html.Div([html.Dt("Reason"), html.Dd(review.get("reason", "—"))]),
                    html.Div([html.Dt("Gate"), html.Dd(gate.get("status", "—"))]),
                    html.Div(
                        [
                            html.Dt("Decision identity"),
                            html.Dd(decision.decision_identity),
                        ]
                    ),
                    html.Div(
                        [html.Dt("Referenced evidence"), html.Dd(str(len(references)))]
                    ),
                ],
                className="run-detail-fields",
            ),
        ],
        className="operator-message operator-message-success",
    )
