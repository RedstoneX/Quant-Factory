"""Decision rail for the final saved-test review page."""

from __future__ import annotations

from dash import dcc, html


def run_launch_rail(
    *,
    ready: bool,
    launch_disabled: bool,
    launch_title: str,
) -> html.Aside:
    """Render truthful readiness and one explicit launch action."""

    gate = html.Section(
        [
            html.Div(
                [
                    html.H2("5 checks passed" if ready else "Final checks incomplete"),
                    html.Span(
                        "Ready" if ready else "Blocked",
                        className=(
                            "surface-status-text surface-status-safe"
                            if ready
                            else "surface-status-text surface-status-blocked"
                        ),
                    ),
                ],
                className="surface-heading",
            ),
            html.Ul(
                [
                    html.Li("Exact saved version"),
                    html.Li("Approved implementation"),
                    html.Li("Verified local price history"),
                    html.Li("Fixed costs and session"),
                    html.Li("No unresolved duplicate start"),
                ],
                className=(
                    "launch-check-list" if ready else "launch-check-list launch-check-list-blocked"
                ),
            ),
        ],
        className="panel run-launch-gate",
    )
    action = html.Section(
        [
            html.Span("NEEDS YOU", className="run-confirm-label"),
            html.Strong("Confirm this saved test"),
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
                "Start test",
                id="launch-run",
                n_clicks=0,
                disabled=launch_disabled,
                title=launch_title,
                className="primary-action run-launch-button",
            ),
            html.Div("Confirm the saved test above.", id="launch-message", className="save-message"),
            dcc.Link(
                "Open Results",
                href="/research/backtest-results",
                className="secondary-action run-results-link",
            ),
        ],
        className="panel run-launch-action",
    )
    return html.Aside([gate, action], className="run-launch-rail")
