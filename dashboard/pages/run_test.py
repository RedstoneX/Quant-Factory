"""Final approved-research review and explicit launch page."""

from __future__ import annotations

from pathlib import Path

from dash import dcc, html

from dashboard.candidate_workflow import candidate_configuration_binding
from dashboard.components.configuration_summary import configuration_summary
from dashboard.components.operator_context import operator_context
from dashboard.components.run_test_review import run_launch_rail
from dashboard.pages.common import page_heading
from dashboard.run_adapter import (
    CatalogSnapshot,
    ConfigurationReadinessView,
    SavedConfigurationView,
    configuration_readiness_by_id,
    list_idea_drafts,
    list_saved_configurations,
)


def layout(
    *,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    database: str | Path | None = None,
    catalog_snapshot: CatalogSnapshot | None = None,
    readiness_by_id: dict[str, ConfigurationReadinessView] | None = None,
    loading: bool = False,
) -> html.Div:
    """Render one explicit, route-gated research launch control."""

    available = (
        list_saved_configurations(database)
        if configurations is None and database is not None
        else configurations
        if configurations is not None
        else ()
    )
    readiness_by_id = dict(readiness_by_id or {})
    missing_readiness = tuple(
        configuration
        for configuration in available
        if configuration.configuration_id not in readiness_by_id
    )
    if missing_readiness:
        readiness_by_id.update(
            configuration_readiness_by_id(missing_readiness, catalog_snapshot)
        )
    binding = None
    if database is not None:
        drafts = list_idea_drafts(database)
        binding = candidate_configuration_binding(
            drafts[0].draft_id if drafts else None,
            database=database,
        )
    selected = binding.configuration if binding is not None else None
    readiness = readiness_by_id.get(selected.configuration_id) if selected else None
    ready_for_confirmation = bool(readiness and readiness.ready and not loading)
    preview = configuration_summary(
        readiness,
        component_id="run-configuration-preview",
        loading=loading,
        empty_title=(
            "Implementation needed"
            if binding is not None and binding.blocker_code == "implementation_required"
            else "No Candidate test is ready"
        ),
        empty_message=(
            binding.blocker_reason
            if binding is not None and binding.blocker_reason
            else "Choose and accept a Candidate on Ideas, then complete its exact implementation."
        ),
    )
    # The page-owned callback prepares a browser-session key before enabling.
    launch_disabled = True
    launch_title = "Preparing a durable browser-session run ticket."

    return html.Div(
        [
            page_heading(
                "RESEARCH / RUN TEST",
                "Final review before one test",
                "Nothing can change here. This is the only page that can start a research test.",
            ),
            html.Section(
                [
                    html.Span("EXACT CANDIDATE", className="page-eyebrow"),
                    html.Strong(
                        binding.identity.title
                        if binding is not None and binding.identity is not None
                        else "No runnable Candidate selected"
                    ),
                    html.Small(
                        (
                            f"{binding.identity.candidate_id} · version {binding.identity.short_version} · {binding.identity.attribution}"
                            if binding is not None and binding.identity is not None
                            else "Run Test will not substitute a fixture or unrelated setup."
                        )
                    ),
                ],
                id="run-candidate-identity",
                className="candidate-workflow-identity candidate-workflow-identity-run",
            ),
            operator_context(component_id="run-test-operator-context"),
            dcc.Store(
                id="run-test-launch-state",
                storage_type="session",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2("Exactly what will be tested"),
                                            html.P(
                                                "This saved version is locked. Return to Set up to create a new version.",
                                                className="section-description",
                                            ),
                                        ]
                                    ),
                                    html.Span("Locked for review", className="surface-status-text"),
                                ],
                                className="surface-heading",
                            ),
                            preview,
                            html.Div(
                                [
                                    html.Div([html.Span("Input"), html.Strong("1 persisted setup")], className="launch-flow-step"),
                                    html.Span("→", className="launch-flow-arrow", **{"aria-hidden": "true"}),
                                    html.Div([html.Span("Engine"), html.Strong("VectorBT research run")], className="launch-flow-step"),
                                    html.Span("→", className="launch-flow-arrow", **{"aria-hidden": "true"}),
                                    html.Div([html.Span("Persistence"), html.Strong("Run, artifacts, lineage")], className="launch-flow-step"),
                                    html.Span("→", className="launch-flow-arrow", **{"aria-hidden": "true"}),
                                    html.Div([html.Span("Destination"), html.Strong("Results")], className="launch-flow-step"),
                                ],
                                className="launch-flow",
                            ),
                        ],
                        className="run-contract-workspace",
                    ),
                    run_launch_rail(
                        ready=ready_for_confirmation,
                        launch_disabled=launch_disabled,
                        launch_title=launch_title,
                    ),
                ],
                className="run-review-grid",
            ),
            html.Div(
                [
                    html.Strong("After launch:"),
                    html.Span(
                        " this page keeps the same run visible through queued, running, retrying, failed, or succeeded states. Results remains the separate analysis step."
                    ),
                ],
                className="run-review-footer",
            ),
        ],
        className="page-container run-test-page",
    )
