"""Recovery coverage for persisted history and selected-run action ownership."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from dash import Dash, html

from dashboard.app import DashboardContext, create_app
from dashboard.callbacks.backtest_results import register_backtest_results_callbacks
from dashboard.callbacks.compare_backtests import register_compare_backtests_callbacks
from dashboard.run_adapter import SavedConfigurationView
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from market_data import DataAudit
from orchestration import FixtureRunService, RunLaunchResult, RunSummary
from persistence import (
    ArtifactAvailability,
    ArtifactType,
    PersistenceService,
    ReviewState,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.models import normalized_configuration_document


def _callback_function(app: Dash, output_fragment: str):
    entry = next(
        value for key, value in app.callback_map.items() if output_fragment in key
    )
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def _data() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=2, freq="D")
    return pd.DataFrame({"Open": [1.0, 2.0], "Close": [1.0, 2.0]}, index=index)


def _audit(data: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Test",
        provider_implementation="fixture",
        interval="1 day",
        requested_start="2026-01-01",
        requested_dynamic_end_policy="test",
        latest_completed_exchange_session="2026-01-02",
        prices_adjusted=True,
        adjustment_verification="test",
        download_time="2026-01-02T21:00:00+00:00",
        download_timezone="UTC",
        actual_first_row_date="2026-01-01",
        actual_last_row_date="2026-01-02",
        row_count=len(data),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
    )


def _configuration_view(configuration_id: str) -> SavedConfigurationView:
    return SavedConfigurationView(
        configuration_id=configuration_id,
        experiment_id="history_recovery",
        strategy_id="history_recovery_strategy",
        strategy_version="1.0.0",
        strategy_name="History Recovery Strategy",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE.value,
        active=True,
        parameters={},
        execution={},
        market_data={},
        config_hash=configuration_id,
    )


def _run(run_id: str, configuration_id: str = "config-a") -> RunSummary:
    return RunSummary(
        run_id=run_id,
        configuration_id=configuration_id,
        strategy_id="history_recovery_strategy",
        strategy_version="1.0.0",
        stage="fixture",
        status="running",
        created_at="2026-01-01T00:00:00+00:00",
        started_at="2026-01-01T00:00:01+00:00",
        completed_at=None,
        error_summary=None,
        prefect_flow_run_id=None,
        prefect_api_url=None,
        attempt_count=1,
    )


class _ActionRunService:
    def __init__(self) -> None:
        self.launches: list[str] = []
        self.cancellations: list[str] = []
        self.reproductions: list[str] = []
        self.runs = {
            "stored-run": _run("stored-run"),
            "dropdown-run": _run("dropdown-run"),
        }

    def get_run(self, run_id: str):
        return self.runs.get(run_id)

    def launch_fixture(self, *, configuration_id: str):
        self.launches.append(configuration_id)
        run = _run("new-launch", configuration_id)
        return RunLaunchResult(run=run, prefect_result=None)

    def request_fixture_cancellation(self, run_id: str):
        self.cancellations.append(run_id)
        return self.runs[run_id]

    def reproduce_fixture_run(self, run_id: str, *, artifact_root: Path):
        self.reproductions.append(run_id)
        raise RuntimeError("stop after target capture")

    def recent_runs(self, *, limit: int = 20):
        return tuple(self.runs.values())

    def recent_events(self, *, limit: int = 20):
        return ()

    def events_for_run(self, run_id: str):
        return ()

    def all_runs(self):
        return tuple(self.runs.values())

    def all_history(self, *, artifact_root: Path | None = None):
        return ()


class _DetailAdapter:
    artifact_root = Path(".")

    def selected_run_detail(self, run_id: str):  # pragma: no cover - not used here
        raise KeyError(run_id)


def test_selected_run_actions_read_session_store_instead_of_stale_dropdown(
    tmp_path: Path,
) -> None:
    app = Dash(__name__)
    service = _ActionRunService()
    database = tmp_path / "state.sqlite3"
    register_backtest_results_callbacks(
        app,
        runs=service,
        detail_adapter=_DetailAdapter(),
        configurations=(_configuration_view("config-a"),),
        readiness_by_id={},
        dashboard_database=database,
        artifact_root=tmp_path,
    )
    register_compare_backtests_callbacks(
        app,
        runs=service,
        detail_adapter=_DetailAdapter(),
        dashboard_database=database,
        artifact_root=tmp_path,
    )

    historical_state = {
        (item["id"], item["property"])
        for item in app.callback_map["..historical-launch-message.children...historical-launch-message.className.."]["state"]
    }
    cancel_state = {
        (item["id"], item["property"])
        for item in app.callback_map["..cancellation-message.children...cancellation-message.className.."]["state"]
    }
    reproduction_state = {
        (item["id"], item["property"])
        for item in next(
            value
            for key, value in app.callback_map.items()
            if "reproduction-message.children" in key
        )["state"]
    }

    assert ("selected-run-state", "data") in historical_state
    assert ("selected-run-selector", "value") not in historical_state
    assert ("selected-run-state", "data") in cancel_state
    assert ("selected-run-selector", "value") not in cancel_state
    assert ("selected-run-state", "data") in reproduction_state
    assert ("selected-run-selector", "value") not in reproduction_state

    historical_launch = _callback_function(app, "historical-launch-message")
    historical_launch(1, "stored-run", "/research/backtest-results")
    cancel = _callback_function(app, "cancellation-message")
    cancel(1, "stored-run", "/research/backtest-results")
    reproduce = _callback_function(app, "reproduction-message")
    reproduce(1, "stored-run", "/research/backtest-results")

    assert service.launches == ["config-a"]
    assert service.cancellations == ["stored-run"]
    assert service.reproductions == ["stored-run"]


@pytest.mark.parametrize(
    ("configuration_payload", "expected_issue"),
    (
        ("{not-json", "saved configuration is invalid:"),
        (canonical_json({}), "saved configuration experiment_id is invalid"),
        (
            canonical_json(
                {
                    "experiment_id": "history_recovery",
                    "parameters": {},
                    "execution": {},
                    "market_data": None,
                }
            ),
            "saved configuration market_data is not an object",
        ),
    ),
)
def test_all_history_keeps_row_visible_when_saved_configuration_is_malformed(
    tmp_path: Path,
    configuration_payload: str,
    expected_issue: str,
) -> None:
    database = tmp_path / "state" / "history-recovery.sqlite3"
    service = PersistenceService(database)
    try:
        strategy = service.register_strategy(
            strategy_id="history_recovery_strategy",
            strategy_version="1.0.0",
            display_name="History Recovery Strategy",
            description="History recovery fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="history_recovery",
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                market_data={"provider": "fixture", "symbol": "SPY", "interval": "1d"},
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
            stage=RunStage.FIXTURE,
            run_id="invalid-config-run",
            status=RunStatus.SUCCEEDED,
        )
        with transaction(service.connection):
            service.results.add_parameter_result(
                run_id="invalid-config-run",
                row_id="rank-1",
                normalized_parameters={"window": 14},
                metrics={
                    "total_return": 0.12,
                    "annualized_return": 0.20,
                    "sharpe_ratio": 1.2,
                    "number_of_trades": 3,
                },
                ranking_position=1,
                screening_status="passed",
            )
            service.reviews.update(
                target_type="run",
                target_id="invalid-config-run",
                state=ReviewState.WATCHLIST,
                note="Keep visible.",
                operator="local-user",
            )
        service.register_artifact(
            run_id="invalid-config-run",
            artifact_type=ArtifactType.VALIDATION_EVIDENCE,
            logical_name="validation_evidence",
            media_type="application/json",
            format="json",
            location="state/artifacts/invalid-config-run/validation_evidence.json",
            content=canonical_json({"status": "passed"}).encode("utf-8"),
            availability_state=ArtifactAvailability.AVAILABLE,
        )
        with transaction(service.connection):
            service.connection.execute(
                """
                UPDATE experiment_configurations
                SET canonical_config_json=?
                WHERE configuration_id=?
                """,
                (configuration_payload, configuration.configuration_id),
            )
    finally:
        service.close()

    rows = FixtureRunService(database=database).all_history(artifact_root=tmp_path)

    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "invalid-config-run"
    assert row["instrument"] == "Configuration unavailable"
    assert row["strategy"] == "History Recovery Strategy"
    assert row["stage"] == "Fixture backtest"
    assert row["status"] == "Succeeded"
    assert row["review"] == "Watchlist"
    assert row["total_return"] == 0.12
    assert row["metric_basis"] == "Rank 1 result"
    assert row["artifact_status"] == "1 registered artifacts"
    assert str(row["evidence"]).startswith("Evidence invalid: saved configuration is invalid:")
    assert expected_issue in str(row["evidence"])
    assert str(row["reproducibility"]).startswith(
        "Configuration invalid: saved configuration is invalid:"
    )
    assert expected_issue in str(row["reproducibility"])


@pytest.mark.parametrize(
    ("configuration_payload", "expected_issue"),
    (
        ("{not-json", "saved configuration is invalid:"),
        (canonical_json({}), "saved configuration experiment_id is invalid"),
        (
            canonical_json(
                {
                    "experiment_id": "history_recovery_layout",
                    "parameters": {},
                    "execution": {},
                    "market_data": None,
                }
            ),
            "saved configuration market_data is not an object",
        ),
    ),
)
def test_dashboard_initial_layout_survives_malformed_history_configuration(
    tmp_path: Path,
    configuration_payload: str,
    expected_issue: str,
) -> None:
    database = tmp_path / "state" / "history-recovery-layout.sqlite3"
    service = PersistenceService(database)
    try:
        strategy = service.register_strategy(
            strategy_id="history_recovery_strategy",
            strategy_version="1.0.0",
            display_name="History Recovery Strategy",
            description="History recovery fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configuration = service.upsert_configuration(
            normalized_configuration_document(
                experiment_id="history_recovery_layout",
                strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version,
                market_data={"provider": "fixture", "symbol": "SPY", "interval": "1d"},
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
            stage=RunStage.FIXTURE,
            run_id="layout-invalid-config-run",
            status=RunStatus.SUCCEEDED,
        )
        with transaction(service.connection):
            service.connection.execute(
                """
                UPDATE experiment_configurations
                SET canonical_config_json=?
                WHERE configuration_id=?
                """,
                (configuration_payload, configuration.configuration_id),
            )
    finally:
        service.close()

    data = _data()
    app = create_app(
        DashboardContext(pd.DataFrame(), data, _audit(data)),
        database,
        run_service=FixtureRunService(database=database),
        run_detail_adapter=RunDetailDashboardAdapter(
            database=database,
            artifact_root=tmp_path,
        ),
    )

    layout = app.layout()
    rendered = str(layout)
    assert "layout-invalid-config-run" in rendered
    assert "Configuration unavailable" in rendered
    assert "Evidence invalid: saved configuration is invalid:" in rendered
    assert expected_issue in rendered
