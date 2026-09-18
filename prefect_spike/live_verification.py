"""Explicit live Prefect-server verification for the compatibility spike.

This module never starts Prefect. It requires ``PREFECT_API_URL`` to point at an
already-running isolated self-hosted server.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import UUID

from orchestration import FixtureRunService
from orchestration.research_launch_claims import ResearchLaunchInvocationError
from persistence import PersistenceService, RunStatus, StrategyLifecycle
from persistence.models import normalized_configuration_document


@dataclass(frozen=True)
class LiveVerificationResult:
    quant_factory_run_id: str
    prefect_flow_run_id: str
    quant_factory_status: str
    prefect_state_name: str
    prefect_logs_found: bool
    attempt_count: int


@dataclass(frozen=True)
class LiveTimeoutResult:
    quant_factory_run_id: str
    prefect_flow_run_id: str
    quant_factory_status: str
    prefect_state_name: str
    error_summary: str | None


def _prepare_configuration(database_path: Path, configuration_id_seed: str) -> str:
    service = PersistenceService(database_path)
    try:
        service.register_strategy(
            strategy_id="prefect_fixture_strategy",
            strategy_version="1.0.0",
            display_name="Prefect Fixture Strategy",
            description="Synthetic Prefect compatibility fixture",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        document = normalized_configuration_document(
            experiment_id=f"prefect_fixture_{configuration_id_seed}",
            strategy_id="prefect_fixture_strategy",
            strategy_version="1.0.0",
            market_data={"kind": "none", "reason": "compatibility fixture"},
            parameters={"fixture": True},
            execution={"kind": "prefect_spike_fixture"},
            ranking={"columns": ("deterministic_value",), "ascending": (False,)},
            screening={"kind": "none"},
        )
        return service.upsert_configuration(document).configuration_id
    finally:
        service.close()


def _live_launch_key(kind: str, run_id: str) -> str:
    digest = hashlib.sha256(f"{kind}:{run_id}".encode("utf-8")).hexdigest()
    return f"launch_live_{digest}"


async def _read_prefect_evidence_once(flow_run_id: str) -> tuple[str, bool]:
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.filters import (
        FlowRunFilter,
        FlowRunFilterId,
        LogFilter,
        LogFilterFlowRunId,
        LogFilterTaskRunId,
        TaskRunFilter,
        TaskRunFilterFlowRunId,
    )

    flow_uuid = UUID(flow_run_id)
    async with get_client() as client:
        flow_run = await client.read_flow_run(flow_uuid)
        flow_logs = await client.read_logs(
            LogFilter(flow_run_id=LogFilterFlowRunId(any_=[flow_uuid])),
            limit=20,
        )
        task_runs = await client.read_task_runs(
            flow_run_filter=FlowRunFilter(id=FlowRunFilterId(any_=[flow_uuid])),
            task_run_filter=TaskRunFilter(flow_run_id=TaskRunFilterFlowRunId(any_=[flow_uuid])),
            limit=50,
        )
        task_run_ids = [task_run.id for task_run in task_runs]
        task_logs = []
        if task_run_ids:
            task_logs = await client.read_logs(
                LogFilter(task_run_id=LogFilterTaskRunId(any_=task_run_ids)),
                limit=20,
            )
    state_name = flow_run.state_name or (flow_run.state.name if flow_run.state else "")
    return state_name, bool(flow_logs or task_logs)


def _read_prefect_evidence_with_polling(
    flow_run_id: str,
    *,
    timeout_seconds: float = 3.0,
    poll_interval_seconds: float = 0.2,
) -> tuple[str, bool]:
    deadline = time.monotonic() + timeout_seconds
    state_name = ""
    while True:
        state_name, logs_found = asyncio.run(_read_prefect_evidence_once(flow_run_id))
        if logs_found or time.monotonic() >= deadline:
            return state_name, logs_found
        time.sleep(poll_interval_seconds)


def run_live_verification(
    *,
    database_path: str | Path,
    run_id: str = "prefect_live_fixture_run",
    attempt_marker_path: str | Path,
) -> LiveVerificationResult:
    if not os.environ.get("PREFECT_API_URL"):
        raise RuntimeError(
            "PREFECT_API_URL is required and must point at an already-started "
            "self-hosted Prefect server."
        )
    database = Path(database_path)
    configuration_id = _prepare_configuration(database, configuration_id_seed=run_id)
    launched = FixtureRunService(database=database).launch_fixture(
        idempotency_key=_live_launch_key("success", run_id),
        configuration_id=configuration_id,
        run_id=run_id,
        attempt_marker_path=attempt_marker_path,
    )
    if launched.run.prefect_flow_run_id is None:
        raise RuntimeError("durable live verification has no acknowledged Prefect identity")
    prefect_state_name, prefect_logs_found = _read_prefect_evidence_with_polling(
        launched.run.prefect_flow_run_id
    )
    service = PersistenceService(database)
    try:
        run = service.runs.get(launched.run.run_id)
        if run is None:
            raise RuntimeError(f"Quant Factory run was not persisted: {launched.run.run_id}")
        if run.status != RunStatus.SUCCEEDED:
            raise RuntimeError(f"Quant Factory run did not succeed: {run.status.value}")
    finally:
        service.close()
    return LiveVerificationResult(
        quant_factory_run_id=launched.run.run_id,
        prefect_flow_run_id=launched.run.prefect_flow_run_id,
        quant_factory_status=RunStatus.SUCCEEDED.value,
        prefect_state_name=prefect_state_name,
        prefect_logs_found=prefect_logs_found,
        attempt_count=launched.run.attempt_count,
    )


def run_live_timeout_verification(
    *,
    database_path: str | Path,
    run_id: str = "prefect_live_timeout_fixture_run",
    timeout_seconds: float = 1.0,
) -> LiveTimeoutResult:
    if not os.environ.get("PREFECT_API_URL"):
        raise RuntimeError(
            "PREFECT_API_URL is required and must point at an already-started "
            "self-hosted Prefect server."
        )
    database = Path(database_path)
    configuration_id = _prepare_configuration(database, configuration_id_seed=run_id)
    launch_service = FixtureRunService(database=database)
    try:
        launch_service.launch_fixture(
            idempotency_key=_live_launch_key("timeout", run_id),
            configuration_id=configuration_id,
            run_id=run_id,
            prefect_timeout_seconds=timeout_seconds,
        )
    except ResearchLaunchInvocationError:
        pass
    run = launch_service.get_run(run_id)
    if run is None:
        raise RuntimeError(f"Quant Factory run was not persisted: {run_id}")
    if run.prefect_flow_run_id is None:
        raise RuntimeError("durable timeout verification has no Prefect identity")
    if run.status == RunStatus.RUNNING.value:
        raise RuntimeError("Quant Factory timeout run was left running")
    if run.status != RunStatus.FAILED.value:
        raise RuntimeError(f"Quant Factory timeout run did not fail: {run.status}")
    prefect_state_name, _ = _read_prefect_evidence_with_polling(
        run.prefect_flow_run_id
    )
    normalized = prefect_state_name.strip().lower()
    if not any(marker in normalized for marker in ("failed", "timed", "crashed")):
        raise RuntimeError(
            f"Prefect timeout run did not report failure/timeout: {prefect_state_name}"
        )
    return LiveTimeoutResult(
        quant_factory_run_id=run_id,
        prefect_flow_run_id=run.prefect_flow_run_id,
        quant_factory_status=RunStatus.FAILED.value,
        prefect_state_name=prefect_state_name,
        error_summary=run.error_summary,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-path", required=True)
    parser.add_argument("--run-id", default="prefect_live_fixture_run")
    parser.add_argument("--attempt-marker-path", required=True)
    args = parser.parse_args()
    result = run_live_verification(
        database_path=args.database_path,
        run_id=args.run_id,
        attempt_marker_path=args.attempt_marker_path,
    )
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised manually with external server
    raise SystemExit(main())
