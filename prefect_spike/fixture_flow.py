"""Isolated Prefect fixture for the bounded compatibility spike.

The code in this package is deliberately not production orchestration. It
exercises a narrow seam between Prefect technical execution and Quant Factory's
local persistence model without downloading data, discovering strategies, or
running a backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Any

from persistence import EventSeverity, PersistenceService, RunEventType, RunStage, RunStatus
from persistence.database import transaction
from prefect_spike.spym_vectorbt_fixture import (
    execute_spym_21c_fixture_on_active_run,
    is_spym_21c_fixture_request,
)

try:  # pragma: no cover - unavailable behavior is covered by monkeypatching
    from prefect import flow, get_run_logger, task
    from prefect.context import get_run_context
except Exception:  # pragma: no cover
    flow = None
    get_run_context = None
    get_run_logger = None
    task = None
    PREFECT_AVAILABLE = False
else:
    PREFECT_AVAILABLE = True


PREFECT_TO_QF_STATUS = {
    "pending": RunStatus.CREATED,
    "scheduled": RunStatus.CREATED,
    "running": RunStatus.RUNNING,
    "completed": RunStatus.SUCCEEDED,
    "failed": RunStatus.FAILED,
    "crashed": RunStatus.FAILED,
    "cancelled": RunStatus.CANCELLED,
    "cancelling": RunStatus.CANCELLED,
    "timedout": RunStatus.FAILED,
    "timed_out": RunStatus.FAILED,
    "timeout": RunStatus.FAILED,
}


@dataclass(frozen=True)
class PrefectRunReference:
    """Technical execution identity returned by the spike adapter."""

    flow_run_id: str
    api_url: str | None = None


@dataclass(frozen=True)
class PrefectFixtureResult:
    """Separated Quant Factory and Prefect identities from a fixture run."""

    quant_factory_run_id: str
    prefect_flow_run_id: str
    configuration_id: str
    deterministic_value: int
    attempt_count: int
    prefect_api_url: str | None = None


class ControlledTransientFixtureError(RuntimeError):
    """Controlled fixture failure eligible for the bounded Slice 18C-1 retry."""


class ControlledFixtureCancellation(RuntimeError):
    """Controlled signal that a fixture acknowledged a cancellation request."""


def _state_name(state: object) -> str:
    if isinstance(state, str):
        return state
    name = getattr(state, "name", None)
    if name:
        return str(name)
    state_type = getattr(state, "type", None)
    if state_type is not None:
        value = getattr(state_type, "value", state_type)
        return str(value)
    raise ValueError(f"unsupported Prefect state object for spike: {state!r}")


def map_prefect_state_to_quant_factory(state: object) -> RunStatus:
    """Map a Prefect state object or name into the bounded run-status model."""

    raw_name = _state_name(state)
    normalized = raw_name.strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return PREFECT_TO_QF_STATUS[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported Prefect state for spike: {raw_name}") from exc


def ensure_prefect_available() -> None:
    if not PREFECT_AVAILABLE:
        raise RuntimeError("Prefect is not available in this environment")


def _configuration_identity(service: PersistenceService, configuration_id: str):
    configuration = service.configurations.get(configuration_id)
    if configuration is None:
        raise KeyError(f"unknown Quant Factory configuration: {configuration_id}")
    return configuration


def _run_environment(
    *,
    prefect_reference: PrefectRunReference,
    source: str,
    frozen_runtime_lineage: dict[str, Any] | None = None,
    reproduction_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    environment = {
        "prefect_spike": True,
        "prefect_identity_storage": "technical_run_environment",
        "prefect_flow_run_id": prefect_reference.flow_run_id,
        "prefect_reference_source": source,
    }
    if frozen_runtime_lineage is not None:
        environment["runtime_lineage"] = frozen_runtime_lineage
    if reproduction_metadata is not None:
        environment["reproduction"] = reproduction_metadata
    if prefect_reference.api_url:
        environment["prefect_api_url"] = prefect_reference.api_url
    return environment


def _create_or_reference_run(
    service: PersistenceService,
    *,
    configuration_id: str,
    quant_factory_run_id: str,
    prefect_reference: PrefectRunReference,
    reference_source: str,
    frozen_runtime_lineage: dict[str, Any] | None = None,
    reproduction_metadata: dict[str, Any] | None = None,
):
    existing = service.runs.get(quant_factory_run_id)
    if existing is not None:
        return existing
    configuration = _configuration_identity(service, configuration_id)
    return service.create_run_with_operator_event(
        configuration_id=configuration.configuration_id,
        strategy_id=configuration.strategy_id,
        strategy_version=configuration.strategy_version,
        stage=RunStage.FIXTURE,
        run_id=quant_factory_run_id,
        status=RunStatus.CREATED,
        environment=_run_environment(
            prefect_reference=prefect_reference,
            source=reference_source,
            frozen_runtime_lineage=frozen_runtime_lineage,
            reproduction_metadata=reproduction_metadata,
        ),
        event_type=RunEventType.RUN_CREATED,
        severity=EventSeverity.INFO,
        message="Run created for deterministic Prefect fixture execution.",
    )


def _persist_fixture_result(
    service: PersistenceService,
    *,
    quant_factory_run_id: str,
    configuration_id: str,
    prefect_flow_run_id: str,
    deterministic_value: int,
    attempt_count: int,
) -> None:
    with transaction(service.connection):
        service.require_active_run_for_completion(quant_factory_run_id)
        service.results.add_parameter_result(
            run_id=quant_factory_run_id,
            row_id=f"prefect_fixture:{quant_factory_run_id}",
            normalized_parameters={"configuration_id": configuration_id},
            metrics={
                "deterministic_value": deterministic_value,
                "attempt_count": attempt_count,
            },
            ranking_position=1,
            screening_status="infrastructure_fixture",
            rejection_reasons="",
        )


def acknowledge_fixture_cancellation(
    service: PersistenceService,
    *,
    quant_factory_run_id: str,
) -> None:
    """Cooperatively acknowledge a durable request before completion output."""
    if service.cancellation_requested(quant_factory_run_id):
        service.acknowledge_run_cancellation(quant_factory_run_id)
        raise ControlledFixtureCancellation("fixture cancellation acknowledged")


def reconcile_quant_factory_run_status(
    service: PersistenceService,
    *,
    quant_factory_run_id: str,
    prefect_state: object,
    error_summary: str | None = None,
):
    """Apply the bounded Prefect-to-Quant-Factory status mapping to one run."""

    target_status = map_prefect_state_to_quant_factory(prefect_state)
    current = service.runs.get(quant_factory_run_id)
    if current is None:
        raise KeyError(f"unknown run {quant_factory_run_id}")
    if current.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
        return current
    if target_status == RunStatus.CREATED:
        return current
    if current.status == RunStatus.CREATED and target_status in {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }:
        service.transition_run_with_operator_event(
            run_id=quant_factory_run_id,
            status=RunStatus.RUNNING,
            event_type=RunEventType.RUN_STARTED,
            severity=EventSeverity.INFO,
            message="Run started through Prefect fixture execution.",
        )
        current = service.runs.get(quant_factory_run_id)
    if current is not None and current.status != target_status:
        event_type, severity, message = {
            RunStatus.RUNNING: (
                RunEventType.RUN_STARTED,
                EventSeverity.INFO,
                "Run started through Prefect fixture execution.",
            ),
            RunStatus.SUCCEEDED: (
                RunEventType.RUN_SUCCEEDED,
                EventSeverity.INFO,
                "Run completed successfully.",
            ),
            RunStatus.FAILED: (
                RunEventType.RUN_FAILED,
                EventSeverity.ERROR,
                "Run failed; see the Prefect reference for technical details.",
            ),
            RunStatus.CANCELLED: (
                RunEventType.RUN_CANCELLED,
                EventSeverity.ERROR,
                "Run was cancelled.",
            ),
        }[target_status]
        return service.transition_run_with_operator_event(
            run_id=quant_factory_run_id,
            status=target_status,
            event_type=event_type,
            severity=severity,
            message=message,
            error_summary=error_summary if target_status == RunStatus.FAILED else None,
        )
    return current


def deterministic_fixture_body(
    *,
    database_path: str | Path,
    configuration_id: str,
    quant_factory_run_id: str,
    prefect_flow_run_id: str,
    deterministic_value: int = 1729,
    prefect_api_url: str | None = None,
    fail_after_run_start: bool = False,
    controlled_transient_failures: int = 0,
    retry_pending: bool = False,
    saved_parameters: object | None = None,
    saved_execution_assumptions: object | None = None,
    frozen_runtime_lineage: dict[str, Any] | None = None,
    reproduction_metadata: dict[str, Any] | None = None,
) -> PrefectFixtureResult:
    """Run the database side effects without requiring a Prefect server."""

    service = PersistenceService(database_path)
    try:
        run = _create_or_reference_run(
            service,
            configuration_id=configuration_id,
            quant_factory_run_id=quant_factory_run_id,
            prefect_reference=PrefectRunReference(
                flow_run_id=prefect_flow_run_id,
                api_url=prefect_api_url,
            ),
            reference_source="controlled_input",
            frozen_runtime_lineage=frozen_runtime_lineage,
            reproduction_metadata=reproduction_metadata,
        )
        run = service.increment_run_attempt(run.run_id)
        reconcile_quant_factory_run_status(
            service,
            quant_factory_run_id=quant_factory_run_id,
            prefect_state="Running",
        )
        if run.attempt_count <= controlled_transient_failures:
            raise ControlledTransientFixtureError("controlled transient fixture failure")
        if fail_after_run_start:
            raise RuntimeError("controlled Prefect fixture failure")
        acknowledge_fixture_cancellation(
            service,
            quant_factory_run_id=quant_factory_run_id,
        )
        if is_spym_21c_fixture_request(
            saved_parameters=saved_parameters,
            saved_execution_assumptions=saved_execution_assumptions,
        ):
            if not isinstance(saved_execution_assumptions, dict):
                raise RuntimeError("SPYM fixture requires saved execution assumptions")
            deterministic_value = execute_spym_21c_fixture_on_active_run(
                service,
                quant_factory_run_id=quant_factory_run_id,
                configuration_id=configuration_id,
                saved_execution_assumptions=saved_execution_assumptions,
                database_path=database_path,
                cancellation_check=lambda: acknowledge_fixture_cancellation(
                    service,
                    quant_factory_run_id=quant_factory_run_id,
                ),
            )
            reconcile_quant_factory_run_status(
                service,
                quant_factory_run_id=quant_factory_run_id,
                prefect_state="Completed",
            )
            return PrefectFixtureResult(
                quant_factory_run_id=quant_factory_run_id,
                prefect_flow_run_id=prefect_flow_run_id,
                configuration_id=configuration_id,
                deterministic_value=deterministic_value,
                attempt_count=run.attempt_count,
                prefect_api_url=prefect_api_url,
            )
        _persist_fixture_result(
            service,
            quant_factory_run_id=quant_factory_run_id,
            configuration_id=configuration_id,
            prefect_flow_run_id=prefect_flow_run_id,
            deterministic_value=deterministic_value,
            attempt_count=run.attempt_count,
        )
        reconcile_quant_factory_run_status(
            service,
            quant_factory_run_id=quant_factory_run_id,
            prefect_state="Completed",
        )
        return PrefectFixtureResult(
            quant_factory_run_id=quant_factory_run_id,
            prefect_flow_run_id=prefect_flow_run_id,
            configuration_id=configuration_id,
            deterministic_value=deterministic_value,
            attempt_count=run.attempt_count,
            prefect_api_url=prefect_api_url,
        )
    except (ControlledTransientFixtureError, ControlledFixtureCancellation):
        if retry_pending:
            raise
        reconcile_quant_factory_run_status(
            service,
            quant_factory_run_id=quant_factory_run_id,
            prefect_state="Failed",
            error_summary="controlled transient fixture failure",
        )
        raise
    except Exception as exc:
        if service.runs.get(quant_factory_run_id) is not None:
            reconcile_quant_factory_run_status(
                service,
                quant_factory_run_id=quant_factory_run_id,
                prefect_state="Failed",
                error_summary=str(exc),
            )
        raise
    finally:
        service.close()


if PREFECT_AVAILABLE:

    @task(retries=1, retry_delay_seconds=0, log_prints=True)
    def deterministic_retry_task(attempt_marker_path: str | None = None) -> dict[str, int]:
        logger = get_run_logger()
        if attempt_marker_path:
            marker = Path(attempt_marker_path)
            if not marker.exists():
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text("first-attempt-failed\n", encoding="utf-8")
                logger.warning("controlled first-attempt failure for Prefect spike")
                raise RuntimeError("controlled first-attempt failure")
        logger.info("deterministic Prefect spike task completed")
        return {"deterministic_value": 1729}

    @task(timeout_seconds=0.2)
    def timeout_probe_task(seconds: float) -> str:
        time.sleep(seconds)
        return "completed"

    @flow(name="quant-factory-prefect-compatibility-fixture", log_prints=True)
    def prefect_fixture_flow(
        *,
        database_path: str,
        configuration_id: str,
        quant_factory_run_id: str,
        attempt_marker_path: str | None = None,
        fail_after_run_start: bool = False,
        timeout_seconds: float | None = None,
        saved_parameters: object | None = None,
        saved_execution_assumptions: object | None = None,
        frozen_runtime_lineage: dict[str, Any] | None = None,
        reproduction_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        logger = get_run_logger()
        context = get_run_context()
        prefect_flow_run_id = str(context.flow_run.id)
        prefect_api_url = os.environ.get("PREFECT_API_URL")
        service = PersistenceService(database_path)
        try:
            _create_or_reference_run(
                service,
                configuration_id=configuration_id,
                quant_factory_run_id=quant_factory_run_id,
                prefect_reference=PrefectRunReference(
                    flow_run_id=prefect_flow_run_id,
                    api_url=prefect_api_url,
                ),
                reference_source="prefect_context",
                frozen_runtime_lineage=frozen_runtime_lineage,
                reproduction_metadata=reproduction_metadata,
            )
            run = service.increment_run_attempt(quant_factory_run_id)
            logger.info(
                "Quant Factory run linked to Prefect flow run",
                extra={
                    "quant_factory_run_id": quant_factory_run_id,
                    "prefect_flow_run_id": prefect_flow_run_id,
                },
            )
            reconcile_quant_factory_run_status(
                service,
                quant_factory_run_id=quant_factory_run_id,
                prefect_state="Running",
            )
            if fail_after_run_start:
                raise RuntimeError("controlled Prefect fixture failure")
            if timeout_seconds is not None:
                timeout_probe_task(timeout_seconds)
            acknowledge_fixture_cancellation(
                service,
                quant_factory_run_id=quant_factory_run_id,
            )
            if is_spym_21c_fixture_request(
                saved_parameters=saved_parameters,
                saved_execution_assumptions=saved_execution_assumptions,
            ):
                if not isinstance(saved_execution_assumptions, dict):
                    raise RuntimeError("SPYM fixture requires saved execution assumptions")
                deterministic_value = execute_spym_21c_fixture_on_active_run(
                    service,
                    quant_factory_run_id=quant_factory_run_id,
                    configuration_id=configuration_id,
                    saved_execution_assumptions=saved_execution_assumptions,
                    database_path=database_path,
                    cancellation_check=lambda: acknowledge_fixture_cancellation(
                        service,
                        quant_factory_run_id=quant_factory_run_id,
                    ),
                )
                reconcile_quant_factory_run_status(
                    service,
                    quant_factory_run_id=quant_factory_run_id,
                    prefect_state="Completed",
                )
                return {
                    "quant_factory_run_id": quant_factory_run_id,
                    "prefect_flow_run_id": prefect_flow_run_id,
                    "configuration_id": configuration_id,
                    "deterministic_value": deterministic_value,
                    "attempt_count": run.attempt_count,
                    "prefect_api_url": prefect_api_url,
                }
            task_result = deterministic_retry_task(attempt_marker_path)
            _persist_fixture_result(
                service,
                quant_factory_run_id=quant_factory_run_id,
                configuration_id=configuration_id,
                prefect_flow_run_id=prefect_flow_run_id,
                deterministic_value=int(task_result["deterministic_value"]),
                attempt_count=run.attempt_count,
            )
            reconcile_quant_factory_run_status(
                service,
                quant_factory_run_id=quant_factory_run_id,
                prefect_state="Completed",
            )
            return {
                "quant_factory_run_id": quant_factory_run_id,
                "prefect_flow_run_id": prefect_flow_run_id,
                "configuration_id": configuration_id,
                "deterministic_value": int(task_result["deterministic_value"]),
                "attempt_count": run.attempt_count,
                "prefect_api_url": prefect_api_url,
            }
        except ControlledFixtureCancellation:
            raise
        except Exception as exc:
            logger.exception("Prefect compatibility fixture failed")
            state_name = "TimedOut" if timeout_seconds is not None else "Failed"
            reconcile_quant_factory_run_status(
                service,
                quant_factory_run_id=quant_factory_run_id,
                prefect_state=state_name,
                error_summary=str(exc),
            )
            raise
        finally:
            service.close()


def run_prefect_fixture_flow(
    *,
    database_path: str | Path,
    configuration_id: str,
    quant_factory_run_id: str,
    attempt_marker_path: str | Path | None = None,
    fail_after_run_start: bool = False,
    timeout_seconds: float | None = None,
    saved_parameters: object | None = None,
    saved_execution_assumptions: object | None = None,
    frozen_runtime_lineage: dict[str, Any] | None = None,
    reproduction_metadata: dict[str, Any] | None = None,
) -> PrefectFixtureResult:
    """Execute the isolated Prefect fixture flow and return separated IDs."""

    ensure_prefect_available()
    if "PREFECT_API_URL" not in os.environ:
        raise RuntimeError(
            "PREFECT_API_URL is required for live Prefect spike verification; "
            "this adapter never starts an ephemeral server automatically."
        )
    assert prefect_fixture_flow is not None
    result = prefect_fixture_flow(
        database_path=str(database_path),
        configuration_id=configuration_id,
        quant_factory_run_id=quant_factory_run_id,
        attempt_marker_path=str(attempt_marker_path) if attempt_marker_path else None,
        fail_after_run_start=fail_after_run_start,
        timeout_seconds=timeout_seconds,
        saved_parameters=saved_parameters,
        saved_execution_assumptions=saved_execution_assumptions,
        frozen_runtime_lineage=frozen_runtime_lineage,
        reproduction_metadata=reproduction_metadata,
    )
    return PrefectFixtureResult(**result)


if not PREFECT_AVAILABLE:
    prefect_fixture_flow = None
    deterministic_retry_task = None
    timeout_probe_task = None
