"""Final exact-Candidate review and explicit research-launch page."""

from __future__ import annotations

import json
from pathlib import Path

from dash import dcc, html

from dashboard.candidate_workflow import candidate_configuration_binding
from dashboard.components.configuration_summary import configuration_summary
from dashboard.components.run_test_review import run_launch_rail
from dashboard.run_adapter import CatalogSnapshot, ConfigurationField, ConfigurationReadinessView, SavedConfigurationView, configuration_readiness


def layout(*, configurations: tuple[SavedConfigurationView, ...] | None = None, database: str | Path | None = None, catalog_snapshot: CatalogSnapshot | None = None, readiness_by_id: dict[str, ConfigurationReadinessView] | None = None, loading: bool = False) -> html.Div:
    """Render one route-gated research launch without weakening confirmation."""
    del configurations, catalog_snapshot, readiness_by_id
    return html.Div(
        [dcc.Store(id="run-test-launch-state", storage_type="session"),
         html.Div(render_selected_run_test(None, None, database=database, loading=loading), id="run-test-dynamic-view")],
        className="page-container run-test-page",
    )


def render_selected_run_test(draft_id: str | None, configuration_id: str | None, *, database: str | Path | None, loading: bool = False) -> html.Div:
    """Show only the browser-selected Candidate's exact persisted test contract."""
    binding = candidate_configuration_binding(draft_id, database=database) if database is not None else None
    selected = binding.configuration if binding is not None and binding.bound else None
    if selected is not None and selected.configuration_id != configuration_id:
        selected = None
    readiness = configuration_readiness(selected, None) if selected is not None else None
    ready = bool(readiness and readiness.ready and not loading)
    blocker = (binding.blocker_reason if binding is not None and not binding.bound else
               "The selected saved setup does not match this Candidate." if binding is not None and selected is None else
               "The saved configuration did not pass preflight." if not ready else None)
    technical_preview = configuration_summary(
        readiness,
        component_id="run-configuration-preview",
        loading=loading,
        empty_title="Implementation needed" if binding is not None and binding.blocker_code == "implementation_required" else "No Candidate test is ready",
        empty_message=blocker or "Choose and accept a Candidate on Ideas, then complete its exact implementation.",
    )
    return html.Div(
        [
            _page_header(),
            _status_quartet(binding, ready),
            _configuration_strip(binding, readiness, ready),
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
                            _contract_grid(readiness, binding),
                            _launch_flow(),
                            _provenance(readiness, binding, selected),
                            html.Div(
                                technical_preview,
                                className="run-callback-controls",
                            ),
                        ],
                        className="run-contract-workspace",
                    ),
                    run_launch_rail(ready=ready, launch_disabled=True, launch_title=blocker or "Confirm this saved test before starting.", blocker=blocker),
                ],
                className="run-approved-workspace",
            ),
            html.Div([html.Strong("After launch:"), html.Span(" this page keeps the same run visible through queued, running, retrying, failed, or succeeded states."), html.Span("Results remains a separate analysis step.")], className="run-review-footer"),
        ],
        className="run-test-selected-view",
    )


def _page_header() -> html.Header:
    return html.Header(
        [html.P("RESEARCH / RUN TEST", className="page-eyebrow"), html.H1("Review before running", className="page-title"), html.P("Confirm the immutable configuration, provenance and preflight checks before starting exactly one run.", className="page-description")],
        className="page-heading",
    )


def _status_quartet(binding, ready: bool) -> html.Section:
    accepted = binding is not None and binding.identity is not None and binding.identity.status == "owner_approved"
    return html.Section(
        [
            _strip_item("Run status", "Not run"),
            _strip_item("Evidence outcome", "Not run"),
            _strip_item("Human decision", "Accepted Candidate" if accepted else "Candidate acceptance required"),
            _strip_item("Next safe action", "Review and run test" if ready else "Complete implementation" if accepted else "Select accepted Candidate"),
        ],
        id="run-test-operator-context",
        className="run-status-quartet",
        **{"aria-label": "Test review context"},
    )


def _configuration_strip(binding, readiness, ready: bool) -> html.Section:
    identity = binding.identity if binding is not None else None
    return html.Section(
        [
            html.Div([html.Span("Approved saved configuration"), html.Div([html.Select([html.Option(identity.title if identity is not None else "No runnable Candidate selected", value=readiness.configuration_id if readiness is not None else "")], disabled=True, **{"aria-label": "Approved saved configuration"}, className="run-locked-configuration-select"), html.Small(identity.attribution if identity is not None else "No source recorded")], id="run-candidate-identity")], className="run-selector-cell run-selector-primary"),
            _strip_item("Configuration type", readiness.lifecycle.replace("_", " ").title() if readiness else "Unavailable"),
            _strip_item("Candidate version", identity.short_version if identity is not None else "Unavailable"),
            html.Div("Ready for final review" if ready else "Blocked", className="run-selector-state run-selector-state-ready" if ready else "run-selector-state run-selector-state-blocked"),
        ],
        className="run-configuration-strip",
        **{"aria-label": "Selected runnable configuration"},
    )


