"""Set up page callback ownership for immutable fixture configurations."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from dash import ALL, Dash, Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.application import _active_route, _callback_triggered_id
from dashboard.components.configuration_summary import configuration_summary
from dashboard.pages.setup import _draft_controls
from dashboard.run_adapter import (
    CatalogSnapshot,
    ConfigurationReadinessView,
    SavedConfigurationView,
)
from dashboard.setup_draft import (
    SetupDraftBase,
    SetupDraftError,
    base_from_view,
    evaluate_setup_draft,
    load_persisted_base,
    save_setup_draft,
)


def register_setup_callbacks(
    app: Dash,
    *,
    configurations: tuple[SavedConfigurationView, ...],
    readiness_by_id: dict[str, ConfigurationReadinessView],
    dashboard_database: str | Path,
    catalog_snapshot: CatalogSnapshot | None,
) -> None:
    """Register callbacks whose writable outputs all belong to Set up."""

    configurations_by_id = {
        configuration.configuration_id: configuration
        for configuration in configurations
    }
    bases_by_id: dict[str, SetupDraftBase] = {}
    draft_revisions: dict[str, int] = {
        configuration.configuration_id: 0 for configuration in configurations
    }

    def base_for(configuration_id: str | None) -> SetupDraftBase | None:
        if not configuration_id:
            return None
        cached = bases_by_id.get(configuration_id)
        if cached is not None:
            return cached
        configuration = configurations_by_id.get(configuration_id)
        if configuration is None:
            return None
        base = load_persisted_base(dashboard_database, configuration)
        bases_by_id[configuration_id] = base
        return base

    def options() -> list[dict[str, object]]:
        ordered = sorted(
            configurations_by_id.values(),
            key=lambda item: (
                not item.launchable,
                item.strategy_name.lower(),
                item.experiment_id.lower(),
                item.configuration_id,
            ),
        )
        return [
            {
                "label": item.label,
                "value": item.configuration_id,
                "disabled": not item.launchable,
            }
            for item in ordered
        ]

    @app.callback(
        Output("selected-configuration-state", "data"),
        Input("configuration-selector", "value"),
        prevent_initial_call=True,
    )
    def preserve_selected_configuration(configuration_id: str | None):
        if not configuration_id:
            raise PreventUpdate
        return configuration_id

    @app.callback(
        Output("setup-draft-fields", "children"),
        Input("configuration-selector", "value"),
    )
    def render_setup_draft(configuration_id: str | None):
        try:
            return _draft_controls(
                base_for(configuration_id),
                revision=draft_revisions.get(configuration_id or "", 0),
            )
        except SetupDraftError as exc:
            return html.Div(
                [
                    html.Strong("Saved setup unavailable"),
                    html.P(str(exc)),
                ],
                className="operator-message operator-message-error",
            )

    @app.callback(
        Output("configuration-preview", "children"),
        Output("review-test-action", "href"),
        Output("review-test-action", "className"),
        Output("review-test-action", "title"),
        Output("save-configuration", "disabled"),
        Output("save-configuration", "title"),
        Output("setup-draft-status", "children"),
        Output("setup-draft-status", "className"),
        Input("configuration-selector", "value"),
        Input(
            {
                "type": "setup-draft-input",
                "configuration": ALL,
                "revision": ALL,
                "section": ALL,
                "path": ALL,
            },
            "value",
        ),
        State(
            {
                "type": "setup-draft-input",
                "configuration": ALL,
                "revision": ALL,
                "section": ALL,
                "path": ALL,
            },
            "id",
        ),
    )
    def preview_setup_configuration(
        configuration_id: str | None,
        field_values: list[object] | None,
        field_ids: list[Mapping[str, object]] | None,
    ):
        try:
            base = base_for(configuration_id)
        except SetupDraftError as exc:
            return _unavailable_preview(str(exc))
        if base is None:
            summary = configuration_summary(
                None,
                component_id="configuration-preview-content",
            )
            return (
                summary.children,
                None,
                "primary-action action-disabled",
                "Choose an approved saved setup before continuing.",
                True,
                "Choose an approved saved setup before saving.",
                "No saved setup is selected.",
                "save-message error-state",
            )
        evaluation = evaluate_setup_draft(
            base,
            field_ids=tuple(field_ids or ()),
            field_values=tuple(field_values or ()),
            catalog_snapshot=catalog_snapshot,
        )
        summary = configuration_summary(
            evaluation.readiness,
            component_id="configuration-preview-content",
        )
        preview_children: list[object] = []
        if evaluation.errors:
            preview_children.append(
                html.Div(
                    [
                        html.Strong("Correct the setup draft before saving"),
                        html.Ul([html.Li(error) for error in evaluation.errors]),
                    ],
                    className="operator-message operator-message-error",
                )
            )
        preview_children.extend(summary.children)

        saved_and_ready = (
            not evaluation.dirty
            and not evaluation.errors
            and evaluation.readiness.ready
        )
        if evaluation.errors:
            status = "Unsaved changes need correction; the saved setup is unchanged."
            status_class = "save-message error-state"
        elif evaluation.dirty and not evaluation.readiness.ready:
            status = "Unsaved changes are blocked by the preflight reasons below."
            status_class = "save-message error-state"
        elif evaluation.dirty:
            status = "Unsaved changes are ready to create a new immutable setup."
            status_class = "save-message unsaved-state"
        else:
            status = "Saved setup selected — no unsaved changes."
            status_class = "save-message"
        return (
            preview_children,
            "/research/run-test" if saved_and_ready else None,
            "primary-action" if saved_and_ready else "primary-action action-disabled",
            (
                "Review this immutable saved setup before running it."
                if saved_and_ready
                else "Resolve every preflight blocker and restore or save draft changes before reviewing this test."
            ),
            not evaluation.saveable,
            (
                "Create a new immutable saved setup."
                if evaluation.saveable
                else "Change an approved field and resolve every blocker before saving."
            ),
            status,
            status_class,
        )

    @app.callback(
        Output("configuration-selector", "options"),
        Output("configuration-selector", "value"),
        Output("setup-save-message", "children"),
        Output("setup-save-message", "className"),
        Input("save-configuration", "n_clicks"),
        Input("url", "pathname"),
        State("configuration-selector", "value"),
        State(
            {
                "type": "setup-draft-input",
                "configuration": ALL,
                "revision": ALL,
                "section": ALL,
                "path": ALL,
            },
            "value",
        ),
        State(
            {
                "type": "setup-draft-input",
                "configuration": ALL,
                "revision": ALL,
                "section": ALL,
                "path": ALL,
            },
            "id",
        ),
    )
    def save_configuration(
        n_clicks: int | None,
        pathname: str | None,
        configuration_id: str | None,
        field_values: list[object] | None,
        field_ids: list[Mapping[str, object]] | None,
    ):
        if not _active_route(pathname, "/research/setup"):
            raise PreventUpdate
        triggered = _callback_triggered_id()
        if triggered != "save-configuration":
            selected = (
                configuration_id
                if configuration_id in configurations_by_id
                else next(iter(configurations_by_id), None)
            )
            return options(), selected, no_update, no_update
        if not n_clicks:
            raise PreventUpdate
        try:
            base = base_for(configuration_id)
            if base is None:
                raise SetupDraftError("Choose an approved saved setup before saving.")
            evaluation = evaluate_setup_draft(
                base,
                field_ids=tuple(field_ids or ()),
                field_values=tuple(field_values or ()),
                catalog_snapshot=catalog_snapshot,
            )
            result = save_setup_draft(dashboard_database, evaluation)
        except (KeyError, RuntimeError, SetupDraftError, TypeError, ValueError) as exc:
            return (
                options(),
                no_update,
                html.Div(
                    [
                        html.Strong("Setup was not saved"),
                        html.P(str(exc)),
                        html.P("Your page-local draft is still available for correction."),
                    ]
                ),
                "save-message error-state",
            )

        configurations_by_id[result.view.configuration_id] = result.view
        readiness_by_id[result.view.configuration_id] = evaluation.readiness
        bases_by_id[result.view.configuration_id] = base_from_view(
            result.view,
            evaluation.document,
        )
        draft_revisions[result.view.configuration_id] = (
            draft_revisions.get(result.view.configuration_id, 0) + 1
        )
        outcome = (
            "Saved a new immutable setup."
            if result.created
            else "This exact immutable setup was already saved; no duplicate was created."
        )
        return (
            options(),
            result.view.configuration_id,
            html.Div(
                [
                    html.Strong(outcome),
                    html.P("Review test uses the selected saved identity shown below."),
                ],
                **{"data-configuration-id": result.view.configuration_id},
            ),
            "save-message success-state",
        )


def _unavailable_preview(detail: str):
    return (
        html.Div(
            [html.Strong("Saved setup unavailable"), html.P(detail)],
            className="operator-message operator-message-error",
        ),
        None,
        "primary-action action-disabled",
        "Reload Set up before continuing.",
        True,
        "Reload Set up before saving.",
        "The saved setup could not be read.",
        "save-message error-state",
    )
