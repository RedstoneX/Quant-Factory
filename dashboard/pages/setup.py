"""Page-local approved Set up composition for one exact saved Candidate."""

from __future__ import annotations

import json
from pathlib import Path

from dash import dcc, html
import plotly.graph_objects as go

from dashboard.candidate_workflow import candidate_configuration_binding
from dashboard.mes_candidate_setup import candidate_setup_definition
from dashboard.run_adapter import (
    CatalogSnapshot,
    ConfigurationReadinessView,
    SavedConfigurationView,
    SetupStrategyView,
    configuration_readiness,
)
from persistence import canonical_json
from strategies import get_strategy
from strategies.mes_vwap_orb_candidate import MES_VWAP_ORB_SPEC, STRATEGY_ID as ORB_STRATEGY_ID
from strategies.mes_sma_crossover_candidate import MES_SMA_SPEC


def layout(
    *,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    setup_strategies: tuple[SetupStrategyView, ...] | None = None,
    database: str | Path | None = None,
    catalog_snapshot: CatalogSnapshot | None = None,
    readiness_by_id: dict[str, ConfigurationReadinessView] | None = None,
    loading: bool = False,
) -> html.Div:
    """Mount a safe Set up shell; browser selection hydrates its exact content."""
    del configurations, setup_strategies, catalog_snapshot
    return html.Div(
        [
            dcc.Store(id="selected-configuration-state", storage_type="session"),
            dcc.Store(id="created-configuration-state", storage_type="session"),
            html.Div(render_selected_setup(None, database=database, readiness_by_id=readiness_by_id, loading=loading), id="setup-dynamic-view"),
            html.Div("", id="idea-configuration-status", role="status", className="setup-save-status"),
            html.Div(id="configuration-preview", className="setup-readiness-detail"),
        ],
        className="page-container setup-page setup-reference-page",
    )