def _strip_item(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value)], className="run-selector-cell")


def _contract_grid(readiness: ConfigurationReadinessView | None, binding) -> html.Div:
    execution = binding.configuration.execution if binding is not None and binding.configuration is not None else {}
    cells = (
        ("Instrument & timeframe", f"{readiness.instrument} · {readiness.timeframe}"),
        ("Exact period", readiness.requested_coverage),
        ("Provider", f"{readiness.provider} · {readiness.dataset}"),
        ("Fixed rules", _fixed_rule_summary(binding) or _field_sentence(readiness.parameters, "No adjustable rules")),
        ("Execution", " · ".join(f"{key.replace('_', ' ').title()}: {execution[key]}" for key in ("mode", "direction", "order_size") if key in execution) or "No execution assumptions recorded"),
        ("Sizing & costs", " · ".join(f"{key.replace('_', ' ').title()}: {execution[key]}" for key in ("position_sizing", "initial_cash", "fixed_fee_per_contract_per_side", "slippage_ticks") if key in execution) or "No costs recorded"),
    ) if readiness is not None else (("Implementation", "No exact Candidate implementation is bound yet."),)
    return html.Div([html.Div([html.Span(label), html.Strong(value)]) for label, value in cells], className="run-contract-grid")


def _field_sentence(fields: tuple[ConfigurationField, ...], empty: str) -> str:
    return " · ".join(f"{field.label}: {field.value}" for field in fields) or empty


def _fixed_rule_summary(binding) -> str:
    draft = binding.draft if binding is not None else None
    if draft is None or not getattr(draft, "candidate_json", None):
        return ""
    try:
        fixed = json.loads(draft.candidate_json).get("fixed", {})
    except (TypeError, ValueError):
        return ""
    if not isinstance(fixed, dict):
        return ""
    keys = ("opening_range_minutes", "breakout_buffer_ticks", "vwap_confirmation", "minimum_breakout_body_ratio", "target_r", "time_exit")
    selected = [key for key in keys if key in fixed] or list(fixed)[:6]
    return " · ".join(f"{key.replace('_', ' ').title()}: {fixed[key]}" for key in selected)


def _launch_flow() -> html.Section:
    items = (("Input", "1 persisted setup"), ("Engine", "VectorBT research run"), ("Persistence", "Run, artifacts, lineage"), ("Destination", "Results"))
    children: list[object] = []
    for index, (label, value) in enumerate(items):
        if index:
            children.append(html.Span("→", className="run-flow-arrow", **{"aria-hidden": "true"}))
        children.append(html.Div([html.Span(label), html.Strong(value)], className="run-flow-step"))
    return html.Section([html.Div([html.H3("What one click will do"), html.Span("No hidden expansion")], className="run-flow-heading"), html.Div(children, className="run-flow-line")], className="run-launch-flow")


def _provenance(readiness, binding, configuration) -> html.Div:
    identity = binding.identity if binding is not None else None
    execution = configuration.execution if configuration is not None else {}
    fixed = {}
    if binding is not None and binding.draft is not None and getattr(binding.draft, "candidate_json", None):
        try:
            fixed = json.loads(binding.draft.candidate_json).get("fixed", {})
        except (TypeError, ValueError):
            pass
    boundary = f"Flat by {fixed['time_exit']}" if isinstance(fixed, dict) and fixed.get("time_exit") else "See exact Candidate rule"
    return html.Div(
        [
            _detail_section("Data & provenance", (("Data binding", readiness.dataset if readiness else "Unavailable"), ("Coverage", readiness.actual_coverage if readiness else "Unavailable"), ("Provider", readiness.provider if readiness else "Unavailable"), ("Lineage", f"Idea → {identity.short_version} → immutable setup" if identity is not None and readiness is not None else "Implementation not yet bound"))),
            _detail_section("Run behavior", (("Submission", "Explicit confirmation; exactly once"), ("Accumulation", "On" if execution.get("accumulate") is True else "Off" if execution.get("accumulate") is False else "Unavailable"), ("Position boundary", boundary if configuration is not None else "Unavailable"), ("Promotion", "Never automatic"))),
        ],
        className="run-provenance-grid",
    )


def _detail_section(title: str, rows: tuple[tuple[str, str], ...]) -> html.Section:
    return html.Section([html.H3(title), html.Dl([html.Div([html.Dt(label), html.Dd(value)]) for label, value in rows])], className="run-provenance-section")
