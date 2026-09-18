"""Approved fixture configuration selection for Milestone 23."""

from __future__ import annotations

from dash import dcc, html

from dashboard.components.configuration_summary import configuration_summary
from dashboard.pages.common import page_heading
from dashboard.run_adapter import (
    CatalogSnapshot,
    SavedConfigurationView,
    configuration_readiness_by_id,
    list_saved_configurations,
)
from dashboard.setup_draft import SetupDraftBase, base_from_view, draft_fields


def layout(
    *,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    catalog_snapshot: CatalogSnapshot | None = None,
    loading: bool = False,
) -> html.Div:
    """Select and inspect an immutable approved configuration without launching it."""

    available = (
        list_saved_configurations()
        if configurations is None
        else configurations
    )
    from dashboard.application import _strategy_research_path

    readiness_by_id = configuration_readiness_by_id(available, catalog_snapshot)
    first = next(
        (
            configuration
            for configuration in available
            if readiness_by_id[configuration.configuration_id].ready
        ),
        available[0] if available else None,
    )
    first_readiness = readiness_by_id.get(first.configuration_id) if first else None
    first_base = base_from_view(first) if first is not None else None

    if available:
        selector = dcc.Dropdown(
            id="configuration-selector",
            options=[
                {
                    "label": configuration.label,
                    "value": configuration.configuration_id,
                    "disabled": not configuration.launchable,
                }
                for configuration in available
            ],
            value=first.configuration_id,
            disabled=loading,
            clearable=False,
            persistence=True,
            persistence_type="session",
        )
        preview = configuration_summary(
            first_readiness,
            component_id="configuration-preview",
            loading=loading,
        )
    else:
        selector = dcc.Dropdown(
            id="configuration-selector",
            options=[],
            value=None,
            disabled=True,
            placeholder="No approved configuration is available",
            persistence=True,
            persistence_type="session",
        )
        preview = configuration_summary(
            None,
            component_id="configuration-preview",
            loading=loading,
            empty_title="No approved choices",
            empty_message=(
                "An approved saved fixture configuration is required before a test can be reviewed or run."
            ),
        )

    review_enabled = first_readiness is not None and first_readiness.ready and not loading

    return html.Div(
        [
            page_heading(
                "RESEARCH / SET UP",
                "Set up a test",
                "Choose and inspect an approved immutable fixture configuration before any work starts.",
            ),
            _strategy_research_path("/research/setup"),
            dcc.Store(
                id="selected-configuration-state",
                data=first.configuration_id if first else None,
                storage_type="session",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.Label(
                                "Saved setup",
                                htmlFor="configuration-selector",
                                className="field-label",
                            ),
                            selector,
                            html.P(
                                "Only approved infrastructure fixtures are available during Milestone 23.",
                                className="field-help",
                            ),
                        ],
                        className="panel configuration-selector-panel",
                    ),
                    html.Section(
                        [
                            html.Strong("Infrastructure fixture — not profit evidence"),
                            html.P(
                                "A successful test proves the workflow and evidence path; it does not qualify a strategy for paper or live trading.",
                                className="field-help",
                            ),
                            dcc.Link(
                                "Review test",
                                id="review-test-action",
                                href="/research/run-test" if review_enabled else None,
                                className=(
                                    "primary-action"
                                    if review_enabled
                                    else "primary-action action-disabled"
                                ),
                                title=(
                                    "Review this immutable saved setup before running it."
                                    if review_enabled
                                    else "Resolve every preflight blocker before reviewing this test."
                                ),
                            ),
                        ],
                        className="panel launch-controls-panel",
                    ),
                ],
                className="run-launch-row",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("Edit fixture setup"),
                                    html.P(
                                        "Changes stay in this browser until you save a new immutable setup. The selected saved setup is never overwritten.",
                                        className="field-help",
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Button(
                                        "Save configuration",
                                        id="save-configuration",
                                        n_clicks=0,
                                        disabled=True,
                                        title="Change an approved bounded field before saving.",
                                        className="primary-action",
                                    ),
                                    html.Div(
                                        "Saved setup selected — no unsaved changes.",
                                        id="setup-draft-status",
                                        className="save-message",
                                    ),
                                ],
                                className="setup-draft-actions",
                            ),
                        ],
                        className="setup-draft-heading",
                    ),
                    html.Div(
                        _draft_controls(first_base, revision=0),
                        id="setup-draft-fields",
                        className="setup-draft-fields",
                    ),
                    html.Div(
                        id="setup-save-message",
                        className="save-message",
                    ),
                ],
                className="panel setup-draft-panel",
            ),
            preview,
        ],
        className="page-container setup-page",
    )


def _draft_controls(
    base: SetupDraftBase | None,
    *,
    revision: int,
) -> list[html.Div]:
    if base is None:
        return [
            html.Div(
                "No approved immutable setup is available to use as a draft.",
                className="empty-state-copy",
            )
        ]

    sections: list[html.Div] = []
    grouped = {section: [] for section in ("market_data", "parameters", "execution")}
    for field in draft_fields(base):
        control_id = {
            "type": "setup-draft-input",
            "configuration": base.configuration.configuration_id,
            "revision": revision,
            "section": field.section,
            "path": field.path,
        }
        if isinstance(field.value, bool) or field.options:
            choices = field.options or (True, False)
            control = dcc.Dropdown(
                id=control_id,
                options=[
                    {
                        "label": (
                            "Yes"
                            if choice is True
                            else "No"
                            if choice is False
                            else str(choice)
                        ),
                        "value": choice,
                    }
                    for choice in choices
                ],
                value=field.value,
                clearable=False,
                disabled=not field.editable,
                persistence=True,
                persistence_type="session",
            )
        elif isinstance(field.value, (int, float)) and not isinstance(
            field.value, bool
        ):
            control = dcc.Input(
                id=control_id,
                type="number",
                value=field.value,
                step=1 if isinstance(field.value, int) else "any",
                disabled=not field.editable,
                debounce=True,
                persistence=True,
                persistence_type="session",
                className="setup-draft-input",
            )
        elif isinstance(field.value, str):
            control = dcc.Input(
                id=control_id,
                type="text",
                value=field.value,
                disabled=not field.editable,
                debounce=True,
                persistence=True,
                persistence_type="session",
                className="setup-draft-input",
            )
        else:
            control = html.Code(str(field.value), className="configuration-identity")
        grouped[field.section].append(
            html.Div(
                [
                    html.Label(field.label, className="field-label"),
                    control,
                    html.P(field.reason, className="field-help"),
                ],
                className=(
                    "setup-draft-field"
                    if field.editable
                    else "setup-draft-field setup-draft-field-fixed"
                ),
                **{
                    "data-setup-section": field.section,
                    "data-setup-path": field.path,
                    "data-editable": "true" if field.editable else "false",
                },
            )
        )

    labels = {
        "market_data": "Data and coverage",
        "parameters": "Approved parameters",
        "execution": "Execution and cost assumptions",
    }
    for section, controls in grouped.items():
        sections.append(
            html.Div(
                [html.H3(labels[section]), *controls],
                className="setup-draft-section",
            )
        )
    return sections