def render_selected_setup(
    draft_id: str | None,
    *,
    database: str | Path | None,
    readiness_by_id: dict[str, ConfigurationReadinessView] | None = None,
    loading: bool = False,
) -> html.Div:
    """Render only the browser-selected Candidate and its linked saved setup."""
    binding = candidate_configuration_binding(draft_id, database=database) if database is not None else None
    identity = binding.identity if binding is not None else None
    definition = candidate_setup_definition(identity)
    exact = definition is not None
    configuration = binding.configuration if binding is not None and binding.bound else None
    preview = configuration
    if exact and preview is None and binding is not None and binding.blocker_code == "implementation_required":
        document = json.loads(canonical_json(definition.configuration_document()))
        preview = SavedConfigurationView(
            configuration_id="", experiment_id=document["experiment_id"],
            strategy_id=document["strategy_id"], strategy_version=document["strategy_version"],
            strategy_name=MES_VWAP_ORB_SPEC.identity.name if document["strategy_id"] == ORB_STRATEGY_ID else MES_SMA_SPEC.identity.name, lifecycle="candidate", active=True,
            parameters=document["parameters"], execution=document["execution"],
            market_data=document["market_data"], config_hash="", document=document,
        )
    readiness = (readiness_by_id or {}).get(configuration.configuration_id) if configuration is not None else None
    if preview is not None and readiness is None:
        readiness = configuration_readiness(preview, None)
    implementation_ready = _implementation_ready(preview) if preview is not None else False
    saved = configuration is not None
    ready = bool(saved and readiness and readiness.ready and implementation_ready and not loading)
    state = "Saved · ready for review" if ready else "Saved · needs attention" if saved else "Ready to save" if preview is not None and readiness and readiness.ready and implementation_ready else "Setup needs attention" if preview is not None else "Implementation required" if identity and identity.status == "owner_approved" else "Candidate required"
    message = "Saved setup does not launch a test. Continue to Run test for a separate final review." if ready else "The approved Candidate and its fixed rules are shown here. Saving never launches a test." if preview is not None and not saved else "Saved setup needs its readiness checks before Run test." if saved else binding.blocker_reason if binding is not None else "Select an accepted Candidate on Ideas first."
    return html.Div(
        [
            html.Header(
                [
                    html.Div([html.P("RESEARCH / SET UP", className="page-eyebrow"), html.H1("Define the experiment", className="page-title"), html.P("See exactly what Quant Factory will test before an immutable setup is saved.", className="page-description")]),
                    html.Button("Save setup draft", id="save-idea-configuration", n_clicks=0, disabled=not exact or saved or loading or not implementation_ready or not (readiness and readiness.ready), className="setup-save-button"),
                ],
                className="page-heading page-heading-with-actions setup-page-heading",
            ),
            html.Section(
                [
                    _identity_cell("From idea", identity.title if identity else "No Candidate selected", f"{identity.attribution} · {identity.short_version}" if identity else "Select on Ideas", cell_id="setup-candidate-identity"),
                    _strategy_cell(preview.strategy_name if preview else "Implementation required", "Exact Candidate implementation" if saved and implementation_ready else "Implementation unavailable" if saved else "Fixed owner-approved rules; no tuning" if preview else "No unrelated fixture substitution"),
                    html.Div([html.Label("Saved setup", id="configuration-selector-label", htmlFor="configuration-selector"), dcc.Dropdown(id="configuration-selector", options=[{"label": configuration.experiment_id, "value": configuration.configuration_id}] if saved else [], value=configuration.configuration_id if saved else None, disabled=not saved, clearable=False, placeholder="New setup draft"), html.Small(configuration.configuration_id[:12] if saved else "Save to create an immutable configuration" if exact else "No matching configuration")], className="setup-approved-identity-cell", role="group", **{"aria-labelledby": "configuration-selector-label"}),
                    html.Div(html.Span(state, id="setup-context-state", className="setup-context-state setup-context-state-ready" if ready else "setup-context-state setup-context-state-blocked"), id="setup-current-state", className="setup-identity-state"),
                ],
                className="setup-approved-identity",
                **{"aria-label": "Experiment identity"},
            ),
            html.Main(
                [
                    html.Section(
                        [
                            html.Header([html.Div([html.H2("Fixed-rule preview"), html.P("Entry, exit and risk boundaries without running research.")]), html.Div([html.Span(f"{_saved_text(preview.market_data.get('symbol'))} · {_saved_text(preview.market_data.get('interval') or preview.market_data.get('timeframe'))}" if preview else "Selected Candidate", className="setup-ref-badge"), html.Span("Not evidence", className="setup-ref-badge setup-ref-badge-amber")], className="setup-ref-badges")], className="setup-ref-panel-head"),
                            _rule_preview() if exact and definition.experiment.strategy_id == ORB_STRATEGY_ID else _other_candidate_preview(identity, preview, message),
                            _other_candidate_matrix(preview, readiness),
                            _other_candidate_contract(identity, preview, saved, ready, message, readiness, implementation_ready),
                        ],
                        className="setup-ref-analysis",
                    ),
                    _other_candidate_controls(identity, preview, readiness, saved=saved, ready=ready, implementation_ready=implementation_ready),
                ],
                className="setup-ref-workspace",
            ),
        ],
        className="setup-selected-view",
    )


def _identity_cell(label: str, value: str, detail: str, *, cell_id: str | None = None) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value), html.Small(detail)], className="setup-approved-identity-cell", **({"id": cell_id} if cell_id is not None else {}))


def _strategy_cell(value: str, detail: str) -> html.Div:
    return html.Div([html.Span("Approved strategy"), html.Select([html.Option(value, value=value)], disabled=True, **{"aria-label": "Approved strategy"}, className="setup-identity-select"), html.Small(detail)], className="setup-approved-identity-cell")


def _implementation_ready(configuration: SavedConfigurationView) -> bool:
    try:
        implementation = get_strategy(configuration.strategy_id)
    except KeyError:
        return False
    return implementation.spec.identity.version == configuration.strategy_version


def _saved_text(value: object) -> str:
    if value is None:
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _period(configuration: SavedConfigurationView) -> tuple[str, str]:
    market = configuration.market_data
    validation = configuration.document.get("candidate_validation_runtime") or {}
    end = validation.get("data_as_of") if isinstance(validation, dict) else None
    if isinstance(end, str) and "T" in end:
        end = end.split("T", 1)[0]
    return (
        _saved_text(market.get("requested_start") or market.get("coverage_start")),
        _saved_text(end or market.get("requested_end") or market.get("coverage_end") or market.get("end_date_policy")),
    )


