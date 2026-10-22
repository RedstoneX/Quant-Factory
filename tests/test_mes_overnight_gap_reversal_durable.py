"""Durable-boundary tests for the single fixed R11 MES development screen."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pandas as pd
import pytest

import backtesting.run_mes_overnight_gap_reversal_durable as durable
from test_mes_overnight_gap_reversal import _data as mes_gap_data, databento_frame, write_mes_catalog
import prefect_spike.mes_overnight_gap_reversal_flow as mes_flow
from backtesting.run_mes_overnight_gap_reversal import (
    MESGapInputs,
    load_mes_gap_inputs,
    saved_configuration_document,
)
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
    MES_OVERNIGHT_GAP_REVERSAL_SPEC,
    MESMappingInterval,
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
        "vectorbtpro": {"available": True, "version": "2026.10.5"},
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


def _catalog(tmp_path: Path) -> dict[str, Path]:
    """Four December-2023 sessions with two gap trades, in the vendor parquet schema."""
    return write_mes_catalog(tmp_path, databento_frame(mes_gap_data()))


def _preflight(database: Path, tmp_path: Path) -> durable.MESGapPreflight:
    catalog = _catalog(tmp_path)
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
        dataset_path=catalog["dataset_path"],
        locations_path=catalog["locations_path"],
        manifest_dir=catalog["manifest_dir"],
        runtime_lineage=_runtime_lineage(),
        canonical_git={
            "remote_url": durable.CANONICAL_REMOTE,
            "branch": "main",
            "head": "b" * 40,
            "origin_main": "b" * 40,
            "remote_main": "b" * 40,
        },
    )


def _inputs(preflight: durable.MESGapPreflight) -> MESGapInputs:
    return load_mes_gap_inputs(
        mapping_response=preflight.mapping_response,
        manifest_dir=preflight.manifest_dir,
        locations_path=preflight.locations_path,
    )


def test_preflight_requires_credential_before_creating_any_claim_or_run(
    monkeypatch, tmp_path: Path
) -> None:
    database = tmp_path / "state" / "preflight.sqlite3"
    catalog = _catalog(tmp_path)
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DATABENTO_API_KEY"):
        durable._preflight_mes_screen(
            database=database,
            manifest_dir=catalog["manifest_dir"],
            locations_path=catalog["locations_path"],
        )

    assert not database.exists()


def test_operator_entrypoint_hard_pins_identity_and_requires_canonical_main(
    monkeypatch,
) -> None:
    assert durable.FAILED_ATTEMPT_IDEMPOTENCY_KEY == "r11_mes_gap_20190506_20231229_v1"
    assert durable.FIXED_IDEMPOTENCY_KEY == "r11_mes_gap_20190506_20231229_v2"
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


@pytest.mark.licensed_vectorbt
def test_preflight_saves_exact_configuration_without_persisting_secret(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "preflight-success.sqlite3"
    catalog = _catalog(tmp_path)
    seen = []
    result = durable._preflight_mes_screen(
        database=database,
        manifest_dir=catalog["manifest_dir"],
        locations_path=catalog["locations_path"],
        api_key="owned-test-secret",
        mapping_resolver=lambda key: seen.append(key) or _mapping_response(),
        runtime_lineage_provider=_runtime_lineage,
        canonical_checkout_verifier=lambda: {
            "remote_url": durable.CANONICAL_REMOTE,
            "branch": "main",
            "head": "b" * 40,
            "origin_main": "b" * 40,
            "remote_main": "b" * 40,
        },
    )

    assert seen == ["owned-test-secret"]
    assert result.dataset_path == catalog["dataset_path"]
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
        manifest_dir=catalog["manifest_dir"],
        locations_path=catalog["locations_path"],
        api_key="owned-test-secret",
        mapping_resolver=lambda key: _mapping_response(),
        runtime_lineage_provider=_runtime_lineage,
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


@pytest.mark.licensed_vectorbt
def test_screened_out_launch_persists_one_successful_screen_and_replay_is_noop(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "screen.sqlite3"
    preflight = _preflight(database, tmp_path)
    calls = []

    def loader():
        calls.append("load")
        return _inputs(preflight)

    def executor(inputs):
        calls.append("execute")
        return durable._MESGapDurableRuntime._execute(inputs)

    runtime = durable._MESGapDurableRuntime(
        database=database,
        artifact_root=tmp_path,
        preflight=preflight,
        loader=loader,
        executor=executor,
        dispatcher_instance_id="d9f7d4e8-588b-44ef-8366-eb4ea46d79c6",
    )
    # The real Prefect flow runs in-process and binds its own flow-run id.
    first = runtime.launch()
    second = runtime.launch()

    assert first.claim.created is True
    assert first.claim.submission.idempotency_key == durable.FIXED_IDEMPOTENCY_KEY
    assert first.dispatch.invoked is True
    assert isinstance(first.dispatch.value, durable.MESDurableScreenOutcome)
    assert first.dispatch.value.screening_status == "screened_out"
    assert second.claim.created is False
    assert second.dispatch.invoked is False
    assert calls == ["load", "execute"]
    assert UUID(first.dispatch.submission.prefect_flow_run_id or "")  # a real flow-run id was bound
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
        environment = json.loads(runs[0].environment_json)
        assert environment["recovery_of"] == durable.FAILED_ATTEMPT_IDEMPOTENCY_KEY
        assert environment["recovery_reason"] == "predicate_loader_index_contract"
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
        loader=lambda: _inputs(preflight),
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
