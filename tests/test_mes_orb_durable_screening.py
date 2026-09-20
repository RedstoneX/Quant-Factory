"""Decision-288 durable MES ORB screening adapter coverage."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

import backtesting.run_mes_orb_durable as durable_module
from backtesting.run_mes_orb import ROLL_STATUS, _config
from backtesting.run_mes_orb_durable import (
    EVIDENCE_LABELS,
    EXPECTED_DATASET_ROWS,
    EXPECTED_DATASET_SHA256,
    EXPECTED_FIRST_TIMESTAMP,
    EXPECTED_LAST_TIMESTAMP,
    experiment_config,
    parameter_combinations,
    prepare_run_pair,
    run_durable_screening,
)
from backtesting.screening import ScreeningResult
from backtesting.validation import ValidationResult
from dashboard.callbacks.review_state import load_durable_review
from dashboard.application import _run_detail_panel
from dashboard.run_detail_adapter import (
    RunDetailDashboardAdapter,
    _calendar_cagr,
    _screening_outcome_fields,
)
from market_data import DataAudit
from orchestration import FixtureRunService
from persistence import (
    ArtifactType,
    PersistenceService,
    ReviewState,
    RunEventType,
    RunStage,
    RunStatus,
    StrategyLifecycle,
)
from strategies import get_strategy


def _frame() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            "2019-05-05T22:00:00+00:00",
            "2019-05-05T22:05:00+00:00",
            "2026-02-13T21:50:00+00:00",
            "2026-02-13T21:55:00+00:00",
        ]
    )
    return pd.DataFrame(
        {
            "Open": [100.0, 100.5, 101.0, 101.5],
            "High": [100.75, 101.25, 101.75, 102.25],
            "Low": [99.75, 100.25, 100.75, 101.25],
            "Close": [100.5, 101.0, 101.5, 102.0],
            "Volume": [10, 11, 12, 13],
        },
        index=index,
    )


def _audit() -> DataAudit:
    return DataAudit(
        cache_schema_version=1,
        symbol="MES",
        provider="Databento",
        provider_implementation="verified local catalog manifest",
        interval="5m",
        requested_start=EXPECTED_FIRST_TIMESTAMP,
        requested_dynamic_end_policy="Fixed extent of the cataloged dataset",
        latest_completed_exchange_session="2026-02-13",
        prices_adjusted=False,
        adjustment_verification=(
            "Confirmed Databento MES.c.0 calendar/front-expiry rank zero; "
            "prices are original and unadjusted"
        ),
        download_time="2026-07-07T17:09:09Z",
        download_timezone="UTC",
        actual_first_row_date=EXPECTED_FIRST_TIMESTAMP,
        actual_last_row_date=EXPECTED_LAST_TIMESTAMP,
        row_count=EXPECTED_DATASET_ROWS,
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
        unexpected_session_gaps=[],
        provider_warnings=["Unadjusted calendar-roll discontinuities remain."],
        cache_path="futures/MES/5m/MES_5m_databento.parquet",
        cache_action="verified and reused",
        cache_decision_reason=f"SHA-256 matched manifest {EXPECTED_DATASET_SHA256}",
    )


def _metadata() -> dict[str, Any]:
    return {
        "dataset_id": "futures_MES_5m_databento",
        "status": "validated",
        "symbol": "MES",
        "provider": "Databento",
        "timeframe": "5m",
        "sha256": EXPECTED_DATASET_SHA256,
        "row_count": EXPECTED_DATASET_ROWS,
        "earliest_timestamp": EXPECTED_FIRST_TIMESTAMP,
        "latest_timestamp": EXPECTED_LAST_TIMESTAMP,
        "continuous_symbol": "MES.c.0",
        "roll_rule": "calendar/front-expiry rank zero",
        "price_adjustment": "none; original unadjusted contract prices",
        "contract_series_classification": "confirmed",
        "null_counts": {name: 0 for name in ("open", "high", "low", "close", "volume")},
        "ohlc_violation_count": 0,
    }


def _loader():
    return _frame(), _audit(), _metadata()


def _fake_executor(calls: list[str], *, fail_direction: str | None = None):
    def execute(config, data, audit, *, write_output):
        del data, audit
        calls.append(config.execution.direction)
        direction = "long" if config.execution.direction == "longonly" else "short"
        if direction == fail_direction:
            raise RuntimeError(f"injected {direction} failure")
        spec = get_strategy(config.strategy_id).spec
        rows = []
        screening = []
        for parameters in config.parameter_combinations:
            row_id = (
                f"{direction}-{parameters['range_minutes']}-"
                f"{parameters['breakout_offset_ticks']}"
            )
            score = float(parameters["range_minutes"] * 10 + parameters["breakout_offset_ticks"])
            rows.append(
                {
                    **parameters,
                    "total_return": score / 10_000,
                    "annualized_return": score / 20_000,
                    "sharpe_ratio": score / 1_000,
                    "max_drawdown": -0.01,
                    "number_of_trades": 25,
                    "win_rate": 0.55,
                    "parameter_row_id": row_id,
                    "screening_status": "passed",
                    "screening_passed_rule_count": 5,
                    "screening_failed_rule_count": 0,
                    "screening_rejection_reasons": "",
                }
            )
            screening.append(
                ScreeningResult(
                    parameter_row_id=row_id,
                    passed=True,
                    rule_results=(),
                    passed_rule_count=5,
                    failed_rule_count=0,
                    strategy_id=config.strategy_id,
                    strategy_version=spec.identity.version,
                    normalized_parameters=dict(parameters),
                    execution_assumptions=asdict_execution(config),
                    rejection_reasons=(),
                )
            )
        ranked = pd.DataFrame(rows).sort_values(
            ["total_return", "sharpe_ratio"],
            ascending=[False, False],
            kind="mergesort",
        ).reset_index(drop=True)
        return SimpleNamespace(
            ranked_results=ranked,
            passing_results=ranked.copy(),
            screened_out_results=ranked.iloc[0:0].copy(),
            experiment_id=config.experiment_id,
            strategy_id=config.strategy_id,
            strategy_name=spec.identity.name,
            strategy_version=spec.identity.version,
            normalized_parameters=tuple(dict(item) for item in config.parameter_combinations),
            market_data_audit=_audit(),
            execution_assumptions=asdict_execution(config),
            run_timestamp="2026-09-19T00:00:00+00:00",
            evaluated_combinations=len(ranked),
            rejected_combinations=0,
            rejections=(),
            validation_results=(
                ValidationResult(
                    gate_id="fake_inputs",
                    status="passed",
                    severity="info",
                    message="Deterministic test executor accepted inputs.",
                ),
            ),
            screening_config=config.screening,
            screening_results=tuple(screening),
            parameter_plan_summary=None,
        )

    return execute


def asdict_execution(config) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(config.execution)


def _portfolio_builder(captured: list[dict[str, Any]]):
    def build(prepared, result, data):
        del data
        top = result.ranked_results.iloc[0].to_dict()
        captured.append(
            {
                "direction": prepared.direction,
                "parameter_row_id": top["parameter_row_id"],
                "range_minutes": top["range_minutes"],
                "breakout_offset_ticks": top["breakout_offset_ticks"],
            }
        )
        trades = pd.DataFrame(
            [
                {
                    "Entry Timestamp": pd.Timestamp("2025-01-15T15:00:00Z"),
                    "Exit Timestamp": pd.Timestamp("2025-01-15T21:00:00Z"),
                    "Entry Price": 502.5,
                    "Exit Price": 507.5,
                    "PnL": 5.0,
                    "Fees": 1.24,
                    "Size": 1.0,
                }
            ]
        )
        orders = pd.DataFrame(
            [
                {
                    "Timestamp": pd.Timestamp("2025-01-15T15:00:00Z"),
                    "Price": 502.5,
                    "Fees": 0.62,
                    "Size": 1.0,
                }
            ]
        )
        value = pd.Series(
            [100_000.0, 100_005.0],
            index=pd.DatetimeIndex(
                ["2025-01-15T15:00:00Z", "2025-01-15T21:00:00Z"]
            ),
        )
        return SimpleNamespace(
            trades=SimpleNamespace(records_readable=trades),
            orders=SimpleNamespace(records_readable=orders),
            value=value,
        )

    return build


def _no_op_dataset_validator(metadata, data) -> None:
    assert metadata["sha256"] == EXPECTED_DATASET_SHA256
    assert data.index[0].isoformat() == EXPECTED_FIRST_TIMESTAMP
    assert data.index[-1].isoformat() == EXPECTED_LAST_TIMESTAMP


def _run(
    tmp_path: Path,
    *,
    plan: str,
    executor,
    portfolio_builder,
):
    database = tmp_path / "state" / "orb.sqlite3"
    outcome = run_durable_screening(
        plan=plan,
        database=database,
        artifact_root=tmp_path,
        run_ids={"long": f"{plan}-long", "short": f"{plan}-short"},
        data_loader=_loader,
        dataset_validator=_no_op_dataset_validator,
        experiment_executor=executor,
        portfolio_builder=portfolio_builder,
    )
    return database, outcome


def test_predeclared_plans_and_legacy_roll_metadata_are_exact() -> None:
    reference = parameter_combinations("reference")
    matrix = parameter_combinations("matrix")

    assert reference == ({"range_minutes": 30, "breakout_offset_ticks": 0},)
    assert len(matrix) == 15
    assert {row["range_minutes"] for row in matrix} == {5, 15, 30, 45, 60}
    assert {row["breakout_offset_ticks"] for row in matrix} == {0, 1, 2}
    assert len(experiment_config("long", "reference").parameter_combinations) == 1
    assert len(experiment_config("short", "matrix").parameter_combinations) == 15
    execution = experiment_config("long", "reference").execution
    assert execution.initial_cash == 100_000.0
    assert execution.order_size == 1.0
    assert execution.price_multiplier == 5.0
    assert execution.fixed_fee_per_contract_per_side == 0.62
    assert execution.slippage_ticks == 1.0
    assert ROLL_STATUS == "confirmed_mes_c_0_calendar_front_expiry_unadjusted"
    assert "unresolved" not in _config("longonly").execution.__repr__()


def test_screening_protected_data_state_requires_explicit_false() -> None:
    base = {
        "stage": "screening",
        "screening": {
            "evaluated_combinations": 1,
            "passed": 0,
            "screened_out": 1,
        },
        "promotion_blockers": ["No independent evidence."],
    }

    explicit = _screening_outcome_fields({**base, "protected_data_used": False})
    absent = _screening_outcome_fields(base)
    malformed = _screening_outcome_fields({**base, "protected_data_used": "false"})

    assert {field.label: field.value for field in explicit}["Protected-data state"] == (
        "Not used; development/reference evidence only"
    )
    for fields in (absent, malformed):
        values = {field.label: field.value for field in fields}
        assert "Not established" in values["Protected-data state"]
        assert values["Lockbox eligibility"] == "No"
        assert values["Strategy progression"] == "No strategy progression occurred."


def test_command_defaults_to_reference_and_requires_explicit_matrix_choice(
    monkeypatch,
) -> None:
    selected: list[str] = []

    def fake_run(*, plan, database):
        del database
        selected.append(plan)
        return SimpleNamespace(runs=(), failures=(), exit_code=0)

    monkeypatch.setattr(durable_module, "run_durable_screening", fake_run)
    assert durable_module.main([]) == 0
    assert durable_module.main(["--plan", "matrix"]) == 0
    assert selected == ["reference", "matrix"]


def test_direct_script_help_starts_from_repository_root() -> None:
    project_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "backtesting/run_mes_orb_durable.py", "--help"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--plan {reference,matrix}" in completed.stdout


def test_pair_preparation_is_atomic_and_rolls_back_the_first_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = PersistenceService(tmp_path / "state" / "atomic.sqlite3")
    original = service.runs.create
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected second-run failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(service.runs, "create", fail_second)
    try:
        with pytest.raises(RuntimeError, match="second-run failure"):
            prepare_run_pair(
                service,
                plan="reference",
                run_ids={"long": "atomic-long", "short": "atomic-short"},
            )
        assert service.connection.execute("SELECT COUNT(*) FROM strategies").fetchone()[0] == 0
        assert service.connection.execute("SELECT COUNT(*) FROM experiment_configurations").fetchone()[0] == 0
        assert service.connection.execute("SELECT COUNT(*) FROM experiment_runs").fetchone()[0] == 0
        assert service.connection.execute("SELECT COUNT(*) FROM run_operator_events").fetchone()[0] == 0
    finally:
        service.close()


@pytest.mark.parametrize("plan,expected_rows", [("reference", 1), ("matrix", 15)])
def test_durable_pair_persists_ranked_evidence_and_opens_in_existing_results(
    tmp_path: Path,
    plan: str,
    expected_rows: int,
) -> None:
    calls: list[str] = []
    captured: list[dict[str, Any]] = []
    database, outcome = _run(
        tmp_path,
        plan=plan,
        executor=_fake_executor(calls),
        portfolio_builder=_portfolio_builder(captured),
    )

    assert outcome.exit_code == 0
    assert calls == ["longonly", "shortonly"]
    assert len(captured) == 2
    if plan == "matrix":
        assert all(row["range_minutes"] == 60 for row in captured)
        assert all(row["breakout_offset_ticks"] == 2 for row in captured)

    service = PersistenceService(database)
    saved_metrics_by_run: dict[str, dict[str, Any]] = {}
    try:
        for prepared in outcome.runs:
            run = service.runs.get(prepared.run_id)
            assert run is not None
            assert run.stage == RunStage.SCREENING
            assert run.status == RunStatus.SUCCEEDED
            strategy = service.strategies.get(run.strategy_id, run.strategy_version)
            assert strategy is not None
            assert strategy.lifecycle == StrategyLifecycle.CANDIDATE
            rows = service.results.list_parameter_results(run.run_id)
            saved_metrics_by_run[run.run_id] = json.loads(rows[0].metrics_json)
            assert len(rows) == expected_rows
            assert [row.ranking_position for row in rows] == list(
                range(1, expected_rows + 1)
            )
            assert rows[0].row_id == captured[
                0 if prepared.direction == "long" else 1
            ]["parameter_row_id"]
            assert service.reviews.get_current("run", run.run_id) is None
            assert service.reviews.history("run", run.run_id) == ()
            provenance = service.results.get_data_provenance(run.run_id)
            assert provenance is not None
            assert provenance.checksum == EXPECTED_DATASET_SHA256
            assert provenance.manifest_reference.endswith(
                "futures_MES_5m_databento.json"
            )
            validation_summary = json.loads(provenance.validation_summary_json)
            assert validation_summary["contract_series"] == "MES.c.0"
            assert validation_summary["roll_discontinuities"] == (
                "unadjusted_explicit_limitation"
            )
            assert service.results.get_execution_assumptions(run.run_id) is not None
            artifacts = service.list_run_artifacts(run.run_id)
            assert {artifact.logical_name for artifact in artifacts} == {
                "dataset_manifest",
                "equity_curve",
                "metrics",
                "parameter_results",
                "run_summary",
                "trades_and_orders",
                "validation_evidence",
            }
            assert {artifact.artifact_type for artifact in artifacts} == {
                ArtifactType.DATASET_MANIFEST,
                ArtifactType.EQUITY_CURVE,
                ArtifactType.METRICS,
                ArtifactType.PARAMETER_RESULTS,
                ArtifactType.RUN_SUMMARY,
                ArtifactType.TRADES_OR_ORDERS,
                ArtifactType.VALIDATION_EVIDENCE,
            }
            retrieval = service.retrieve_run_artifacts(
                run.run_id,
                artifact_root=tmp_path,
            )
            assert all(item.valid for item in retrieval.validations)
            manifest = service.read_persisted_run_manifest(run.run_id)
            assert manifest is not None
            assert service.run_manifest_checksum(
                service.build_run_manifest(run.run_id)
            ) == manifest[1]

            base = tmp_path / "state" / "artifacts" / run.run_id
            summary = json.loads((base / "run_summary.json").read_text())
            assert summary["evidence_label"] == EVIDENCE_LABELS[plan]
            assert summary["status_at_artifact_capture"] == RunStatus.RUNNING.value
            assert "terminal_status" not in summary
            assert summary["promotion_eligible"] is False
            assert "benchmark_omission" in summary
            assert summary["selected_parameter_row_id"] == rows[0].row_id
            metrics = json.loads((base / "metrics.json").read_text())
            trades = json.loads((base / "trades_and_orders.json").read_text())
            equity = json.loads((base / "equity_curve.json").read_text())
            validation = json.loads((base / "validation_evidence.json").read_text())
            assert metrics["parameter_row_id"] == rows[0].row_id
            assert trades["parameter_row_id"] == rows[0].row_id
            assert equity["parameter_row_id"] == rows[0].row_id
            assert validation["selected_parameter_row_id"] == rows[0].row_id
            assert validation["direction"] == prepared.direction
            assert trades["price_unit"] == "index_points"
            assert trades["pnl_unit"] == "USD"
            assert trades["price_multiplier"] == 5.0
            assert trades["trades"][0]["Entry Price"] == 100.5
            assert trades["trades"][0]["Exit Price"] == 101.5
            assert trades["orders"][0]["Price"] == 100.5
            assert trades["trades"][0]["PnL"] == 5.0
            assert trades["trades"][0]["Fees"] == 1.24
    finally:
        service.close()

    history = FixtureRunService(database=database).all_history(artifact_root=tmp_path)
    assert {row["run_id"] for row in history} == {
        f"{plan}-long",
        f"{plan}-short",
    }
    review = load_durable_review(database, tmp_path, f"{plan}-long")
    assert review.state == ReviewState.UNREVIEWED
    detail = RunDetailDashboardAdapter(
        database,
        artifact_root=tmp_path,
    ).selected_run_detail(f"{plan}-long")
    assert detail.result_summary.status == "available"
    assert len(detail.result_summary.table_rows) == expected_rows
    assert "deterministic fixture" not in detail.result_summary.message.lower()
    assert "development/reference evidence only" in detail.result_summary.message
    assert detail.evidence.metrics
    assert detail.evidence.trades
    assert detail.evidence.price_series
    assert detail.evidence.source_interval == "5m"
    assert detail.evidence.price_unit == "index_points"
    assert detail.evidence.pnl_unit == "USD"
    assert detail.evidence.promotion_eligible is False
    assert detail.evidence.evidence_classification is not None
    assert any("Evidence classification" in notice for notice in detail.evidence.notices)
    assert any("Promotion blocked" in notice for notice in detail.evidence.notices)
    assert any("basis were not persisted" in notice for notice in detail.evidence.notices)
    assert any(
        "not the engine annualization or a new screening metric" in notice
        for notice in detail.evidence.notices
    )
    assert {
        field.label: field.value for field in detail.evidence.validation_outcome
    }["Protected-data state"] == "Not used; development/reference evidence only"
    assert "Annualized return (recorded engine output)" in {
        field.label for field in detail.evidence.metrics
    }
    metric_values = {field.label: field.value for field in detail.evidence.metrics}
    assert metric_values["Annualized return (recorded engine output)"] == (
        f"{saved_metrics_by_run[f'{plan}-long']['annualized_return']:.2%}"
    )
    assert "Calendar CAGR (derived from recorded coverage)" in metric_values
    assert not any("integrity" in warning.lower() for warning in detail.warnings)
    selected_run = next(
        run
        for run in FixtureRunService(database=database).recent_runs(limit=10)
        if run.run_id == f"{plan}-long"
    )
    rendered = str(_run_detail_panel(selected_run, detail=detail))
    assert "Development/reference only" in rendered
    assert "Promotion is blocked" in rendered
    assert "Open exact saved-run link" in rendered
    assert f"run_id={plan}-long" in rendered
    assert "Recorded MES assumptions" in rendered
    assert "MES contract(s)" in rendered
    assert "$5.0 per MES index point" in rendered
    assert "$0.62 per contract per side" in rendered
    assert "engine outputs under these persisted backtest costs" in rendered
    assert "Fixture-only" not in rendered
    assert "Research fixture" not in rendered


def test_calendar_cagr_uses_only_recorded_return_and_coverage() -> None:
    expected = pytest.approx(0.007823193067260314)
    assert _calendar_cagr(
        0.0542477,
        "2019-05-05T22:00:00+00:00..2026-02-13T21:55:00+00:00",
    ) == expected
    assert _calendar_cagr(
        0.0542477,
        "2019-05-05T22:00:00+00:00/2026-02-13T21:55:00+00:00",
    ) == expected


@pytest.mark.parametrize(
    ("total_return", "actual_coverage"),
    [
        (-1.0, "2020-01-01..2021-01-01"),
        (float("nan"), "2020-01-01..2021-01-01"),
        (True, "2020-01-01..2021-01-01"),
        (
            1e308,
            "2020-01-01T00:00:00+00:00..2020-01-01T00:00:01+00:00",
        ),
        (0.05, None),
        (0.05, "not-recorded"),
        (0.05, "2021-01-01..2020-01-01"),
        (0.05, "2020-01-01..2020-01-01"),
        (0.05, "2020-01-01T00:00:00+00:00..2021-01-01"),
    ],
)
def test_calendar_cagr_fails_closed_for_invalid_persisted_inputs(
    total_return: object,
    actual_coverage: object,
) -> None:
    assert _calendar_cagr(total_return, actual_coverage) is None


def test_second_direction_failure_is_terminal_without_retry_and_keeps_first_success(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    database, outcome = _run(
        tmp_path,
        plan="reference",
        executor=_fake_executor(calls, fail_direction="short"),
        portfolio_builder=_portfolio_builder([]),
    )

    assert outcome.exit_code == 1
    assert calls == ["longonly", "shortonly"]
    service = PersistenceService(database)
    try:
        assert service.runs.get("reference-long").status == RunStatus.SUCCEEDED
        failed = service.runs.get("reference-short")
        assert failed is not None
        assert failed.status == RunStatus.FAILED
        assert "without retry" in (failed.error_summary or "")
        events = service.events.list_for_run("reference-short")
        assert [event.event_type for event in events] == [
            RunEventType.RUN_CREATED,
            RunEventType.RUN_STARTED,
            RunEventType.RUN_FAILED,
        ]
        assert service.results.list_parameter_results("reference-short") == ()
    finally:
        service.close()


def test_manifest_failure_marks_runs_failed_without_false_success_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fail_manifest(self, manifest) -> None:
        del self, manifest
        raise RuntimeError("injected manifest persistence failure")

    monkeypatch.setattr(PersistenceService, "persist_run_manifest", fail_manifest)
    database, outcome = _run(
        tmp_path,
        plan="reference",
        executor=_fake_executor(calls),
        portfolio_builder=_portfolio_builder([]),
    )

    assert outcome.exit_code == 1
    assert calls == ["longonly", "shortonly"]
    service = PersistenceService(database)
    try:
        for prepared in outcome.runs:
            run = service.runs.get(prepared.run_id)
            assert run is not None
            assert run.status == RunStatus.FAILED
            assert "manifest persistence failure" in (run.error_summary or "")
            summary_path = (
                tmp_path
                / "state"
                / "artifacts"
                / prepared.run_id
                / "run_summary.json"
            )
            summary = json.loads(summary_path.read_text())
            assert summary["status_at_artifact_capture"] == RunStatus.RUNNING.value
            assert "terminal_status" not in summary
            assert service.read_persisted_run_manifest(prepared.run_id) is None
    finally:
        service.close()


def test_both_runs_exist_before_loader_and_no_compute_starts_on_data_failure(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "ordering.sqlite3"
    executor_calls: list[str] = []

    def failing_loader():
        service = PersistenceService(database)
        try:
            runs = service.runs.list(stage=RunStage.SCREENING)
            assert {run.run_id for run in runs} == {"order-long", "order-short"}
            assert all(run.status == RunStatus.CREATED for run in runs)
            assert all(len(service.events.list_for_run(run.run_id)) == 1 for run in runs)
        finally:
            service.close()
        raise RuntimeError("injected data verification failure")

    outcome = run_durable_screening(
        plan="reference",
        database=database,
        artifact_root=tmp_path,
        run_ids={"long": "order-long", "short": "order-short"},
        data_loader=failing_loader,
        experiment_executor=_fake_executor(executor_calls),
        portfolio_builder=_portfolio_builder([]),
    )

    assert outcome.exit_code == 1
    assert executor_calls == []
    service = PersistenceService(database)
    try:
        for run_id in ("order-long", "order-short"):
            run = service.runs.get(run_id)
            assert run is not None
            assert run.status == RunStatus.FAILED
            assert "before computation" in (run.error_summary or "")
            assert [event.event_type for event in service.events.list_for_run(run_id)] == [
                RunEventType.RUN_CREATED,
                RunEventType.RUN_FAILED,
            ]
    finally:
        service.close()