def _costs(execution: dict) -> str:
    fee = execution.get("fixed_fee_per_contract_per_side")
    slippage_ticks = execution.get("slippage_ticks")
    if fee is not None:
        return f"${fee} / contract / side; {slippage_ticks} adverse tick(s) / side" if slippage_ticks is not None else f"${fee} / contract / side"
    return f"Fee {_rate(execution.get('fees'))}; adverse slippage {_rate(execution.get('slippage'))} per side"


def _rate(value: object) -> str:
    return f"{float(value) * 100:g}%" if isinstance(value, (int, float)) else _saved_text(value)


def _execution_label(value: object) -> str:
    if value == "both":
        return "Long and short"
    return str(value).replace("_", " ").capitalize() if isinstance(value, str) else _saved_text(value)


def _capital(value: object) -> str:
    return f"${value:,.0f}" if isinstance(value, (int, float)) else _saved_text(value)


def _stress_costs(configuration: SavedConfigurationView) -> str | None:
    runtime = configuration.document.get("candidate_validation_runtime") or {}
    robustness = runtime.get("robustness") or {} if isinstance(runtime, dict) else {}
    stress = robustness.get("fixed_rule_cost_stress") if isinstance(robustness, dict) else None
    if not isinstance(stress, dict):
        return None
    return f"Higher-cost check: ${stress['fixed_fee_per_contract_per_side']} / contract / side and {stress['slippage_ticks']} adverse ticks / side."


def _other_candidate_preview(identity, configuration: SavedConfigurationView | None, message: str) -> html.Section:
    try:
        definition = json.loads(identity.fixed_definition) if identity else {}
    except (TypeError, ValueError):
        definition = {"rule": identity.fixed_definition} if identity else {}
    if not isinstance(definition, dict):
        definition = {"rule": definition}
    lines = [f"{key.replace('_', ' ').title()}: {', '.join(str(item) for item in value) if isinstance(value, list) else _saved_text(value)}" for section, entries in definition.items() for key, value in (entries.items() if isinstance(entries, dict) else ((section, entries),))]
    return html.Section(
        [
            html.Div([html.Strong("Selected Candidate"), html.Span("Persisted contract · no synthetic strategy chart")], className="setup-rule-toolbar"),
            html.Div(
                [html.H3(identity.title if identity else "No Candidate selected"),
                 html.P(identity.rationale if identity else message),
                 html.Span("Accepted fixed definition" if configuration else "Setup blocked"),
                 html.Div([html.P(line, className="setup-generic-definition") for line in lines] if identity else html.P(message), className="setup-generic-definition-list")],
                className="setup-generic-preview",
            ),
            html.P("Only the selected Candidate's saved definition is shown. No test has been run from this page.", className="setup-rule-note"),
        ],
        className="setup-rule-preview",
    )


def _other_candidate_matrix(configuration: SavedConfigurationView | None, readiness: ConfigurationReadinessView | None) -> html.Section:
    if configuration is None:
        rows = (("Implementation", "No exact saved configuration is linked", "None", "Blocked"),)
    else:
        market = configuration.market_data
        execution = configuration.execution
        parameter_count = len(configuration.parameters)
        start, end = _period(configuration)
        rows = (
            ("Market data", " · ".join(_saved_text(value) for value in (market.get("symbol"), market.get("provider"), market.get("interval") or market.get("timeframe")) if value is not None) or "Not recorded", "1 saved dataset", "Available" if readiness and readiness.ready else "Blocked"),
            ("Requested period", f"{start} → {end}", "1 saved window", "Available" if readiness and readiness.ready else "Blocked"),
            ("Signal rule", configuration.strategy_name, f"{parameter_count} saved parameter set{'s' if parameter_count != 1 else ''}", "Immutable"),
            ("Execution", " · ".join(_execution_label(value) for value in (execution.get("direction"), execution.get("mode") or execution.get("execution_mode"), execution.get("order_size")) if value is not None) or "Not recorded", "1 saved model", "Immutable"),
            ("Trading costs", _costs(execution) + ("; " + _stress_costs(configuration) if _stress_costs(configuration) else ""), "Saved assumptions", "Explicit"),
            ("Evidence role", "Exact selected Candidate; no fixture substitution", "No promotion", "Explicit"),
        )
    return html.Section(
        [html.Div([html.Div([html.H3("Bounded experiment matrix"), html.P("Values are read from the selected saved configuration.")]), html.Strong("One selected Candidate × one linked configuration")], className="setup-ref-matrix-head"),
         html.Table([html.Thead(html.Tr([html.Th("Dimension"), html.Th("Included"), html.Th("Search space"), html.Th("Status")])), html.Tbody([html.Tr([html.Td(name), html.Td(included), html.Td(space), html.Td(status, className="setup-ref-status-blocked" if status in {"Check required", "Blocked"} else "")]) for name, included, space, status in rows])], className="setup-ref-table")],
        className="setup-ref-matrix",
    )


