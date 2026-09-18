"""Reusable operator summary for one immutable saved configuration."""

from __future__ import annotations

from dash import dcc, html

from dashboard.run_adapter import ConfigurationField, ConfigurationReadinessView


def configuration_summary(
    readiness: ConfigurationReadinessView | None,
    *,
    component_id: str,
    loading: bool = False,
    empty_title: str = "No saved setup selected",
    empty_message: str = (
        "Choose an approved immutable saved setup before reviewing or running a test."
    ),
) -> html.Div:
    """Render explicit loading, empty, blocked, and ready states."""

    if loading:
        return html.Div(
            [
                html.H2("Loading saved setup"),
                html.P(
                    "The saved setup and local data checks are still loading. Run test remains disabled.",
                    className="empty-state-copy",
                ),
            ],
            id=component_id,
            className="panel loading-state",
            **{"data-state": "loading"},
        )
    if readiness is None:
        return html.Div(
            [
                html.H2(empty_title),
                html.P(
                    empty_message,
                    className="empty-state-copy",
                ),
                dcc.Link(
                    "Return to Set up",
                    href="/research/setup",
                    className="secondary-action",
                ),
            ],
            id=component_id,
            className="panel empty-state",
            **{"data-state": "empty"},
        )

    status_text = {
        "ready": "Ready for final review",
        "data_unavailable": "Data unavailable — test blocked",
        "unsupported": "Unsupported setup — test blocked",
    }.get(readiness.state, "Setup not ready — test blocked")
    status_class = (
        "configuration-status configuration-status-ready"
        if readiness.ready
        else "configuration-status configuration-status-blocked"
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Span(status_text, className=status_class),
                    html.Code(
                        readiness.configuration_id,
                        className="configuration-identity",
                    ),
                ],
                className="configuration-preview-header",
            ),
            html.Div(
                [
                    _summary_card(
                        "Strategy",
                        readiness.strategy_name,
                        readiness.strategy_identity,
                    ),
                    _summary_card(
                        "Instrument",
                        readiness.instrument,
                        f"{readiness.provider} · {readiness.dataset}",
                    ),
                    _summary_card(
                        "Timeframe",
                        readiness.timeframe,
                        readiness.lifecycle.replace("_", " ").title(),
                    ),
                ],
                className="summary-grid configuration-summary-grid",
            ),
            html.Section(
                [
                    html.H3("Data used"),
                    _field_list(
                        (
                            ConfigurationField("Provider", readiness.provider),
                            ConfigurationField("Dataset", readiness.dataset),
                            ConfigurationField("Instrument", readiness.instrument),
                            ConfigurationField("Timeframe", readiness.timeframe),
                            ConfigurationField(
                                "Requested coverage",
                                readiness.requested_coverage,
                            ),
                            ConfigurationField("Actual coverage", readiness.actual_coverage),
                            ConfigurationField(
                                "Local availability",
                                readiness.local_availability,
                            ),
                            ConfigurationField(
                                "Local validation",
                                readiness.local_validation,
                            ),
                        )
                    ),
                ],
                className="panel configuration-detail-panel",
            ),
            _preflight(readiness),
            html.Div(
                [
                    html.Section(
                        [
                            html.H3("Parameters"),
                            _field_list(
                                readiness.parameters,
                                empty="No parameters recorded.",
                            ),
                        ],
                        className="panel configuration-detail-panel",
                    ),
                    html.Section(
                        [
                            html.H3("Execution assumptions"),
                            _field_list(
                                readiness.execution_assumptions,
                                empty="No execution assumptions recorded.",
                            ),
                        ],
                        className="panel configuration-detail-panel",
                    ),
                ],
                className="two-column configuration-detail-grid",
            ),
            html.Details(
                [
                    html.Summary("Technical details"),
                    html.Dl(
                        [
                            html.Dt("Experiment"),
                            html.Dd(readiness.experiment_id),
                            html.Dt("Configuration checksum"),
                            html.Dd(readiness.config_hash),
                        ],
                        className="run-detail-fields",
                    ),
                ],
                className="technical-details",
            ),
        ],
        id=component_id,
        className=f"configuration-readiness configuration-readiness-{readiness.state}",
        **{"data-state": readiness.state},
    )


def _summary_card(label: str, value: str, detail: str) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="summary-label"),
            html.Strong(value),
            html.P(detail, className="summary-detail"),
        ],
        className="summary-card",
    )


def _preflight(readiness: ConfigurationReadinessView) -> html.Section:
    if readiness.ready:
        body = html.Ul(
            [
                html.Li("Saved immutable configuration found."),
                html.Li("Strategy is an active Milestone 23 infrastructure fixture."),
                html.Li(
                    "Required local data checks passed."
                    if readiness.dataset != "No market data"
                    else "This deterministic fixture does not require market data."
                ),
            ],
            className="preflight-check-list",
        )
    else:
        body = html.Ol(
            [
                html.Li(
                    [
                        html.Strong(blocker.reason),
                        html.P(blocker.remedy, className="field-help"),
                        dcc.Link(
                            "Open the correction page",
                            href=blocker.remedy_href,
                            className="secondary-action",
                        ),
                    ]
                )
                for blocker in readiness.blockers
            ],
            className="preflight-blocker-list",
        )
    return html.Section(
        [
            html.H3("Preflight checks"),
            html.P(
                "Ready — no blocking reason found."
                if readiness.ready
                else f"Blocked — {len(readiness.blockers)} correction(s) required.",
                className="field-help",
            ),
            body,
        ],
        className=(
            "panel preflight-panel preflight-ready"
            if readiness.ready
            else "panel preflight-panel preflight-blocked"
        ),
    )


def _field_list(
    fields: tuple[ConfigurationField, ...],
    *,
    empty: str = "No details recorded.",
) -> html.Dl | html.P:
    if not fields:
        return html.P(empty, className="empty-state-copy")
    children = []
    for field in fields:
        children.extend((html.Dt(field.label), html.Dd(field.value)))
    return html.Dl(children, className="run-detail-fields")
