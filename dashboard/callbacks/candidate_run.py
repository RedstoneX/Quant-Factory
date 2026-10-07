"""Exact-Candidate Run Test preview callback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import Dash, Input, Output
from dash.exceptions import PreventUpdate

from dashboard.candidate_workflow import candidate_selection_blocker
from dashboard.components.configuration_summary import configuration_summary
from dashboard.pages.run_test import render_selected_run_test
from dashboard.run_adapter import (
    ConfigurationReadinessView,
    SavedConfigurationView,
    configuration_readiness,
    list_saved_configurations,
)


def register_candidate_run_preview(
    app: Dash,
    *,
    configurations: tuple[SavedConfigurationView, ...],
    readiness_by_id: dict[str, ConfigurationReadinessView],
    database: str | Path,
) -> None:
    @app.callback(
        Output("run-test-dynamic-view", "children"),
        Input("idea-draft-store", "data"),
        Input("selected-configuration-state", "data"),
        Input("route-research-run-test", "style"),
    )
    def show_selected_test(draft: dict[str, Any] | None, configuration_id: str | None, route_style: dict[str, str] | None):
        if (route_style or {}).get("display") != "block":
            raise PreventUpdate
        return render_selected_run_test(str((draft or {}).get("draft_id") or ""), configuration_id, database=database)

    @app.callback(
        Output("run-configuration-preview", "children"),
        Input("selected-configuration-state", "data"),
        Input("idea-draft-store", "data"),
        Input("route-research-run-test", "style"),
    )
    def preview_configuration(
        configuration_id: str | None,
        draft: dict[str, Any] | None = None,
        route_style: dict[str, str] | None = None,
    ):
        if route_style is not None and route_style.get("display") != "block":
            raise PreventUpdate
        blocker = candidate_selection_blocker(
            str((draft or {}).get("draft_id") or ""),
            configuration_id,
            database=database,
        )
        if blocker:
            return configuration_summary(
                None,
                component_id="run-configuration-preview-content",
                empty_title="No Candidate test is ready",
                empty_message=blocker,
            ).children
        readiness = readiness_by_id.get(configuration_id or "")
        if readiness is None:
            available = configurations + list_saved_configurations(database)
            selected = next(
                (item for item in available if item.configuration_id == configuration_id),
                None,
            )
            if selected is not None:
                readiness = configuration_readiness(selected, None)
                readiness_by_id[selected.configuration_id] = readiness
        return configuration_summary(
            readiness,
            component_id="run-configuration-preview-content",
        ).children
