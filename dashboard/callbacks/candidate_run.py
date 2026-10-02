"""Exact-Candidate Run Test preview callback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import Dash, Input, Output

from dashboard.candidate_workflow import candidate_selection_blocker
from dashboard.components.configuration_summary import configuration_summary
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
        Output("run-configuration-preview", "children"),
        Input("selected-configuration-state", "data"),
        Input("idea-draft-store", "data"),
    )
    def preview_configuration(
        configuration_id: str | None,
        draft: dict[str, Any] | None = None,
    ):
        if draft is not None:
            blocker = candidate_selection_blocker(
                str(draft.get("draft_id") or ""),
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