def _other_candidate_contract(identity, configuration: SavedConfigurationView | None, saved: bool, ready: bool, message: str, readiness: ConfigurationReadinessView | None, implementation_ready: bool) -> html.Section:
    start, end = _period(configuration) if configuration else ("Unavailable", "Unavailable")
    facts = (
        ("Candidate", identity.title if identity else "None selected"),
        ("Version", identity.short_version if identity else "Unavailable"),
        ("Saved setup", configuration.experiment_id if saved and configuration else "Not saved"),
        ("Strategy", configuration.strategy_name if configuration else "Implementation required"),
        ("Data & period", f"{_saved_text(configuration.market_data.get('symbol'))} · {_saved_text(configuration.market_data.get('interval') or configuration.market_data.get('timeframe'))} · {start} → {end}" if configuration else "Unavailable"),
        ("Execution", _execution_label(configuration.execution.get("mode") or configuration.execution.get("execution_mode")) if configuration else "Unavailable"),
        ("Costs", _costs(configuration.execution) if configuration else "Unavailable"),
        ("Run eligibility", "Separate Run test review" if ready else "Blocked until exact setup is ready"),
    )
    reasons = [blocker.reason for blocker in getattr(readiness, "blockers", ()) if implementation_ready or blocker.code != "candidate_runtime_unavailable"]
    if saved and not implementation_ready:
        reasons.insert(0, "This saved Candidate has no matching strategy implementation. Implement the approved rule and bind local data before Run test.")
    next_message = " ".join(reasons) if reasons else message
    return html.Section(
        [html.Div([html.Div([html.H3("Immutable contract preview"), html.P("Facts from the selected Candidate and its saved setup.")]), html.Span("Saved" if saved else "Not saved", className="setup-ref-contract-state")], className="setup-ref-contract-head"),
         html.Div([html.Div([html.Span(label), html.Strong(value)]) for label, value in facts], className="setup-ref-contract-cells"),
         html.Div([html.Span(next_message), dcc.Link("Continue to Run test" if ready else "Save setup draft" if not saved and implementation_ready and readiness and readiness.ready else "Review accepted Candidate", id="review-test-action", href="/research/run-test" if ready else "#save-idea-configuration" if not saved and implementation_ready and readiness and readiness.ready else "/research/ideas", className="setup-ref-next-link")], className="setup-ref-contract-foot")],
        className="setup-ref-contract",
    )


