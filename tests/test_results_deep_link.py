"""Focused Results-owned deep-link selection regressions."""

from __future__ import annotations

from pathlib import Path

from dash import Dash, no_update

from dashboard.callbacks.backtest_results import (
    _INVALID_REQUESTED_RUN_STATE,
    _unknown_requested_run_state,
    register_backtest_results_callbacks,
)
from orchestration import DurableResearchLaunchService, RunSummary


def _run(run_id: str) -> RunSummary:
    return RunSummary(
        run_id=run_id,
        configuration_id="configuration-fixture",
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        stage="fixture",
        status="succeeded",
        created_at="2026-09-18T00:00:00Z",
        started_at="2026-09-18T00:00:01Z",
        completed_at="2026-09-18T00:00:02Z",
        error_summary=None,
        prefect_flow_run_id=None,
        prefect_api_url=None,
        attempt_count=1,
    )


class _Runs:
    def __init__(self) -> None:
        self.records = {
            run.run_id: run
            for run in (
                _run("default-run"),
                _run("run:target one"),
                _run("second-run"),
                _run("operator-choice"),
            )
        }
        self.lookups: list[str] = []

    def get_run(self, run_id: str) -> RunSummary | None:
        self.lookups.append(run_id)
        return self.records.get(run_id)

    def recent_runs(self, *, limit: int = 20) -> tuple[RunSummary, ...]:
        assert limit == 20
        return (self.records["default-run"],)

    def events_for_run(self, run_id: str) -> tuple[object, ...]:
        assert run_id in self.records
        return ()


class _DetailAdapter:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root

    def selected_run_detail(self, run_id: str):
        raise RuntimeError(f"detail retrieval unavailable for {run_id}")


def _callback(app: Dash, output_fragment: str):
    entry = next(
        value
        for key, value in app.callback_map.items()
        if output_fragment in key
    )
    return getattr(entry["callback"], "__wrapped__", entry["callback"])


def _app(tmp_path: Path) -> tuple[Dash, _Runs]:
    app = Dash(__name__, suppress_callback_exceptions=True)
    runs = _Runs()
    register_backtest_results_callbacks(
        app,
        runs=runs,
        detail_adapter=_DetailAdapter(tmp_path),
        configurations=(),
        readiness_by_id={},
        dashboard_database=tmp_path / "state.sqlite3",
        artifact_root=tmp_path,
        research_launches=DurableResearchLaunchService(
            database=tmp_path / "state.sqlite3"
        ),
    )
    return app, runs


def test_registered_results_callback_adopts_one_encoded_persisted_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, runs = _app(tmp_path)
    entry = next(
        value
        for key, value in app.callback_map.items()
        if key == "selected-run-state.data"
    )
    assert ("url", "search") in {
        (item["id"], item["property"]) for item in entry["inputs"]
    }
    assert ("url", "pathname") in {
        (item["id"], item["property"]) for item in entry["state"]
    }

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "url",
    )
    preserve = _callback(app, "selected-run-state")

    selected = preserve(
        "default-run",
        None,
        "?run_id=run%3Atarget+one",
        "default-run",
        "/research/backtest-results",
    )

    assert selected == "run:target one"
    assert runs.lookups[-1] == "run:target one"


def test_results_deep_link_preserves_unknown_identity_and_renders_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, runs = _app(tmp_path)
    preserve = _callback(app, "selected-run-state")
    refresh_selector = _callback(app, "selected-run-selector.options")
    inspect = _callback(app, "selected-run-detail")
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "url",
    )

    requested = preserve(
        "default-run",
        None,
        "?run_id=unknown-run",
        "operator-choice",
        "/research/backtest-results",
    )

    assert requested == _unknown_requested_run_state("unknown-run")
    assert runs.lookups == ["unknown-run"]

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-run-state",
    )
    options, selected = refresh_selector(
        0,
        None,
        None,
        None,
        requested,
        "operator-choice",
        [{"label": "Operator choice", "value": "operator-choice"}],
    )
    rendered = str(inspect(requested, "operator-choice", 0, 0, 0, 0))

    assert selected == requested
    assert {
        option["value"]: option["label"] for option in options
    }[requested] == "Requested run not found — unknown-run"
    assert "Requested run not found" in rendered
    assert "unknown-run" in rendered
    assert "operator-choice" not in rendered


