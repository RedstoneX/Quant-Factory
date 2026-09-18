"""Focused Milestone 23 Setup -> Run readiness and ownership tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dash import html

from dashboard.app import create_app
from dashboard.components.configuration_summary import configuration_summary
from dashboard.health import DatasetHealth
from dashboard.run_adapter import (
    SavedConfigurationView,
    configuration_readiness,
)
from market_data.catalog import DatasetManifest


def _configuration(**changes: object) -> SavedConfigurationView:
    base = SavedConfigurationView(
        configuration_id="a" * 64,
        experiment_id="milestone_21c_spym_databento_vectorbt_fixture",
        strategy_id="spym_rsi_mean_reversion_fixture",
        strategy_version="1.0.0",
        strategy_name="SPYM RSI mean-reversion infrastructure fixture",
        lifecycle="infrastructure_fixture",
        active=True,
        parameters={"fixture": True, "window": 14},
        execution={"kind": "fixture", "fees": 0.0, "slippage": 0.0},
        market_data={
            "dataset_id": "equities_SPYM_1m_databento_equs_mini",
            "dataset": "EQUS.MINI",
            "symbol": "SPYM",
            "provider": "databento",
            "timeframe": "1m",
            "coverage_start": "2025-10-31",
            "coverage_end_policy": "latest_fully_completed_nyse_session",
        },
        config_hash="b" * 64,
    )
    return replace(base, **changes)


def _manifest() -> DatasetManifest:
    return DatasetManifest.from_dict(
        {
            "dataset_id": "equities_SPYM_1m_databento_equs_mini",
            "status": "validated",
            "asset_class": "equity",
            "symbol": "SPYM",
            "provider": "databento",
            "dataset": "EQUS.MINI",
            "timeframe": "1m",
            "format": "parquet",
            "canonical_relative_path": "equities/SPYM/1m/SPYM.parquet",
            "sha256": "c" * 64,
            "size_bytes": 100,
            "row_count": 10,
            "earliest_timestamp": "2025-10-31T13:30:00+00:00",
            "latest_timestamp": "2026-07-13T19:59:00+00:00",
        }
    )


def _catalog(
    *,
    availability: str = "Available locally",
    checksum: str = "Verified",
    manifest: DatasetManifest | None = None,
):
    selected = manifest or _manifest()
    return (
        object(),
        (DatasetHealth(selected, availability, checksum, "test evidence"),),
        None,
    )


def _text(component: object) -> str:
    if component is None:
        return ""
    if isinstance(component, (str, int, float)):
        return str(component)
    if isinstance(component, (list, tuple)):
        return " ".join(_text(child) for child in component)
    return _text(getattr(component, "children", None))


def _callback(app, output_fragment: str):
    entry = next(
        value
        for key, value in app.callback_map.items()
        if output_fragment in key
    )
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def test_readiness_is_immutable_complete_and_ready_only_for_verified_data() -> None:
    view = configuration_readiness(_configuration(), _catalog())

    assert view.ready
    assert view.state == "ready"
    assert view.provider == "databento"
    assert view.dataset == "EQUS.MINI"
    assert view.instrument == "SPYM"
    assert view.timeframe == "1m"
    assert view.requested_coverage == (
        "From 2025-10-31; end: Latest fully completed nyse session"
    )
    assert view.actual_coverage == (
        "2025-10-31T13:30:00+00:00 to 2026-07-13T19:59:00+00:00"
    )
    assert view.local_availability == "Available locally"
    assert view.local_validation == "Verified"
    assert view.parameters
    assert view.execution_assumptions
    assert view.blockers == ()

    rendered = _text(configuration_summary(view, component_id="summary"))
    for expected in (
        "Provider",
        "Dataset",
        "Instrument",
        "Timeframe",
        "Requested coverage",
        "Actual coverage",
        "Local availability",
        "Local validation",
        "Parameters",
        "Execution assumptions",
    ):
        assert expected in rendered


def test_missing_required_inputs_fail_closed_in_stable_operator_order() -> None:
    view = configuration_readiness(
        _configuration(
            market_data={"kind": "catalog"},
            execution={},
        ),
        _catalog(),
    )

    assert not view.ready
    assert view.state == "unsupported"
    assert [blocker.code for blocker in view.blockers] == [
        "missing_execution_assumptions",
        "missing_provider",
        "missing_dataset_id",
        "missing_instrument",
        "missing_timeframe",
    ]
    assert all(blocker.reason and blocker.remedy for blocker in view.blockers)


def test_mismatch_and_unverified_local_file_are_all_reported() -> None:
    invalid_manifest = replace(_manifest(), status="quarantined")
    view = configuration_readiness(
        _configuration(
            market_data={
                "dataset_id": "equities_SPYM_1m_databento_equs_mini",
                "dataset": "WRONG.FEED",
                "symbol": "SPY",
                "provider": "other-provider",
                "timeframe": "5m",
            }
        ),
        _catalog(
            availability="Missing locally",
            checksum="Not checked",
            manifest=invalid_manifest,
        ),
    )

    assert not view.ready
    assert view.state == "data_unavailable"
    assert [blocker.code for blocker in view.blockers] == [
        "provider_mismatch",
        "instrument_mismatch",
        "timeframe_mismatch",
        "dataset_mismatch",
        "manifest_not_validated",
        "data_unavailable",
        "checksum_unverified",
    ]


def test_unchecked_catalog_and_explicit_data_free_fixture_do_not_imply_health() -> None:
    unchecked = configuration_readiness(
        _configuration(),
        (None, (DatasetHealth(_manifest(), "Not inspected", "Not inspected", "missing config"),), "missing config"),
    )
    assert not unchecked.ready
    assert unchecked.local_availability == "Not inspected"
    assert unchecked.local_validation == "Not inspected"
    assert [blocker.code for blocker in unchecked.blockers][-1] == "catalog_not_checked"

    data_free = configuration_readiness(
        _configuration(market_data={"kind": "none"}),
        None,
    )
    assert data_free.ready
    assert data_free.dataset == "No market data"
    assert data_free.local_availability == "Not required"
    assert data_free.local_validation == "Not required"


def test_loading_empty_unsupported_and_data_unavailable_states_are_explicit() -> None:
    loading = configuration_summary(None, component_id="loading", loading=True)
    empty = configuration_summary(None, component_id="empty")
    unsupported = configuration_summary(
        configuration_readiness(
            _configuration(active=False, market_data={"kind": "none"}),
            None,
        ),
        component_id="unsupported",
    )
    unavailable = configuration_summary(
        configuration_readiness(_configuration(), None),
        component_id="unavailable",
    )

    assert getattr(loading, "data-state") == "loading"
    assert getattr(empty, "data-state") == "empty"
    assert getattr(unsupported, "data-state") == "unsupported"
    assert getattr(unavailable, "data-state") == "data_unavailable"
    assert "Run test remains disabled" in _text(loading)
    assert "test blocked" in _text(unavailable)


def test_setup_and_run_callbacks_own_only_their_page_outputs_and_recovery_refreshes_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _configuration(market_data={"kind": "none"})
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    monkeypatch.setattr("dashboard.application.inspect_catalog", lambda: (None, (), "test"))
    app = create_app(review_database=tmp_path / "dashboard.sqlite3")

    setup_key = next(key for key in app.callback_map if "configuration-preview.children" in key)
    run_key = next(key for key in app.callback_map if "run-configuration-preview.children" in key)
    assert "run-configuration-preview" not in setup_key
    assert "configuration-preview.children" not in run_key.replace(
        "run-configuration-preview.children", ""
    )

    selected_owner = app.callback_map["selected-configuration-state.data"]
    assert selected_owner["inputs"] == [
        {"id": "configuration-selector", "property": "value"}
    ]
    results_key = next(key for key in app.callback_map if "results-operator-context.children" in key)
    result_inputs = {
        (item["id"], item["property"])
        for item in app.callback_map[results_key]["inputs"]
    }
    assert ("stale-recovery-message", "children") in result_inputs


def test_registered_run_preview_and_launch_fail_closed_on_preflight_blocker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    monkeypatch.setattr(
        "dashboard.application.inspect_catalog",
        lambda: (None, (DatasetHealth(_manifest(), "Not inspected", "Not inspected", "missing config"),), "missing config"),
    )
    app = create_app(review_database=tmp_path / "dashboard.sqlite3")

    run_preview = _callback(app, "run-configuration-preview.children")
    children = run_preview(configuration.configuration_id)
    assert "Local dataset availability and checksum were not verified" in _text(
        html.Div(children)
    )

    setup_preview = _callback(app, "configuration-preview.children")
    _, href, class_name, setup_title = setup_preview(
        configuration.configuration_id
    )
    assert href is None
    assert "action-disabled" in class_name
    assert "Resolve every preflight blocker" in setup_title

    launch = _callback(app, "launch-message.children")
    _, message, class_name, _, _, disabled, title, label = launch(
        1,
        configuration.configuration_id,
        None,
        "/research/run-test",
    )
    assert "did not pass preflight" in _text(message)
    assert class_name == "save-message error-state"
    assert disabled is True
    assert title == "This persisted selection is not launchable."
    assert label == "Run test"
