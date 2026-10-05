"""Exact-Candidate binding callbacks shared by Setup and Run Test."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dash import Dash, Input, Output, html

from dashboard.candidate_workflow import candidate_configuration_binding
from dashboard.components.configuration_summary import configuration_summary
from dashboard.run_adapter import ConfigurationReadinessView, configuration_readiness


def _preview_outputs(
    configuration_id: str | None,
    readiness_by_id: dict[str, ConfigurationReadinessView],
) -> tuple[Any, str, str, str, str, str, str]:
    readiness = readiness_by_id.get(configuration_id or "")
    summary = configuration_summary(
        readiness,
        component_id="configuration-preview-content",
        empty_action_href=None,
    )
    if readiness is None:
        return (
            summary.children,
            "/research/ideas",
            "secondary-action",
            "Review the accepted Candidate while its exact implementation is pending.",
            "Return to accepted idea",
            "No saved setup",
            "setup-context-state setup-context-state-blocked",
        )
    if not readiness.ready:
        return (
            summary.children,
            "/research/ideas",
            "secondary-action",
            "Review the accepted Candidate while its exact implementation is pending.",
            "Return to accepted idea",
            "Setup blocked",
            "setup-context-state setup-context-state-blocked",
        )
    return (
        summary.children,
        "/research/run-test",
        "primary-action",
        "Review this immutable saved setup before running it.",
        "Continue to final review",
        "Ready to review",
        "setup-context-state setup-context-state-ready",
    )


def register_candidate_setup_callbacks(
    app: Dash,
    *,
    readiness_by_id: dict[str, ConfigurationReadinessView],
    database: str | Path,
) -> None:
    @app.callback(
        Output("configuration-selector", "options"),
        Output("configuration-selector", "value"),
        Input("idea-draft-store", "data"),
        Input("created-configuration-state", "data"),
    )
    def bind_candidate_configuration(draft: dict[str, Any] | None, _created: dict[str, Any] | None):
        binding = candidate_configuration_binding(str((draft or {}).get("draft_id") or ""), database=database)
        configuration = binding.configuration
        if configuration is None:
            return [], None
        option = {"label": configuration.label, "value": configuration.configuration_id, "disabled": not configuration.launchable}
        return [option], configuration.configuration_id

    @app.callback(
        Output("configuration-preview", "children"),
        Output("review-test-action", "href"),
        Output("review-test-action", "className"),
        Output("review-test-action", "title"),
        Output("review-test-action", "children"),
        Output("setup-context-state", "children"),
        Output("setup-context-state", "className"),
        Input("selected-configuration-state", "data"),
        Input("idea-draft-store", "data"),
    )
    def preview_setup_configuration(configuration_id: str | None, draft: dict[str, Any] | None = None):
        binding = candidate_configuration_binding(str((draft or {}).get("draft_id") or ""), database=database)
        if not binding.bound:
            title = "Implementation needed" if binding.blocker_code == "implementation_required" else "Candidate not ready"
            summary = configuration_summary(
                None,
                component_id="configuration-preview-content",
                empty_title=title,
                empty_message=binding.blocker_reason or "Candidate setup is unavailable.",
                empty_action_href=None,
            )
            return (
                summary.children,
                "/research/ideas",
                "secondary-action",
                "Review the accepted Candidate while its exact implementation is pending.",
                "Return to accepted idea",
                title,
                "setup-context-state setup-context-state-blocked",
            )
        if configuration_id != binding.configuration.configuration_id:
            configuration_id = None
        elif configuration_id not in readiness_by_id:
            readiness_by_id[configuration_id] = configuration_readiness(binding.configuration, None)
        return _preview_outputs(configuration_id, readiness_by_id)

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
        return content, content
