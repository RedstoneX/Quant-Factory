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
                    html.Span("Saved test · read only", className="surface-status-text"),
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
                        "Market",
                        readiness.instrument,
                        f"{readiness.timeframe} prices",
                    ),
                    _summary_card(
                        "Saved test version",
                        readiness.experiment_id,
                        "Locked until a new version is saved",
                    ),
                ],
                className="summary-grid configuration-summary-grid",
            ),
            _plain_english_contract(readiness),
            _preflight(readiness),
            _technical_details(readiness),
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


def _contract_row(label: str, value: str) -> html.Div:
    return html.Div([html.Dt(label), html.Dd(value)], className="configuration-contract-row")


def _field_sentence(fields: tuple[ConfigurationField, ...], empty: str) -> str:
    if not fields:
        return empty
    return " · ".join(f"{field.label}: {field.value}" for field in fields)


def _plain_english_contract(readiness: ConfigurationReadinessView) -> html.Section:
    return html.Section(
        [
            html.Div(
                [
                    html.H3("The test, in plain English"),
                    html.Span("Every saved choice is visible", className="surface-status-text"),
                ],
                className="configuration-contract-heading",
            ),
            html.Dl(
                [
                    _contract_row(
                        "Market & price history",
                        f"{readiness.instrument} · {readiness.timeframe} · {readiness.provider} {readiness.dataset}",
                    ),
                    _contract_row(
                        "Research period",
                        f"Requested {readiness.requested_coverage}; available {readiness.actual_coverage}",
                    ),
                    _contract_row(
                        "Rules being tested",
                        _field_sentence(readiness.parameters, "No adjustable choices"),
                    ),
                    _contract_row(
                        "Trading assumptions",
                        _field_sentence(readiness.execution_assumptions, "No assumptions recorded"),
                    ),
                ],
                className="configuration-contract-grid",
            ),
        ],
        className="configuration-contract",
    )


def _technical_details(readiness: ConfigurationReadinessView) -> html.Details:
    data_fields = (
        ConfigurationField("Provider", readiness.provider),
        ConfigurationField("Dataset", readiness.dataset),
        ConfigurationField("Instrument", readiness.instrument),
        ConfigurationField("Timeframe", readiness.timeframe),
        ConfigurationField("Requested coverage", readiness.requested_coverage),
        ConfigurationField("Actual coverage", readiness.actual_coverage),
        ConfigurationField("Local availability", readiness.local_availability),
        ConfigurationField("Local validation", readiness.local_validation),
    )
    identity = html.Dl(
        [
            html.Dt("Strategy identity"),
            html.Dd(readiness.strategy_identity),
            html.Dt("Lifecycle"),
            html.Dd(readiness.lifecycle.replace("_", " ").title()),
            html.Dt("Configuration ID"),
            html.Dd(readiness.configuration_id),
            html.Dt("Configuration checksum"),
            html.Dd(readiness.config_hash),
        ],
        className="run-detail-fields",
    )
    return html.Details(
        [
            html.Summary("Technical details"),
            html.Div(
                [
                    html.Section([html.H3("Data used"), _field_list(data_fields)]),
                    html.Section(
                        [
                            html.H3("Parameters"),
                            _field_list(readiness.parameters, empty="No parameters recorded."),
                            html.H3("Execution assumptions"),
                            _field_list(
                                readiness.execution_assumptions,
                                empty="No execution assumptions recorded.",
                            ),
                        ]
                    ),
                    identity,
                ],
                className="configuration-technical-grid",
            ),
        ],
        className="technical-details",
    )


def _preflight(readiness: ConfigurationReadinessView) -> html.Section:
    if readiness.ready:
        body = html.Ul(
            [
                html.Li("Saved immutable configuration found."),
                html.Li(
                    "Strategy is an active owner-approved candidate with a connected runtime."
                    if readiness.lifecycle == "candidate"
                    else "Strategy is an active deterministic infrastructure fixture."
                ),
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
    return html.Dl(
        [
            html.Div([html.Dt(field.label), html.Dd(field.value)])
            for field in fields
        ],
        className="run-detail-fields",
    )
