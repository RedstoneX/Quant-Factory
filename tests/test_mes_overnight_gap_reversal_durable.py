"""Durable-boundary tests for the single fixed R11 MES development screen."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pandas as pd
import pytest

import backtesting.run_mes_overnight_gap_reversal_durable as durable
import prefect_spike.mes_overnight_gap_reversal_flow as mes_flow
from backtesting.run_mes_overnight_gap_reversal import (
    MESGapInputs,
    MESGapScreenExecution,
    SCREENING_CONFIG,
    execution_assumptions,
    saved_configuration_document,
)
from backtesting.screening import screen_metrics
from orchestration import ResearchLaunchInvocationError
from persistence import (
    PersistenceService,
    ResearchSubmissionState,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from strategies.mes_overnight_gap_reversal import (
    FEE_PER_SIDE,
    MES_OVERNIGHT_GAP_REVERSAL_SPEC,
    MESGapSignalBundle,
    MESGapTrade,
    MESMappingInterval,
    SignalResult,
    mes_mapping_checksum,
)


def _runtime_lineage() -> dict:
    document = {
        "git": {
            "commit_available": True,
            "commit_sha": "b" * 40,
            "dirty_available": True,
            "dirty_state": "clean",
            "dirty_entry_count": 0,
        },
        "python": {
            "implementation": "CPython",
            "version": "3.12.3",
            "cache_tag": "cpython-312",
        },
        "vectorbtpro": {"available": True, "version": "2026.4.7"},
        "packages": {"fingerprint": "c" * 64, "count": 1},
        "platform": {"system": "Linux", "machine": "x86_64"},
    }
    document["runtime_identity"] = hashlib.sha256(
        canonical_json(document).encode("utf-8")
    ).hexdigest()
    return document


def _mapping_response() -> dict:
    return {
        "result": {
            "MES.c.0": [
                {"d0": "2019-05-06", "d1": "2023-12-30", "s": "12345"}
            ]
        },
        "symbols": ["MES.c.0"],
        "partial": [],
        "not_found": [],
        "message": "OK",
        "status": 0,
    }


def _register_configuration(database: Path) -> str:
    service = PersistenceService(database)
    try:
        spec = MES_OVERNIGHT_GAP_REVERSAL_SPEC
        service.register_strategy(
            strategy_id=spec.identity.strategy_id,
            strategy_version=spec.identity.version,
            display_name=spec.identity.name,
            description=spec.identity.description,
            lifecycle=StrategyLifecycle.CANDIDATE,
        )
        return service.upsert_configuration(
            saved_configuration_document()
        ).configuration_id
    finally:
        service.close()


def _preflight(database: Path, tmp_path: Path) -> durable.MESGapPreflight:
    intervals = (
        MESMappingInterval(
            pd.Timestamp("2019-05-06").date(),
            pd.Timestamp("2023-12-30").date(),
            "12345",
        ),
    )
    return durable.MESGapPreflight(
        configuration_id=_register_configuration(database),
        mapping_response=_mapping_response(),
        mapping_intervals=intervals,
        mapping_checksum=mes_mapping_checksum(intervals),
        dataset_path=tmp_path / "MES.parquet",
        locations_path=tmp_path / "locations.toml",
        manifest_dir=tmp_path,
        runtime_lineage=_runtime_lineage(),
        canonical_git={
            "remote_url": durable.CANONICAL_REMOTE,
            "branch": "main",
            "head": "b" * 40,
            "origin_main": "b" * 40,
            "remote_main": "b" * 40,
        },
    )


def _inputs(preflight: durable.MESGapPreflight, tmp_path: Path) -> MESGapInputs:
    index = pd.DatetimeIndex(
        ["2023-12-21T14:35:00Z", "2023-12-21T15:00:00Z"]
    )
    data = pd.DataFrame(
        {
            "Open": [101.0, 100.0],
            "High": [101.5, 100.5],
            "Low": [100.5, 99.5],
            "Close": [101.0, 100.0],
            "Volume": [10.0, 10.0],
        },
        index=index,
    )
    manifest = SimpleNamespace(
        metadata={
            "dataset_id": durable.DATASET_ID,
            "status": "validated",
            "sha256": durable.EXPECTED_DATASET_SHA256,
            "row_count": durable.EXPECTED_DATASET_ROWS,
        },
        sha256=durable.EXPECTED_DATASET_SHA256,
        status="validated",
    )
    return MESGapInputs(
        data=data,
        audit=SimpleNamespace(),
        manifest=manifest,
        dataset_path=tmp_path / "MES.parquet",
        mapping_intervals=preflight.mapping_intervals,
        mapping_checksum=preflight.mapping_checksum,
    )


def _execution(inputs: MESGapInputs) -> MESGapScreenExecution:
    entry = inputs.data.index[0]
    exit_ = inputs.data.index[1]
    trade = MESGapTrade(
        session_date="2023-12-21",
        prior_session_date="2023-12-20",
        mapping_instrument_id="12345",
        gap=0.01,
        direction="short",
        direction_value=-1,
        entry_timestamp=entry,
        exit_timestamp=exit_,
        entry_raw=101.0,
        exit_raw=100.0,
        entry_fill=100.75,
        exit_fill=100.25,
        fee_per_side=FEE_PER_SIDE,
        net_pnl=1.26,
    )
    metadata = {
        "calendar_session_count": 2,
        "completed_trade_count": 1,
        "excluded_session_count": 1,
        "exclusion_reason_counts": {"missing_prior_session_boundary": 1},
        "excluded_sessions": (
            {
                "session_date": "2023-12-20",
                "reason": "missing_prior_session_boundary",
            },
        ),
    }
    signals = SignalResult(
        entries=pd.Series(False, index=inputs.data.index),
        exits=pd.Series(False, index=inputs.data.index),
        short_entries=pd.Series([True, False], index=inputs.data.index),
        short_exits=pd.Series([False, True], index=inputs.data.index),
        parameters={},
        metadata=metadata,
    )
    bundle = MESGapSignalBundle(
        signals=signals,
        scheduled_sessions=("2023-12-20", "2023-12-21"),
        completed_trades=(trade,),
        excluded_sessions=metadata["excluded_sessions"],
        daily_net_pnl=pd.Series(
            [0.0, 1.26], index=pd.DatetimeIndex(["2023-12-20", "2023-12-21"])
        ),
    )
    metrics = {
        "number_of_trades": 1,
        "total_return": 0.0000126,
        "annualized_return": 0.001588,
        "sharpe_ratio": 0.2,
        "max_drawdown": 0.0,
        "win_rate": 1.0,
    }
    screened = screen_metrics(
        experiment_id="r11_mes_overnight_gap_reversal_development",
        strategy_id=MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.strategy_id,
        strategy_version=MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.version,
        parameters={},
        execution_assumptions=execution_assumptions(),
        metrics=metrics,
        config=SCREENING_CONFIG,
    )
    row = metrics | {
        "parameter_row_id": screened.parameter_row_id,
        "screening_status": "screened_out",
        "screening_passed_rule_count": screened.passed_rule_count,
        "screening_failed_rule_count": screened.failed_rule_count,
        "screening_rejection_reasons": " | ".join(screened.rejection_reasons),
    }
    result = SimpleNamespace(
        ranked_results=pd.DataFrame([row]),
        passing_results=pd.DataFrame([row]).iloc[0:0],
        screened_out_results=pd.DataFrame([row]),
        experiment_id="r11_mes_overnight_gap_reversal_development",
        strategy_id=MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.strategy_id,
        strategy_version=MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.version,
        evaluated_combinations=1,
        validation_results=({"gate_id": "licensed_engine", "status": "passed"},),
        screening_results=(screened,),
    )
    trades = pd.DataFrame(
        [
            {
                "Size": 1.0,
                "Entry Index": entry,
                "Exit Index": exit_,
                "Avg Entry Price": 503.75,
                "Avg Exit Price": 501.25,
                "Entry Fees": FEE_PER_SIDE,
                "Exit Fees": FEE_PER_SIDE,
                "PnL": 1.26,
                "Direction": "Short",
                "Status": "Closed",
            }
        ]
    )
    orders = pd.DataFrame(
        [
            {"Fill Index": entry, "Size": 1.0, "Price": 503.75, "Fees": FEE_PER_SIDE, "Side": "Sell"},
            {"Fill Index": exit_, "Size": 1.0, "Price": 501.25, "Fees": FEE_PER_SIDE, "Side": "Buy"},
        ]
    )
    portfolio = SimpleNamespace(
        trades=SimpleNamespace(records_readable=trades),
        orders=SimpleNamespace(records_readable=orders),
    )
    daily_equity = pd.Series(
        [100_000.0, 100_001.26],
        index=pd.DatetimeIndex(["2023-12-20", "2023-12-21"]),
        name="equity",
    )
    daily_returns = pd.Series(
        [0.0, 0.0000126], index=daily_equity.index, name="daily_return"
    )
    return MESGapScreenExecution(
        result=result,
        portfolio=portfolio,
        bundle=bundle,
        daily_equity=daily_equity,
        daily_returns=daily_returns,
    )


def test_preflight_requires_credential_before_creating_any_claim_or_run(
    monkeypatch, tmp_path: Path
) -> None:
    database = tmp_path / "state" / "preflight.sqlite3"
    manifest = SimpleNamespace(metadata={}, sha256="a" * 64)
    monkeypatch.setattr(durable, "load_dataset_manifest", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(durable, "assert_exact_mes_manifest", lambda value: None)
    monkeypatch.setattr(durable, "load_data_locations", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        durable, "verify_dataset_file", lambda *args, **kwargs: tmp_path / "MES.parquet"
    )

    with pytest.raises(RuntimeError, match="DATABENTO_API_KEY"):
        durable._preflight_mes_screen(database=database)

    assert not database.exists()


def test_operator_entrypoint_hard_pins_identity_and_requires_canonical_main(
    monkeypatch,
) -> None:
    assert tuple(inspect.signature(durable.launch_mes_screen).parameters) == (
        "locations_path",
    )
    assert tuple(inspect.signature(durable.preflight_mes_screen).parameters) == (
        "locations_path",
    )
    assert tuple(inspect.signature(durable._MESGapDurableRuntime.launch).parameters) == (
        "self",
    )
    values = {
        ("remote", "get-url", "origin"): durable.CANONICAL_REMOTE,
        ("symbolic-ref", "--short", "HEAD"): "main",
        ("rev-parse", "HEAD"): "b" * 40,
        ("rev-parse", "origin/main"): "b" * 40,
        ("ls-remote", "--exit-code", "origin", "refs/heads/main"): (
            f"{'b' * 40}\trefs/heads/main"
        ),
    }
    monkeypatch.setattr(durable, "_git_stdout", lambda *args: values[args])

    assert durable.verify_canonical_main_checkout()["head"] == "b" * 40
    values[("symbolic-ref", "--short", "HEAD")] = "codex/not-main"
    with pytest.raises(RuntimeError, match="latest canonical main"):
        durable.verify_canonical_main_checkout()


def test_preflight_saves_exact_configuration_without_persisting_secret(
    monkeypatch, tmp_path: Path
) -> None:
    database = tmp_path / "state" / "preflight-success.sqlite3"
    manifest = SimpleNamespace(metadata={}, sha256="a" * 64)
    monkeypatch.setattr(durable, "load_dataset_manifest", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(durable, "assert_exact_mes_manifest", lambda value: None)
    monkeypatch.setattr(durable, "load_data_locations", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        durable, "verify_dataset_file", lambda *args, **kwargs: tmp_path / "MES.parquet"
    )
    seen = []
    result = durable._preflight_mes_screen(
        database=database,
        api_key="owned-test-secret",
        mapping_resolver=lambda key: seen.append(key) or _mapping_response(),
        runtime_lineage_provider=_runtime_lineage,
        vectorbt_loader=lambda: SimpleNamespace(__version__="2026.4.7"),
        vectorbt_probe=lambda engine: seen.append("licensed-probe"),
        canonical_checkout_verifier=lambda: {
            "remote_url": durable.CANONICAL_REMOTE,
            "branch": "main",
            "head": "b" * 40,
            "origin_main": "b" * 40,
            "remote_main": "b" * 40,
        },
    )

    assert seen == ["licensed-probe", "owned-test-secret"]
    assert result.mapping_response == _mapping_response()
    assert "owned-test-secret" not in database.read_bytes().decode("utf-8", errors="ignore")
    service = PersistenceService(database)
    try:
        assert service.runs.list() == ()
        assert service.configurations.get(result.configuration_id) is not None
        service.update_strategy_lifecycle(
            MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.strategy_id,
            MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.version,
            lifecycle=StrategyLifecycle.REJECTED,
            active=False,
        )
    finally:
        service.close()
    durable._preflight_mes_screen(
        database=database,
        api_key="owned-test-secret",
        mapping_resolver=lambda key: _mapping_response(),
        runtime_lineage_provider=_runtime_lineage,
        vectorbt_loader=lambda: SimpleNamespace(__version__="2026.4.7"),
        vectorbt_probe=lambda engine: None,
        canonical_checkout_verifier=lambda: {
            "remote_url": durable.CANONICAL_REMOTE,
            "branch": "main",
            "head": "b" * 40,
            "origin_main": "b" * 40,
            "remote_main": "b" * 40,
        },
    )
    service = PersistenceService(database)
    try:
        strategy = service.strategies.get(
            MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.strategy_id,
            MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.version,
        )
        assert strategy is not None
        assert strategy.lifecycle == StrategyLifecycle.REJECTED
        assert strategy.active is False
    finally:
        service.close()


def test_screened_out_launch_persists_one_successful_screen_and_replay_is_noop(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "screen.sqlite3"
    preflight = _preflight(database, tmp_path)
    calls = []

    def loader():
        calls.append("load")
        return _inputs(preflight, tmp_path)

    def executor(inputs):
        calls.append("execute")
        return _execution(inputs)

    runtime = durable._MESGapDurableRuntime(
        database=database,
        artifact_root=tmp_path,
        preflight=preflight,
        loader=loader,
        executor=executor,
        dispatcher_instance_id="d9f7d4e8-588b-44ef-8366-eb4ea46d79c6",
    )
    flow_id = "7a08f11d-1cc1-445c-a82e-d8a51893456f"
    monkeypatch.setattr(
        runtime,
        "_prefect_adapter",
        lambda submission, _claims: runtime.execute_flow(
            submission=submission,
            prefect_flow_run_id=flow_id,
        ),
    )
    first = runtime.launch()
    second = runtime.launch()

    assert first.claim.created is True
    assert first.dispatch.invoked is True
    assert isinstance(first.dispatch.value, durable.MESDurableScreenOutcome)
    assert first.dispatch.value.screening_status == "screened_out"
    assert second.claim.created is False
    assert second.dispatch.invoked is False
    assert calls == ["load", "execute"]
    assert UUID(first.dispatch.submission.prefect_flow_run_id or "") == UUID(flow_id)
    assert runtime.reopen_completed_outcome(first.claim.run.run_id) == (
        durable.MESDurableScreenOutcome(
            run_id=first.claim.run.run_id,
            configuration_id=preflight.configuration_id,
            screening_status="screened_out",
        )
    )

    service = PersistenceService(database)
    try:
        runs = service.runs.list()
        assert len(runs) == 1
        assert runs[0].stage == RunStage.SCREENING
        assert runs[0].status == RunStatus.SUCCEEDED
        strategy = service.strategies.get(
            MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.strategy_id,
            MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.version,
        )
        assert strategy is not None
        assert strategy.lifecycle == StrategyLifecycle.REJECTED
        assert strategy.active is False
        submission = service.connection.execute(
            "SELECT state FROM research_run_submissions"
        ).fetchone()
        assert submission["state"] == ResearchSubmissionState.ACKNOWLEDGED.value
        assert len(service.results.list_parameter_results(runs[0].run_id)) == 1
        assert service.results.list_parameter_results(runs[0].run_id)[0].screening_status == "screened_out"
        assert service.results.get_data_provenance(runs[0].run_id) is not None
        assert service.results.get_execution_assumptions(runs[0].run_id) is not None
        artifacts = service.list_run_artifacts(runs[0].run_id)
        assert {item.logical_name for item in artifacts} == {
            "run_summary",
            "metrics",
            "parameter_results",
            "trades_and_orders",
            "equity_curve",
            "validation_evidence",
            "symbology_mapping",
            "dataset_manifest",
        }
        retrieved = service.retrieve_run_artifacts(
            runs[0].run_id, artifact_root=tmp_path
        )
        assert all(item.valid for item in retrieved.validations)
    finally:
        service.close()


def test_failure_after_prefect_binding_fails_run_without_success_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "failed.sqlite3"
    preflight = _preflight(database, tmp_path)
    runtime = durable._MESGapDurableRuntime(
        database=database,
        artifact_root=tmp_path,
        preflight=preflight,
        loader=lambda: _inputs(preflight, tmp_path),
        executor=lambda inputs: (_ for _ in ()).throw(RuntimeError("controlled failure")),
        dispatcher_instance_id="f6a61a77-d831-4b2d-94df-b54be0f14e20",
    )
    monkeypatch.setattr(
        runtime,
        "_prefect_adapter",
        lambda submission, _claims: runtime.execute_flow(
            submission=submission,
            prefect_flow_run_id="f8e490da-f73a-419d-947b-32181e937ee4",
        ),
    )

    with pytest.raises(ResearchLaunchInvocationError):
        runtime.launch()

    service = PersistenceService(database)
    try:
        runs = service.runs.list()
        assert len(runs) == 1
        assert runs[0].stage == RunStage.SCREENING
        assert runs[0].status == RunStatus.FAILED
        assert service.results.list_parameter_results(runs[0].run_id) == ()
        assert service.list_run_artifacts(runs[0].run_id) == ()
        assert service.read_persisted_run_manifest(runs[0].run_id) is None
    finally:
        service.close()


def test_prefect_boundary_forwards_the_actual_flow_identity(monkeypatch) -> None:
    observed = {}

    class Runtime:
        @staticmethod
        def execute_flow(**kwargs):
            observed.update(kwargs)
            return "done"

    submission = SimpleNamespace(run_id="qf-run")
    flow_id = "594c5dc8-51c0-4b7e-a00f-bbdf0a2f587d"
    monkeypatch.setattr(
        mes_flow.FlowRunContext,
        "get",
        lambda: SimpleNamespace(flow_run=SimpleNamespace(id=UUID(flow_id))),
    )

    result = mes_flow.run_mes_gap_screen_flow.fn(
        runtime=Runtime(), submission=submission
    )

    assert result == "done"
    assert observed == {
        "submission": submission,
        "prefect_flow_run_id": flow_id,
    }