def _other_candidate_controls(identity, configuration: SavedConfigurationView | None, readiness: ConfigurationReadinessView | None, *, saved: bool, ready: bool, implementation_ready: bool) -> html.Aside:
    if configuration is None:
        content = html.Section([html.H3("No setup controls available"), html.P("An exact implementation must be linked to this accepted Candidate before a test can be defined.")], className="setup-ref-rail-section")
    else:
        market = configuration.market_data
        execution = configuration.execution
        parameter_items = configuration.parameters if isinstance(configuration.parameters, dict) else ({} if all(not item for item in configuration.parameters) else {"parameter sets": configuration.parameters})
        start, end = _period(configuration)
        content = [
            html.Section([html.Div([html.H3("Data & scope"), html.Span("Saved" if saved else "Approved")], className="setup-ref-section-title"), _fixed_select("Provider", _saved_text(market.get("provider"))), html.Div([_fixed_select("Instrument", _saved_text(market.get("symbol"))), _fixed_select("Timeframe", _saved_text(market.get("interval") or market.get("timeframe")))], className="setup-ref-field-row"), html.Div([_fixed_input("Start date", start), _fixed_input("End date", end)], className="setup-ref-field-row"), html.P(f"Local data: {getattr(readiness, 'local_availability', 'Checked when saving')}", className="setup-ref-control-note")], className="setup-ref-rail-section"),
            html.Section([html.Div([html.H3("Signal parameters"), html.Span("Fixed contract")], className="setup-ref-section-title"), *([_fixed_select(str(key).replace("_", " ").title(), _saved_text(value)) for key, value in parameter_items.items() if value != {}] or [html.P("No adjustable parameters in this fixed rule.", className="setup-ref-control-note")])], className="setup-ref-rail-section"),
            html.Section([html.Div([html.H3("Execution assumptions"), html.Span("Saved" if saved else "Approved")], className="setup-ref-section-title"), html.Div([_fixed_select("Direction", _execution_label(execution.get("direction"))), _fixed_select("Entry", _execution_label(execution.get("mode") or execution.get("execution_mode")))], className="setup-ref-field-row"), html.Div([_fixed_select("Order size (units)", _saved_text(execution.get("order_size"))), _fixed_select("Initial cash model", _capital(execution.get("initial_cash")))], className="setup-ref-field-row"), html.Div([_fixed_select("Sizing", _execution_label(execution.get("position_sizing"))), _fixed_select("Accumulation", _saved_text(execution.get("accumulate")))], className="setup-ref-field-row") if "position_sizing" in execution and "accumulate" in execution else None, _fixed_select("Signal timing", _execution_label(execution.get("signal_timing"))) if "signal_timing" in execution else None, _fixed_select("Execution price", _execution_label(execution.get("execution_price_field"))) if "execution_price_field" in execution else None, html.Div([_fixed_select("Price multiplier", _saved_text(execution.get("price_multiplier"))), _fixed_select("Tick size", _saved_text(execution.get("tick_size")))], className="setup-ref-field-row") if "price_multiplier" in execution and "tick_size" in execution else None, html.Div([_fixed_select("Fee / contract / side", f"${execution['fixed_fee_per_contract_per_side']}"), _fixed_select("Slippage ticks / side", _saved_text(execution.get("slippage_ticks")))], className="setup-ref-field-row") if execution.get("fixed_fee_per_contract_per_side") is not None else html.Div([_fixed_select("Fee rate", _rate(execution.get("fees"))), _fixed_select("Slippage rate", _rate(execution.get("slippage")))], className="setup-ref-field-row"), *([html.P(_stress_costs(configuration), className="setup-ref-control-note")] if _stress_costs(configuration) else [])], className="setup-ref-rail-section"),
        ]
    return html.Aside(
        [html.Div([html.Div([html.H2("Bounded setup controls"), html.Span("Ready" if ready else "Save-ready" if configuration and not saved and implementation_ready and readiness and readiness.ready else "Blocked", className="setup-ref-ready")]), html.P("Values shown below come from this Candidate's exact contract.")], className="setup-ref-rail-head"),
         *(content if isinstance(content, list) else [content]),
         html.Section([html.Div([html.H3("Evidence boundary"), html.Span("Fixed")], className="setup-ref-section-title"), html.Div([html.Strong("Candidate evidence only"), html.P("This page does not run research or authorize promotion, paper, or live trading.")], className="setup-ref-boundary")], className="setup-ref-rail-section"),
         html.Div([html.Strong("Selected: " + (identity.title if identity else "None")), html.P("A different Candidate must be selected on Ideas; this contract cannot silently switch.")], className="setup-ref-rail-foot")],
        className="setup-ref-rail",
    )


def _rule_preview() -> html.Section:
    return html.Section(
        [
            html.Div([html.Strong("Illustrative session"), html.Span("Synthetic prices · US Eastern time · not market data")], className="setup-rule-toolbar"),
            dcc.Graph(figure=_illustrative_rule_figure(), config={"displayModeBar": False, "staticPlot": True}, className="setup-rule-chart"),
            html.Div(
                [
                    html.Span("09:30–09:45 · first three 5-minute bars fix the range"),
                    html.Span("Breakout · 4 ticks + VWAP + body ≥ 55%"),
                    html.Span("Next-bar entry · opposite-range stop · 1.5R target · flat by 15:55"),
                ],
                className="setup-rule-chart-key",
            ),
            html.P("Illustrative rule geometry—not a simulated trade or performance evidence. Stop counts first if stop and target touch together. The saved contract below is authoritative.", className="setup-rule-note"),
        ],
        className="setup-rule-preview",
    )


