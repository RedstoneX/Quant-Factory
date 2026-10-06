"""Exact Candidate selection and save action for Set up."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import Dash, Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.candidate_workflow import candidate_configuration_binding
from dashboard.mes_candidate_setup import save_mes_candidate_setup
from dashboard.pages.setup import render_selected_setup
from dashboard.run_adapter import ConfigurationReadinessView


def register_candidate_setup_callbacks(
    app: Dash,
    *,
    readiness_by_id: dict[str, ConfigurationReadinessView],
    database: str | Path,
) -> None:
    del readiness_by_id

    @app.callback(
        Output("setup-dynamic-view", "children"),
        Input("idea-draft-store", "data"),
        Input("created-configuration-state", "data"),
        Input("route-research-setup", "style"),
    )
    def show_selected_setup(
        draft: dict[str, Any] | None,
        _created: dict[str, Any] | None,
        setup_style: dict[str, str] | None,
    ):
        if (setup_style or {}).get("display") != "block":
            raise PreventUpdate
        return render_selected_setup(str((draft or {}).get("draft_id") or ""), database=database)

    @app.callback(
        Output("configuration-selector", "options"),
        Output("configuration-selector", "value"),
        Input("idea-draft-store", "data"),
        Input("created-configuration-state", "data"),
        Input("route-research-setup", "style"),
        Input("route-research-run-test", "style"),
    )
    def bind_candidate_configuration(
        draft: dict[str, Any] | None,
        _created: dict[str, Any] | None,
        setup_style: dict[str, str] | None,
        run_style: dict[str, str] | None,
    ):
        if not any((style or {}).get("display") == "block" for style in (setup_style, run_style)):
            raise PreventUpdate
        binding = candidate_configuration_binding(str((draft or {}).get("draft_id") or ""), database=database)
        configuration = binding.configuration
        if configuration is None:
            return [], None
        return [{"label": configuration.experiment_id, "value": configuration.configuration_id}], configuration.configuration_id

    @app.callback(
        Output("idea-configuration-status", "children"),
        Output("created-configuration-state", "data"),
        Input("save-idea-configuration", "n_clicks"),
        State("idea-draft-store", "data"),
        prevent_initial_call=True,
    )
    def save_exact_candidate(n_clicks: int | None, draft: dict[str, Any] | None):
        if not n_clicks:
            raise PreventUpdate
        draft_id = str((draft or {}).get("draft_id") or "")
        try:
            configuration_id = save_mes_candidate_setup(draft_id=draft_id, database=database)
        except (TypeError, ValueError, RuntimeError, FileNotFoundError) as exc:
            return f"Setup not saved: {exc}", no_update
        return (
            "Saved the exact Candidate setup. No test was launched.",
            {"configuration_id": configuration_id, "draft_id": draft_id},
        )

    @app.callback(
        Output("setup-candidate-identity", "children"),
        Output("run-candidate-identity", "children"),
        Input("idea-draft-store", "data"),
    )
    def show_selected_idea(draft: dict[str, Any] | None):
        binding = candidate_configuration_binding(str((draft or {}).get("draft_id") or ""), database=database)
        identity = binding.identity
        content = (
            [html.Strong(identity.title), html.Small(f"{identity.candidate_id} · version {identity.short_version} · {identity.attribution}")]
            if identity is not None
            else [html.Strong("Choose and accept a Candidate on Ideas first."), html.Small(binding.blocker_reason or "No exact Candidate selected")]
        )
        run_content = [
            html.Select(
                [html.Option(identity.title if identity is not None else "No runnable Candidate selected", value=binding.configuration.configuration_id if binding.configuration is not None else "")],
                disabled=True,
                **{"aria-label": "Approved saved configuration"},
                className="run-locked-configuration-select",
            ),
            html.Small(identity.attribution if identity is not None else "No source recorded"),
        ]
        return content, run_content
