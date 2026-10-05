"""Final exact-Candidate review and explicit research-launch page."""

from __future__ import annotations

from pathlib import Path

from dash import dcc, html

from dashboard.candidate_workflow import candidate_configuration_binding
from dashboard.components.configuration_summary import configuration_summary
from dashboard.components.run_test_review import run_launch_rail
from dashboard.run_adapter import CatalogSnapshot, ConfigurationField, ConfigurationReadinessView, SavedConfigurationView, configuration_readiness_by_id, list_idea_drafts, list_saved_configurations


def layout(*, configurations: tuple[SavedConfigurationView, ...] | None = None, database: str | Path | None = None, catalog_snapshot: CatalogSnapshot | None = None, readiness_by_id: dict[str, ConfigurationReadinessView] | None = None, loading: bool = False) -> html.Div:
    """Render one route-gated research launch without weakening confirmation."""
    available = list_saved_configurations(database) if configurations is None and database is not None else configurations or ()
    readiness_by_id = dict(readiness_by_id or {})
    missing = tuple(item for item in available if item.configuration_id not in readiness_by_id)
    if missing:
        readiness_by_id.update(configuration_readiness_by_id(missing, catalog_snapshot))
    binding = None
    if database is not None:
        drafts = list_idea_drafts(database)
        binding = candidate_configuration_binding(drafts[0].draft_id if drafts else None, database=database)
    selected = binding.configuration if binding is not None else None
    readiness = readiness_by_id.get(selected.configuration_id) if selected else None
    ready = bool(readiness and readiness.ready and not loading)
    technical_preview = configuration_summary(
        readiness,
        component_id="run-configuration-preview",
        loading=loading,
        empty_title="Implementation needed" if binding is not None and binding.blocker_code == "implementation_required" else "No Candidate test is ready",
        empty_message=binding.blocker_reason if binding is not None and binding.blocker_reason else "Choose and accept a Candidate on Ideas, then complete its exact implementation.",
    )
    return html.Div(
        [
            _page_header(),
            _status_quartet(ready),
            _configuration_strip(binding, readiness, ready),
            dcc.Store(id="run-test-launch-state", storage_type="session"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Header(
                                [
                                    html.Div([html.H2("Immutable run contract"), html.P("This is the exact persisted configuration the engine will receive.", className="section-description")]),
                                    html.Div([html.Span("1 configuration", className="surface-badge"), html.Span("Research only", className="surface-badge run-boundary-badge")], className="run-contract-badges"),
                                ],
                                className="surface-heading",
                            ),
                            _contract_grid(readiness),
                            _launch_flow(),
                            _provenance(readiness, binding),
                            html.Div(
                                technical_preview,
                                className="run-callback-controls",
                            ),
                        ],
                        className="run-contract-workspace",
                    ),
                    run_launch_rail(ready=ready, launch_disabled=True, launch_title="Preparing a durable browser-session run ticket."),
                ],
                className="run-approved-workspace",
            ),
            html.Div([html.Strong("After launch:"), html.Span(" this page keeps the same run visible through queued, running, retrying, failed, or succeeded states."), html.Span("Results remains a separate analysis step.")], className="run-review-footer"),
        ],
        className="page-container run-test-page",
    )


def _page_header() -> html.Header:
    return html.Header(
        [html.P("RESEARCH / RUN TEST", className="page-eyebrow"), html.H1("Review before running", className="page-title"), html.P("Confirm the immutable configuration, provenance and preflight checks before starting exactly one run.", className="page-description")],
        className="page-heading",
    )


def _status_quartet(ready: bool) -> html.Section:
    return html.Section(
        [
            _strip_item("Run status", "Not run"),
            _strip_item("Evidence outcome", "Not run"),
            _strip_item("Human decision", "Accepted Candidate" if ready else "Implementation required"),
            _strip_item("Next safe action", "Review and run test" if ready else "Complete implementation"),
        ],
        id="run-test-operator-context",
        className="run-status-quartet",
        **{"aria-label": "Test review context"},
    )


