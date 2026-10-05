"""Approved exact-Candidate setup presentation."""

from __future__ import annotations

from pathlib import Path

from dash import dcc, html

from dashboard.candidate_workflow import candidate_configuration_binding
from dashboard.components.candidate_setup import candidate_identity_summary, candidate_implementation_boundary
from dashboard.components.configuration_summary import configuration_summary
from dashboard.run_adapter import CatalogSnapshot, ConfigurationReadinessView, SavedConfigurationView, SetupStrategyView, configuration_readiness_by_id, list_idea_drafts, list_saved_configurations


def layout(*, configurations: tuple[SavedConfigurationView, ...] | None = None, setup_strategies: tuple[SetupStrategyView, ...] | None = None, database: str | Path | None = None, catalog_snapshot: CatalogSnapshot | None = None, readiness_by_id: dict[str, ConfigurationReadinessView] | None = None, loading: bool = False) -> html.Div:
    """Show one exact Candidate setup without implying that it can already run."""
    del setup_strategies
    available = list_saved_configurations(database) if database is not None else configurations or ()
    readiness_by_id = dict(readiness_by_id or {})
    missing = tuple(item for item in available if item.configuration_id not in readiness_by_id)
    if missing:
        readiness_by_id.update(configuration_readiness_by_id(missing, catalog_snapshot))
    drafts = list_idea_drafts(database) if database is not None else ()
    selected_draft = drafts[0] if drafts else None
    binding = candidate_configuration_binding(selected_draft.draft_id if selected_draft else None, database=database) if database is not None else None
    configuration = binding.configuration if binding is not None else None
    readiness = readiness_by_id.get(configuration.configuration_id) if configuration is not None else None
    ready = bool(readiness and readiness.ready and not loading)
    preview = configuration_summary(
        readiness,
        component_id="configuration-preview",
        loading=loading,
        empty_title="Implementation needed",
        empty_message=binding.blocker_reason if binding is not None and binding.blocker_reason else "Choose and accept a Candidate on Ideas before preparing a test.",
        empty_action_href=None,
    )
    state = "Ready to review" if ready else "Setup blocked" if readiness is not None else "Implementation needed" if binding is not None and binding.blocker_code == "implementation_required" else "Candidate not ready"
    return html.Div(
        [
            _page_header(state),
            dcc.Store(id="selected-configuration-state", data=configuration.configuration_id if configuration else None, storage_type="session"),
            dcc.Store(id="created-configuration-state", storage_type="session"),
            _identity_strip(selected_draft, binding, configuration, state, ready),
            html.Main(
                [
                    html.Section(
                        [
                            html.Header(
                                [
                                    html.Div([html.H2("Fixed-rule preview"), html.P("Review the exact accepted meaning and persisted setup without running research.", className="section-description")]),
                                    html.Span("Saved contract" if readiness else "Not executable", className="surface-status-text"),
                                ],
                                className="setup-section-heading",
                            ),
                            _candidate_contract(binding),
                            html.Div(
                                [
                                    html.Label("Approved Candidate implementation", id="configuration-selector-label", htmlFor="configuration-selector", className="field-label"),
                                    _configuration_selector(configuration, loading),
                                    html.P("Only an implementation linked to this exact Candidate may appear.", className="field-help"),
                                ],
                                className="setup-approved-implementation",
                                role="group",
                                **{"aria-labelledby": "configuration-selector-label"},
                            ),
                            html.Div(preview, className="setup-configuration-preview"),
                        ],
                        className="setup-contract-workspace",
                    ),
                    html.Aside(
                        [
                            candidate_implementation_boundary(open_boundary=configuration is None),
                            html.P("Saving a setup never starts a test. Run test is the separate launch page.", className="setup-footer-note"),
                        ],
                        className="setup-decision-rail",
                    ),
                ],
                className="setup-approved-workspace",
            ),
        ],
        className="page-container setup-page",
    )


def _configuration_selector(configuration: SavedConfigurationView | None, loading: bool) -> dcc.Dropdown:
    if configuration is None:
        return dcc.Dropdown(id="configuration-selector", options=[], value=None, disabled=True, placeholder="Waiting for the exact implementation", persistence=True, persistence_type="session")
    return dcc.Dropdown(id="configuration-selector", options=[{"label": configuration.label, "value": configuration.configuration_id, "disabled": not configuration.launchable}], value=configuration.configuration_id, disabled=loading, clearable=False, persistence=True, persistence_type="session")


def _page_header(state: str) -> html.Header:
    return html.Header(
        [
            html.Div([html.P("RESEARCH / SET UP", className="page-eyebrow"), html.H1("Define the experiment", className="page-title"), html.P("See exactly what Quant Factory can prepare before an immutable setup is saved.", className="page-description")]),
            html.Span(state, className="setup-header-state"),
        ],
        className="page-heading page-heading-with-actions setup-page-heading",
    )


def _identity_strip(selected_draft, binding, configuration, state: str, ready: bool) -> html.Section:
    identity = binding.identity if binding is not None else None
    return html.Section(
        [
            _identity_cell("From idea", candidate_identity_summary(selected_draft, binding), identity.attribution if identity is not None else "No accepted Candidate"),
            _identity_cell("Approved implementation", configuration.label if configuration is not None else "Implementation required", "Exact Candidate binding only"),
            _identity_cell("Saved setup", configuration.experiment_id if configuration is not None else "Not created", "Immutable after saving"),
            html.Div(html.Span(state, id="setup-context-state", className="setup-context-state setup-context-state-ready" if ready else "setup-context-state setup-context-state-blocked"), id="setup-current-state", className="setup-identity-state"),
        ],
        className="setup-approved-identity",
        **{"aria-label": "Selected Candidate setup"},
    )


def _identity_cell(label: str, value, detail: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value), html.Small(detail)], className="setup-approved-identity-cell")


def _candidate_contract(binding) -> html.Section:
    identity = binding.identity if binding is not None else None
    if identity is None:
        return html.Section([html.H3("No accepted Candidate selected"), html.P("Choose and accept one Candidate on Ideas before Setup can define an experiment.", className="empty-state-copy")], className="setup-candidate-contract setup-candidate-contract-empty")
    return html.Section(
        [
            html.Div([html.Span("EXACT CANDIDATE", className="setup-state-label"), html.H3(identity.title), html.P(identity.rationale)], className="setup-candidate-summary"),
            html.Div(
                [
                    _contract_fact("Idea family", identity.family.replace("_", " ").title()),
                    _contract_fact("Version", identity.short_version),
                    _contract_fact("Fixed definition", identity.fixed_definition),
                    _contract_fact("Evidence contract", identity.evidence_contract),
                ],
                className="setup-candidate-facts",
            ),
            html.P("The implementation preview remains unavailable until these exact rules are implemented and bound.", className="setup-implementation-note") if not binding.bound else None,
        ],
        className="setup-candidate-contract",
    )


def _contract_fact(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value or "Not specified")])
