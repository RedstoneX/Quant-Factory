"""Decision rail for the final saved-test review page."""

from __future__ import annotations

from dash import dcc, html


def run_launch_rail(
    *,
    ready: bool,
    launch_disabled: bool,
    launch_title: str,
    blocker: str | None = None,
) -> html.Aside:
    """Render truthful readiness and one explicit launch action."""

    gate = html.Section(
        [
            html.Div(
                [
                    html.H2("Preflight"),
                    html.Span(
                        "Setup ready" if ready else "Blocked",
                        className="surface-status-text surface-status-safe" if ready else "surface-status-text surface-status-blocked",
                    ),
                ],
                className="surface-heading",
            ),
            html.Ul(
                [
                    _check("Persisted setup", "Exact immutable version selected." if ready else "No exact ready setup selected.", passed=ready),
                    _check("Approved implementation", "Candidate logic is bound." if ready else "Implementation review incomplete.", passed=ready),
                    _check("Verified local price history", "Required local checks passed." if ready else "Local data checks incomplete.", passed=ready),
                    _check("Fixed costs and session", "Saved assumptions cannot change here." if ready else "Saved assumptions unavailable.", passed=ready),
                    _check("Submission state", "Durable ticket and duplicate status are checked before submission." if ready else "Awaiting an exact ready setup.", passed=ready),
                ],
                className="launch-check-list",
            ),
        ],
        className="run-launch-gate",
    )
    confirmation_controls = [
        dcc.Checklist(
            id="confirm-run-test",
            options=[
                {
                    "label": html.Div(
                        [
                            html.Strong("I reviewed this test"),
                            html.Span("Use these locked rules for exactly one research run."),
                        ]
                    ),
                    "value": "confirmed",
                    "disabled": not ready,
                }
            ],
            value=[],
            className="run-confirmation",
        ),
        html.Button(
            "Run test",
            id="launch-run",
            n_clicks=0,
            disabled=launch_disabled,
            title=launch_title,
            className="primary-action run-launch-button",
        ),
        html.Div(
            "Confirm the saved test above.",
            id="launch-message",
            className="save-message",
        ),
    ]
    action_content = (
        [html.Span("NEEDS YOU", className="run-confirm-label"),
         html.Strong("Confirm this saved test"),
         *confirmation_controls]
        if ready else
        [html.Span("BLOCKED", className="run-confirm-label"),
         html.Strong("Complete the exact Candidate setup"),
         html.P(blocker or "This exact Candidate cannot be started until its strategy logic is implemented and bound.", className="section-description"),
         dcc.Link("Return to Set up", href="/research/setup", className="primary-action run-results-link"),
         html.Div(confirmation_controls, className="run-callback-controls")]
    )
    action = html.Section(
        action_content,
        className="run-launch-action",
    )
    return html.Aside(
        [gate, action],
        className="run-launch-rail run-launch-rail-panel",
    )


def _check(label: str, detail: str, *, passed: bool) -> html.Li:
    return html.Li([html.Strong(label), html.Span(detail)], className="run-check-pass" if passed else "run-check-blocked")
