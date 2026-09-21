"""Deterministic tests for the minimal visual decision dashboard."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading

import pandas as pd
import pytest
from dash import html, no_update
from dash.exceptions import PreventUpdate

import backtesting.run_rsi_demo as demo
from dashboard.adapter import reconstruct_selected_portfolio
from dashboard.app import (
    DashboardContext,
    NAVIGATION_LINKS,
    ROUTE_CONTAINER_IDS,
    ROUTE_REGISTRY,
    _backtest_selector_label,
    _details,
    _detail_fields,
    _curve_graph,
    _detail_subsection,
    _navigation,
    _ranked_column_definitions,
    _recent_events_panel,
    _recent_runs_panel,
    _run_action_controls,
    _run_detail_analysis_tabs,
    _run_detail_panel,
    _trade_pnl_chart,
    _select_initial_backtest,
    _runs_page,
    create_app,
    create_layout,
    page_for_path,
    parameters_from_row,
    route_content_for_path,
    route_container_styles_for_path,
)
from dashboard.formatting import format_assumption, format_metric
from dashboard.project_status import PROJECT_STATUS
from dashboard.routing import NAVIGATION_ITEMS, navigation_item_id
from dashboard.state_ownership import STATE_OWNERS
from dashboard.run_adapter import SavedConfigurationView
from dashboard.run_detail_adapter import (
    ArtifactInventoryView,
    DetailField,
    ResultSummaryView,
    RunEvidenceView,
    RunDetailDashboardAdapter,
    SelectedRunDetailView,
)
from orchestration import (
    DurableResearchLaunchService,
    FixtureRunService,
    ResearchLaunchConflictError,
    ResearchLaunchContentionError,
    ResearchLaunchRequest,
    RunEvent,
    RunLaunchResult,
    RunServiceError,
    RunSummary,
    new_dispatcher_instance_id,
)
from market_data import DataAudit
from persistence import (
    ArtifactAvailability,
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    ReviewState,
    ResearchLaunchOperation,
    ResearchRunSubmissionRecord,
    ResearchSubmissionState,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.models import normalized_configuration_document
from prefect_spike.fixture_flow import deterministic_fixture_body
from prefect_spike.spym_vectorbt_fixture import ensure_spym_21c_saved_configuration
from tests.test_review_context_artifacts import (
    REVIEW_PARAMETERS,
    _persist_review_prerequisites,
    _review_service,
    _source_lock_artifact,
)



@pytest.fixture(autouse=True)
def isolated_health_catalog(monkeypatch):
    # Unit layout/callback tests should not hash the operator's real data on
    # every app construction. Filesystem verification has dedicated tests;
    # the real-browser suite exercises the configured catalog end to end.
    monkeypatch.setattr("dashboard.application.inspect_catalog", lambda: (None, (), "Unit test catalog"))


def _walk_components(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk_components(child)
    elif children is not None:
        yield from _walk_components(children)


def _component_text(component) -> str:
    return " ".join(
        str(item)
        for item in _walk_components(component)
        if isinstance(item, (str, int, float))
    )


def _json_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_json_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_json_text(item) for item in value)
    return ""


def _json_components_with_href(value: object) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    if isinstance(value, dict):
        props = value.get("props")
        if isinstance(props, dict) and "href" in props:
            matches.append(props)
        for item in value.values():
            matches.extend(_json_components_with_href(item))
    elif isinstance(value, list):
        for item in value:
            matches.extend(_json_components_with_href(item))
    return matches


def _component_ids(component) -> list[str]:
    return [
        str(component_id)
        for item in _walk_components(component)
        if (component_id := getattr(item, "id", None)) is not None
    ]


def _callback_ref_ids(app) -> set[str]:
    refs: set[str] = set()
    for metadata in app.callback_map.values():
        for group_name in ("inputs", "state"):
            for item in metadata.get(group_name, ()):
                refs.add(str(item["id"]))
        output = metadata.get("output")
        outputs = output if isinstance(output, (list, tuple)) else [output]
        for item in outputs:
            component_id = getattr(item, "component_id", None)
            if component_id is not None:
                refs.add(str(component_id))
    return refs


def _resolved_layout(app):
    layout = app.layout
    return layout() if callable(layout) else layout


def _visible_route_container_ids(layout) -> list[str]:
    return [
        component.id
        for component in _walk_components(layout)
        if getattr(component, "id", None) in ROUTE_CONTAINER_IDS
        and getattr(component, "style", None) == {"display": "block"}
    ]


def _active_navigation_hrefs(layout) -> list[str]:
    return [
        component.href
        for component in _walk_components(layout)
        if getattr(component, "className", None)
        and "navigation-link-active" in component.className
    ]


def _data() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=80, freq="D")
    return pd.DataFrame(
        {
            "Open": [99 + ((i % 12) - 6) * 2 for i in range(len(index))],
            "Close": [100 + ((i % 12) - 6) * 2 for i in range(len(index))],
        },
        index=index,
        dtype=float,
    )


def _audit(data: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="vectorbtpro.YFData.pull",
        interval="1 day",
        requested_start="2016-01-01",
        requested_dynamic_end_policy="test",
        latest_completed_exchange_session="2024-03-20",
        prices_adjusted=True,
        adjustment_verification="test",
        download_time="2024-03-20T17:00:00-04:00",
        download_timezone="America/New_York",
        actual_first_row_date="2024-01-01",
        actual_last_row_date="2024-03-20",
        row_count=len(data),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
    )


def _ranked_row() -> dict[str, object]:
    return {
        "rsi_window": 7,
        "entry_threshold": 25,
        "exit_threshold": 60,
        "total_return": 0.5,
        "annualized_return": 0.1,
        "sharpe_ratio": 0.7,
        "max_drawdown": -0.3,
        "number_of_trades": 35,
        "win_rate": 0.9,
        "data_source": "Yahoo Finance",
        "prices_adjusted": True,
        "data_start_date": "2024-01-01",
        "data_end_date": "2024-03-20",
        "row_count": 80,
    }


def test_selected_parameter_reconstruction_outputs_series_and_metadata() -> None:
    data = _data()
    selected = reconstruct_selected_portfolio(
        demo.EXPERIMENT_CONFIG,
        data,
        _audit(data),
        {"window": 7, "entry_threshold": 25, "exit_threshold": 60},
    )
    assert selected.equity.index.equals(data.index)
    assert selected.drawdown.index.equals(data.index)
    assert selected.equity.name == "Equity"
    assert selected.drawdown.name == "Drawdown"
    assert (selected.drawdown <= 0).all()
    assert selected.strategy_identity == {
        "strategy_id": "rsi_mean_reversion",
        "name": "RSI Mean Reversion",
        "version": "1.0.0",
        "family": "mean_reversion",
    }
    assert selected.provenance["provider"] == "Yahoo Finance"
    assert selected.execution_assumptions["fees"] == 0.0005
    assert selected.execution_assumptions["signal_timing_label"] == (
        "Signal calculated after market close"
    )
    assert selected.execution_assumptions["execution_timing_label"] == (
        "Order filled at next session open"
    )
    assert selected.execution_assumptions["execution_price"] == "Open"
    assert selected.execution_assumptions["strategy"]["same_bar_limitation"]
    _, execution_details = _details(selected)
    rendered = " ".join(str(component.children) for component in execution_details)
    assert "Signal calculated after market close" in rendered
    assert "Order filled at next session open" in rendered
    assert "Execution price: Open" in rendered


def test_dashboard_review_without_authoritative_context_fails_closed(
    tmp_path: Path,
) -> None:
    database, _, service, adapter = _review_decision_stack(tmp_path)
    json_path = tmp_path / "reviews.json"
    context = DashboardContext(pd.DataFrame([_ranked_row()]), _data(), _audit(_data()))
    app = create_app(
        context,
        database,
        run_service=service,
        run_detail_adapter=adapter,
    )
    load_review = _callback_function(app, "review-status")
    save_review = _callback_function(app, "review-message")

    target_id = "decision_review_run"
    status, note, history = load_review(target_id)
    assert status == ReviewState.UNREVIEWED.value
    assert note == ""
    assert "No durable decision" in str(history)

    message = save_review(
        1,
        target_id,
        ReviewState.WATCHLIST.value,
        "  Promising, inspect execution timing.  ",
    )

    assert "Durable decision unavailable" in str(message)
    assert not json_path.exists()
    persistence = PersistenceService(database)
    try:
        assert persistence.reviews.get_current("run", target_id) is None
        assert persistence.reviews.history("run", target_id) == ()
        assert not any(
            artifact.logical_name == "evidence_decision_record"
            for artifact in persistence.list_run_artifacts(target_id)
        )
    finally:
        persistence.close()


def test_dashboard_review_does_not_mutate_audit_history_without_context(
    tmp_path: Path,
) -> None:
    database, _, service, adapter = _review_decision_stack(tmp_path)
    context = DashboardContext(pd.DataFrame([_ranked_row()]), _data(), _audit(_data()))
    app = create_app(
        context,
        database,
        run_service=service,
        run_detail_adapter=adapter,
    )
    save_review = _callback_function(app, "review-message")
    target_id = "decision_review_run"

    save_review(1, target_id, ReviewState.REVISE.value, "Needs work")
    save_review(2, target_id, ReviewState.REJECT.value, "Rejected")

    service = PersistenceService(database)
    try:
        assert service.reviews.history("run", target_id) == ()
        assert service.reviews.get_current("run", target_id) is None
    finally:
        service.close()


def test_dashboard_review_invalid_state_fails_closed(tmp_path: Path) -> None:
    database, _, service, adapter = _review_decision_stack(tmp_path)
    context = DashboardContext(pd.DataFrame([_ranked_row()]), _data(), _audit(_data()))
    app = create_app(
        context,
        database,
        run_service=service,
        run_detail_adapter=adapter,
    )
    save_review = _callback_function(app, "review-message")
    target_id = "decision_review_run"

    with pytest.raises(ValueError, match="Unsupported review status"):
        save_review(1, target_id, "Watchlist", "legacy label")

    service = PersistenceService(database)
    try:
        assert service.reviews.get_current("run", target_id) is None
        assert service.reviews.history("run", target_id) == ()
    finally:
        service.close()


def test_dashboard_review_with_valid_context_enables_and_persists_decision(
    tmp_path: Path,
) -> None:
    database, _, service, adapter = _review_context_stack(tmp_path)
    context = DashboardContext(pd.DataFrame([_ranked_row()]), _data(), _audit(_data()))
    app = create_app(
        context,
        database,
        run_service=service,
        run_detail_adapter=adapter,
    )
    availability = _callback_function(app, "save-review.disabled")
    save_review = _callback_function(app, "review-message")

    target_id = "review_context_target"
    disabled, title, message = availability(target_id)
    assert disabled is False
    assert "Persist a durable evidence decision" in title
    assert message == ""

    result = save_review(
        1,
        target_id,
        ReviewState.WATCHLIST.value,
        "Approved with explicit persisted context.",
    )

    assert "Evidence decision artifact validated" in str(result)
    status, note, history = _callback_function(app, "review-status")(target_id)
    assert status == ReviewState.WATCHLIST.value
    assert note == "Approved with explicit persisted context."
    assert "Unreviewed → Watchlist" in str(history)
    context_children, context_class = _callback_function(
        app,
        "results-operator-context",
    )(target_id, 0, result)
    assert context_class == "operator-context"
    assert "Watchlist" in _component_text(html.Div(context_children))
    persistence = PersistenceService(database)
    try:
        current = persistence.reviews.get_current("run", target_id)
        assert current is not None
        assert current.state == ReviewState.WATCHLIST
        assert current.note == "Approved with explicit persisted context."
        assert any(
            artifact.logical_name == "evidence_decision_record"
            for artifact in persistence.list_run_artifacts(target_id)
        )
    finally:
        persistence.close()


def test_results_review_conflict_preserves_form_and_existing_decision(
    tmp_path: Path,
) -> None:
    database, _, service, adapter = _review_context_stack(tmp_path)
    app = create_app(
        DashboardContext(pd.DataFrame([_ranked_row()]), _data(), _audit(_data())),
        database,
        run_service=service,
        run_detail_adapter=adapter,
    )
    save_review = _callback_function(app, "review-message")
    first_message, first_history = save_review(
        1,
        "review_context_target",
        ReviewState.WATCHLIST.value,
        "First durable decision.",
    )
    conflict_message, conflict_history = save_review(
        2,
        "review_context_target",
        ReviewState.REJECT.value,
        "Unsaved conflicting decision remains in the form.",
    )

    assert "Evidence decision artifact validated" in str(first_message)
    assert "First durable decision" in str(first_history)
    assert "conflicting evidence decision artifact" in str(conflict_message)
    assert "No review change was saved" in str(conflict_message)
    assert conflict_history is no_update
    save_entry = next(
        entry
        for entry in app.callback_map.values()
        if any(item["id"] == "save-review" for item in entry.get("inputs", ()))
    )
    assert {output.component_id for output in save_entry["output"]} == {
        "review-message",
        "review-history",
    }

    persistence = PersistenceService(database)
    try:
        current = persistence.reviews.get_current("run", "review_context_target")
        assert current is not None
        assert current.state == ReviewState.WATCHLIST
        assert current.note == "First durable decision."
        assert len(persistence.reviews.history("run", "review_context_target")) == 1
    finally:
        persistence.close()


def test_results_review_and_quartet_fail_closed_for_corrupt_decision(
    tmp_path: Path,
) -> None:
    database, artifact_root, service, adapter = _review_context_stack(tmp_path)
    app = create_app(
        DashboardContext(pd.DataFrame([_ranked_row()]), _data(), _audit(_data())),
        database,
        run_service=service,
        run_detail_adapter=adapter,
    )
    saved = _callback_function(app, "review-message")(
        1,
        "review_context_target",
        ReviewState.WATCHLIST.value,
        "Validated before deliberate corruption.",
    )
    persistence = PersistenceService(database)
    try:
        decision_artifact = next(
            artifact
            for artifact in persistence.list_run_artifacts("review_context_target")
            if artifact.logical_name == "evidence_decision_record"
        )
    finally:
        persistence.close()
    (artifact_root / decision_artifact.location).write_text(
        '{"corrupt": true}',
        encoding="utf-8",
    )

    status, note, history = _callback_function(app, "review-status")(
        "review_context_target"
    )
    context_children, context_class = _callback_function(
        app,
        "results-operator-context",
    )("review_context_target", 0, saved)
    context_text = _component_text(html.Div(context_children))

    assert status == ReviewState.UNREVIEWED.value
    assert note == ""
    assert "unavailable" in str(history).lower()
    assert context_class == "operator-context"
    assert "Unavailable" in context_text
    assert "Watchlist" not in context_text


def test_compare_renders_independent_persisted_context_for_each_selected_run(
    tmp_path: Path,
) -> None:
    database, artifact_root, service, adapter = _review_context_stack(tmp_path)
    persistence = PersistenceService(database)
    try:
        unreviewed = persistence.runs.get("wf-run")
        assert unreviewed is not None
        unreviewed_configuration = unreviewed.configuration_id
    finally:
        persistence.close()
    service._runs.append(
        service._summary("wf-run", unreviewed_configuration, "succeeded")
    )
    app = create_app(
        DashboardContext(pd.DataFrame([_ranked_row()]), _data(), _audit(_data())),
        database,
        run_service=service,
        run_detail_adapter=adapter,
    )
    saved = _callback_function(app, "review-message")(
        1,
        "review_context_target",
        ReviewState.WATCHLIST.value,
        "Keep this fixture under observation.",
    )

    comparison, comparison_class = _callback_function(
        app,
        "run-comparison-output",
    )(
        0,
        "/research/compare-backtests",
        "?run_id=review_context_target&run_id=wf-run",
    )
    contexts = [
        component
        for component in _walk_components(comparison)
        if "compare-run-card" in str(getattr(component, "className", ""))
    ]

    assert comparison_class == "run-comparison-output"
    assert len(contexts) == 2
    assert contexts[0].to_plotly_json()["props"]["data-run-id"] == (
        "review_context_target"
    )
    assert contexts[1].to_plotly_json()["props"]["data-run-id"] == "wf-run"
    first_text = _component_text(contexts[0])
    second_text = _component_text(contexts[1])
    assert "Watchlist" in first_text
    assert "Unreviewed" not in first_text
    assert "Unreviewed" in second_text
    assert "Watchlist" not in second_text
    context_ids = [
        getattr(component, "id", None)
        for article in contexts
        for component in _walk_components(article)
        if str(getattr(component, "id", "")).startswith(
            "compare-operator-context-"
        )
    ]
    assert context_ids == [
        "compare-operator-context-1",
        "compare-operator-context-2",
    ]


def test_metric_and_assumption_formatting() -> None:
    assert format_metric("total_return", 0.994541) == "99.45%"
    assert format_metric("sharpe_ratio", 0.70137) == "0.70"
    assert format_metric("number_of_trades", 35) == "35"
    assert format_assumption("initial_cash", 10_000) == "$10,000"
    assert format_assumption("fees", 0.0005) == "0.050%"
    assert format_assumption("leverage", 1.0) == "1×"


def test_layout_and_app_creation_without_server(tmp_path: Path) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    layout = create_layout(context)
    assert layout is not None

    app = create_app(context, tmp_path / "reviews.json")
    assert _resolved_layout(app) is not None
    assert app.title == "Quant Factory"
    assert len(app.callback_map) == 34
    assert app.config.meta_tags == [
        {
            "name": "viewport",
            "content": (
                "width=device-width, initial-scale=1, "
                "maximum-scale=5, user-scalable=yes"
            ),
        }
    ]


def test_dashboard_callback_outputs_are_singly_owned(tmp_path: Path) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")

    output_keys = "\n".join(app.callback_map)

    assert output_keys.count("selected-run-selector.value") == 1
    assert output_keys.count("selected-run-selector.options") == 1
    assert output_keys.count("find-compare-grid.rowData") == 1
    assert output_keys.count("find-compare-grid.selectedRows") == 1
    assert output_keys.count("run-comparison-output.children") == 1
    assert output_keys.count("reproduction-message.children") == 1
    assert output_keys.count("selected-run-detail.children") == 1
    assert output_keys.count("historical-launch-message.children") == 1
    assert "page-content.children" not in output_keys
    assert "navigation-container.children" not in output_keys
    assert "url.pathname" not in output_keys
    assert ".hidden" not in output_keys
    route_visibility_output = next(
        key for key in app.callback_map if key.startswith("..route-home.style")
    )
    route_inputs = {
        (item["id"], item["property"])
        for item in app.callback_map[route_visibility_output]["inputs"]
    }
    assert route_inputs == {("url", "pathname")}
    for container_id in ROUTE_CONTAINER_IDS:
        assert output_keys.count(f"{container_id}.style") == 1
    for path, _ in NAVIGATION_LINKS:
        link_output = f"navigation-link-{path.strip('/').replace('/', '-')}.className"
        assert output_keys.count(link_output) == 1
    for path, _ in NAVIGATION_ITEMS:
        assert output_keys.count(f"{navigation_item_id(path)}.aria-current") == 1


def test_all_callback_components_exist_in_full_mounted_layout(tmp_path: Path) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")
    mounted_ids = set(_component_ids(_resolved_layout(app)))

    missing = sorted(_callback_ref_ids(app) - mounted_ids)

    assert "refresh-comparisons" in mounted_ids
    assert missing == []


def test_full_mounted_layout_has_globally_unique_component_ids(tmp_path: Path) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")
    component_ids = [
        component_id
        for component in _walk_components(_resolved_layout(app))
        if (component_id := getattr(component, "id", None)) is not None
    ]

    duplicates = sorted(
        component_id
        for component_id in set(component_ids)
        if component_ids.count(component_id) > 1
    )

    assert duplicates == []


def test_page_specific_callbacks_do_not_control_routes_or_navigation(
    tmp_path: Path,
) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")

    route_callback_keys = {
        next(key for key in app.callback_map if key.startswith("..route-home.style")),
        next(
            key
            for key in app.callback_map
            if key.startswith("..navigation-link-research-ideas.className")
        ),
        next(
            key
            for key in app.callback_map
            if key.startswith("..responsive-active-page.children")
        ),
    }
    # ADR 0008 permits passive page-owned refresh when entering a mounted page.
    # Trade evidence must populate on Home -> Backtest Results navigation while
    # retaining the URL/navigation output restrictions below.
    passive_route_refresh_keys = {
        "..selected-trade-grid.rowData...trade-explorer-summary.children..."
        "selected-trade-grid.selectedRows..",
        "find-compare-grid.rowData",
        "find-compare-grid.selectedRows",
        "..find-compare-selection-message.children..."
        "find-compare-selection-message.className...find-compare-results-link.href..."
        "find-compare-results-link.style...find-compare-exact-link.href..."
        "find-compare-exact-link.style..",
        "..run-comparison-output.children...run-comparison-output.className..",
    }

    for output_key, metadata in app.callback_map.items():
        output_text = str(output_key)
        input_refs = {
            (item["id"], item["property"])
            for item in metadata["inputs"]
        }
        if ("url", "pathname") in input_refs:
            assert output_key in route_callback_keys | passive_route_refresh_keys
        if output_key not in route_callback_keys:
            assert "page-content" not in output_text
            assert "navigation-container" not in output_text
            assert "navigation-link" not in output_text
            assert "url.pathname" not in output_text


def test_dash_route_callback_endpoint_keeps_workflow_pages_separate(
    tmp_path: Path,
) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")
    client = app.server.test_client()
    route_output = next(
        key for key in app.callback_map if key.startswith("..route-home.style")
    )
    route_outputs = [
        {"id": container_id, "property": "style"}
        for container_id in ROUTE_CONTAINER_IDS
    ]
    navigation_output = next(
        key
        for key in app.callback_map
        if key.startswith("..navigation-link-research-ideas.className")
    )
    navigation_outputs = [
        {"id": f"navigation-link-{path.strip('/').replace('/', '-')}", "property": "className"}
        for path, _ in NAVIGATION_LINKS
    ] + [
        {"id": navigation_item_id(path), "property": "aria-current"}
        for path, _ in NAVIGATION_ITEMS
    ]

    def invoke_route(pathname: str) -> dict[str, object]:
        response = client.post(
            "/_dash-update-component",
            json={
                "output": route_output,
                "outputs": route_outputs,
                "inputs": [
                    {
                        "id": "url",
                        "property": "pathname",
                        "value": pathname,
                    }
                ],
                "state": [],
                "changedPropIds": ["url.pathname"],
            },
        )
        assert response.status_code == 200
        return response.get_json()

    def invoke_navigation(pathname: str) -> dict[str, object]:
        response = client.post(
            "/_dash-update-component",
            json={
                "output": navigation_output,
                "outputs": navigation_outputs,
                "inputs": [
                    {
                        "id": "url",
                        "property": "pathname",
                        "value": pathname,
                    }
                ],
                "state": [],
                "changedPropIds": ["url.pathname"],
            },
        )
        assert response.status_code == 200
        return response.get_json()

    mounted_pages = {
        path: _component_text(
            next(
                component
                for component in _walk_components(_resolved_layout(app))
                if getattr(component, "id", None) == container_id
            )
        )
        for path, container_id in ROUTE_REGISTRY
    }
    mounted_pages["__not_found__"] = _component_text(
        next(
            component
            for component in _walk_components(_resolved_layout(app))
            if getattr(component, "id", None) == "route-not-found"
        )
    )

    def visible_routes(payload: dict[str, object]) -> list[str]:
        response = payload["response"]
        assert isinstance(response, dict)
        visible: list[str] = []
        for path, container_id in ROUTE_REGISTRY:
            if response[container_id]["style"] == {"display": "block"}:
                visible.append(path)
        if response["route-not-found"]["style"] == {"display": "block"}:
            visible.append("__not_found__")
        return visible

    def active_hrefs(payload: dict[str, object]) -> list[str]:
        response = payload["response"]
        assert isinstance(response, dict)
        active: list[str] = []
        for path, _ in NAVIGATION_LINKS:
            link_id = f"navigation-link-{path.strip('/').replace('/', '-')}"
            link_response = response[link_id]
            if "navigation-link-active" in link_response["className"]:
                active.append(path)
        return active

    def current_hrefs(payload: dict[str, object]) -> list[str]:
        response = payload["response"]
        assert isinstance(response, dict)
        return [
            path
            for path, _ in NAVIGATION_ITEMS
            if response[navigation_item_id(path)]["aria-current"] == "page"
        ]

    backtest_visible = visible_routes(invoke_route("/research/backtest-results"))
    backtest_text = mounted_pages["/research/backtest-results"]
    backtest_active = active_hrefs(invoke_navigation("/research/backtest-results"))
    assert "Results" in backtest_text
    assert "Understand what happened, whether the evidence is usable, and what decision is required." in backtest_text
    assert "Review decision" in backtest_text
    assert "review-status" in str(
        page_for_path("/research/backtest-results", context)
    )
    assert backtest_visible == ["/research/backtest-results"]
    assert backtest_active == ["/research/backtest-results"]
    assert current_hrefs(invoke_navigation("/research/backtest-results")) == [
        "/research/backtest-results"
    ]

    home_visible = visible_routes(invoke_route("/"))
    home_text = mounted_pages["/"]
    assert "Research readiness" in home_text
    assert "Not checked" in home_text
    assert (
        "complete passive browser workflow are complete through Step 14"
        in home_text
    )
    assert home_visible == ["/"]

    retired_review_visible = visible_routes(
        invoke_route("/research/strategy-review")
    )
    retired_review_active = active_hrefs(
        invoke_navigation("/research/strategy-review")
    )
    assert retired_review_visible == ["__not_found__"]
    assert retired_review_active == []
    assert current_hrefs(invoke_navigation("/research/strategy-review")) == []

    missing_visible = visible_routes(invoke_route("/not-a-route"))
    missing_text = mounted_pages["__not_found__"]
    missing_active = active_hrefs(invoke_navigation("/not-a-route"))
    assert "Page not found" in missing_text
    assert missing_visible == ["__not_found__"]
    assert missing_active == []
    assert current_hrefs(invoke_navigation("/not-a-route")) == []

    expected_titles = {
        "/": "Home",
        "/research/ideas": "Ideas",
        "/research/setup": "Set up a test",
        "/research/run-test": "Run test",
        "/research/market-data": "Market Data",
        "/research/backtest-results": "Results",
        "/research/compare-backtests": "Find & Compare",
        "/paper/fleet": "Paper Trading Overview",
        "/paper/strategy": "Strategy Monitor",
        "/system": "System Status",
        "/system/providers": "Data Sources",
        "/settings": "Settings",
    }
    for pathname, title in expected_titles.items():
        assert visible_routes(invoke_route(pathname)) == [pathname]
        assert title in mounted_pages[pathname]
        expected_active = [] if pathname == "/" else [pathname]
        assert active_hrefs(invoke_navigation(pathname)) == expected_active
        assert current_hrefs(invoke_navigation(pathname)) == [pathname]


def test_route_visibility_callback_is_not_initial_call_suppressed(
    tmp_path: Path,
) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")
    route_output = next(
        key for key in app.callback_map if key.startswith("..route-home.style")
    )
    route_callback = next(
        item for item in app._callback_list if item["output"] == route_output
    )

    assert route_callback["prevent_initial_call"] is False
    assert route_callback["inputs"] == [{"id": "url", "property": "pathname"}]


def test_serialized_location_uses_server_selected_pathname(
    tmp_path: Path,
) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")
    client = app.server.test_client()

    response = client.get("/_dash-layout")
    assert response.status_code == 200
    layout_payload = response.get_json()

    def find_url_props(value: object) -> dict[str, object]:
        if isinstance(value, dict):
            props = value.get("props")
            if isinstance(props, dict) and props.get("id") == "url":
                return props
            for item in value.values():
                found = find_url_props(item)
                if found:
                    return found
        if isinstance(value, list):
            for item in value:
                found = find_url_props(item)
                if found:
                    return found
        return {}

    url_props = find_url_props(layout_payload)

    assert url_props["refresh"] == "callback-nav"
    assert url_props["pathname"] == "/"
    assert "href" not in url_props
    assert "search" not in url_props
    assert "hash" not in url_props


def test_location_uses_standard_link_navigation_for_route_visibility_callback() -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))

    layout = create_layout(context)
    url = next(
        component
        for component in _walk_components(layout)
        if getattr(component, "id", None) == "url"
    )

    assert url.refresh == "callback-nav"
    assert url.pathname == "/"
    assert not hasattr(url, "href")


def test_deep_link_layout_initializes_visible_route_from_request_cookie(
    tmp_path: Path,
) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")
    client = app.server.test_client()

    page_response = client.get("/research/backtest-results")
    assert page_response.status_code == 200

    layout_response = client.get("/_dash-layout")
    assert layout_response.status_code == 200
    layout_payload = layout_response.get_json()

    route_styles: dict[str, object] = {}
    navigation_classes: dict[str, str] = {}

    def collect(value: object) -> None:
        if isinstance(value, dict):
            props = value.get("props")
            if isinstance(props, dict):
                component_id = props.get("id")
                if component_id in ROUTE_CONTAINER_IDS:
                    route_styles[str(component_id)] = props.get("style")
                if component_id == "navigation-link-research-backtest-results":
                    navigation_classes[str(component_id)] = str(
                        props.get("className")
                    )
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(layout_payload)
    visible = [
        container_id
        for container_id in ROUTE_CONTAINER_IDS
        if route_styles[container_id] == {"display": "block"}
    ]

    assert visible == ["route-research-backtest-results"]
    assert route_styles["route-home"] == {"display": "none"}
    assert (
        navigation_classes["navigation-link-research-backtest-results"]
        == "navigation-link navigation-link-active"
    )
    url_props: dict[str, object] = {}

    def find_url(value: object) -> None:
        if isinstance(value, dict):
            props = value.get("props")
            if isinstance(props, dict) and props.get("id") == "url":
                url_props.update(props)
            for item in value.values():
                find_url(item)
        elif isinstance(value, list):
            for item in value:
                find_url(item)

    find_url(layout_payload)
    assert url_props["pathname"] == "/research/backtest-results"


def test_route_callbacks_ignore_unhydrated_location_none(
    tmp_path: Path,
) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")

    route_callback = _callback_function(app, "route-home.style")
    navigation_callback = _callback_function(
        app,
        "navigation-link-research-backtest-results.className",
    )

    with pytest.raises(PreventUpdate):
        route_callback(None)
    with pytest.raises(PreventUpdate):
        navigation_callback(None)


def test_deep_link_refresh_uses_browser_path_without_home_overwrite(
    tmp_path: Path,
) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")
    route_output = next(
        key for key in app.callback_map if key.startswith("..route-home.style")
    )
    route_outputs = [
        {"id": container_id, "property": "style"}
        for container_id in ROUTE_CONTAINER_IDS
    ]

    response = app.server.test_client().post(
        "/_dash-update-component",
        json={
            "output": route_output,
            "outputs": route_outputs,
            "inputs": [
                {
                    "id": "url",
                    "property": "pathname",
                    "value": "/research/backtest-results",
                }
            ],
            "state": [],
            "changedPropIds": ["url.pathname"],
        },
    )
    payload = response.get_json()
    visible = [
        container_id
        for container_id in ROUTE_CONTAINER_IDS
        if payload["response"][container_id]["style"] == {"display": "block"}
    ]

    assert response.status_code == 200
    assert visible == ["route-research-backtest-results"]
    assert payload["response"]["route-home"]["style"] == {"display": "none"}


def test_selected_run_callbacks_use_mounted_backtest_selection_state(
    tmp_path: Path,
) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")

    detail_inputs = {
        (item["id"], item["property"]): item
        for item in app.callback_map["selected-run-detail.children"]["inputs"]
    }
    refresh_output = "..recent-runs-monitor.children...recent-events-monitor.children.."
    selector_output = (
        "..selected-run-selector.options...selected-run-selector.value.."
    )
    refresh_inputs = {
        (item["id"], item["property"]): item
        for item in app.callback_map[refresh_output]["inputs"]
    }
    selector_inputs = {
        (item["id"], item["property"]): item
        for item in app.callback_map[selector_output]["inputs"]
    }
    selector_states = {
        (item["id"], item["property"]): item
        for item in app.callback_map[selector_output]["state"]
    }

    assert ("selected-run-state", "data") in detail_inputs
    assert ("selected-run-selector", "value") in detail_inputs
    assert ("launch-selected-run-configuration", "n_clicks") not in detail_inputs
    assert ("cancel-selected-run", "n_clicks") not in detail_inputs
    assert detail_inputs[("cancellation-message", "children")]["allow_optional"]
    assert refresh_inputs[
        ("historical-launch-message", "children")
    ]["allow_optional"]
    assert refresh_inputs[("reproduction-message", "children")]["allow_optional"]
    assert refresh_inputs[("cancellation-message", "children")]["allow_optional"]
    assert ("refresh-runs", "n_clicks") in refresh_inputs
    assert ("refresh-runs", "n_clicks") in selector_inputs
    assert ("refresh-comparisons", "n_clicks") not in selector_inputs
    assert "run-monitor-interval" not in str(_resolved_layout(app))
    assert selector_inputs[
        ("historical-launch-state", "data")
    ]["allow_optional"]
    assert selector_inputs[("reproduction-launch-state", "data")]["allow_optional"]
    assert ("run-test-launch-state", "data") in selector_inputs
    assert ("selected-run-state", "data") in selector_inputs
    assert ("selected-run-state", "data") not in selector_states

    comparison_inputs = {
        (item["id"], item["property"]): item
        for item in app.callback_map["find-compare-grid.rowData"]["inputs"]
    }
    assert set(comparison_inputs) == {
        ("refresh-comparisons", "n_clicks"),
        ("url", "pathname"),
        ("url", "search"),
    }

    compare_output = next(
        value
        for key, value in app.callback_map.items()
        if "run-comparison-output.children" in key
    )
    compare_inputs = {
        (item["id"], item["property"])
        for item in compare_output["inputs"]
    }
    assert compare_inputs == {
        ("refresh-comparisons", "n_clicks"),
        ("url", "pathname"),
        ("url", "search"),
    }


def test_user_action_callbacks_ignore_inactive_routes(tmp_path: Path) -> None:
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, tmp_path / "reviews.json")

    guarded_calls = (
        ("launch-message", (1, "missing-configuration", None, "/")),
        ("historical-launch-message", (1, "missing-run", None, "/")),
        ("reproduction-message", (1, "missing-run", None, "/")),
        (
            "run-comparison-output",
            (0, "/research/backtest-results", "?run_id=a&run_id=b"),
        ),
        ("cancellation-message", (1, "missing-run", "/")),
        ("stale-recovery-message", (1, "2026-07-13T12:00:00Z", "/")),
        (
            "review-message",
            (
                1,
                "missing-run",
                ReviewState.WATCHLIST.value,
                "Review note",
                "/research/compare-backtests",
            ),
        ),
    )

    for output_fragment, args in guarded_calls:
        with pytest.raises(PreventUpdate):
            _callback_function(app, output_fragment)(*args)


def test_selection_parameter_mapping_and_rsi_grid_preservation() -> None:
    assert parameters_from_row(_ranked_row()) == {
        "window": 7,
        "entry_threshold": 25,
        "exit_threshold": 60,
    }
    assert len(demo.PARAMETER_COMBINATIONS) == 27
    assert demo.PARAMETER_COMBINATIONS[0] == {
        "window": 7,
        "entry_threshold": 20,
        "exit_threshold": 50,
    }


def test_application_shell_routes_known_and_unknown_pages() -> None:
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )

    layout = create_layout(context)
    assert layout.id == "application-shell"
    assert layout.className == "application-shell theme-light"
    component_ids = [
        getattr(component, "id", None)
        for component in _walk_components(layout)
        if getattr(component, "id", None) is not None
    ]
    assert len(component_ids) == len(set(component_ids))
    navigation_container = next(
        component
        for component in _walk_components(layout)
        if getattr(component, "id", None) == "navigation-container"
    )
    navigation = next(
        component
        for component in _walk_components(navigation_container)
        if getattr(component, "className", None) == "sidebar"
    )
    assert getattr(navigation, "className", None) == "sidebar"
    assert {
        getattr(component, "id", None)
        for component in _walk_components(navigation_container)
    } >= {
        "navigation-drawer-toggle",
        "responsive-active-page",
        "navigation-drawer-panel",
    }
    assert {
        getattr(component, "id", None)
        for component in _walk_components(navigation)
    } >= {
        f"navigation-link-{path.strip('/').replace('/', '-')}"
        for path, _ in NAVIGATION_LINKS
    }
    route_containers = [
        component
        for component in _walk_components(layout)
        if getattr(component, "id", None) in ROUTE_CONTAINER_IDS
    ]
    assert [component.id for component in route_containers] == list(ROUTE_CONTAINER_IDS)
    assert [
        component.style for component in route_containers
    ] == list(route_container_styles_for_path("/"))

    home = page_for_path("/", context)
    home_text = _component_text(home)
    assert home.className == "page-container home-page"
    assert "RESEARCH / HOME" in home_text
    assert "Home" in home_text
    assert PROJECT_STATUS.home_subtitle in home_text
    assert str(PROJECT_STATUS.current_milestone_number) in home_text
    assert PROJECT_STATUS.current_milestone_title in home_text
    assert PROJECT_STATUS.current_milestone_status in home_text
    assert (
        "complete passive browser workflow are complete through Step 14"
        in home_text
    )
    assert "Terry's Step 15 final dashboard and workflow acceptance" in home_text
    assert "New candidate and edge research are paused until beta" in home_text
    assert (
        "Protected-data inspection, promotion, deployment, paper execution, and live "
        "trading remain blocked"
        in home_text
    )
    assert "Not checked" in home_text
    assert "Milestone 20" not in home_text
    assert "Operator Home" not in home_text
    assert (
        page_for_path("/research/market-data", context).className
        == "page-container"
    )
    assert page_for_path("/research/ideas", context).className == "page-container ideas-page"
    assert page_for_path("/research/setup", context).className == "page-container setup-page"
    assert page_for_path("/research/run-test", context).className == "page-container run-test-page"
    assert page_for_path("/research/backtest-results", context).className == "page-container"
    comparisons = page_for_path("/research/compare-backtests", context)
    assert comparisons.className == "page-container comparison-page"
    rendered_comparisons = str(comparisons)
    assert "Find & Compare" in rendered_comparisons
    assert "find-compare-grid" in rendered_comparisons
    assert "comparison-loading" in rendered_comparisons
    assert "find-compare-exact-link" in rendered_comparisons
    assert "run-comparison-output" in rendered_comparisons
    assert "href='/research/compare-backtests'" in str(
        page_for_path("/research/backtest-results", context)
    )
    for legacy_path in (
        "/data-catalog",
        "/review",
        "/runs",
        "/comparisons",
        "/research/data-catalog",
        "/research/experiments",
        "/research/backtest-detail",
        "/research/comparisons",
        "/research/strategy-review",
    ):
        assert "Page not found" in _component_text(page_for_path(legacy_path, context))
    assert page_for_path("/paper/fleet", context).className == "page-container pending-page"
    assert page_for_path("/paper/strategy", context).className == "page-container pending-page"
    system = page_for_path("/system", context)
    system_text = _component_text(system)
    assert system.className == "page-container"
    assert "New candidate and edge research are paused until beta" in system_text
    assert "essential dashboard pages are complete for this bounded path" in system_text
    assert (
        "Protected-data inspection, promotion, deployment, paper execution, and live "
        "trading remain blocked"
        in system_text
    )
    assert page_for_path("/system/providers", context).className == "page-container"
    assert page_for_path("/settings", context).className == "page-container pending-page"
    assert page_for_path("/missing", context).className == "page-container"


def test_pathname_selects_one_visible_mounted_route() -> None:
    expected_visible = {
        "/": "route-home",
        "/research/ideas": "route-research-ideas",
        "/research/setup": "route-research-setup",
        "/research/run-test": "route-research-run-test",
        "/research/market-data": "route-research-market-data",
        "/research/backtest-results": "route-research-backtest-results",
        "/research/strategy-review": "route-not-found",
        "/research/compare-backtests": "route-research-compare-backtests",
        "/not-a-route": "route-not-found",
    }

    for pathname, visible_container in expected_visible.items():
        styles = route_container_styles_for_path(pathname)
        visible = [
            container_id
            for container_id, style in zip(ROUTE_CONTAINER_IDS, styles, strict=True)
            if style == {"display": "block"}
        ]
        hidden = [
            container_id
            for container_id, style in zip(ROUTE_CONTAINER_IDS, styles, strict=True)
            if style == {"display": "none"}
        ]

        assert visible == [visible_container]
        assert sorted(visible + hidden) == sorted(ROUTE_CONTAINER_IDS)


def test_location_route_renders_one_active_page_and_navigation() -> None:
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )

    expected = {
        "/": "Home",
        "/research/ideas": "Ideas",
        "/research/setup": "Set up a test",
        "/research/run-test": "Run test",
        "/research/market-data": "Market Data",
        "/research/backtest-results": "Results",
        "/research/compare-backtests": "Find & Compare",
    }

    for pathname, title in expected.items():
        page = route_content_for_path(pathname, context)
        navigation = _navigation(pathname)
        rendered_page = _component_text(page)

        assert title in rendered_page
        assert getattr(page, "className", "").startswith("page-container")
        if pathname == "/research/backtest-results":
            assert "Review decision" in rendered_page
            assert "Understand what happened, whether the evidence is usable, and what decision is required." in rendered_page
        if pathname == "/research/market-data":
            assert "View the price history used in strategy research." in rendered_page
            if pathname == "/research/compare-backtests":
                assert (
                    "Search, sort, and filter every saved test. Select one row for "
                    "its exact Results page, or two to four rows for an exact "
                    "comparison."
                ) in rendered_page

        links = [
            component
            for component in _walk_components(navigation)
            if getattr(component, "className", None)
            and "navigation-link" in component.className
        ]
        active = [
            link
            for link in links
            if "navigation-link-active" in link.className
        ]

        if pathname == "/":
            assert active == []
        else:
            assert len(active) == 1
            assert active[0].href == pathname


def test_ideas_page_is_browser_session_text_only() -> None:
    from dashboard.callbacks.ideas import (
        _idea_draft_transition,
        _valid_source_url,
    )

    page = page_for_path("/research/ideas", None)
    rendered = _component_text(page)
    ids = {
        getattr(component, "id", None)
        for component in _walk_components(page)
    }

    assert "Draft only — nothing will run" in rendered
    assert "will not open, preview, download, summarize, approve, or execute" in rendered
    assert {
        "idea-draft-store",
        "idea-title",
        "idea-description",
        "idea-source-url",
        "idea-attribution",
        "idea-notes",
        "save-idea-draft",
        "discard-idea-draft",
        "confirm-discard-idea-draft",
    }.issubset(ids)
    assert _valid_source_url("")
    assert _valid_source_url("https://example.com/research")
    assert not _valid_source_url("javascript:alert(1)")
    assert not _valid_source_url("https://user:secret@example.com/private")

    saved = {
        "title": "Saved title",
        "description": "",
        "source_url": "https://example.com/source",
        "attribution": "Owner",
        "notes": "",
        "saved_at": "2026-09-18T04:00:00Z",
    }
    edited = {key: saved[key] for key in saved if key != "saved_at"}
    edited["notes"] = "Unsaved question"
    unchanged_store, unsaved_status, _, confirm = _idea_draft_transition(
        "idea-notes",
        edited,
        saved,
    )
    assert unchanged_store is no_update
    assert "Unsaved local changes" in unsaved_status
    assert confirm is False

    invalid = {**edited, "source_url": "javascript:do-not-run()"}
    unchanged_store, invalid_status, _, confirm = _idea_draft_transition(
        "save-idea-draft",
        invalid,
        saved,
    )
    assert unchanged_store is no_update
    assert "Your text is unchanged" in invalid_status
    assert confirm is False

    draft, saved_status, _, confirm = _idea_draft_transition(
        "save-idea-draft",
        {**edited, "source_url": "https://example.com/new"},
        saved,
        saved_at="2026-09-18T04:05:00Z",
    )
    assert draft["saved_at"] == "2026-09-18T04:05:00Z"
    assert "2026-09-18T04:05:00Z" in saved_status
    assert confirm is False

    unchanged_store, discard_status, _, confirm = _idea_draft_transition(
        "discard-idea-draft",
        edited,
        saved,
    )
    assert unchanged_store is no_update
    assert "Confirm before removing" in discard_status
    assert confirm is True


def test_every_workflow_page_has_same_active_six_step_progress() -> None:
    paths = (
        "/",
        "/research/ideas",
        "/research/setup",
        "/research/run-test",
        "/research/backtest-results",
        "/research/compare-backtests",
    )
    expected_labels = ["Home", "Ideas", "Set up", "Run test", "Results", "Compare"]
    expected_identities = [
        "Home",
        "Ideas",
        "Set up a test",
        "Run test",
        "Results",
        "Find & Compare",
    ]

    for pathname, identity in zip(paths, expected_identities, strict=True):
        page = page_for_path(pathname, None, ())
        heading = next(
            component
            for component in _walk_components(page)
            if isinstance(component, html.H1)
        )
        progress = next(
            component
            for component in _walk_components(page)
            if getattr(component, "className", None) == "strategy-research-path"
        )
        cards = [
            component
            for component in _walk_components(progress)
            if "research-path-card" in str(getattr(component, "className", ""))
        ]
        active = [
            card
            for card in cards
            if "research-path-card-active" in card.className
        ]

        assert heading.children == identity
        assert [card.children[1].children for card in cards] == expected_labels
        assert [card.href for card in active] == [pathname]
        assert active[0].title == f"Current step: {active[0].children[1].children}"


def test_workflow_mounts_page_unique_operator_contexts_without_inference() -> None:
    from dashboard.app import _results_operator_context

    run = _DashboardRunService()._summary(
        "operator_context_run",
        "a" * 64,
        "succeeded",
    )
    evidence = RunEvidenceView(
        notices=(),
        metrics=(),
        trades=(),
        orders=(),
        equity_curve=(),
        drawdown_curve=(),
        validation=(),
        provenance=(),
        warnings=(),
        validation_outcome=(
            DetailField("Normalized status", "Insufficient evidence"),
        ),
    )
    selected_context = _results_operator_context(
        run,
        _selected_detail_view(evidence=evidence),
    )
    selected_text = _component_text(selected_context)

    assert "Succeeded" in selected_text
    assert "Insufficient evidence" in selected_text
    assert "Unavailable" in selected_text
    assert "Inspect evidence" in selected_text

    run_page = page_for_path("/research/run-test", None, ())
    results_page = page_for_path(
        "/research/backtest-results",
        None,
        (),
        recent_runs=(run,),
        selected_run_id=run.run_id,
    )
    compare_page = page_for_path(
        "/research/compare-backtests",
        None,
        recent_runs=(run,),
    )
    context_ids = {
        getattr(component, "id", None)
        for page in (run_page, results_page, compare_page)
        for component in _walk_components(page)
        if getattr(component, "id", None)
        in {
            "run-test-operator-context",
            "results-operator-context",
        }
    }

    assert context_ids == {
        "run-test-operator-context",
        "results-operator-context",
    }
    assert "No run selected" in _component_text(run_page)
    assert "Succeeded" in _component_text(results_page)
    assert "comparison-operator-contexts" in str(compare_page)
    assert "Choose persisted tests to compare" in _component_text(compare_page)


def test_home_registered_page_uses_honest_unchecked_health_and_one_action() -> None:
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )

    page = route_content_for_path("/", context, recent_runs=(), recent_events=())
    rendered = _component_text(page)

    assert page.className == "page-container home-page"
    assert "Research readiness" in rendered
    assert "No selected, active, or persisted run is available yet." in rendered
    assert "No recent failures require attention." in rendered
    assert rendered.count("Not checked") >= 12
    assert "New candidate and edge research are paused until beta" in rendered
    assert "P&L" not in rendered
    assert "profit" not in rendered.lower()
    action = next(
        component
        for component in _walk_components(page)
        if getattr(component, "id", None) == "home-primary-action"
    )
    assert action.children == "Capture an idea"
    assert action.href == "/research/ideas"
    health_ids = {
        getattr(component, "id", None)
        for component in _walk_components(page)
        if str(getattr(component, "id", "")).startswith("home-health-")
    }
    assert health_ids == {
        "home-health-summary",
        "home-health-cards",
        "home-health-database",
        "home-health-worker",
        "home-health-provider",
        "home-health-cache",
        "home-health-artifact",
        "home-health-credential",
    }


def test_home_registered_page_uses_selected_run_and_recent_events() -> None:
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    run = RunSummary(
        run_id="visual_run",
        configuration_id="a" * 64,
        strategy_id="prefect_fixture_strategy",
        strategy_version="1.0.0",
        stage="fixture",
        status="succeeded",
        created_at="2026-07-13T12:00:00Z",
        started_at="2026-07-13T12:00:01Z",
        completed_at="2026-07-13T12:00:02Z",
        error_summary=None,
        prefect_flow_run_id=None,
        prefect_api_url=None,
        attempt_count=1,
    )
    active = replace(
        run,
        run_id="active_run",
        strategy_id="another_fixture_strategy",
        status="running",
        completed_at=None,
    )
    event = RunEvent(
        event_id=1,
        run_id="event_failure",
        event_type="run_failed",
        timestamp="2026-07-13T12:00:03Z",
        severity="error",
        message="Recorded fixture failure requires attention.",
        source="fixture",
    )

    page = page_for_path(
        "/",
        context,
        recent_runs=(active, run),
        recent_events=(event,),
        selected_run_id=run.run_id,
    )
    rendered = _component_text(page)
    current_run = next(
        component
        for component in _walk_components(page)
        if getattr(component, "id", None) == "home-current-run"
    )
    failures = next(
        component
        for component in _walk_components(page)
        if getattr(component, "id", None) == "home-attention-failures"
    )
    action = next(
        component
        for component in _walk_components(page)
        if getattr(component, "id", None) == "home-primary-action"
    )

    assert "Prefect Fixture Strategy · Succeeded" in _component_text(current_run)
    assert "2026-07-13T12:00:02Z" in rendered
    assert "Another Fixture Strategy" not in _component_text(current_run)
    assert "Recorded fixture failure requires attention." in _component_text(failures)
    assert "2026-07-13T12:00:03Z" in rendered
    assert action.children == "Inspect failure"
    assert action.href == "/research/backtest-results"


def test_navigation_marks_current_page_active() -> None:
    from dashboard.app import _navigation

    navigation = _navigation("/research/backtest-results")
    brand = next(
        child.children
        for child in navigation.children
        if getattr(child, "className", None) == "sidebar-brand-item navigation-item"
    )
    groups_container = next(
        child
        for child in navigation.children
        if getattr(child, "className", None) == "sidebar-navigation-groups"
    )
    labels = [
        child.children
        for child in groups_container.children
        if getattr(child, "className", None) == "sidebar-section-label"
    ]
    links = [
        item.children
        for child in groups_container.children
        if getattr(child, "className", None) == "navigation-links"
        for item in child.children
    ]

    active = [
        link
        for link in links
        if "navigation-link-active" in link.className
    ]

    assert labels == [
        "Research workflow",
        "Research support",
        "Paper Trading",
        "System",
    ]
    assert brand.href == "/"
    assert brand.title == "Quant Factory Home"
    assert "QF" in _component_text(brand)
    assert "QUANT" in _component_text(brand)
    assert "FACTORY" in _component_text(brand)
    assert "/" not in [link.href for link in links]
    assert {
        "/research/ideas",
        "/research/setup",
        "/research/run-test",
        "/research/market-data",
        "/research/backtest-results",
        "/research/compare-backtests",
    }.issubset({link.href for link in links})
    assert "/research/strategy-review" not in {link.href for link in links}
    assert len(active) == 1
    assert active[0].href == "/research/backtest-results"
    assert [link.children[0].children for link in links[:5]] == [
        "Ideas",
        "Set up",
        "Run test",
        "Results",
        "Compare",
    ]


def test_ranked_grid_columns_use_operator_friendly_formats() -> None:
    row = {
        **_ranked_row(),
        "screening_status": "passed",
        "validation_status": "passed",
    }
    definitions = _ranked_column_definitions(pd.DataFrame([row]))
    by_field = {definition["field"]: definition for definition in definitions}

    assert "parameter_row_id" not in by_field
    assert "data_source" not in by_field

    assert by_field["total_return"]["cellClass"] == (
        "qf-table-cell qf-table-cell-center"
    )
    assert by_field["total_return"]["headerClass"] == (
        "qf-table-header qf-table-header-wrap qf-table-header-center"
    )
    assert by_field["total_return"]["width"] <= 110
    assert "* 100" in by_field["total_return"]["valueFormatter"]["function"]
    assert "toFixed(2)" in by_field["sharpe_ratio"]["valueFormatter"]["function"]
    assert "Math.round" in by_field["number_of_trades"]["valueFormatter"]["function"]
    assert "Math.round" in by_field["rsi_window"]["valueFormatter"]["function"]
    assert by_field["entry_threshold"]["headerName"] == "Entry"
    assert by_field["annualized_return"]["headerName"] == "Annual Return"
    assert by_field["annualized_return"]["headerTooltip"] == "Annual Return"
    assert by_field["screening_status"]["minWidth"] >= 170
    assert by_field["validation_status"]["minWidth"] >= 170


def test_results_page_keeps_run_history_grid_beside_durable_review() -> None:
    page = _runs_page()
    grid = next(
        component
        for component in _walk_components(page)
        if getattr(component, "id", None) == "run-history-grid"
    )

    assert grid.id == "run-history-grid"
    assert grid.rowData == []
    assert grid.selectedRows == []
    assert grid.dashGridOptions["rowSelection"] == {
        "mode": "singleRow",
        "checkboxes": False,
        "enableClickSelection": True,
    }
    assert grid.columnSize == "responsiveSizeToFit"
    assert grid.columnSizeOptions == {"defaultMinWidth": 72}
    assert grid.style == {"height": "360px", "width": "100%"}
    assert "review-status" in str(page)
    assert "review-history" in str(page)


def test_dashboard_css_includes_phone_breakpoint() -> None:
    css = (
        Path(__file__).resolve().parents[1]
        / "dashboard"
        / "assets"
        / "style.css"
    ).read_text(encoding="utf-8")

    assert "@media (max-width: 390px)" in css
    assert "min-width: 720px" in css
    assert "-webkit-overflow-scrolling: touch" in css


def _saved_configuration() -> SavedConfigurationView:
    return SavedConfigurationView(
        configuration_id="a" * 64,
        experiment_id="slice_18a_fixture",
        strategy_id="prefect_fixture_strategy",
        strategy_version="1.0.0",
        strategy_name="Prefect Fixture Strategy",
        lifecycle="infrastructure_fixture",
        active=True,
        parameters={"fixture": True},
        execution={"kind": "prefect_fixture"},
        market_data={"kind": "none"},
        config_hash="a" * 64,
    )


def _selected_detail_view(
    *,
    artifacts: tuple[ArtifactInventoryView, ...] = (),
    result_rows: tuple[tuple[DetailField, ...], ...] = (),
    warnings: tuple[str, ...] = (),
    lineage_value: str = "abc123",
    evidence: RunEvidenceView | None = None,
) -> SelectedRunDetailView:
    return SelectedRunDetailView(
        configuration_fields=(
            DetailField("Configuration ID", "a" * 64),
            DetailField("Experiment ID", "slice_18a_fixture"),
            DetailField("Strategy", "prefect_fixture_strategy@1.0.0"),
            DetailField("Configuration checksum", "checksum-a"),
        ),
        parameters=(
            DetailField("Fixture", "Yes"),
            DetailField("Nested", "window: 14; threshold: 25"),
        ),
        market_data=(DetailField("Kind", "none"),),
        execution=(DetailField("Kind", "prefect_fixture"),),
        ranking=(DetailField("Columns", "deterministic_value"),),
        screening=(DetailField("Minimum Trades", "1"),),
        lineage_fields=(
            DetailField("Git commit", lineage_value),
            DetailField("Python", "3.12.0"),
            DetailField("VectorBT Pro", "Not recorded"),
            DetailField("Dataset identity", "dataset-id"),
            DetailField("Parent/child lineage", "Not recorded for this fixture run"),
        ),
        manifest_fields=(
            DetailField("Schema version", "3"),
            DetailField("Manifest checksum", "manifest-checksum"),
        ),
        artifacts=artifacts,
        result_summary=ResultSummaryView(
            status="available" if result_rows else "empty",
            message=(
                "Persisted deterministic fixture result summary."
                if result_rows
                else "No persisted parameter result summary is available for this run."
            ),
            rows=result_rows,
        ),
        evidence=evidence or RunEvidenceView(
            notices=(),
            metrics=(),
            trades=(),
            orders=(),
            equity_curve=(),
            drawdown_curve=(),
            validation=(),
            provenance=(),
            warnings=(),
        ),
        warnings=warnings,
    )


class _DashboardRunDetailAdapter:
    def __init__(self, detail: SelectedRunDetailView | Exception | None = None) -> None:
        self.detail = detail or _selected_detail_view()
        self.requests: list[str] = []

    def selected_run_detail(self, run_id: str) -> SelectedRunDetailView:
        self.requests.append(run_id)
        if isinstance(self.detail, Exception):
            raise self.detail
        return self.detail


def test_saved_configuration_view_is_launchable_and_labeled() -> None:
    configuration = _saved_configuration()

    assert configuration.launchable
    assert "Prefect Fixture Strategy" in configuration.label
    assert "slice_18a_fixture" in configuration.label
    assert configuration.configuration_id[:10] in configuration.label


def test_setup_and_run_test_split_configuration_from_launch() -> None:
    configuration = _saved_configuration()
    setup_page = page_for_path("/research/setup", None, (configuration,))
    run_page = page_for_path("/research/run-test", None, (configuration,))
    results_page = page_for_path("/research/backtest-results", None, (configuration,))
    selector = next(
        component
        for component in _walk_components(setup_page)
        if getattr(component, "id", None) == "configuration-selector"
    )
    preview = next(
        component
        for component in _walk_components(setup_page)
        if getattr(component, "id", None) == "configuration-preview"
    )
    launch_button = next(
        component
        for component in _walk_components(run_page)
        if getattr(component, "id", None) == "launch-run"
    )

    assert selector.id == "configuration-selector"
    assert selector.value == "a" * 64
    assert selector.options[0]["disabled"] is False
    assert selector.persistence is True
    assert selector.persistence_type == "session"
    assert preview.id == "configuration-preview"
    assert launch_button.id == "launch-run"
    assert launch_button.disabled is True
    assert launch_button.title == "Preparing a durable browser-session run ticket."
    assert not any(
        getattr(component, "id", None) in {"configuration-selector", "launch-run"}
        for component in _walk_components(results_page)
    )
    rendered = _component_text(preview)
    classes = [
        getattr(component, "className", "")
        for component in _walk_components(preview)
    ]
    assert "Parameters" in rendered
    assert "Fixture" in rendered
    assert "Yes" in rendered
    assert "Execution assumptions" in rendered
    assert "Kind" in rendered
    assert "Prefect fixture" in rendered
    assert "prefect_fixture" in rendered
    assert "configuration-document" not in classes


def test_setup_and_run_test_handle_empty_configuration_list() -> None:
    setup_page = page_for_path("/research/setup", None, ())
    run_page = page_for_path("/research/run-test", None, ())

    assert "No approved choices" in _component_text(setup_page)
    assert "No saved setup selected" in _component_text(run_page)
    launch_button = next(
        component
        for component in _walk_components(run_page)
        if getattr(component, "id", None) == "launch-run"
    )
    assert launch_button.disabled is True


def test_backtest_selector_labels_distinguish_persisted_stages() -> None:
    service = _DashboardRunService()
    target = replace(
        service._summary("spym-target", "a" * 64),
        strategy_id="spym_rsi_mean_reversion_fixture",
    )

    labels = {
        stage: _backtest_selector_label(replace(target, stage=stage))
        for stage in ("fixture", "walk_forward", "monte_carlo", "robustness", "oos")
    }

    assert labels == {
        "fixture": "SPYM RSI Mean Reversion Fixture · SPYM · 1m · Fixture backtest · Succeeded",
        "walk_forward": "SPYM RSI Mean Reversion Fixture · SPYM · 1m · Walk-forward validation · Succeeded",
        "monte_carlo": "SPYM RSI Mean Reversion Fixture · SPYM · 1m · Monte Carlo validation · Succeeded",
        "robustness": "SPYM RSI Mean Reversion Fixture · SPYM · 1m · Robustness validation · Succeeded",
        "oos": "SPYM RSI Mean Reversion Fixture · SPYM · 1m · Out-of-sample evidence · Succeeded",
    }


def test_backtest_selection_owns_results_review_form() -> None:
    service = _DashboardRunService()
    target = replace(
        service._summary("spym-target", "a" * 64),
        strategy_id="spym_rsi_mean_reversion_fixture",
        stage="fixture",
    )
    robustness = replace(
        service._summary("spym-robustness", "a" * 64),
        strategy_id="spym_rsi_mean_reversion_fixture",
        stage="robustness",
    )
    runs = (robustness, target)
    detail_page = _runs_page((_saved_configuration(),), recent_runs=runs)
    detail_selector = next(
        component
        for component in _walk_components(detail_page)
        if getattr(component, "id", None) == "selected-run-selector"
    )
    detail_store = next(
        component
        for component in _walk_components(detail_page)
        if getattr(component, "id", None) == "selected-run-state"
    )
    review_ids = {
        getattr(component, "id", None)
        for component in _walk_components(detail_page)
        if getattr(component, "id", None)
        in {"review-status", "review-note", "save-review", "review-history"}
    }

    assert detail_selector.value == target.run_id
    assert detail_store.data == target.run_id
    assert review_ids == {
        "review-status",
        "review-note",
        "save-review",
        "review-history",
    }


def test_backtest_detail_analysis_tabs_are_in_page_controls_with_concise_evidence() -> None:
    detail = _selected_detail_view(
        evidence=RunEvidenceView(
            notices=(),
            metrics=(DetailField("Total Return", "0.01"),),
            trades=(),
            orders=(),
            equity_curve=(),
            drawdown_curve=(),
            validation=(DetailField("Walk-forward", "passed"),),
            provenance=(),
            warnings=(),
            validation_outcome=(
                DetailField("Normalized status", "passed"),
                DetailField("Reasons", "All persisted validation stages passed."),
            ),
        )
    )
    tabs = _run_detail_analysis_tabs(detail)
    by_value = {tab.value: tab for tab in tabs.children}

    assert tabs.id == "run-detail-analysis-tabs"
    assert tabs.value == "evidence"
    assert tabs.parent_style == {
        "display": "flex",
        "flexWrap": "wrap",
        "gap": "8px",
    }
    assert list(by_value) == [
        "evidence",
        "assumptions",
        "lineage",
        "configuration",
        "diagnostics",
    ]
    assert [tab.label for tab in tabs.children] == [
        "Strategy Checks",
        "Trading Assumptions",
        "Research History",
        "Strategy Settings",
        "Technical Details",
    ]
    for tab in tabs.children:
        assert tab.className == "run-analysis-tab"
        assert tab.selected_className == "run-analysis-tab-selected"
        assert tab.style["border"] == "1px solid #cbd7e6"
        assert tab.style["minHeight"] == "44px"
        assert tab.selected_style == {
            "backgroundColor": "#2357d9",
            "border": "1px solid #2357d9",
            "color": "#ffffff",
            "fontWeight": 800,
        }
    assert all(
        getattr(component, "href", None) is None
        for component in _walk_components(tabs)
    )

    expected_panels = {
        "evidence": "Validation summary",
        "assumptions": "Trading assumptions",
        "lineage": "Research history",
        "configuration": "Strategy settings",
        "diagnostics": "Artifacts and validation",
    }
    for value, heading in expected_panels.items():
        tabs.value = value
        assert tabs.value == value
        assert heading in _component_text(by_value[value].children)

    evidence_panel = by_value["evidence"].children
    technical_details = next(
        component
        for component in _walk_components(evidence_panel)
        if component.__class__.__name__ == "Details"
    )
    assert "All persisted validation stages passed." in _component_text(evidence_panel)
    assert "Next action: Review the supporting evidence" in _component_text(evidence_panel)
    assert "Show technical details" in _component_text(technical_details)
    assert not getattr(technical_details, "open", False)


def test_initial_backtest_keeps_fixture_when_companion_has_richer_evidence() -> None:
    service = _DashboardRunService()
    fixture = replace(
        service._summary("spym-target", "a" * 64),
        strategy_id="spym_rsi_mean_reversion_fixture",
        stage="fixture",
    )
    robustness = replace(
        service._summary("spym-robustness", "a" * 64),
        strategy_id="spym_rsi_mean_reversion_fixture",
        stage="robustness",
    )
    rich_companion_detail = replace(
        _selected_detail_view(),
        evidence=RunEvidenceView(
            notices=(),
            metrics=(DetailField("Total Return", "0.01"),),
            trades=({"PnL": 1.0},),
            orders=(),
            equity_curve=({"timestamp": "2026-01-01", "value": 10_000.0},),
            drawdown_curve=(),
            validation=(DetailField("Outcome", "passed"),),
            provenance=(),
            warnings=(),
        ),
    )

    class DetailByRun:
        def selected_run_detail(self, run_id: str) -> SelectedRunDetailView:
            return {
                fixture.run_id: _selected_detail_view(),
                robustness.run_id: rich_companion_detail,
            }[run_id]

    selected, detail = _select_initial_backtest(
        (fixture, robustness),
        DetailByRun(),
    )

    assert selected == fixture
    assert detail == _selected_detail_view()


def test_application_shell_is_fixed_light_mode_without_theme_controls() -> None:
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )

    layout = create_layout(context)
    component_ids = {
        component.id
        for component in _walk_components(layout)
        if getattr(component, "id", None)
    }

    assert layout.className == "application-shell theme-light"
    assert "theme-toggle" not in component_ids
    assert "theme-store" not in component_ids


@pytest.mark.parametrize(
    ("content", "expected_body"),
    [
        (html.P("Scalar"), ("Scalar",)),
        ([html.P("List one"), html.P("List two")], ("List one", "List two")),
        ((html.P("Tuple one"), html.P("Tuple two")), ("Tuple one", "Tuple two")),
    ],
)
def test_detail_subsection_flattens_component_content(
    content,
    expected_body: tuple[str, ...],
) -> None:
    subsection = _detail_subsection(
        "Evidence heading",
        content,
        "evidence-subsection",
    )

    assert subsection.className == "run-detail-subsection evidence-subsection"
    assert subsection.children[0].children == "Evidence heading"
    assert tuple(child.children for child in subsection.children[1:]) == expected_body
    assert len(subsection.children[1:]) == len(expected_body)
    assert not any(
        isinstance(child, (list, tuple))
        for child in subsection.children
    )


def test_dashboard_state_ownership_contract_names_callback_owners() -> None:
    assert STATE_OWNERS == {
        "active_route": {
            "source": "url.pathname",
            "owner": "dashboard.callbacks.routing",
            "rule": (
                "Route callbacks only derive visibility and navigation classes; "
                "no callback writes the URL."
            ),
        },
        "navigation_drawer": {
            "source": "navigation-drawer-state.data",
            "owner": "dashboard.callbacks.routing",
            "rule": (
                "An explicit menu-button click toggles the responsive drawer; "
                "every primary-navigation selection or pathname change closes "
                "it without rebuilding navigation or writing the URL."
            ),
        },
        "health_snapshot": {
            "source": "health-observation-snapshot.data",
            "owner": "dashboard.callbacks.health",
            "rule": (
                "A redacted read-only observation is fixed for the browser layout; "
                "the passive interval re-evaluates only its freshness presentation "
                "without probing services or replacing routes."
            ),
        },
        "idea_draft": {
            "source": "idea-draft-store.data",
            "owner": "dashboard.callbacks.ideas",
            "rule": (
                "Ideas stores operator-authored text in the browser session only "
                "and never retrieves or executes it."
            ),
        },
        "selected_configuration": {
            "source": "selected-configuration-state.data",
            "control": "configuration-selector.value",
            "owner": "dashboard.callbacks.setup",
            "rule": (
                "Set up writes the operator choice to one session store; Run test "
                "reads that identity without mutation or an automatic launch."
            ),
        },
        "run_test_launch": {
            "source": "run-test-launch-state.data",
            "owner": "dashboard.callbacks.backtest_results",
            "rule": (
                "Run test owns one session launch key bound to its immutable "
                "configuration; submitted keys are never rebound and persisted "
                "submission state is authoritative."
            ),
        },
        "selected_backtest": {
            "source": "selected-run-selector.value",
            "store": "selected-run-state.data",
            "owner": "dashboard.callbacks.backtest_results",
            "rule": (
                "Explicit selector changes win over passive refresh and hydration "
                "callbacks."
            ),
        },
        "historical_relaunch": {
            "source": "historical-launch-state.data",
            "owner": "dashboard.callbacks.backtest_results",
            "rule": (
                "Results owns a distinct historical-relaunch key bound to the "
                "selected source run; it never shares reproduction or Run test state."
            ),
        },
        "reproduction_launch": {
            "source": "reproduction-launch-state.data",
            "owner": "dashboard.callbacks.backtest_results",
            "rule": (
                "Results owns a distinct reproduction key bound to the selected "
                "source run; submitted keys remain immutable across refresh and "
                "retry delivery."
            ),
        },
        "review_selection": {
            "source": "selected-run-state.data",
            "owner": "dashboard.callbacks.results_review",
            "rule": (
                "Results binds durable-review form state and messages to the shared "
                "selected persisted run; no separate review identity is written."
            ),
        },
        "comparison_selection": {
            "source": "find-compare-grid.selectedRows",
            "owner": "dashboard.callbacks.compare_backtests",
            "rule": (
                "Find & Compare owns full-history grid selection, exact links, "
                "and comparison output."
            ),
        },
    }


def test_dashboard_package_lazily_exports_create_app() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import dashboard; "
                "assert 'dashboard.app' not in sys.modules; "
                "from dashboard import create_app; "
                "assert callable(create_app); "
                "assert 'dashboard.app' in sys.modules"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_dashboard_css_contains_dark_theme_rules() -> None:
    css = (
        Path(__file__).resolve().parents[1]
        / "dashboard"
        / "assets"
        / "style.css"
    ).read_text(encoding="utf-8")

    assert ".theme-dark .application-content" in css
    assert ".theme-dark .ag-root-wrapper" in css
    assert ".theme-toggle" in css


def test_dashboard_css_contains_dark_component_corrections() -> None:
    css = (
        Path(__file__).resolve().parents[1]
        / "dashboard"
        / "assets"
        / "style.css"
    ).read_text(encoding="utf-8")

    assert "#navigation-container" in css
    assert ".theme-dark .ag-row" in css
    assert ".theme-dark .ag-row-selected" in css
    assert ".theme-dark .Select-menu-outer" in css
    assert ".theme-dark .VirtualizedSelectFocusedOption" in css
    assert ".theme-dark .historical-launch-message" in css
    assert ".theme-dark .run-detail-subsection" in css
    assert ".artifact-status-error" in css


def test_dashboard_css_includes_operator_readability_structure() -> None:
    css = (
        Path(__file__).resolve().parents[1]
        / "dashboard"
        / "assets"
        / "style.css"
    ).read_text(encoding="utf-8")

    assert ".operator-message-error" in css
    assert ".operator-value-list" in css
    assert ".run-detail-subsection h3" in css
    assert ".run-identity-strip" in css
    assert ".run-outcome-card" in css
    assert ".run-main-chart-grid" in css
    assert ".run-secondary-chart-grid" in css
    assert ".run-visual-card" in css
    assert ".launch-controls-panel" in css
    assert ".history-overflow" in css
    assert ".run-comparison-table" in css
    assert ".comparison-page" in css
    assert ".comparison-selected-grid" in css
    assert ".comparison-empty-state" in css
    assert ".workflow-group" in css
    assert ".stale-before-input" in css
    assert "width: min(100%, 380px)" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css
    assert "font-size: 16px" in css
    assert "background: #e4ecf5" in css
    assert ".configuration-detail-panel .run-detail-fields div" in css
    assert "grid-template-columns: minmax(130px, 0.38fr) minmax(0, 0.62fr)" in css
    assert ".qf-data-grid" in css
    assert ".qf-ranked-grid .ag-center-cols-container" in css
    assert ".qf-trades-grid .ag-center-cols-container" in css
    assert ".qf-table-header-center" in css
    assert ".qf-table-cell-center" in css
    assert ".table-panel .ag-root-wrapper" in css


def test_detail_fields_render_structured_values_as_operator_rows() -> None:
    fields = (
        DetailField(
            "Execution assumptions",
            {
                "fees_bps": 1.5,
                "same_bar_limitation": True,
                "slippage_model": {
                    "kind": "fixed_bps",
                    "value": 0.25,
                },
            },
        ),
    )

    rendered = _detail_fields(fields, empty="No assumptions recorded.")
    text = _component_text(rendered)
    classes = [
        getattr(component, "className", "")
        for component in _walk_components(rendered)
    ]

    assert "Fees" in text
    assert "Same-bar limitation" in text
    assert "Yes" in text
    assert "Slippage model" in text
    assert "Fixed basis points" in text
    assert "fixed_bps" in text
    assert "operator-value-list" in classes
    assert "{'fees_bps'" not in text


def test_recent_run_and_event_histories_collapse_overflow() -> None:
    service = _DashboardRunService(
        initial_runs=tuple(
            _DashboardRunService()._summary(
                f"run_{index}",
                "a" * 64,
                "succeeded",
            )
            for index in range(6)
        )
    )
    runs_panel = _recent_runs_panel(service.recent_runs())
    events_panel = _recent_events_panel(
        tuple(
            RunEvent(
                event_id=index,
                run_id=f"run_{index}",
                event_type="run_completed",
                severity="info",
                message=f"Run {index} completed.",
                timestamp=f"2026-07-13T12:00:{index:02d}Z",
                source="fixture",
            )
            for index in range(7)
        )
    )

    rendered_runs = _component_text(runs_panel)
    rendered_events = _component_text(events_panel)
    classes = [
        getattr(component, "className", "")
        for component in _walk_components(runs_panel)
    ] + [
        getattr(component, "className", "")
        for component in _walk_components(events_panel)
    ]

    assert "Show 2 older runs" in rendered_runs
    assert "Show 2 older events" in rendered_events
    assert "history-overflow" in classes


class _DashboardResearchLaunches:
    def __init__(self) -> None:
        self.by_key: dict[str, ResearchRunSubmissionRecord] = {}

    def acknowledge(
        self,
        key: str,
        run: RunSummary,
        *,
        operation: ResearchLaunchOperation,
        source_run_id: str | None,
    ) -> ResearchRunSubmissionRecord:
        existing = self.by_key.get(key)
        if existing is not None:
            return existing
        canonical_request_json = canonical_json(
            {
                "operation_kind": operation.value,
                "configuration_id": run.configuration_id,
                "source_run_id": source_run_id,
            }
        )
        record = ResearchRunSubmissionRecord(
            idempotency_key=key,
            run_id=run.run_id,
            configuration_id=run.configuration_id,
            canonical_request_json=canonical_request_json,
            request_fingerprint=hashlib.sha256(
                canonical_request_json.encode("utf-8")
            ).hexdigest(),
            state=ResearchSubmissionState.ACKNOWLEDGED,
            dispatcher_instance_id="00000000-0000-4000-8000-000000000001",
            prefect_flow_run_id=run.prefect_flow_run_id,
            prefect_api_url=run.prefect_api_url,
            claimed_at=run.created_at,
            invocation_started_at=run.started_at,
            acknowledged_at=run.started_at,
            unknown_at=None,
            unknown_evidence_reference=None,
            resolved_at=None,
            resolution_evidence_reference=None,
            updated_at=run.completed_at or run.started_at or run.created_at,
            error_summary=None,
        )
        self.by_key[key] = record
        return record

    def get(self, key: str) -> ResearchRunSubmissionRecord | None:
        return self.by_key.get(key)

    def get_for_run(self, run_id: str) -> ResearchRunSubmissionRecord | None:
        return next(
            (record for record in self.by_key.values() if record.run_id == run_id),
            None,
        )


class _DashboardRunService:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        run_status: str = "succeeded",
        initial_runs: tuple[RunSummary, ...] | None = None,
        launch_run_ids: list[str] | None = None,
    ) -> None:
        self.error = error
        self.run_status = run_status
        self.configuration_ids: list[str] = []
        self.launch_run_ids = launch_run_ids or ["run_dashboard_fixture"]
        self.cancellation_requests: list[str] = []
        self.stale_recovery_requests: list[str] = []
        self.stale_recovery_result: tuple[RunSummary, ...] = ()
        self.run_queries = 0
        self.event_queries = 0
        self.run_detail_queries: list[str] = []
        self.run_event_queries: list[str] = []
        self.durable_requests: list[dict[str, object]] = []
        self.durable_request_by_key: dict[str, dict[str, object]] = {}
        self.research_launch_service = _DashboardResearchLaunches()
        self._runs: list[RunSummary] = list(initial_runs) if initial_runs is not None else [
            self._summary("run_dashboard_fixture", "a" * 64, run_status)
        ]

    def _summary(
        self,
        run_id: str,
        configuration_id: str,
        status: str | None = None,
        *,
        error_summary: str | None = None,
    ) -> RunSummary:
        resolved_status = status or self.run_status
        completed_at = (
            "2026-07-13T12:00:02Z"
            if resolved_status in {"succeeded", "failed", "cancelled"}
            else None
        )
        return RunSummary(
            run_id=run_id,
            configuration_id=configuration_id,
            strategy_id="prefect_fixture_strategy",
            strategy_version="1.0.0",
            stage="fixture",
            status=resolved_status,
            created_at="2026-07-13T12:00:00Z",
            started_at="2026-07-13T12:00:01Z",
            completed_at=completed_at,
            error_summary=error_summary,
            prefect_flow_run_id=f"prefect-{run_id}",
            prefect_api_url="http://127.0.0.1:4200/api",
            attempt_count=1,
        )

    def launch_fixture(
        self,
        *,
        configuration_id: str,
        idempotency_key: str,
        operation: ResearchLaunchOperation,
        source_run_id: str | None,
        source_lineage: object,
    ):
        existing = self.research_launch_service.get(idempotency_key)
        if existing is not None:
            request = {
                "configuration_id": configuration_id,
                "operation": operation,
                "source_run_id": source_run_id,
            }
            if self.durable_request_by_key[idempotency_key] != request:
                raise ResearchLaunchConflictError(
                    "research launch key is already bound to a different request"
                )
            run = self.get_run(existing.run_id)
            assert run is not None
            return RunLaunchResult(run=run, prefect_result=None)
        self.configuration_ids.append(configuration_id)
        self.durable_requests.append(
            {
                "idempotency_key": idempotency_key,
                "operation": operation,
                "source_run_id": source_run_id,
                "source_lineage": source_lineage,
            }
        )
        self.durable_request_by_key[idempotency_key] = {
            "configuration_id": configuration_id,
            "operation": operation,
            "source_run_id": source_run_id,
        }
        if self.error is not None:
            raise self.error
        run_id = (
            self.launch_run_ids.pop(0)
            if self.launch_run_ids
            else f"run_dashboard_fixture_{len(self._runs) + 1}"
        )
        run = self._summary(run_id, configuration_id, self.run_status)
        self._runs.insert(0, run)
        self.research_launch_service.acknowledge(
            idempotency_key,
            run,
            operation=operation,
            source_run_id=source_run_id,
        )
        return RunLaunchResult(
            run=run,
            prefect_result=None,
        )

    def reproduce_fixture_run(
        self,
        source_run_id: str,
        *,
        artifact_root: Path,
        idempotency_key: str,
    ):
        source = self.get_run(source_run_id)
        if source is None:
            raise KeyError(source_run_id)
        return self.launch_fixture(
            configuration_id=source.configuration_id,
            idempotency_key=idempotency_key,
            operation=ResearchLaunchOperation.REPRODUCTION,
            source_run_id=source_run_id,
            source_lineage=None,
        )


    def recent_runs(self, *, limit: int = 20):
        self.run_queries += 1
        assert limit == 20
        return tuple(self._runs[:limit])

    def all_runs(self):
        return tuple(self._runs)

    def all_history(self, *, artifact_root: Path | None = None):
        return tuple(
            {
                "run_id": run.run_id,
                "created_at": run.created_at,
                "instrument": "Not recorded",
                "strategy": run.strategy_id.replace("_", " ").title(),
                "stage": "Fixture backtest" if run.stage == "fixture" else run.stage,
                "status": run.status.replace("_", " ").title(),
                "review": "Not reviewed",
                "evidence": "No validation evidence",
                "metric_basis": "No persisted ranked result",
                "total_return": None,
                "annualized_return": None,
                "sharpe_ratio": None,
                "number_of_trades": None,
                "artifact_status": "No registered artifacts",
                "reproducibility": "Manifest missing",
            }
            for run in self._runs
        )

    def recent_events(self, *, limit: int = 20):
        self.event_queries += 1
        assert limit == 20
        return (
            RunEvent(
                event_id=1,
                run_id="run_dashboard_fixture",
                event_type="run_succeeded",
                timestamp="2026-07-13T12:00:02Z",
                severity="info",
                message="Run completed successfully.",
                source="quant_factory",
            ),
        )


    def recover_stale_fixture_runs(self, *, stale_before: str):
        self.stale_recovery_requests.append(stale_before)
        if self.error is not None:
            raise self.error
        return self.stale_recovery_result

    def request_fixture_cancellation(self, run_id: str):
        self.cancellation_requests.append(run_id)
        if self.error is not None:
            raise self.error
        return self.recent_runs()[0]

    def get_run(self, run_id: str):
        self.run_detail_queries.append(run_id)
        if run_id == "missing-run":
            return None
        for run in self._runs:
            if run.run_id == run_id:
                return run
        return None

    def events_for_run(self, run_id: str):
        self.run_event_queries.append(run_id)
        return self.recent_events()


class _PersistedDashboardRunService:
    """Minimal frozen seam backed by the real durable SQLite claim service."""

    def __init__(self, database: Path, invocations: list[str]) -> None:
        self.database_path = database
        self.reader = FixtureRunService(database=database)
        self.research_launch_service = DurableResearchLaunchService(database=database)
        self.invocations = invocations

    def launch_fixture(
        self,
        *,
        configuration_id: str,
        idempotency_key: str,
        operation: ResearchLaunchOperation,
        source_run_id: str | None,
        source_lineage: object,
    ) -> RunLaunchResult:
        claim = self.research_launch_service.claim(
            idempotency_key=idempotency_key,
            request=ResearchLaunchRequest(
                operation=operation,
                configuration_id=configuration_id,
                source_run_id=source_run_id,
                source_lineage=source_lineage,
            ),
        )
        dispatcher_id = new_dispatcher_instance_id()

        def invoke(submission: ResearchRunSubmissionRecord) -> None:
            self.invocations.append(idempotency_key)
            self.research_launch_service.bind_prefect_identity(
                idempotency_key=idempotency_key,
                run_id=submission.run_id,
                configuration_id=submission.configuration_id,
                canonical_request_json=submission.canonical_request_json,
                request_fingerprint=submission.request_fingerprint,
                prefect_flow_run_id=f"prefect-{submission.run_id}",
            )
            persistence = PersistenceService(self.database_path)
            try:
                persistence.transition_run(submission.run_id, RunStatus.SUCCEEDED)
            finally:
                persistence.close()

        self.research_launch_service.dispatch(
            idempotency_key=idempotency_key,
            dispatcher_instance_id=dispatcher_id,
            invoke=invoke,
        )
        run = self.reader.get_run(claim.run.run_id)
        assert run is not None
        return RunLaunchResult(run=run, prefect_result=None)

    def reproduce_fixture_run(
        self,
        source_run_id: str,
        *,
        artifact_root: Path,
        idempotency_key: str,
    ) -> RunLaunchResult:
        source = self.get_run(source_run_id)
        if source is None:
            raise KeyError(source_run_id)
        return self.launch_fixture(
            configuration_id=source.configuration_id,
            idempotency_key=idempotency_key,
            operation=ResearchLaunchOperation.REPRODUCTION,
            source_run_id=source_run_id,
            source_lineage=None,
        )

    def get_run(self, run_id: str) -> RunSummary | None:
        return self.reader.get_run(run_id)

    def recent_runs(self, *, limit: int = 20):
        return self.reader.recent_runs(limit=limit)

    def recent_events(self, *, limit: int = 20):
        return self.reader.recent_events(limit=limit)

    def all_runs(self):
        return self.reader.all_runs()

    def all_history(self, *, artifact_root: Path | None = None):
        return self.reader.all_history(artifact_root=artifact_root)

    def events_for_run(self, run_id: str):
        return self.reader.events_for_run(run_id)


def _callback_function(app, output_fragment: str):
    entries = [
        value
        for key, value in app.callback_map.items()
        if output_fragment in key
    ]
    if output_fragment == "review-message" and len(entries) > 1:
        entry = next(
            value
            for value in entries
            if any(item["id"] == "save-review" for item in value.get("inputs", ()))
        )
    else:
        entry = entries[0]
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def test_selected_setup_identity_updates_run_test_preview(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first = _saved_configuration()
    second = replace(
        first,
        configuration_id="b" * 64,
        config_hash="c" * 64,
        experiment_id="second_operator_choice",
    )
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (first, second),
    )
    app = create_app(review_database=tmp_path / "selected-setup.sqlite3")
    preserve = _callback_function(app, "selected-configuration-state.data")
    setup_preview = _callback_function(app, "configuration-preview")
    run_preview = _callback_function(app, "run-configuration-preview")

    assert preserve(second.configuration_id) == second.configuration_id
    setup_children, href, _class_name, _setup_title = setup_preview(
        second.configuration_id
    )
    run_children = run_preview(second.configuration_id)

    assert "second_operator_choice" in _component_text(html.Div(setup_children))
    assert "second_operator_choice" in _component_text(html.Div(run_children))
    assert href == "/research/run-test"


def test_initial_idea_hydration_cannot_overwrite_first_keystroke(
    tmp_path: Path,
) -> None:
    app = create_app(review_database=tmp_path / "idea-hydration.sqlite3")
    hydrate = _callback_function(app, "idea-title.value")

    values = hydrate(None)

    assert values == (no_update,) * 5


def _comparison_run_summaries() -> tuple[RunSummary, RunSummary]:
    service = _DashboardRunService()
    return (
        service._summary("compare_run_a", "a" * 64, "succeeded"),
        service._summary("compare_run_b", "b" * 64, "succeeded"),
    )


def _comparison_database(tmp_path: Path) -> Path:
    database = tmp_path / "comparison.sqlite3"
    service = PersistenceService(database)
    try:
        strategy = service.register_strategy(
            strategy_id="compare_strategy",
            strategy_version="1.0.0",
            display_name="Comparison Strategy",
            description="Dashboard comparison fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configs = []
        for name, window, fee in (
            ("a", 10, 0.0005),
            ("b", 20, 0.001),
        ):
            configs.append(
                service.upsert_configuration(
                    normalized_configuration_document(
                        experiment_id=f"comparison_{name}",
                        strategy_id=strategy.strategy_id,
                        strategy_version=strategy.strategy_version,
                        market_data={
                            "provider": "fixture",
                            "symbol": "SPY",
                            "interval": "1d",
                        },
                        parameters={"window": window, "threshold": 25},
                        execution={
                            "fill_model": "next_open",
                            "fees": fee,
                        },
                        ranking={"metric": "sharpe_ratio"},
                        screening={"minimum_trades": 1},
                    )
                )
            )

        for run_id, config, window, fee, checksum, return_value in (
            ("compare_run_a", configs[0], 10, 0.0005, "dataset-a", 0.12),
            ("compare_run_b", configs[1], 20, 0.001, "dataset-b", 0.08),
        ):
            service.create_run(
                configuration_id=config.configuration_id,
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                stage=RunStage.FIXTURE,
                run_id=run_id,
                status=RunStatus.SUCCEEDED,
            )
            with transaction(service.connection):
                service.results.set_data_provenance(
                    DataProvenanceRecord(
                        run_id=run_id,
                        provider="fixture",
                        provider_implementation="dashboard-test",
                        symbol="SPY",
                        interval="1d",
                        timezone="America/New_York",
                        requested_coverage="2024-01-01/2024-01-31",
                        actual_coverage="2024-01-01/2024-01-31",
                        adjusted=True,
                        row_count=21,
                        cache_action="fixture",
                        validation_summary_json=canonical_json({"status": "valid"}),
                        manifest_reference=f"manifest-{run_id}",
                        checksum=checksum,
                    )
                )
                service.results.set_execution_assumptions(
                    ExecutionAssumptionsRecord(
                        run_id=run_id,
                        assumptions_json=canonical_json(
                            {"fill_model": "next_open", "fees": fee}
                        ),
                    )
                )
                service.results.add_parameter_result(
                    run_id=run_id,
                    row_id=f"{run_id}-row",
                    normalized_parameters={"window": window, "threshold": 25},
                    metrics={
                        "total_return": return_value,
                        "sharpe_ratio": 1.1,
                        "number_of_trades": 4,
                    },
                    ranking_position=1,
                    screening_status="passed",
                )
        with transaction(service.connection):
            service.results.add_artifact(
                run_id="compare_run_a",
                artifact_type=ArtifactType.VALIDATION_EVIDENCE.value,
                schema_version=1,
                path="artifacts/compare_run_a/evidence.json",
                validation_status="valid",
                availability=ArtifactAvailability.AVAILABLE,
                checksum="evidence-a",
            )
    finally:
        service.close()
    return database


def _review_decision_stack(
    tmp_path: Path,
) -> tuple[Path, Path, _DashboardRunService, RunDetailDashboardAdapter]:
    database = tmp_path / "review-decision.sqlite3"
    artifact_root = tmp_path / "artifacts"
    service = PersistenceService(database)
    try:
        strategy = service.register_strategy(
            strategy_id="review_strategy",
            strategy_version="1.0.0",
            display_name="Review Strategy",
            description="Dashboard evidence decision fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="review_experiment",
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                market_data={
                    "provider": "fixture",
                    "symbol": "SPY",
                    "interval": "1d",
                },
                parameters={"window": 14},
                execution={"kind": "fixture"},
                ranking={"columns": ("total_return",), "ascending": (False,)},
                screening={"kind": "none"},
            )
        )
        service.create_run(
            configuration_id=configuration.configuration_id,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            stage=RunStage.OOS,
            run_id="decision_review_run",
            status=RunStatus.SUCCEEDED,
        )
        with transaction(service.connection):
            service.results.set_data_provenance(
                DataProvenanceRecord(
                    run_id="decision_review_run",
                    provider="fixture",
                    provider_implementation="dashboard-review-test",
                    symbol="SPY",
                    interval="1d",
                    timezone="America/New_York",
                    requested_coverage="2024-01-01/2024-01-31",
                    actual_coverage="2024-01-01/2024-01-31",
                    adjusted=True,
                    row_count=21,
                    cache_action="fixture",
                    validation_summary_json=canonical_json({"status": "valid"}),
                    manifest_reference="manifest-review",
                    checksum="dataset-review",
                )
            )
            service.results.set_execution_assumptions(
                ExecutionAssumptionsRecord(
                    run_id="decision_review_run",
                    assumptions_json=canonical_json({"kind": "fixture"}),
                )
            )
            service.results.add_parameter_result(
                run_id="decision_review_run",
                row_id="decision-review-row",
                normalized_parameters={"window": 14},
                metrics={
                    "total_return": 0.12,
                    "max_drawdown": -0.03,
                    "number_of_trades": 12,
                },
                ranking_position=1,
                screening_status="passed",
            )
        location = "artifacts/decision_review_run/validation_evidence.json"
        target = artifact_root / location
        target.parent.mkdir(parents=True, exist_ok=True)
        content = canonical_json(
            {
                "artifact": {"evidence_identity": "review-evidence"},
                "validation": {"status": "passed"},
            }
        ).encode("utf-8")
        target.write_bytes(content)
        service.register_artifact(
            run_id="decision_review_run",
            artifact_type=ArtifactType.VALIDATION_EVIDENCE,
            logical_name="validation_evidence",
            media_type="application/json",
            format="json",
            location=location,
            content=content,
        )
        service.persist_run_manifest(service.build_run_manifest("decision_review_run"))
        summary_service = _DashboardRunService(
            initial_runs=(
                _DashboardRunService()._summary(
                    "decision_review_run",
                    configuration.configuration_id,
                    "succeeded",
                ),
            )
        )
    finally:
        service.close()
    return (
        database,
        artifact_root,
        summary_service,
        RunDetailDashboardAdapter(database=database, artifact_root=artifact_root),
    )


def _review_context_stack(
    tmp_path: Path,
) -> tuple[Path, Path, _DashboardRunService, RunDetailDashboardAdapter]:
    service = _review_service(tmp_path)
    database = tmp_path / "state.sqlite3"
    artifact_root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, artifact_root)
    source = service.runs.get("wf-run")
    assert source is not None
    service.create_run(
        configuration_id=source.configuration_id,
        strategy_id=source.strategy_id,
        strategy_version=source.strategy_version,
        stage=RunStage.OOS,
        run_id="review_context_target",
        status=RunStatus.SUCCEEDED,
    )
    with transaction(service.connection):
        service.results.set_data_provenance(
            DataProvenanceRecord(
                run_id="review_context_target",
                provider="fixture",
                provider_implementation="fixture-provider",
                symbol="SPY",
                interval="1 day",
                timezone="UTC",
                requested_coverage="2020-01-01",
                actual_coverage="2020-01-01..2020-04-30",
                adjusted=True,
                row_count=120,
                cache_action="fixture",
                validation_summary_json=canonical_json({"status": "valid"}),
                manifest_reference="data/manifests/fixture.json",
                checksum="dataset-checksum",
            )
        )
        service.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id="review_context_target",
                assumptions_json=canonical_json({"kind": "fixture"}),
            )
        )
        service.results.add_parameter_result(
            run_id="review_context_target",
            row_id="review-context-row",
            normalized_parameters=REVIEW_PARAMETERS,
            metrics={
                "total_return": 0.1,
                "max_drawdown": -0.03,
                "number_of_trades": 5,
            },
            ranking_position=1,
            screening_status="passed",
        )
    service.persist_run_manifest(service.build_run_manifest("review_context_target"))
    from persistence.evidence_service import ValidationEvidenceArtifactService

    source_lock_artifact_id = _source_lock_artifact(
        service,
        artifact_root,
        run_id="review_context_target",
    )
    ValidationEvidenceArtifactService(service).persist_review_context(
        target_run_id="review_context_target",
        source_lock_run_id="review_context_target",
        source_lock_artifact_id=source_lock_artifact_id,
        walk_forward_run_id="wf-run",
        monte_carlo_run_id="mc-run",
        robustness_run_id="robust-run",
        protected_data_state="gated",
        artifact_root=artifact_root,
        created_at="2026-01-01T00:00:00+00:00",
    )
    service.close()
    summary_service = _DashboardRunService(
        initial_runs=(
            _DashboardRunService()._summary(
                "review_context_target",
                source.configuration_id,
                "succeeded",
            ),
        )
    )
    return (
        database,
        artifact_root,
        summary_service,
        RunDetailDashboardAdapter(database=database, artifact_root=artifact_root),
    )


def _reproduction_configuration(tmp_path: Path) -> tuple[Path, str]:
    database = tmp_path / "state" / "reproduction.sqlite3"
    service = PersistenceService(database)
    try:
        strategy = service.register_strategy(
            strategy_id="reproduction_strategy",
            strategy_version="1.0.0",
            display_name="Reproduction Strategy",
            description="Dashboard reproduction fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="reproduction_fixture",
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                market_data={"provider": "fixture", "symbol": "SPY", "interval": "1d"},
                parameters={"fixture": True},
                execution={"kind": "prefect_fixture"},
                ranking={"columns": ("deterministic_value",), "ascending": (False,)},
                screening={"kind": "none"},
            )
        )
        return database, configuration.configuration_id
    finally:
        service.close()


def _attach_reproduction_lineage(
    database: Path,
    artifact_root: Path,
    *,
    run_id: str,
    configuration_id: str,
) -> None:
    service = PersistenceService(database)
    try:
        location = f"artifacts/{run_id}/run-summary.json"
        content = b'{"status":"succeeded","deterministic_value":1729}'
        target = artifact_root / location
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        with transaction(service.connection):
            service.results.set_data_provenance(
                DataProvenanceRecord(
                    run_id=run_id,
                    provider="fixture",
                    provider_implementation="dashboard-reproduction-test",
                    symbol="SPY",
                    interval="1d",
                    timezone="America/New_York",
                    requested_coverage="2024-01-01/2024-01-31",
                    actual_coverage="2024-01-01/2024-01-31",
                    adjusted=True,
                    row_count=21,
                    cache_action="fixture",
                    validation_summary_json=canonical_json({"status": "valid"}),
                    manifest_reference="data/manifests/reproduction.json",
                    checksum="dataset-reproduction",
                )
            )
            service.results.set_execution_assumptions(
                ExecutionAssumptionsRecord(
                    run_id=run_id,
                    assumptions_json=canonical_json({"kind": "prefect_fixture"}),
                )
            )
        service.register_artifact(
            run_id=run_id,
            artifact_type=ArtifactType.RUN_SUMMARY,
            logical_name="run-summary",
            media_type="application/json",
            format="json",
            location=location,
            content=content,
        )
        service.persist_run_manifest(service.build_run_manifest(run_id))
        _ = configuration_id
    finally:
        service.close()


def _reproduction_launcher(artifact_root: Path):
    def launch(**kwargs):
        kwargs.pop("attempt_marker_path", None)
        result = deterministic_fixture_body(
            **kwargs,
            prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
            prefect_api_url="http://127.0.0.1:4200/api",
        )
        _attach_reproduction_lineage(
            Path(kwargs["database_path"]),
            artifact_root,
            run_id=kwargs["quant_factory_run_id"],
            configuration_id=kwargs["configuration_id"],
        )
        return result

    return launch


def _reproduction_service(tmp_path: Path) -> tuple[Path, Path, FixtureRunService, str]:
    database, configuration_id = _reproduction_configuration(tmp_path)
    artifact_root = tmp_path / "artifact-root"
    service = FixtureRunService(
        database=database,
        fixture_launcher=_reproduction_launcher(artifact_root),
    )
    service.launch_fixture(
        configuration_id=configuration_id,
        run_id="source_reproduction_run",
    )
    return database, artifact_root, service, configuration_id


def test_dashboard_uses_frozen_durable_reproduction_service_seam(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, artifact_root, service, configuration_id = _reproduction_service(tmp_path)
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        database,
        run_service=service,
        run_detail_adapter=RunDetailDashboardAdapter(
            database=database,
            artifact_root=artifact_root,
        ),
    )
    reproduce = _callback_function(app, "reproduction-message")

    _, message, class_name, *_ = reproduce(
        1,
        "source_reproduction_run",
    )
    rendered_message = str(message)

    assert class_name == "reproduction-message"
    assert "Submission: Acknowledged" in rendered_message
    assert "Run status: Succeeded" in rendered_message

    persistence = PersistenceService(database)
    try:
        source = persistence.runs.get("source_reproduction_run")
        reproduced = [
            run
            for run in persistence.runs.list()
            if run.run_id != "source_reproduction_run"
        ]
        assert source is not None
        assert source.configuration_id == configuration_id
        assert len(reproduced) == 1
        assert reproduced[0].configuration_id == configuration_id
    finally:
        persistence.close()

def test_dashboard_reproduction_fails_closed_for_invalid_lineage_or_artifacts(
    tmp_path: Path,
) -> None:
    database, artifact_root, service, _ = _reproduction_service(tmp_path)
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        database,
        run_service=service,
        run_detail_adapter=RunDetailDashboardAdapter(
            database=database,
            artifact_root=artifact_root,
        ),
    )
    reproduce = _callback_function(app, "reproduction-message")

    (artifact_root / "artifacts/source_reproduction_run/run-summary.json").write_text(
        '{"status":"corrupt"}',
        encoding="utf-8",
    )

    _, message, class_name, *_ = reproduce(
        1,
        "source_reproduction_run",
    )
    assert class_name == "reproduction-message error-state"
    assert "Run reproduction did not start" in str(message)
    assert "invalid reproduction artifacts" in str(message)

    persistence = PersistenceService(database)
    try:
        assert len(persistence.runs.list()) == 1
        persistence.connection.execute(
            "UPDATE run_manifests SET manifest_json=? WHERE run_id=?",
            ("{not-json", "source_reproduction_run"),
        )
        persistence.connection.commit()
    finally:
        persistence.close()

    _, message, class_name, *_ = reproduce(1, "source_reproduction_run")
    assert class_name == "reproduction-message error-state"
    assert "Run reproduction did not start" in str(message)


def test_dashboard_run_comparison_renders_equal_changed_and_missing_fields(
    tmp_path: Path,
) -> None:
    database = _comparison_database(tmp_path)
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        database,
        run_service=_DashboardRunService(initial_runs=_comparison_run_summaries()),
    )
    compare = _callback_function(app, "run-comparison-output")

    panel, class_name = compare(
        0,
        "/research/compare-backtests",
        "?run_id=compare_run_a&run_id=compare_run_b",
    )
    rendered = str(panel)

    assert class_name == "run-comparison-output"
    assert "Can these tests be compared?" in rendered
    assert "compare_run_a" in rendered
    assert "compare_run_b" in rendered
    assert "comparison-row-equal" in rendered
    assert "comparison-row-changed" in rendered
    assert "comparison-row-missing" in rendered
    assert "Execution and costs" in rendered
    assert "0.0005" in rendered
    assert "0.001" in rendered
    assert "Parameters" in rendered
    assert "10" in _component_text(panel)
    assert "20" in _component_text(panel)
    assert "Evidence" in rendered
    assert "Unavailable" in rendered


def test_dashboard_find_compare_mounts_supplied_full_history_without_default_selection() -> None:
    service = _DashboardRunService()
    failed = service._summary("failed_recent", "a" * 64, "failed")
    succeeded_a = service._summary("succeeded_a", "b" * 64, "succeeded")
    succeeded_b = service._summary("succeeded_b", "c" * 64, "succeeded")
    page = page_for_path(
        "/research/compare-backtests",
        DashboardContext(pd.DataFrame([_ranked_row()]), _data(), _audit(_data())),
        recent_runs=(failed, succeeded_a, succeeded_b),
        history_rows=(
            {"run_id": "failed_recent"},
            {"run_id": "succeeded_a"},
            {"run_id": "succeeded_b"},
        ),
    )

    rendered = str(page)
    assert "spym_rsi_mean_reversion_fixture" not in rendered
    assert "failed_recent" in rendered
    assert "succeeded_a" in rendered
    assert "selectedRows=[]" in rendered


def test_dashboard_comparison_read_model_follows_selection_and_refresh(
    tmp_path: Path,
) -> None:
    service = _DashboardRunService(initial_runs=_comparison_run_summaries())
    service._runs.append(service._summary("compare_run_c", "c" * 64, "succeeded"))
    app = create_app(
        DashboardContext(pd.DataFrame([_ranked_row()]), _data(), _audit(_data())),
        _comparison_database(tmp_path),
        run_service=service,
    )
    compare = _callback_function(app, "run-comparison-output")

    rendered_a = str(
        compare(
            0,
            "/research/compare-backtests",
            "?run_id=compare_run_a",
        )[0]
    )
    rendered_b = str(
        compare(
            1,
            "/research/compare-backtests",
            "?run_id=compare_run_b&run_id=compare_run_c",
        )[0]
    )

    assert "compare_run_a" in rendered_a
    assert "compare_run_b" not in rendered_a
    assert "compare_run_b" in rendered_b
    assert "compare_run_c" in rendered_b
    assert "compare_run_a" not in rendered_b


def test_dashboard_run_comparison_fails_closed_for_bad_selection_or_data(
    tmp_path: Path,
) -> None:
    database = _comparison_database(tmp_path)
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, database)
    compare = _callback_function(app, "run-comparison-output")

    invalid, invalid_class = compare(
        0,
        "/research/compare-backtests",
        "?run_id=compare_run_a",
    )
    assert invalid_class == "run-comparison-output"
    assert "requires two to four persisted run identities" in str(invalid)
    missing, missing_class = compare(
        0,
        "/research/compare-backtests",
        "?run_id=compare_run_a&run_id=missing-run",
    )
    assert missing_class == "run-comparison-output"
    assert "missing-run" in str(missing)
    assert "requested persisted runs are unavailable" in str(missing)

    service = PersistenceService(database)
    try:
        with transaction(service.connection):
            service.connection.execute(
                "UPDATE execution_assumptions SET assumptions_json=? WHERE run_id=?",
                ("not-json", "compare_run_b"),
            )
    finally:
        service.close()

    failure, failure_class = compare(
        0,
        "/research/compare-backtests",
        "?run_id=compare_run_a&run_id=compare_run_b",
    )
    assert failure_class == "run-comparison-output"
    assert "invalid persisted evidence" in str(failure)
    assert "persisted execution assumptions" in str(failure)


def test_dashboard_run_comparison_survives_dashboard_recreation(
    tmp_path: Path,
) -> None:
    database = _comparison_database(tmp_path)
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    first = create_app(context, database)
    second = create_app(context, database)

    first_panel, first_class = _callback_function(first, "run-comparison-output")(
        0,
        "/research/compare-backtests",
        "?run_id=compare_run_a&run_id=compare_run_b",
    )
    second_panel, second_class = _callback_function(second, "run-comparison-output")(
        0,
        "/research/compare-backtests",
        "?run_id=compare_run_a&run_id=compare_run_b",
    )
    first_rendered = str(first_panel)
    second_rendered = str(second_panel)

    assert first_class == "run-comparison-output"
    assert second_class == "run-comparison-output"
    assert "compare_run_a" in first_rendered
    assert "compare_run_b" in second_rendered
    assert "comparison-row-changed" in first_rendered
    assert "comparison-row-changed" in second_rendered


def test_dashboard_run_comparison_uses_callback_local_sqlite_connection(
    tmp_path: Path,
) -> None:
    database = _comparison_database(tmp_path)
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(context, database)
    compare = _callback_function(app, "run-comparison-output")
    result: list[object] = []
    errors: list[BaseException] = []

    def invoke_callback() -> None:
        try:
            result.append(
                compare(
                    0,
                    "/research/compare-backtests",
                    "?run_id=compare_run_a&run_id=compare_run_b",
                )
            )
        except BaseException as exc:  # pragma: no cover - assertion below owns reporting
            errors.append(exc)

    callback_thread = threading.Thread(target=invoke_callback)
    callback_thread.start()
    callback_thread.join(timeout=5)

    assert not callback_thread.is_alive()
    assert errors == []
    assert len(result) == 1
    panel, class_name = result[0]
    assert class_name == "run-comparison-output"
    assert "Can these tests be compared?" in str(panel)
    assert "SQLite objects created in a thread" not in str(result[0])


def test_dashboard_launches_selected_saved_configuration(tmp_path: Path, monkeypatch) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    detail_adapter = _DashboardRunDetailAdapter()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=detail_adapter,
    )

    launch = _callback_function(app, "launch-message")
    _, content, class_name, context_children, context_class, *_ = launch(
        1,
        configuration.configuration_id,
    )

    assert service.configuration_ids == [configuration.configuration_id]
    assert class_name == "save-message"
    rendered = str(content)
    assert "run_dashboard_fixture" in rendered
    assert "Succeeded" in rendered
    assert "prefect-run_dashboard_fixture" in rendered
    assert "Succeeded" in _component_text(html.Div(context_children))
    assert "Unavailable" in _component_text(html.Div(context_children))
    assert context_class == "operator-context"


def test_durable_run_test_replays_rapid_duplicate_and_refresh_without_relaunch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    app = create_app(review_database=tmp_path / "durable.sqlite3", run_service=service)
    launch = _callback_function(app, "launch-message")
    prepared = {
        "prepared": {
            "idempotency_key": "launch_00000000000000000000000000000001",
            "operation": "run_test",
            "configuration_id": configuration.configuration_id,
            "source_run_id": None,
        },
        "submitted": None,
    }

    first = launch(1, configuration.configuration_id, prepared, "/research/run-test")
    submitted = first[0]
    duplicate = launch(
        1,
        configuration.configuration_id,
        json.loads(json.dumps(prepared)),
        "/research/run-test",
    )
    refreshed = launch(
        0,
        configuration.configuration_id,
        submitted,
        "/research/run-test",
    )

    assert len(service.durable_requests) == 1
    assert submitted["submitted"]["idempotency_key"] == prepared["prepared"]["idempotency_key"]
    assert duplicate[0]["submitted"]["idempotency_key"] == submitted["submitted"]["idempotency_key"]
    assert refreshed[0]["submitted"]["idempotency_key"] == submitted["submitted"]["idempotency_key"]
    assert "run_dashboard_fixture" in str(refreshed[1])


def test_submitted_run_remains_bound_while_new_selection_gets_new_ticket(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first_configuration = _saved_configuration()
    second_configuration = replace(
        first_configuration,
        configuration_id="b" * 64,
        config_hash="b" * 64,
        experiment_id="second_fixture_selection",
    )
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (first_configuration, second_configuration),
    )
    service = _DashboardRunService(
        initial_runs=(),
        launch_run_ids=["run_config_a", "run_config_b"],
    )
    launch = _callback_function(
        create_app(
            review_database=tmp_path / "selection-change.sqlite3",
            run_service=service,
        ),
        "launch-message",
    )

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "launch-run",
    )
    first = launch(
        1,
        first_configuration.configuration_id,
        None,
        "/research/run-test",
    )
    first_submitted = dict(first[0]["submitted"])
    first_submission = service.research_launch_service.get(
        first_submitted["idempotency_key"]
    )
    assert first_submission is not None

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-configuration-state",
    )
    changed = launch(
        1,
        second_configuration.configuration_id,
        first[0],
        "/research/run-test",
    )

    assert changed[0]["submitted"] == first_submitted
    assert changed[0]["prepared"]["configuration_id"] == (
        second_configuration.configuration_id
    )
    assert changed[0]["prepared"]["idempotency_key"] != (
        first_submitted["idempotency_key"]
    )
    assert changed[5] is False
    assert "Ready to create one durable run ticket" in str(changed[1])
    assert len(service.durable_requests) == 1

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "launch-run",
    )
    second = launch(
        2,
        second_configuration.configuration_id,
        changed[0],
        "/research/run-test",
    )

    assert len(service.durable_requests) == 2
    assert second[0]["submitted"]["configuration_id"] == (
        second_configuration.configuration_id
    )
    assert second[0]["submitted"]["idempotency_key"] != (
        first_submitted["idempotency_key"]
    )
    assert service.research_launch_service.get(
        first_submitted["idempotency_key"]
    ) == first_submission
    assert service.get_run(first_submission.run_id).configuration_id == (
        first_configuration.configuration_id
    )


def test_passive_browser_session_hydration_prepares_distinct_keys_before_enable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    launch = _callback_function(
        create_app(
            review_database=tmp_path / "sessions.sqlite3",
            run_service=_DashboardRunService(),
        ),
        "launch-message",
    )

    first_session = launch(0, configuration.configuration_id, None, "/research/run-test")
    second_session = launch(0, configuration.configuration_id, None, "/research/run-test")

    assert first_session[0]["prepared"]["idempotency_key"] != second_session[0]["prepared"]["idempotency_key"]
    assert first_session[5] is False
    assert second_session[5] is False


def test_durable_run_test_reopens_same_ticket_after_application_restart(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, configuration_id = _reproduction_configuration(tmp_path)
    configuration = replace(
        _saved_configuration(),
        configuration_id=configuration_id,
        config_hash=configuration_id,
        strategy_id="reproduction_strategy",
        strategy_name="Reproduction Strategy",
    )
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    invocations: list[str] = []
    first_service = _PersistedDashboardRunService(database, invocations)
    first_app = create_app(review_database=database, run_service=first_service)
    first_launch = _callback_function(first_app, "launch-message")
    first = first_launch(
        1,
        configuration.configuration_id,
        None,
        "/research/run-test",
    )

    restarted_service = _PersistedDashboardRunService(database, invocations)
    restarted_app = create_app(review_database=database, run_service=restarted_service)
    reopen = _callback_function(restarted_app, "launch-message")
    reopened = reopen(
        0,
        configuration.configuration_id,
        first[0],
        "/research/run-test",
    )

    assert len(invocations) == 1
    assert reopened[0]["submitted"] == first[0]["submitted"]
    assert reopened[0]["prepared"] == first[0]["prepared"]
    assert "Submission: Acknowledged" in str(reopened[1])

    rerun = reopen(
        1,
        configuration.configuration_id,
        reopened[0],
        "/research/run-test",
    )
    assert len(invocations) == 2
    assert rerun[0]["submitted"]["idempotency_key"] == reopened[0]["prepared"]["idempotency_key"]


def test_durable_run_test_two_tabs_share_one_persisted_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, configuration_id = _reproduction_configuration(tmp_path)
    configuration = replace(
        _saved_configuration(),
        configuration_id=configuration_id,
        config_hash=configuration_id,
        strategy_id="reproduction_strategy",
        strategy_name="Reproduction Strategy",
    )
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    invocations: list[str] = []
    tab_a_service = _PersistedDashboardRunService(database, invocations)
    tab_a = _callback_function(
        create_app(review_database=database, run_service=tab_a_service),
        "launch-message",
    )
    prepared = tab_a(0, configuration_id, None, "/research/run-test")[0]
    tab_b_copy = json.loads(json.dumps(prepared))

    first = tab_a(1, configuration_id, prepared, "/research/run-test")
    tab_b_service = _PersistedDashboardRunService(database, invocations)
    tab_b = _callback_function(
        create_app(review_database=database, run_service=tab_b_service),
        "launch-message",
    )
    replay = tab_b(1, configuration_id, tab_b_copy, "/research/run-test")

    assert len(invocations) == 1
    assert replay[0]["submitted"] == first[0]["submitted"]
    assert _component_text(replay[1]) == _component_text(first[1])


def test_durable_persisted_operation_mismatch_fails_without_second_invocation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, configuration_id = _reproduction_configuration(tmp_path)
    configuration = replace(
        _saved_configuration(),
        configuration_id=configuration_id,
        config_hash=configuration_id,
        strategy_id="reproduction_strategy",
        strategy_name="Reproduction Strategy",
    )
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    invocations: list[str] = []
    first_service = _PersistedDashboardRunService(database, invocations)
    app = create_app(review_database=database, run_service=first_service)
    launch = _callback_function(app, "launch-message")
    launched = launch(1, configuration_id, None, "/research/run-test")
    source_run_id = first_service.research_launch_service.get(
        launched[0]["submitted"]["idempotency_key"]
    ).run_id

    second_service = _PersistedDashboardRunService(database, invocations)
    historical = _callback_function(
        create_app(review_database=database, run_service=second_service),
        "historical-launch-message",
    )
    mismatched_store = {
        "prepared": {
            "idempotency_key": launched[0]["submitted"]["idempotency_key"],
            "operation": "historical_relaunch",
            "configuration_id": configuration_id,
            "source_run_id": source_run_id,
        },
        "submitted": None,
    }
    result = historical(
        1,
        source_run_id,
        mismatched_store,
        "/research/backtest-results",
    )

    assert len(invocations) == 1
    assert "different operation or selection" in _component_text(result[1])
    assert result[3] is True


def test_durable_run_test_key_mismatch_fails_without_new_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first_configuration = _saved_configuration()
    second_configuration = replace(
        first_configuration,
        configuration_id="b" * 64,
        config_hash="c" * 64,
    )
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (first_configuration, second_configuration),
    )
    service = _DashboardRunService()
    app = create_app(review_database=tmp_path / "mismatch.sqlite3", run_service=service)
    launch = _callback_function(app, "launch-message")
    first = launch(1, first_configuration.configuration_id, None, "/research/run-test")
    key = first[0]["submitted"]["idempotency_key"]
    mismatched = {
        "prepared": {
            "idempotency_key": key,
            "operation": "run_test",
            "configuration_id": second_configuration.configuration_id,
            "source_run_id": None,
        },
        "submitted": None,
    }

    result = launch(
        2,
        second_configuration.configuration_id,
        mismatched,
        "/research/run-test",
    )

    assert len(service.durable_requests) == 1
    assert "Run ticket conflict" in _component_text(result[1])
    assert result[5] is True


def test_unknown_submission_disables_retry_and_inactive_route_never_mutates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(run_status="created")
    app = create_app(review_database=tmp_path / "unknown.sqlite3", run_service=service)
    launch = _callback_function(app, "launch-message")
    first = launch(1, configuration.configuration_id, None, "/research/run-test")
    key = first[0]["submitted"]["idempotency_key"]
    service.research_launch_service.by_key[key] = replace(
        service.research_launch_service.by_key[key],
        state=ResearchSubmissionState.SUBMISSION_UNKNOWN,
        unknown_at="2026-07-13T12:00:02Z",
        error_summary="Acknowledgement could not be confirmed.",
    )

    unknown = launch(2, configuration.configuration_id, first[0], "/research/run-test")
    assert len(service.durable_requests) == 1
    assert unknown[5] is True
    assert unknown[7] == "Submission unknown"
    assert "Do not retry" in str(unknown[1])

    with pytest.raises(PreventUpdate):
        launch(3, configuration.configuration_id, first[0], "/research/backtest-results")
    assert len(service.durable_requests) == 1


def test_malformed_submitted_identity_fails_closed_without_callback_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    launch = _callback_function(
        create_app(review_database=tmp_path / "malformed.sqlite3", run_service=service),
        "launch-message",
    )

    result = launch(
        1,
        configuration.configuration_id,
        {"prepared": None, "submitted": {"operation": "run_test"}},
        "/research/run-test",
    )

    assert service.durable_requests == []
    assert result[5] is True
    assert "malformed" in _component_text(result[1]).lower()


def test_preclaim_contention_retains_same_prepared_key_for_all_mutations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(
        error=ResearchLaunchContentionError("database is busy"),
    )
    app = create_app(review_database=tmp_path / "contention.sqlite3", run_service=service)
    source_run_id = service.recent_runs()[0].run_id

    callbacks = (
        (
            _callback_function(app, "launch-message"),
            (1, configuration.configuration_id, None, "/research/run-test"),
        ),
        (
            _callback_function(app, "historical-launch-message"),
            (1, source_run_id, None, "/research/backtest-results"),
        ),
        (
            _callback_function(app, "reproduction-message"),
            (1, source_run_id, None, "/research/backtest-results"),
        ),
    )
    for callback, arguments in callbacks:
        result = callback(*arguments)
        assert result[0]["submitted"] is None
        assert result[0]["prepared"]["idempotency_key"].startswith("launch_")


def test_persisted_submission_remains_visible_after_configuration_deactivation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    first_app = create_app(review_database=tmp_path / "retired.sqlite3", run_service=service)
    launch = _callback_function(first_app, "launch-message")
    launched = launch(1, configuration.configuration_id, None, "/research/run-test")

    inactive = replace(configuration, active=False, lifecycle="retired")
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (inactive,),
    )
    reopened = _callback_function(
        create_app(review_database=tmp_path / "retired.sqlite3", run_service=service),
        "launch-message",
    )(0, configuration.configuration_id, launched[0], "/research/run-test")

    assert "Submission: Acknowledged" in _component_text(reopened[1])
    assert "Run status: Succeeded" in _component_text(reopened[1])
    assert reopened[5] is True


def test_partial_durable_service_signature_keeps_launcher_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )

    class PartialService(_DashboardRunService):
        def launch_fixture(self, *, configuration_id: str, idempotency_key: str):
            raise AssertionError("partial durable seam must not be invoked")

    launch = _callback_function(
        create_app(
            review_database=tmp_path / "partial.sqlite3",
            run_service=PartialService(),
        ),
        "launch-message",
    )
    result = launch(1, configuration.configuration_id, None, "/research/run-test")

    assert result[5] is True
    assert "legacy launcher is disabled" in _component_text(result[1])


def test_durable_launch_outputs_have_one_callback_owner(tmp_path: Path, monkeypatch) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    app = create_app(
        review_database=tmp_path / "owners.sqlite3",
        run_service=_DashboardRunService(),
    )
    targets = {
        "run-test-launch-state.data",
        "launch-run.disabled",
        "launch-message.children",
        "historical-launch-state.data",
        "launch-selected-run-configuration.disabled",
        "historical-launch-message.children",
        "reproduction-launch-state.data",
        "reproduce-selected-run.disabled",
        "reproduction-message.children",
    }
    counts = {target: 0 for target in targets}
    for entry in app.callback_map.values():
        outputs = entry["output"] if isinstance(entry["output"], list) else [entry["output"]]
        for output in outputs:
            identity = f"{output.component_id}.{output.component_property}"
            if identity in counts:
                counts[identity] += 1

    assert counts == {target: 1 for target in targets}


def test_dashboard_reports_launch_failure_without_creating_ui_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(error=ValueError("duplicate run"))
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    launch = _callback_function(app, "launch-message")
    _, content, class_name, context_children, context_class, *_ = launch(
        1,
        configuration.configuration_id,
    )

    rendered = _component_text(content)
    assert "Run launch did not start." in rendered
    assert "duplicate run" in rendered
    assert class_name == "save-message error-state"
    assert "No run selected" in _component_text(html.Div(context_children))
    assert context_class == "operator-context operator-context-empty"


def test_dashboard_launches_new_run_from_selected_historical_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    old_run = RunSummary(
        run_id="old_terminal_run",
        configuration_id=configuration.configuration_id,
        strategy_id="prefect_fixture_strategy",
        strategy_version="1.0.0",
        stage="fixture",
        status="failed",
        created_at="2026-07-13T11:00:00Z",
        started_at="2026-07-13T11:00:01Z",
        completed_at="2026-07-13T11:00:02Z",
        error_summary="Historical fixture failure.",
        prefect_flow_run_id="prefect-old-terminal-run",
        prefect_api_url=None,
        attempt_count=1,
    )
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(
        initial_runs=(old_run,),
        launch_run_ids=["new_historical_run"],
    )
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    launch = _callback_function(app, "historical-launch-message")
    _, content, class_name, *_ = launch(1, "old_terminal_run")

    assert service.run_detail_queries[0] == "old_terminal_run"
    assert "new_historical_run" in service.run_detail_queries
    assert service.configuration_ids == [configuration.configuration_id]
    assert service.configuration_ids[0] == old_run.configuration_id
    assert service.recent_runs()[0].run_id == "new_historical_run"
    assert service.recent_runs()[1].run_id == "old_terminal_run"
    assert "old_terminal_run" not in str(content)
    assert "new_historical_run" in str(content)
    assert "prefect-new_historical_run" in str(content)
    assert class_name == "historical-launch-message"
    request = service.durable_requests[0]
    assert request["operation"] == ResearchLaunchOperation.HISTORICAL_RELAUNCH
    assert request["source_run_id"] == "old_terminal_run"
    assert request["source_lineage"] is None


def test_dashboard_reproduction_uses_its_own_durable_key_and_source_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    source = _DashboardRunService()._summary(
        "source_succeeded_run",
        configuration.configuration_id,
        "succeeded",
    )
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(
        initial_runs=(source,),
        launch_run_ids=["reproduced_durable_run"],
    )
    app = create_app(review_database=tmp_path / "reproduce.sqlite3", run_service=service)
    reproduce = _callback_function(app, "reproduction-message")

    store, message, class_name, *_ = reproduce(
        1,
        source.run_id,
        None,
        "/research/backtest-results",
    )

    assert store["submitted"]["operation"] == "reproduction"
    assert store["submitted"]["source_run_id"] == source.run_id
    assert "reproduced_durable_run" in str(message)
    assert class_name == "reproduction-message"
    assert service.durable_requests == [
        {
            "idempotency_key": store["submitted"]["idempotency_key"],
            "operation": ResearchLaunchOperation.REPRODUCTION,
            "source_run_id": source.run_id,
            "source_lineage": None,
        }
    ]


def test_dashboard_rejects_historical_launch_when_configuration_unlaunchable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = replace(_saved_configuration(), active=False)
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    detail_adapter = _DashboardRunDetailAdapter()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=detail_adapter,
    )

    launch = _callback_function(app, "historical-launch-message")
    _, message, class_name, *_ = launch(1, "run_dashboard_fixture")

    assert service.configuration_ids == []
    rendered = _component_text(message)
    assert "Select a launchable persisted run" in rendered
    assert class_name == "historical-launch-message"


def test_dashboard_reports_historical_launch_failures_readably(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(error=RunServiceError("configuration missing"))
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    launch = _callback_function(app, "historical-launch-message")
    _, message, class_name, *_ = launch(1, "run_dashboard_fixture")

    assert service.configuration_ids == [configuration.configuration_id]
    rendered = _component_text(message)
    assert "New run launch did not start." in rendered
    assert "configuration missing" in rendered
    assert class_name == "historical-launch-message error-state"


def test_dashboard_reports_missing_historical_run_before_launch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    launch = _callback_function(app, "historical-launch-message")
    _, message, class_name, *_ = launch(1, "missing-run")

    assert service.configuration_ids == []
    rendered = _component_text(message)
    assert "Select a launchable persisted run" in rendered
    assert class_name == "historical-launch-message"


def test_dynamic_detail_actions_ignore_initial_lifecycle_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    launch = _callback_function(app, "historical-launch-message")
    reproduce = _callback_function(app, "reproduction-message")
    cancel = _callback_function(app, "cancellation-message")

    assert launch(None, "run_dashboard_fixture")[3] is False
    assert launch(0, "run_dashboard_fixture")[3] is False
    before = len(service.durable_requests)
    assert reproduce(None, "run_dashboard_fixture")[3] is False
    assert reproduce(0, "run_dashboard_fixture")[3] is False
    assert len(service.durable_requests) == before
    assert cancel(None, "run_dashboard_fixture") == (no_update, no_update)
    assert cancel(0, "run_dashboard_fixture") == (no_update, no_update)


def test_runs_page_renders_recent_runs_and_operator_events() -> None:
    service = _DashboardRunService()
    page = _runs_page(
        (_saved_configuration(),),
        recent_runs=service.recent_runs(),
        recent_events=service.recent_events(),
    )

    recent_runs = next(
        child
        for child in _walk_components(page)
        if getattr(child, "id", None) == "recent-runs-monitor"
    )
    recent_events = next(
        child
        for child in _walk_components(page)
        if getattr(child, "id", None) == "recent-events-monitor"
    )

    assert recent_runs.id == "recent-runs-monitor"
    assert recent_events.id == "recent-events-monitor"
    assert "run_dashboard_fixture" in str(recent_runs.children)
    assert "prefect-run_dashboard_fixture" in str(recent_runs.children)
    assert "Run completed successfully." in str(recent_events.children)


def test_runs_page_groups_workflows_and_exposes_readable_recovery_input() -> None:
    page = _runs_page((_saved_configuration(),))
    groups = [
        component.className
        for component in page.children
        if "workflow-group" in str(getattr(component, "className", ""))
    ]
    recovery_input = next(
        component
        for component in _walk_components(page)
        if getattr(component, "id", None) == "stale-before-input"
    )

    assert groups == [
        "backtest-detail-workspace workflow-group-results",
        "workflow-group workflow-group-analysis",
        "workflow-group workflow-group-operations",
    ]
    assert recovery_input.className == "stale-before-input"
    assert recovery_input.placeholder == "2026-07-13T12:00:00Z"


def test_run_monitor_refreshes_from_service(tmp_path: Path, monkeypatch) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    refresh = _callback_function(app, "recent-runs-monitor")
    service.run_queries = 0
    service.event_queries = 0
    runs_panel, events_panel = refresh(
        1,
        0,
        0,
        0,
        0,
        0,
    )

    assert service.run_queries == 1
    assert service.event_queries == 1
    assert "run_dashboard_fixture" in str(runs_panel)
    assert "Run completed successfully." in str(events_panel)

    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    options, selected = refresh_selectors(
        0,
        0,
        0,
        0,
        "run_dashboard_fixture",
        "run_dashboard_fixture",
        [],
    )
    refresh_comparison_rows = _callback_function(app, "find-compare-grid.rowData")
    comparison_rows = refresh_comparison_rows(
        0,
        "/research/compare-backtests",
        None,
    )

    assert options == [
        {
            "label": "Infrastructure Fixture · Fixture backtest · Succeeded",
            "value": "run_dashboard_fixture",
        }
    ]
    assert [row["run_id"] for row in comparison_rows] == ["run_dashboard_fixture"]
    assert selected is no_update


def test_run_history_grid_mounts_full_history_with_operator_columns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(
        initial_runs=tuple(
            _DashboardRunService()._summary(
                f"history_grid_run_{index:02d}",
                configuration.configuration_id,
                "succeeded",
            )
            for index in range(21)
        )
    )
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    grid = next(
        component
        for component in _walk_components(_resolved_layout(app))
        if getattr(component, "id", None) == "run-history-grid"
    )
    columns = {column["field"]: column for column in grid.columnDefs}

    assert len(grid.rowData) == 21
    assert grid.rowData[-1]["run_id"] == "history_grid_run_20"
    assert grid.rowData[0]["stage"] == "Fixture backtest"
    assert grid.rowData[0]["status"] == "Succeeded"
    assert columns["run_id"]["hide"] is True
    assert columns["instrument"]["filter"] == "agTextColumnFilter"
    assert columns["review"]["filter"] == "agTextColumnFilter"
    assert columns["evidence"]["filter"] == "agTextColumnFilter"
    assert columns["total_return"]["filter"] == "agNumberColumnFilter"
    assert columns["annualized_return"]["type"] == "numericColumn"
    assert "* 100" in columns["total_return"]["valueFormatter"]["function"]
    assert "toFixed(2)" in columns["sharpe_ratio"]["valueFormatter"]["function"]
    assert "Math.round" in columns["number_of_trades"]["valueFormatter"]["function"]
    assert grid.getRowId == "params.data.run_id"
    assert grid.selectedRows == []


def test_manual_run_refresh_does_not_reset_stable_selection_or_detail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    monkeypatch.setattr("dashboard.callbacks.backtest_results._callback_triggered_id", lambda: "refresh-runs")

    refresh = _callback_function(app, "recent-runs-monitor")
    runs_panel, events_panel = refresh(
        2,
        0,
        0,
        0,
        0,
        0,
    )

    assert "run_dashboard_fixture" in str(runs_panel)
    assert "Run completed successfully." in str(events_panel)
    selector_output = (
        "..selected-run-selector.options...selected-run-selector.value.."
    )
    selector_inputs = {
        (item["id"], item["property"])
        for item in app.callback_map[selector_output]["inputs"]
    }
    assert ("refresh-runs", "n_clicks") in selector_inputs
    assert "run-monitor-interval" not in str(_resolved_layout(app))
    assert service.run_detail_queries == []


def test_selected_run_store_ignores_transient_empty_dropdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    preserve = _callback_function(app, "selected-run-state")

    assert (
        preserve(
            None,
            None,
            "",
            "run_dashboard_fixture",
            "/research/backtest-results",
        )
        is no_update
    )
    assert (
        preserve(
            "run_dashboard_fixture",
            None,
            "",
            None,
            "/research/backtest-results",
        )
        == "run_dashboard_fixture"
    )


def test_user_selected_spym_run_is_not_overwritten_by_delayed_selector_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    infrastructure_fixture = service._summary(
        "run_dashboard_fixture",
        "a" * 64,
        "succeeded",
    )
    spym_run = replace(
        service._summary("spym_persisted_run", "a" * 64, "succeeded"),
        strategy_id="spym_rsi_mean_reversion_fixture",
    )
    service = _DashboardRunService(
        initial_runs=(
            infrastructure_fixture,
            spym_run,
        ),
    )
    chart_detail = _selected_detail_view(
        result_rows=(
            (
                DetailField("Rank", "1"),
                DetailField("Metrics", "total_return: 0.1"),
                DetailField("Parameters", "window: 14"),
            ),
        ),
        evidence=RunEvidenceView(
            notices=(),
            metrics=(
                DetailField("Total Return", "0.10"),
                DetailField("Number Of Trades", "1"),
            ),
            trades=(
                {
                    "Entry Index": "2026-01-01T14:00:00Z",
                    "Exit Index": "2026-01-01T15:00:00Z",
                    "PnL": 12.5,
                    "Status": "Closed",
                },
            ),
            orders=(),
            equity_curve=(
                {"timestamp": "2026-01-01T14:00:00Z", "value": 10_000.0},
                {"timestamp": "2026-01-01T15:00:00Z", "value": 10_012.5},
            ),
            drawdown_curve=(
                {"timestamp": "2026-01-01T14:00:00Z", "drawdown": 0.0},
                {"timestamp": "2026-01-01T15:00:00Z", "drawdown": -0.01},
            ),
            validation=(DetailField("Validation", "passed"),),
            validation_outcome=(DetailField("Normalized status", "passed"),),
            provenance=(),
            warnings=(),
        ),
    )

    class DetailByRun:
        artifact_root = tmp_path

        def __init__(self) -> None:
            self.requests: list[str] = []

        def selected_run_detail(self, run_id: str) -> SelectedRunDetailView:
            self.requests.append(run_id)
            if run_id == "spym_persisted_run":
                return chart_detail
            return _selected_detail_view()

    detail_adapter = DetailByRun()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=detail_adapter,
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    preserve = _callback_function(app, "selected-run-state")
    inspect = _callback_function(app, "selected-run-detail")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-run-selector",
    )
    stored = preserve(
        "spym_persisted_run",
        None,
        "",
        "run_dashboard_fixture",
        "/research/backtest-results",
    )

    monkeypatch.setattr("dashboard.callbacks.backtest_results._callback_triggered_id", lambda: None)
    options, selected = refresh_selectors(
        0,
        0,
        0,
        0,
        stored,
        "spym_persisted_run",
        [],
    )
    refresh_comparison_rows = _callback_function(app, "find-compare-grid.rowData")
    comparison_rows = refresh_comparison_rows(
        0,
        "/research/compare-backtests",
        None,
    )
    panel = inspect(stored, "spym_persisted_run", 0, 0, 0, 0)
    rendered = str(panel)

    assert [option["value"] for option in options] == [
        "run_dashboard_fixture",
        "spym_persisted_run",
    ]
    assert [row["run_id"] for row in comparison_rows] == [
        option["value"] for option in options
    ]
    assert selected is no_update
    assert stored == "spym_persisted_run"
    assert service.run_detail_queries[-1] == "spym_persisted_run"
    assert detail_adapter.requests[-1] == "spym_persisted_run"
    assert "Portfolio value and buy-and-hold comparison" in rendered
    assert "Cumulative trade P&amp;L" in rendered or "Cumulative trade P&L" in rendered
    assert "Recent trades" in rendered


def test_selected_run_store_recontrols_dropdown_after_detail_render_remount(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _DashboardRunService(
        initial_runs=(
            _DashboardRunService()._summary(
                "default_run_a",
                "a" * 64,
                "succeeded",
            ),
            replace(
                _DashboardRunService()._summary(
                    "selected_run_b",
                    "a" * 64,
                    "succeeded",
                ),
                strategy_id="spym_rsi_mean_reversion_fixture",
            ),
        ),
    )
    detail_b = replace(
        _selected_detail_view(),
        evidence=RunEvidenceView(
            notices=(),
            metrics=(DetailField("Total Return", "0.01"),),
            trades=({"PnL": 1.0},),
            orders=(),
            equity_curve=({"timestamp": "2026-01-01", "value": 10_000.0},),
            drawdown_curve=({"timestamp": "2026-01-01", "drawdown": 0.0},),
            validation=(DetailField("Outcome", "passed"),),
            validation_outcome=(DetailField("Normalized status", "passed"),),
            provenance=(),
            warnings=(),
        ),
    )

    class DetailByRun:
        artifact_root = tmp_path

        def selected_run_detail(self, run_id: str) -> SelectedRunDetailView:
            if run_id == "selected_run_b":
                return detail_b
            return _selected_detail_view()

    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=DetailByRun(),
    )
    layout = _resolved_layout(app)
    mounted_selector = next(
        component
        for component in _walk_components(layout)
        if getattr(component, "id", None) == "selected-run-selector"
    )
    mounted_store = next(
        component
        for component in _walk_components(layout)
        if getattr(component, "id", None) == "selected-run-state"
    )
    assert mounted_selector.value == "default_run_a"
    assert mounted_store.data == "default_run_a"
    assert mounted_store.storage_type == "session"

    preserve = _callback_function(app, "selected-run-state")
    inspect = _callback_function(app, "selected-run-detail")
    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-run-selector",
    )
    stored = preserve(
        "selected_run_b",
        None,
        "",
        "default_run_a",
        "/research/backtest-results",
    )
    rendered = str(inspect(stored, "selected_run_b", 0, 0, 0, 0))

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-run-state",
    )
    options, selected = refresh_selectors(
        0,
        0,
        0,
        0,
        stored,
        None,
        mounted_selector.options,
    )

    assert stored == "selected_run_b"
    assert "SPYM RSI Mean Reversion Fixture" in rendered
    assert options is no_update
    assert selected == "selected_run_b"


def test_results_deep_link_wins_simultaneous_stale_selector_trigger(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    service = _DashboardRunService(
        initial_runs=(
            base_service._summary("source_run", "a" * 64, "succeeded"),
            base_service._summary("reproduced_run", "a" * 64, "succeeded"),
        ),
    )
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    preserve = _callback_function(app, "selected-run-state")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-run-selector",
    )
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_ids",
        lambda: frozenset({"selected-run-selector", "url"}),
    )

    selected = preserve(
        "reproduced_run",
        None,
        "?run_id=source_run",
        "reproduced_run",
        "/research/backtest-results",
    )

    assert selected == "source_run"


def test_explicit_selector_can_replace_deep_link_after_hydration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    service = _DashboardRunService(
        initial_runs=(
            base_service._summary("source_run", "a" * 64, "succeeded"),
            base_service._summary("layout_default", "a" * 64, "succeeded"),
        ),
    )
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    preserve = _callback_function(app, "selected-run-state")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-run-selector",
    )
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_ids",
        lambda: frozenset({"selected-run-selector"}),
    )

    selected = preserve(
        "layout_default",
        None,
        "?run_id=source_run",
        "source_run",
        "/research/backtest-results",
    )

    assert selected == "layout_default"


def test_location_hydration_keeps_valid_session_run_over_layout_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    service = _DashboardRunService(
        initial_runs=(
            base_service._summary("session_run", "a" * 64, "succeeded"),
            base_service._summary("layout_default", "a" * 64, "succeeded"),
        ),
    )
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    preserve = _callback_function(app, "selected-run-state")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "url",
    )
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_ids",
        lambda: frozenset({"url"}),
    )

    selected = preserve(
        "layout_default",
        None,
        "",
        "session_run",
        "/research/backtest-results",
    )

    assert selected is no_update


def test_initial_selector_hydration_does_not_rewrite_existing_dropdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _DashboardRunService(
        initial_runs=(
            _DashboardRunService()._summary(
                "run_dashboard_fixture",
                "a" * 64,
                "succeeded",
            ),
            replace(
                _DashboardRunService()._summary(
                    "spym_persisted_run",
                    "a" * 64,
                    "succeeded",
                ),
                strategy_id="spym_rsi_mean_reversion_fixture",
            ),
        ),
    )
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    existing_options = [
        {
            "label": "Infrastructure Fixture · Fixture backtest · Succeeded",
            "value": "run_dashboard_fixture",
        },
        {
            "label": (
                "SPYM RSI Mean Reversion Fixture · SPYM · 1m · "
                "Fixture backtest · Succeeded"
            ),
            "value": "spym_persisted_run",
        },
    ]

    monkeypatch.setattr("dashboard.callbacks.backtest_results._callback_triggered_id", lambda: None)
    options, selected = refresh_selectors(
        0,
        0,
        0,
        0,
        "run_dashboard_fixture",
        "run_dashboard_fixture",
        existing_options,
    )
    refresh_comparison_rows = _callback_function(app, "find-compare-grid.rowData")
    comparison_rows = refresh_comparison_rows(
        0,
        "/research/compare-backtests",
        None,
    )

    assert options is no_update
    assert selected is no_update
    assert [row["run_id"] for row in comparison_rows] == [
        option["value"] for option in existing_options
    ]


def test_initial_session_selection_beats_layout_default_dropdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    recent_runs = tuple(
        base_service._summary(f"recent_run_{index:02d}", "a" * 64, "succeeded")
        for index in range(20)
    )
    historical_run = replace(
        base_service._summary("spym_historical_run", "a" * 64, "succeeded"),
        strategy_id="spym_rsi_mean_reversion_fixture",
    )
    service = _DashboardRunService(initial_runs=recent_runs + (historical_run,))
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    preserve = _callback_function(app, "selected-run-state")
    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    selected_options = [
        {
            "label": f"Infrastructure Fixture · Fixture backtest · Succeeded {index}",
            "value": f"recent_run_{index:02d}",
        }
        for index in range(20)
    ]

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: None,
    )

    stored = preserve(
        "recent_run_00",
        None,
        "",
        "spym_historical_run",
        "/research/backtest-results",
    )
    options, selected = refresh_selectors(
        0,
        "Select an approved saved configuration to launch a new backtest.",
        "Select a historical run to launch its saved configuration.",
        "Select a run to reproduce it from its immutable configuration.",
        "spym_historical_run",
        "recent_run_00",
        selected_options,
    )

    assert stored is no_update
    assert selected == "spym_historical_run"
    assert [option["value"] for option in options][-1] == "spym_historical_run"
    assert "SPYM RSI Mean Reversion Fixture" in options[-1]["label"]


def test_initial_multi_input_hydration_recontrols_selector_from_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    service = _DashboardRunService(
        initial_runs=(
            base_service._summary("session_run", "a" * 64, "succeeded"),
            base_service._summary("layout_default", "a" * 64, "succeeded"),
        ),
    )
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "run-test-launch-state",
    )
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_ids",
        lambda: frozenset(
            {
                "run-test-launch-state",
                "historical-launch-state",
                "reproduction-launch-state",
                "selected-run-state",
            }
        ),
    )

    _, selected = refresh_selectors(
        0,
        None,
        None,
        None,
        "session_run",
        "layout_default",
        [],
    )

    assert selected == "session_run"


def test_initial_empty_launch_message_does_not_prefer_latest_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    recent_runs = tuple(
        base_service._summary(f"recent_run_{index:02d}", "a" * 64, "succeeded")
        for index in range(20)
    )
    historical_run = replace(
        base_service._summary("spym_historical_run", "a" * 64, "succeeded"),
        strategy_id="spym_rsi_mean_reversion_fixture",
    )
    service = _DashboardRunService(initial_runs=recent_runs + (historical_run,))
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "launch-message",
    )
    options, selected = refresh_selectors(
        0,
        "Select an approved saved configuration to launch a new backtest.",
        0,
        0,
        "spym_historical_run",
        "spym_historical_run",
        [],
    )

    assert selected is no_update
    assert [option["value"] for option in options][-1] == "spym_historical_run"


def test_completed_launch_run_outside_recent_limit_still_gets_selector_option(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    recent_runs = tuple(
        base_service._summary(f"recent_run_{index:02d}", "a" * 64, "succeeded")
        for index in range(20)
    )
    completed_run = replace(
        base_service._summary("completed_launch_run", "a" * 64, "succeeded"),
        strategy_id="spym_rsi_mean_reversion_fixture",
    )
    service = _DashboardRunService(initial_runs=recent_runs + (completed_run,))
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    key = "launch_00000000000000000000000000000499"
    service.research_launch_service.acknowledge(
        key,
        completed_run,
        operation=ResearchLaunchOperation.RUN_TEST,
        source_run_id=None,
    )
    launch_state = {
        "prepared": None,
        "submitted": {
            "idempotency_key": key,
            "operation": "run_test",
            "configuration_id": completed_run.configuration_id,
            "source_run_id": None,
        },
    }

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "run-test-launch-state",
    )
    options, selected = refresh_selectors(
        0,
        launch_state,
        0,
        0,
        "recent_run_00",
        "recent_run_00",
        [],
    )

    assert selected == "completed_launch_run"
    assert [option["value"] for option in options][-1] == "completed_launch_run"
    assert "SPYM RSI Mean Reversion Fixture" in options[-1]["label"]


def test_passive_refresh_preserves_selected_run_outside_recent_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    recent_runs = tuple(
        base_service._summary(f"recent_run_{index:02d}", "a" * 64, "succeeded")
        for index in range(20)
    )
    historical_run = replace(
        base_service._summary("spym_historical_run", "a" * 64, "succeeded"),
        strategy_id="spym_rsi_mean_reversion_fixture",
    )
    service = _DashboardRunService(initial_runs=recent_runs + (historical_run,))
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "refresh-runs",
    )
    def unexpected_portfolio_scan(*args, **kwargs):
        raise AssertionError("A valid selected run needs no portfolio scan")
    monkeypatch.setattr("dashboard.callbacks.backtest_results._preferred_backtest_id", unexpected_portfolio_scan)
    options, selected = refresh_selectors(
        1,
        0,
        0,
        0,
        "spym_historical_run",
        "spym_historical_run",
        [],
    )

    assert selected is no_update
    assert [option["value"] for option in options][-1] == "spym_historical_run"
    assert "SPYM RSI Mean Reversion Fixture" in options[-1]["label"]


def test_passive_refresh_restores_stored_run_outside_recent_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    recent_runs = tuple(
        base_service._summary(f"recent_run_{index:02d}", "a" * 64, "succeeded")
        for index in range(20)
    )
    historical_run = replace(
        base_service._summary("spym_historical_run", "a" * 64, "succeeded"),
        strategy_id="spym_rsi_mean_reversion_fixture",
    )
    service = _DashboardRunService(initial_runs=recent_runs + (historical_run,))
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "refresh-runs",
    )
    options, selected = refresh_selectors(
        1,
        0,
        0,
        0,
        "spym_historical_run",
        None,
        [],
    )

    assert selected == "spym_historical_run"
    assert [option["value"] for option in options][-1] == "spym_historical_run"


def test_history_grid_selection_recontrols_stale_dropdown_value(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    recent_runs = tuple(
        base_service._summary(f"recent_run_{index:02d}", "a" * 64, "succeeded")
        for index in range(20)
    )
    historical_run = replace(
        base_service._summary("spym_historical_run", "a" * 64, "succeeded"),
        strategy_id="spym_rsi_mean_reversion_fixture",
    )
    service = _DashboardRunService(initial_runs=recent_runs + (historical_run,))
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    preserve = _callback_function(app, "selected-run-state")
    refresh_selectors = _callback_function(app, "selected-run-selector.options")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "run-history-grid",
    )
    stored = preserve(
        "recent_run_00",
        [{"run_id": "spym_historical_run"}],
        "",
        "recent_run_00",
        "/research/backtest-results",
    )

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-run-state",
    )
    options, selected = refresh_selectors(
        1,
        0,
        0,
        0,
        stored,
        "recent_run_00",
        [],
    )

    assert stored == "spym_historical_run"
    assert selected == "spym_historical_run"
    assert [option["value"] for option in options][-1] == "spym_historical_run"


def test_missing_selected_run_outside_recent_limit_falls_back_to_preferred(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_service = _DashboardRunService()
    recent_runs = tuple(
        base_service._summary(f"recent_run_{index:02d}", "a" * 64, "succeeded")
        for index in range(20)
    )
    service = _DashboardRunService(initial_runs=recent_runs)
    data = _data()
    context = DashboardContext(pd.DataFrame([_ranked_row()]), data, _audit(data))
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "refresh-runs",
    )
    options, selected = refresh_selectors(
        1,
        0,
        0,
        0,
        "missing-run",
        "missing-run",
        [],
    )

    assert selected == "recent_run_00"
    assert "missing-run" not in [option["value"] for option in options]


def test_run_monitor_refresh_selects_new_launch_and_preserves_terminal_history(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    old_run = RunSummary(
        run_id="old_cancelled_run",
        configuration_id=configuration.configuration_id,
        strategy_id="prefect_fixture_strategy",
        strategy_version="1.0.0",
        stage="fixture",
        status="cancelled",
        created_at="2026-07-13T11:00:00Z",
        started_at="2026-07-13T11:00:01Z",
        completed_at="2026-07-13T11:00:02Z",
        error_summary="Run cancelled after fixture acknowledgement.",
        prefect_flow_run_id="prefect-old-cancelled-run",
        prefect_api_url=None,
        attempt_count=1,
    )
    service = _DashboardRunService(
        initial_runs=(old_run,),
        launch_run_ids=["new_run_from_history"],
    )
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    launch = _callback_function(app, "historical-launch-message")
    launch_state, launch_message, _, *_ = launch(1, "old_cancelled_run")
    monkeypatch.setattr("dashboard.callbacks.backtest_results._callback_triggered_id", lambda: "historical-launch-state")

    refresh = _callback_function(app, "recent-runs-monitor")
    runs_panel, _ = refresh(
        1,
        0,
        launch_message,
        0,
        0,
        0,
    )
    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    options, selected = refresh_selectors(
        0,
        0,
        launch_state,
        0,
        "old_cancelled_run",
        "old_cancelled_run",
        [],
    )

    assert selected == "new_run_from_history"
    assert [option["value"] for option in options] == [
        "new_run_from_history",
        "old_cancelled_run",
    ]
    rendered = str(runs_panel)
    assert "new_run_from_history" in rendered
    assert "old_cancelled_run" in rendered
    assert "cancelled" in rendered

    monkeypatch.setattr("dashboard.callbacks.backtest_results._callback_triggered_id", lambda: "cancel-selected-run")
    refresh(
        2,
        0,
        1,
        0,
        1,
        0,
    )
    selector_output = (
        "..selected-run-selector.options...selected-run-selector.value.."
    )
    selector_inputs = {
        (item["id"], item["property"])
        for item in app.callback_map[selector_output]["inputs"]
    }
    assert ("cancel-selected-run", "n_clicks") not in selector_inputs

    monkeypatch.setattr("dashboard.callbacks.backtest_results._callback_triggered_id", lambda: "recover-stale-runs")
    refresh(
        3,
        0,
        1,
        0,
        1,
        1,
    )
    assert ("recover-stale-runs", "n_clicks") not in selector_inputs


def test_run_monitor_refresh_selects_new_main_launch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(launch_run_ids=["new_main_launch"])
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )
    launch = _callback_function(app, "launch-message")
    launch_state, launch_message, *_ = launch(1, configuration.configuration_id)
    monkeypatch.setattr("dashboard.callbacks.backtest_results._callback_triggered_id", lambda: "run-test-launch-state")

    refresh_selectors = _callback_function(app, "selected-run-selector.options")
    options, selected = refresh_selectors(
        0,
        launch_state,
        0,
        0,
        "run_dashboard_fixture",
        "run_dashboard_fixture",
        [],
    )

    assert selected == "new_main_launch"
    assert [option["value"] for option in options][:2] == [
        "new_main_launch",
        "run_dashboard_fixture",
    ]


def test_run_detail_panel_renders_authoritative_summary_and_events() -> None:
    service = _DashboardRunService()
    run = service.recent_runs()[0]
    events = service.recent_events()

    panel = _run_detail_panel(run, events)
    rendered = str(panel)

    assert "run_dashboard_fixture" in rendered
    assert "prefect-run_dashboard_fixture" in rendered
    assert "2026-07-13T12:00:02Z" in rendered
    assert "Run completed successfully." in rendered


def test_run_detail_panel_renders_immutable_configuration_lineage_and_results() -> None:
    service = _DashboardRunService()
    detail = _selected_detail_view(
        artifacts=(
            ArtifactInventoryView(
                artifact_id=1,
                artifact_type="metrics",
                logical_name="metrics",
                schema_version="1",
                format="json",
                availability="available",
                validation_state="valid",
                checksum="sha256:abc",
                reference="artifacts/metrics.json",
                reason="validated",
                severity="success",
            ),
        ),
        result_rows=(
            (
                DetailField("Rank", "1"),
                DetailField("Metrics", "total_return: 0.1; sharpe_ratio: 1.2"),
                DetailField("Parameters", "window: 14"),
            ),
        ),
    )

    panel = _run_detail_panel(
        service.recent_runs()[0],
        service.recent_events(),
        detail=detail,
    )
    rendered = str(panel)

    assert "Strategy settings" in rendered
    assert "Selected backtest" in rendered
    assert "Validation outcome" in rendered
    assert "Strategy Settings" in rendered
    assert "Technical Details" in rendered
    assert "slice_18a_fixture" in rendered
    assert "Fixture" in rendered
    assert "window: 14" in rendered
    assert '{"' not in rendered
    assert "Research history" in rendered
    assert "abc123" in rendered
    assert "VectorBT Pro" in rendered
    assert "Not recorded" in rendered
    assert "Artifacts and validation" in rendered
    assert "artifacts/metrics.json" in rendered
    assert "sha256:abc" in rendered
    assert "Result summary" in rendered
    assert "total_return: 0.1" in rendered
    assert "does not imply profitability" in rendered


def test_run_detail_panel_renders_spym_fixture_persisted_evidence() -> None:
    service = _DashboardRunService()
    detail = _selected_detail_view(
        evidence=RunEvidenceView(
            notices=(
                "Infrastructure fixture only: this run proves factory plumbing and is not profitability evidence.",
                "SPYM is an ingestion and execution fixture here; it is not selected as the final paper or micro-live instrument.",
            ),
            metrics=(
                DetailField("Total Return", "0.000817"),
                DetailField("Number Of Trades", "366"),
            ),
            trades=(
                {
                    "Entry Index": "2025-10-31T14:05:00+00:00",
                    "Exit Index": "2025-10-31T14:39:00+00:00",
                    "PnL": 0.13,
                    "Status": "Closed",
                },
            ),
            orders=(
                {
                    "Timestamp": "2025-10-31T14:05:00+00:00",
                    "Side": "Buy",
                    "Size": 1.0,
                },
            ),
            equity_curve=(
                {"timestamp": "2025-10-31T13:30:00+00:00", "value": 10_000.0},
                {"timestamp": "2025-10-31T13:31:00+00:00", "value": 10_001.0},
            ),
            drawdown_curve=(
                {"timestamp": "2025-10-31T13:30:00+00:00", "drawdown": 0.0},
                {"timestamp": "2025-10-31T13:31:00+00:00", "drawdown": 0.0},
            ),
            validation=(
                DetailField("Data Validation · Dataset", "EQUS.MINI"),
                DetailField("Data Validation · Schema", "ohlcv-1m"),
            ),
            validation_outcome=(
                DetailField("Normalized status", "passed"),
                DetailField("Reasons", "Fixture acceptance evidence recorded."),
            ),
            provenance=(
                DetailField("Provider", "Databento"),
                DetailField("Dataset", "EQUS.MINI"),
                DetailField("Symbol", "SPYM"),
            ),
            warnings=(),
        )
    )

    panel = _run_detail_panel(
        service.recent_runs()[0],
        service.recent_events(),
        detail=detail,
    )
    rendered = str(panel)

    assert "Validation and evidence" in rendered
    assert "Result metrics" in rendered
    assert "Number Of Trades" in rendered
    assert "366" in rendered
    assert "passed" in rendered
    assert "Trade summary" in rendered
    assert "Recent trades" in rendered
    assert "Closed trades" in rendered
    assert "Cumulative trade P&L" in rendered
    assert "Price and completed trades" in rendered
    assert "Evidence not recorded" in rendered
    assert "This run does not include a persisted underlying price" in rendered
    assert "Portfolio value and buy-and-hold comparison" in rendered
    assert "Drawdown over time" in rendered
    assert "Portfolio value" in rendered
    assert "Validation evidence" in rendered
    assert "EQUS.MINI" in rendered
    assert "ohlcv-1m" in rendered
    assert "SPYM is an ingestion and execution fixture" in rendered


def test_recent_trades_grid_uses_responsive_column_profile() -> None:
    detail = _selected_detail_view(
        evidence=RunEvidenceView(
            notices=(),
            metrics=(),
            trades=(
                {
                    "Entry Index": "2025-10-31T14:05:00+00:00",
                    "Exit Index": "2025-10-31T14:39:00+00:00",
                    "Side": "Buy",
                    "PnL": 0.13,
                    "Return": 0.001,
                    "Size": 1.0,
                },
            ),
            orders=(),
            equity_curve=(),
            drawdown_curve=(),
            validation=(),
            provenance=(),
            warnings=(),
        )
    )
    panel = _run_detail_panel(
        _DashboardRunService().recent_runs()[0],
        (),
        detail=detail,
    )
    grids = [
        component
        for component in _walk_components(panel)
        if getattr(component, "className", None)
        == "ag-theme-alpine qf-data-grid qf-trades-grid qf-trade-explorer-grid"
    ]

    assert len(grids) == 1
    columns = {column["field"]: column for column in grids[0].columnDefs}
    assert columns["Entry timestamp"]["minWidth"] >= 160
    assert columns["Direction"]["width"] <= 120
    assert columns["P&L"]["cellClass"] == (
        "qf-table-cell qf-table-cell-center qf-table-cell-number"
    )
    assert columns["Return"]["headerClass"] == (
        "qf-table-header qf-table-header-wrap qf-table-header-center"
    )
    assert grids[0].columnSize == "autoSize"
    assert grids[0].defaultColDef["wrapHeaderText"]
    assert grids[0].defaultColDef["autoHeaderHeight"]


def test_trade_pnl_chart_marks_real_completed_trade_points() -> None:
    chart = _trade_pnl_chart(
        (
            {"Exit Index": "2025-10-31T14:39:00+00:00", "PnL": 10.0, "Return": 0.01, "Status": "Closed"},
            {"Exit Index": "2025-10-31T15:39:00+00:00", "PnL": -4.0, "Return": -0.004, "Status": "Closed"},
        ),
        mode="cumulative",
    )
    trace = chart.figure.data[0]

    assert trace.mode == "lines+markers"
    assert list(trace.marker.color) == ["#16a34a", "#ef4444"]
    assert trace.marker.size == 7
    assert "Trade %{customdata[0]}" in trace.hovertemplate
    assert list(trace.y) == [10.0, 6.0]
    assert chart.figure.layout.xaxis.title.text == "Completed trade number"
    assert chart.figure.layout.xaxis.tickmode == "linear"
    assert chart.figure.layout.xaxis.tick0 == 1
    assert chart.figure.layout.xaxis.dtick == 1
    assert chart.figure.layout.xaxis.tickformat == "d"
    assert chart.figure.layout.margin.b == 62


def test_trade_pnl_chart_uses_spaced_integer_ticks_for_longer_trade_sequences() -> None:
    chart = _trade_pnl_chart(
        tuple({"PnL": float(index), "Status": "Closed"} for index in range(25)),
        mode="cumulative",
    )

    assert chart.figure.layout.xaxis.title.text == "Completed trade number"
    assert chart.figure.layout.xaxis.tickformat == "d"
    assert chart.figure.layout.xaxis.dtick == 3


def test_drawdown_chart_marks_points_and_highlights_maximum_drawdown() -> None:
    chart = _curve_graph(
        (
            {"timestamp": "2025-10-31T13:30:00+00:00", "drawdown": 0.0},
            {"timestamp": "2025-10-31T13:31:00+00:00", "drawdown": -0.04},
            {"timestamp": "2025-10-31T13:32:00+00:00", "drawdown": -0.02},
        ),
        y_field="drawdown",
        title="Drawdown over time",
        color="#ef4444",
        empty="No drawdown.",
        percent=True,
        markers=True,
        emphasize_min=True,
    )

    assert chart.figure.data[0].mode == "lines+markers"
    assert chart.figure.data[1].name == "Maximum drawdown"
    assert list(chart.figure.data[1].y) == [-0.04]
    assert chart.figure.layout.yaxis.tickformat == ".2%"


def test_drawdown_chart_uses_precise_percent_ticks_for_small_drawdowns() -> None:
    chart = _curve_graph(
        (
            {"timestamp": "2025-10-31T13:30:00+00:00", "drawdown": 0.0},
            {"timestamp": "2025-10-31T13:31:00+00:00", "drawdown": -0.0004},
            {"timestamp": "2025-10-31T13:32:00+00:00", "drawdown": -0.0008},
        ),
        y_field="drawdown",
        title="Drawdown over time",
        color="#ef4444",
        empty="No drawdown.",
        percent=True,
        markers=True,
        emphasize_min=True,
    )

    assert chart.figure.layout.yaxis.tickformat == ".3%"
    assert list(chart.figure.data[0].y) == [0.0, -0.0004, -0.0008]
    assert list(chart.figure.data[1].y) == [-0.0008]


def test_selected_backtest_hierarchy_keeps_trace_id_out_of_primary_heading() -> None:
    service = _DashboardRunService()
    run = service.recent_runs()[0]
    panel = _run_detail_panel(run, service.recent_events(), detail=_selected_detail_view())
    headings = [
        component.children
        for component in _walk_components(panel)
        if component.__class__.__name__ == "H2"
    ]
    rendered = str(panel)

    assert run.run_id not in headings
    assert "Fixture-only" in rendered
    assert "Test period" in rendered
    assert "Traceability retained below" in rendered
    assert "Backtest ID" in rendered


def test_run_detail_panel_surfaces_artifact_warning_and_error_states() -> None:
    service = _DashboardRunService()
    detail = _selected_detail_view(
        artifacts=(
            ArtifactInventoryView(
                artifact_id=1,
                artifact_type="metrics",
                logical_name="missing-metrics",
                schema_version="1",
                format="json",
                availability="missing",
                validation_state="missing",
                checksum="sha256:missing",
                reference="artifacts/missing.json",
                reason="artifact_missing",
                severity="warning",
            ),
            ArtifactInventoryView(
                artifact_id=2,
                artifact_type="equity_curve",
                logical_name="corrupt-equity",
                schema_version="1",
                format="json",
                availability="corrupt",
                validation_state="corrupt",
                checksum="sha256:expected",
                reference="artifacts/equity.json",
                reason="artifact_checksum_mismatch",
                severity="error",
            ),
            ArtifactInventoryView(
                artifact_id=3,
                artifact_type="run_summary",
                logical_name="invalid-summary",
                schema_version="1",
                format="json",
                availability="available",
                validation_state="invalid",
                checksum="sha256:summary",
                reference="artifacts/summary.json",
                reason="stored run manifest artifacts do not match database records",
                severity="error",
            ),
        ),
    )

    rendered = str(
        _run_detail_panel(
            service.recent_runs()[0],
            service.recent_events(),
            detail=detail,
        )
    )

    assert "missing-metrics" in rendered
    assert "artifact_missing" in rendered
    assert "artifact-status-warning" in rendered
    assert "corrupt-equity" in rendered
    assert "artifact_checksum_mismatch" in rendered
    assert "invalid-summary" in rendered
    assert "stored run manifest artifacts do not match database records" in rendered
    assert "artifact-status-error" in rendered


def _spym_fixture_launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def test_run_detail_adapter_reads_validated_spym_artifacts_for_dashboard(
    tmp_path: Path,
) -> None:
    from orchestration import FixtureRunService
    from dashboard.run_detail_adapter import RunDetailDashboardAdapter

    database = tmp_path / "state" / "dashboard-21d.sqlite3"
    persistence = PersistenceService(database)
    try:
        configuration_id = ensure_spym_21c_saved_configuration(persistence)
    finally:
        persistence.close()
    FixtureRunService(
        database=database,
        fixture_launcher=_spym_fixture_launcher,
    ).launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-dashboard-21d",
    )

    detail = RunDetailDashboardAdapter(
        database=database,
        artifact_root=tmp_path,
    ).selected_run_detail("qf-dashboard-21d")

    assert not detail.warnings
    assert any(field.label == "Number Of Trades" and field.value == "366" for field in detail.evidence.metrics)
    assert len(detail.evidence.trades) == 366
    assert len(detail.evidence.orders) == 732
    assert len(detail.evidence.equity_curve) == 53528
    assert detail.evidence.drawdown_curve
    assert any(field.value == "Databento" for field in detail.evidence.provenance)
    assert any(field.value == "EQUS.MINI" for field in detail.evidence.validation)
    assert any("not profitability evidence" in notice for notice in detail.evidence.notices)
    assert any("not selected as the final paper or micro-live instrument" in notice for notice in detail.evidence.notices)


def test_run_detail_adapter_fails_closed_for_corrupt_spym_artifact(
    tmp_path: Path,
) -> None:
    from orchestration import FixtureRunService
    from dashboard.run_detail_adapter import RunDetailDashboardAdapter

    database = tmp_path / "state" / "dashboard-21d-corrupt.sqlite3"
    persistence = PersistenceService(database)
    try:
        configuration_id = ensure_spym_21c_saved_configuration(persistence)
    finally:
        persistence.close()
    FixtureRunService(
        database=database,
        fixture_launcher=_spym_fixture_launcher,
    ).launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-dashboard-21d-corrupt",
    )
    metrics_path = (
        tmp_path
        / "state"
        / "artifacts"
        / "qf-dashboard-21d-corrupt"
        / "metrics.json"
    )
    metrics_path.write_text('{"metrics":{"number_of_trades":999}}', encoding="utf-8")

    detail = RunDetailDashboardAdapter(
        database=database,
        artifact_root=tmp_path,
    ).selected_run_detail("qf-dashboard-21d-corrupt")

    assert any(
        "metrics" in warning
        and (
            "artifact_checksum_mismatch" in warning
            or "artifact_size_mismatch" in warning
        )
        for warning in detail.warnings
    )
    metrics_card = next(
        artifact for artifact in detail.artifacts if artifact.logical_name == "metrics"
    )
    assert metrics_card.validation_state == "corrupt"
    assert metrics_card.severity == "error"


def test_run_detail_panel_handles_missing_manifest_config_and_empty_summary() -> None:
    service = _DashboardRunService()
    detail = SelectedRunDetailView(
        configuration_fields=(DetailField("Configuration", "Missing"),),
        parameters=(),
        market_data=(),
        execution=(),
        ranking=(),
        screening=(),
        lineage_fields=(DetailField("Lineage", "Not recorded"),),
        manifest_fields=(DetailField("Manifest", "Not persisted"),),
        artifacts=(),
        result_summary=ResultSummaryView(
            status="empty",
            message="No persisted parameter result summary is available for this run.",
            rows=(),
        ),
        evidence=RunEvidenceView(
            notices=(),
            metrics=(),
            trades=(),
            orders=(),
            equity_curve=(),
            drawdown_curve=(),
            validation=(),
            provenance=(),
            warnings=(),
        ),
        warnings=(
            "The saved configuration for this run is missing.",
            "No persisted run manifest is available.",
        ),
    )

    rendered = str(
        _run_detail_panel(
            service.recent_runs()[0],
            service.recent_events(),
            detail=detail,
        )
    )

    assert "The saved configuration for this run is missing." in rendered
    assert "No persisted run manifest is available." in rendered
    assert "Not recorded" in rendered
    assert "No artifact inventory is available" in rendered
    assert "No persisted parameter result summary is available" in rendered
    assert "No persisted equity curve artifact is available for this run." in rendered
    assert "No persisted drawdown artifact is available for this run." in rendered
    assert (
        "Completed trades appear here when the run has a persisted trades artifact."
        in rendered
    )


def test_run_detail_enables_historical_configuration_launch_when_launchable() -> None:
    service = _DashboardRunService(run_status="failed")
    launchable_controls = _run_action_controls(
        service.recent_runs()[0],
        launchable_configuration=True,
    )
    blocked_controls = _run_action_controls(
        service.recent_runs()[0],
        launchable_configuration=False,
    )

    launchable_launch_controls = launchable_controls.children[0]
    blocked_launch_controls = blocked_controls.children[0]

    assert launchable_launch_controls.children[0].id == "launch-selected-run-configuration"
    assert launchable_launch_controls.children[0].disabled is False
    assert blocked_launch_controls.children[0].disabled is True


def test_dashboard_inspects_selected_run(tmp_path: Path, monkeypatch) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    detail_adapter = _DashboardRunDetailAdapter()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=detail_adapter,
    )

    inspect = _callback_function(app, "selected-run-detail")
    service.run_detail_queries.clear()
    service.run_event_queries.clear()
    detail_adapter.requests.clear()
    panel = inspect("run_dashboard_fixture", "run_dashboard_fixture", 0, 0, 0, 0)

    assert service.run_detail_queries == ["run_dashboard_fixture"]
    assert service.run_event_queries == ["run_dashboard_fixture"]
    assert detail_adapter.requests == ["run_dashboard_fixture"]
    assert "prefect-run_dashboard_fixture" in str(panel)
    assert "Run completed successfully." in str(panel)
    assert "Strategy settings" in str(panel)
    assert "Research history" in str(panel)


def test_selected_run_detail_dash_endpoint_renders_with_absent_detail_controls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    detail_adapter = _DashboardRunDetailAdapter()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=detail_adapter,
    )

    response = app.server.test_client().post(
        "/_dash-update-component",
        json={
            "output": "selected-run-detail.children",
            "outputs": {"id": "selected-run-detail", "property": "children"},
            "changedPropIds": ["selected-run-state.data"],
            "inputs": [
                {
                    "id": "selected-run-state",
                    "property": "data",
                    "value": "run_dashboard_fixture",
                },
                {
                    "id": "selected-run-selector",
                    "property": "value",
                    "value": "run_dashboard_fixture",
                },
                {"id": "refresh-runs", "property": "n_clicks", "value": 0},
                {"id": "launch-run", "property": "n_clicks", "value": 0},
                {
                    "id": "cancel-selected-run",
                    "property": "n_clicks",
                    "value": None,
                },
                {"id": "recover-stale-runs", "property": "n_clicks", "value": 0},
            ],
            "state": [],
        },
    )
    rendered = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "run-detail-hero" in rendered
    assert "Primary metrics" in rendered
    assert "run-analysis-tabs" in rendered
    assert "Select a recent run" not in rendered


def test_selected_run_detail_initializes_from_visible_dropdown_when_store_is_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    detail_adapter = _DashboardRunDetailAdapter()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=detail_adapter,
    )

    inspect = _callback_function(app, "selected-run-detail")
    service.run_detail_queries.clear()
    detail_adapter.requests.clear()
    panel = inspect(None, "run_dashboard_fixture", 0, 0, 0, 0)
    rendered = str(panel)

    assert service.run_detail_queries == ["run_dashboard_fixture"]
    assert detail_adapter.requests == ["run_dashboard_fixture"]
    assert "run-detail-hero" in rendered
    assert "Select a recent run" not in rendered


def test_selected_run_detail_callback_renders_charts_and_tables_for_persisted_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    detail_adapter = _DashboardRunDetailAdapter(
        _selected_detail_view(
            result_rows=(
                (
                    DetailField("Rank", "1"),
                    DetailField("Metrics", "total_return: 0.1"),
                    DetailField("Parameters", "window: 14"),
                ),
            ),
            evidence=RunEvidenceView(
                notices=(),
                metrics=(
                    DetailField("Total Return", "0.10"),
                    DetailField("Number Of Trades", "1"),
                ),
                trades=(
                    {
                        "Entry Index": "2026-01-01T14:00:00Z",
                        "Exit Index": "2026-01-01T15:00:00Z",
                        "PnL": 12.5,
                        "Status": "Closed",
                    },
                ),
                orders=(),
                equity_curve=(
                    {"timestamp": "2026-01-01T14:00:00Z", "value": 10_000.0},
                    {"timestamp": "2026-01-01T15:00:00Z", "value": 10_012.5},
                ),
                drawdown_curve=(
                    {"timestamp": "2026-01-01T14:00:00Z", "drawdown": 0.0},
                    {"timestamp": "2026-01-01T15:00:00Z", "drawdown": -0.01},
                ),
                validation=(DetailField("Validation", "passed"),),
                validation_outcome=(DetailField("Normalized status", "passed"),),
                provenance=(),
                warnings=(),
            ),
        )
    )
    service = _DashboardRunService()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=detail_adapter,
    )

    inspect = _callback_function(app, "selected-run-detail")
    panel = inspect("run_dashboard_fixture", "run_dashboard_fixture", 0, 0, 0, 0)
    rendered = str(panel)

    assert "Portfolio value and buy-and-hold comparison" in rendered
    assert "Cumulative trade P&amp;L" in rendered or "Cumulative trade P&L" in rendered
    assert "Drawdown over time" in rendered
    assert "Trade return distribution" in rendered
    assert "Recent trades" in rendered
    assert "result-summary-card" in rendered
    assert "window: 14" in rendered


def test_dashboard_selected_run_detail_reports_adapter_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    detail_adapter = _DashboardRunDetailAdapter(RuntimeError("manifest missing"))
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
        run_detail_adapter=detail_adapter,
    )

    inspect = _callback_function(app, "selected-run-detail")
    panel = inspect("run_dashboard_fixture", "run_dashboard_fixture", 0, 0, 0, 0)

    assert "Run detail retrieval failed: manifest missing" in str(panel)


def test_dashboard_callbacks_do_not_query_sqlite_or_parse_artifact_files() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "dashboard"
        / "application.py"
    ).read_text(encoding="utf-8")

    assert "sqlite3" not in source
    assert ".connection" not in source
    assert "read_bytes(" not in source
    assert "open(" not in source
    assert "retrieve_run_artifacts(" not in source


def test_dashboard_does_not_construct_lockbox_gate() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "dashboard"
        / "application.py"
    ).read_text(encoding="utf-8")

    assert "LockboxGateResult" not in source
    assert "LockboxArtifactReference" not in source
    assert "lockbox_gate_identity" not in source
    assert "SourceLockEvidence" not in source
    assert "RunDetailDashboardAdapter" in source


def test_dashboard_reports_missing_selected_run(tmp_path: Path, monkeypatch) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    inspect = _callback_function(app, "selected-run-detail")
    service.run_detail_queries.clear()
    service.run_event_queries.clear()
    panel = inspect("missing-run", "missing-run", 0, 0, 0, 0)

    assert service.run_detail_queries == ["missing-run"]
    assert service.run_event_queries == []
    assert "Run not found" in str(panel)

def test_run_detail_enables_cancellation_only_for_running_run() -> None:
    running_service = _DashboardRunService(run_status="running")
    running_controls = _run_action_controls(
        running_service.recent_runs()[0],
        launchable_configuration=True,
    )
    running_button = next(
        component
        for component in _walk_components(running_controls)
        if getattr(component, "id", None) == "cancel-selected-run"
    )

    terminal_service = _DashboardRunService(run_status="succeeded")
    terminal_controls = _run_action_controls(
        terminal_service.recent_runs()[0],
        launchable_configuration=True,
    )
    terminal_button = next(
        component
        for component in _walk_components(terminal_controls)
        if getattr(component, "id", None) == "cancel-selected-run"
    )

    assert running_button.id == "cancel-selected-run"
    assert running_button.disabled is False
    assert terminal_button.disabled is True


def test_dashboard_requests_cooperative_run_cancellation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(run_status="running")
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    cancel = _callback_function(app, "cancellation-message")
    message, class_name = cancel(1, "run_dashboard_fixture")

    assert service.cancellation_requests == ["run_dashboard_fixture"]
    assert "waiting for fixture acknowledgement" in message
    assert class_name == (
        "cancellation-message cancellation-message-pending"
    )


def test_dashboard_reports_cancellation_request_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(
        error=ValueError("run is not active and cannot be cancelled"),
        run_status="running",
    )
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    cancel = _callback_function(app, "cancellation-message")
    message, class_name = cancel(1, "run_dashboard_fixture")

    assert service.cancellation_requests == ["run_dashboard_fixture"]
    assert message == (
        "Cancellation request failed: "
        "run is not active and cannot be cancelled"
    )
    assert class_name == "cancellation-message error-state"


def test_dashboard_does_not_claim_terminal_run_was_cancelled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(run_status="succeeded")
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    cancel = _callback_function(app, "cancellation-message")
    message, class_name = cancel(1, "run_dashboard_fixture")

    assert service.cancellation_requests == ["run_dashboard_fixture"]
    assert message == (
        "Run is already succeeded; no cancellation request was applied."
    )
    assert class_name == "cancellation-message"

def test_dashboard_requires_explicit_stale_recovery_cutoff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    recover = _callback_function(app, "stale-recovery-message")
    message, class_name = recover(1, "   ")

    assert service.stale_recovery_requests == []
    assert "Age-only recovery is disabled" in message
    assert class_name == "stale-recovery-message error-state"


def test_dashboard_reports_no_matching_stale_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    recover = _callback_function(app, "stale-recovery-message")
    message, class_name = recover(1, "2026-07-13T12:00:00Z")

    assert service.stale_recovery_requests == []
    assert "Age-only recovery is disabled" in message
    assert class_name == "stale-recovery-message error-state"


def test_dashboard_reports_recovered_stale_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService()
    service.stale_recovery_result = (
        RunSummary(
            run_id="run_stale_fixture",
            configuration_id=configuration.configuration_id,
            strategy_id="prefect_fixture_strategy",
            strategy_version="1.0.0",
            stage="fixture",
            status="failed",
            created_at="2026-07-12T12:00:00Z",
            started_at="2026-07-12T12:00:01Z",
            completed_at="2026-07-13T12:00:00Z",
            error_summary=(
                "Fixture run remained running beyond the stale "
                "recovery cutoff."
            ),
            prefect_flow_run_id="prefect-stale-fixture",
            prefect_api_url="http://127.0.0.1:4200/api",
            attempt_count=2,
        ),
    )
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    recover = _callback_function(app, "stale-recovery-message")
    message, class_name = recover(1, "2026-07-13T12:00:00Z")

    assert service.stale_recovery_requests == []
    assert "Age-only recovery is disabled" in str(message)
    assert class_name == "stale-recovery-message error-state"


def test_dashboard_reports_stale_recovery_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(
        error=ValueError("stale_before must be an ISO-8601 UTC timestamp"),
    )
    data = _data()
    context = DashboardContext(
        pd.DataFrame([_ranked_row()]),
        data,
        _audit(data),
    )
    app = create_app(
        context,
        tmp_path / "reviews.json",
        run_service=service,
    )

    recover = _callback_function(app, "stale-recovery-message")
    message, class_name = recover(1, "not-a-timestamp")

    assert service.stale_recovery_requests == []
    assert "Age-only recovery is disabled" in message
    assert class_name == "stale-recovery-message error-state"