def _configuration_strip(binding, readiness, ready: bool) -> html.Section:
    identity = binding.identity if binding is not None else None
    return html.Section(
        [
            html.Div([html.Span("Approved saved configuration"), html.Div([html.Strong(identity.title if identity is not None else "No runnable Candidate selected"), html.Small(identity.attribution if identity is not None else "No source recorded")], id="run-candidate-identity")], className="run-selector-cell run-selector-primary"),
            _strip_item("Configuration type", readiness.lifecycle.replace("_", " ").title() if readiness else "Unavailable"),
            _strip_item("Candidate version", identity.short_version if identity is not None else "Unavailable"),
            html.Div("Launchable" if ready else "Blocked", className="run-selector-state run-selector-state-ready" if ready else "run-selector-state run-selector-state-blocked"),
        ],
        className="run-configuration-strip",
        **{"aria-label": "Selected runnable configuration"},
    )


def _strip_item(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value)], className="run-selector-cell")


def _contract_grid(readiness: ConfigurationReadinessView | None) -> html.Div:
    cells = (
        ("Instrument & timeframe", f"{readiness.instrument} · {readiness.timeframe}"),
        ("Exact period", readiness.requested_coverage),
        ("Provider", f"{readiness.provider} · {readiness.dataset}"),
        ("Fixed rules", _field_sentence(readiness.parameters, "No adjustable rules")),
        ("Execution", _field_sentence(readiness.execution_assumptions, "No assumptions recorded")),
        ("Local data", f"{readiness.local_availability} · {readiness.local_validation}"),
    ) if readiness is not None else (("Implementation", "No exact Candidate implementation is bound yet."),)
    return html.Div([html.Div([html.Span(label), html.Strong(value)]) for label, value in cells], className="run-contract-grid")


def _field_sentence(fields: tuple[ConfigurationField, ...], empty: str) -> str:
    return " · ".join(f"{field.label}: {field.value}" for field in fields) or empty


def _launch_flow() -> html.Section:
    items = (("Input", "1 persisted setup"), ("Engine", "VectorBT research run"), ("Persistence", "Run, artifacts, lineage"), ("Destination", "Results"))
    children: list[object] = []
    for index, (label, value) in enumerate(items):
        if index:
            children.append(html.Span("→", className="run-flow-arrow", **{"aria-hidden": "true"}))
        children.append(html.Div([html.Span(label), html.Strong(value)], className="run-flow-step"))
    return html.Section([html.Div([html.H3("What one click will do"), html.Span("No hidden expansion")], className="run-flow-heading"), html.Div(children, className="run-flow-line")], className="run-launch-flow")


def _provenance(readiness, binding) -> html.Div:
    identity = binding.identity if binding is not None else None
    return html.Div(
        [
            _detail_section("Data & provenance", (("Data binding", readiness.dataset if readiness else "Unavailable"), ("Coverage", readiness.actual_coverage if readiness else "Unavailable"), ("Provider", readiness.provider if readiness else "Unavailable"), ("Lineage", f"Idea → {identity.short_version} → immutable setup" if identity is not None and readiness is not None else "Implementation not yet bound"))),
            _detail_section("Run behavior", (("Submission", "Explicit confirmation; exactly once"), ("Accumulation", "As saved in the immutable setup" if readiness else "Unavailable"), ("Position boundary", "As saved in the immutable setup" if readiness else "Unavailable"), ("Promotion", "Never automatic"))),
        ],
        className="run-provenance-grid",
    )


def _detail_section(title: str, rows: tuple[tuple[str, str], ...]) -> html.Section:
    return html.Section([html.H3(title), html.Dl([html.Div([html.Dt(label), html.Dd(value)]) for label, value in rows])], className="run-provenance-section")