def test_results_deep_link_preserves_malformed_request_as_invalid_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, runs = _app(tmp_path)
    preserve = _callback(app, "selected-run-state")
    inspect = _callback(app, "selected-run-detail")
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "url",
    )

    for search in (
        "?run_id=default-run&run_id=second-run",
        "?run_id=%GG",
        "?run_id=",
        "?run_id=bad%0Aidentity",
    ):
        requested = preserve(
            "default-run",
            None,
            search,
            "operator-choice",
            "/research/backtest-results",
        )
        rendered = str(inspect(requested, "operator-choice", 0, 0, 0, 0))

        assert requested == _INVALID_REQUESTED_RUN_STATE
        assert "Invalid Results link" in rendered
        assert "operator-choice" not in rendered

    assert runs.lookups == []


def test_requested_run_failure_states_are_inert_for_results_actions(
    tmp_path: Path,
) -> None:
    app, runs = _app(tmp_path)
    update_actions = _callback(app, "cancel-selected-run.disabled")
    historical = _callback(app, "historical-launch-message")
    reproduce = _callback(app, "reproduction-message")
    cancel = _callback(app, "cancellation-message.children")

    for state in (
        _unknown_requested_run_state("unknown-run"),
        _INVALID_REQUESTED_RUN_STATE,
    ):
        cancel_disabled, cancel_title = update_actions(state, 0, None, None)
        historical_result = historical(
            0,
            state,
            None,
            "/research/backtest-results",
        )
        reproduction_result = reproduce(
            0,
            state,
            None,
            "/research/backtest-results",
        )
        cancellation_message, cancellation_class = cancel(
            1,
            state,
            "/research/backtest-results",
        )

        assert cancel_disabled is True
        assert "select a persisted run" in cancel_title.lower()
        assert historical_result[3] is True
        assert reproduction_result[3] is True
        assert cancellation_message == "No run is selected for cancellation."
        assert cancellation_class == "cancellation-message error-state"

    assert runs.lookups == []


def test_no_query_retains_default_and_explicit_selector_wins(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = _app(tmp_path)
    preserve = _callback(app, "selected-run-state")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: None,
    )
    assert (
        preserve(
            "default-run",
            None,
            "",
            "operator-choice",
            "/research/backtest-results",
        )
        is no_update
    )

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-run-selector",
    )
    assert (
        preserve(
            "operator-choice",
            None,
            "?run_id=second-run",
            "default-run",
            "/research/backtest-results",
        )
        == "operator-choice"
    )


def test_url_input_is_inert_off_results_and_navigation_is_deterministic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = _app(tmp_path)
    preserve = _callback(app, "selected-run-state")
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "url",
    )

    assert (
        preserve(
            "default-run",
            None,
            "?run_id=second-run",
            "default-run",
            "/research/compare-backtests",
        )
        is no_update
    )
    assert (
        preserve(
            "default-run",
            None,
            "?run_id=run%3Atarget+one",
            "default-run",
            "/research/backtest-results",
        )
        == "run:target one"
    )
    assert (
        preserve(
            "run:target one",
            None,
            "?run_id=second-run",
            "run:target one",
            "/research/backtest-results",
        )
        == "second-run"
    )
    assert (
        preserve(
            "second-run",
            None,
            "?run_id=run%3Atarget+one",
            "second-run",
            "/research/backtest-results",
        )
        == "run:target one"
    )


def test_deep_linked_identity_remains_visible_when_detail_retrieval_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, _ = _app(tmp_path)
    preserve = _callback(app, "selected-run-state")
    refresh_selector = _callback(app, "selected-run-selector.options")
    inspect = _callback(app, "selected-run-detail")

    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "url",
    )
    stored = preserve(
        "default-run",
        None,
        "?run_id=second-run",
        "default-run",
        "/research/backtest-results",
    )
    monkeypatch.setattr(
        "dashboard.callbacks.backtest_results._callback_triggered_id",
        lambda: "selected-run-state",
    )
    options, selected = refresh_selector(
        0,
        None,
        None,
        None,
        stored,
        "default-run",
        [{"label": "Default", "value": "default-run"}],
    )
    rendered_detail = str(inspect(stored, "default-run", 0, 0, 0, 0))

    assert selected == "second-run"
    assert "second-run" in {option["value"] for option in options}
    assert "second-run" in rendered_detail
    assert "detail retrieval unavailable" in rendered_detail