def _illustrative_rule_figure() -> go.Figure:
    """Show the fixed rule in the approved chart-first preview, without market data."""
    closes = [100.15, 99.85, 100.25, 100.05, 99.90, 100.20, 100.35, 101.65, 101.75, 101.95, 102.15, 102.00, 102.25, 102.10, 102.35, 102.30]
    opens = [100.35, 100.15, 99.85, 100.25, 100.05, 99.90, 100.20, 100.35, 101.65, 101.75, 101.95, 102.15, 102.00, 102.25, 102.10, 102.35]
    highs = [100.55, 100.30, 100.40, 100.35, 100.20, 100.35, 100.50, 101.80, 101.90, 102.10, 102.30, 102.30, 102.40, 102.35, 102.50, 102.45]
    lows = [100.05, 99.70, 99.75, 99.90, 99.75, 99.80, 100.05, 100.25, 101.50, 101.60, 101.80, 101.85, 101.90, 101.95, 102.00, 102.10]
    figure = go.Figure(
        data=[
            go.Candlestick(x=list(range(len(closes))), open=opens, high=highs, low=lows, close=closes, increasing_line_color="#0b9f76", decreasing_line_color="#dc5c62", showlegend=False, hoverinfo="skip"),
            go.Scatter(x=list(range(len(closes))), y=[100.00, 99.98, 100.00, 100.02, 100.04, 100.06, 100.08, 100.12, 100.17, 100.24, 100.30, 100.36, 100.42, 100.47, 100.53, 100.58], mode="lines", line={"color": "#b66b00", "width": 1.5, "dash": "dot"}, name="VWAP illustration", hoverinfo="skip"),
        ]
    )
    figure.add_hline(y=100.55, line_color="#7d9ec7", line_dash="dash", line_width=1, annotation_text="Opening-range high", annotation_position="top left")
    figure.add_hline(y=99.70, line_color="#7d9ec7", line_dash="dash", line_width=1, annotation_text="Opening-range low / stop", annotation_position="bottom left")
    for x, color in ((2.5, "#b66b00"), (7, "#b66b00"), (8, "#316ff4"), (15, "#dc5c62")):
        figure.add_vline(x=x, line_color=color, line_dash="dot", line_width=1)
    figure.add_annotation(x=6.8, y=102.55, text="Qualified breakout", showarrow=False, font={"size": 10, "color": "#9b5c00"})
    figure.add_annotation(x=9.2, y=102.55, text="Next-bar entry", showarrow=False, font={"size": 10, "color": "#316ff4"})
    figure.add_annotation(x=14, y=102.65, text="Flat by 15:55", showarrow=False, font={"size": 10, "color": "#c94d55"})
    figure.update_layout(
        height=330, margin={"l": 46, "r": 18, "t": 20, "b": 35}, paper_bgcolor="#f8fafd", plot_bgcolor="#f8fafd", showlegend=False,
        xaxis={"range": [-0.7, 15.7], "tickmode": "array", "tickvals": [0, 3, 7, 8, 15], "ticktext": ["09:30", "09:45", "10:05", "10:10", "15:55"], "showgrid": True, "gridcolor": "#e0e8f1", "rangeslider": {"visible": False}, "zeroline": False, "fixedrange": True},
        yaxis={"range": [99.4, 102.8], "showgrid": True, "gridcolor": "#e0e8f1", "tickfont": {"size": 10, "color": "#66758c"}, "zeroline": False, "fixedrange": True},
        font={"family": "Arial, sans-serif", "size": 10, "color": "#66758c"},
    )
    return figure


def _fixed_select(label: str, value: str) -> html.Label:
    return html.Label(
        [html.Span([label, html.Small("Fixed")], className="setup-ref-field-label"), html.Select([html.Option(value, value=value)], disabled=True, className="setup-ref-select")],
        className="setup-ref-field",
    )


def _fixed_input(label: str, value: str) -> html.Label:
    return html.Label(
        [html.Span([label, html.Small("Fixed")], className="setup-ref-field-label"), dcc.Input(type="text", value=value, disabled=True, className="setup-ref-input")],
        className="setup-ref-field",
    )
