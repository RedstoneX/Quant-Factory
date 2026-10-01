"""Local display preferences and read-only authority boundaries."""

from __future__ import annotations

from dash import dcc, html


def layout() -> html.Div:
    """Render presentation-only preferences; research behavior never changes here."""

    return html.Div(
        [
            html.Header(
                [
                    html.P("GLOBAL / SETTINGS", className="page-eyebrow"),
                    html.H1("Make the workspace yours—not the research", className="page-title"),
                    html.P(
                        "Change how Quant Factory is displayed while keeping evidence, strategy behavior, and authority untouched.",
                        className="page-description",
                    ),
                ],
                className="page-heading",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Strong("Presentation only"),
                            html.P(
                                "These preferences can change what you see, never what the engine calculates, stores, promotes, or executes.",
                                className="section-description",
                            ),
                        ]
                    ),
                    html.Span("Private browser profile", className="support-summary-count"),
                ],
                className="support-summary-banner",
            ),
            html.Div(
                [
                    html.Aside(
                        [
                            html.Strong("Display preferences"),
                            html.P(
                                "Intentionally small: research parameters, data restrictions, and launch authority do not belong here.",
                                className="field-help",
                            ),
                        ],
                        className="support-surface settings-explainer",
                    ),
                    html.Div(
                        [
                            html.Section(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                [html.H2("Interface"), html.P("Comfort and navigation choices for this browser.", className="section-description")]
                                            ),
                                            html.Span("Operator controlled", className="surface-badge"),
                                        ],
                                        className="surface-heading",
                                    ),
                                    _preference_row(
                                        "Color theme",
                                        "Use the established light or dark component theme.",
                                        dcc.RadioItems(
                                            id="settings-theme",
                                            options=[
                                                {"label": "Light", "value": "light"},
                                                {"label": "Dark", "value": "dark"},
                                            ],
                                            value="light",
                                            inline=True,
                                            className="settings-choice-group",
                                        ),
                                    ),
                                    _preference_row(
                                        "Information density",
                                        "Adjust spacing only; no information or controls are removed.",
                                        dcc.RadioItems(
                                            id="settings-density",
                                            options=[
                                                {"label": "Comfortable", "value": "comfortable"},
                                                {"label": "Compact", "value": "compact"},
                                            ],
                                            value="comfortable",
                                            inline=True,
                                            className="settings-choice-group",
                                        ),
                                    ),
                                ],
                                className="support-surface",
                            ),
                            html.Section(
                                [
                                    html.Div(
                                        [
                                            html.Div([html.H2("Protected boundaries"), html.P("Visible for clarity; changed only through the authorized project process.", className="section-description")]),
                                            html.Span("System managed", className="surface-badge"),
                                        ],
                                        className="surface-heading",
                                    ),
                                    html.Div(
                                        [
                                            _boundary("Intraday research mandate", "No position carried beyond the strategy session boundary."),
                                            _boundary("Human promotion decision", "No automatic qualification, promotion, or parameter change."),
                                            _boundary("Credential authority", "Named grants remain outside browser preferences; values are never shown."),
                                            _boundary("Trading execution", "Paper and live operation remain unavailable without separate gates and approval."),
                                        ],
                                        className="settings-boundary-grid",
                                    ),
                                ],
                                className="support-surface",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        "No unsaved display changes.",
                                        id="settings-save-status",
                                        className="save-message",
                                    ),
                                    html.Div(
                                        [
                                            html.Button("Reset display defaults", id="reset-display-preferences", n_clicks=0, className="secondary-action"),
                                            html.Button("Save preferences", id="save-display-preferences", n_clicks=0, className="primary-action"),
                                        ],
                                        className="settings-actions",
                                    ),
                                ],
                                className="settings-action-bar",
                            ),
                        ],
                        className="settings-main",
                    ),
                ],
                className="settings-grid",
            ),
        ],
        className="page-container support-page settings-page",
    )


def _preference_row(title: str, description: str, control) -> html.Div:
    return html.Div(
        [
            html.Div([html.Strong(title), html.P(description, className="field-help")]),
            control,
        ],
        className="settings-preference-row",
    )


def _boundary(title: str, description: str) -> html.Div:
    return html.Div(
        [
            html.Strong(title),
            html.P(description, className="field-help"),
            html.Span("Locked", className="settings-boundary-state"),
        ],
        className="settings-boundary",
    )
