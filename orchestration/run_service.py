"""Minimum Slice 18A run service for deterministic fixture launches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import threading

from orchestration.research_launch_claims import (
    DurableResearchLaunchService,
    ResearchLaunchIntegrityError,
    ResearchLaunchRequest,
    new_dispatcher_instance_id,
)
from persistence import (
    ArtifactAvailability,
    ArtifactType,
    EventSeverity,
    ExperimentRunRecord,
    PersistenceService,
    ResearchLaunchOperation,
    ResearchRunSubmissionRecord,
    ResearchSubmissionState,
    RunEventRecord,
    RunEventType,
    RunStatus,
    StrategyLifecycle,
)
from persistence.database import database_path
from persistence.evidence_service import ValidationEvidenceArtifactService
from persistence.service import capture_runtime_lineage_document
from prefect_spike.fixture_flow import PrefectFixtureResult, run_prefect_fixture_flow

FixtureLauncher = Callable[..., PrefectFixtureResult]
MAX_FIXTURE_TIMEOUT_SECONDS = 3_600.0
_DISPATCHER_ID_LOCK = threading.Lock()
_DISPATCHER_ID_PID: int | None = None
_DISPATCHER_ID: str | None = None


def _boot_dispatcher_instance_id() -> str:
    """Return one UUID per process, rotating safely after a pre-fork preload."""

    global _DISPATCHER_ID_PID, _DISPATCHER_ID
    current_pid = os.getpid()
    with _DISPATCHER_ID_LOCK:
        if _DISPATCHER_ID_PID != current_pid or _DISPATCHER_ID is None:
            _DISPATCHER_ID_PID = current_pid
            _DISPATCHER_ID = new_dispatcher_instance_id()
        return _DISPATCHER_ID


class RunServiceError(RuntimeError):
    """Raised when the Slice 18A run service cannot launch a run safely."""


@dataclass(frozen=True)
class FixtureRetryPolicy:
    """Legacy-compatible policy shape; durable launch accepts one attempt only."""

    max_attempts: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("fixture retry max_attempts must be between 1 and 3")


@dataclass(frozen=True)
class RunSummary:
    """Dashboard-oriented run view without Prefect becoming authoritative."""

    run_id: str
    configuration_id: str
    strategy_id: str
    strategy_version: str
    stage: str
    status: str
    created_at: str
    started_at: str | None
    completed_at: str | None
    error_summary: str | None
    prefect_flow_run_id: str | None
    prefect_api_url: str | None
    attempt_count: int


@dataclass(frozen=True)
class RunEvent:
    """Concise append-only event for an operator-facing run view."""

    event_id: int
    run_id: str
    event_type: str
    timestamp: str
    severity: str
    message: str
    source: str


@dataclass(frozen=True)
class RunLaunchResult:
    """Result returned after launching or observing a terminal fixture failure."""

    run: RunSummary
    prefect_result: PrefectFixtureResult | None
    submission: ResearchRunSubmissionRecord | None = None
    invoked: bool = True


@dataclass(frozen=True)
class RunReproductionResult:
    """Dashboard-facing result for a new run derived from a persisted source run."""

    original: RunSummary
    reproduction: RunSummary
    comparison: tuple[dict[str, object], ...]
    notes: tuple[str, ...]


def _prefect_metadata(run: ExperimentRunRecord) -> tuple[str | None, str | None]:
    environment = json.loads(run.environment_json)
    return environment.get("prefect_flow_run_id"), environment.get("prefect_api_url")


def _summary(run: ExperimentRunRecord) -> RunSummary:
    prefect_flow_run_id, prefect_api_url = _prefect_metadata(run)
    return RunSummary(
        run_id=run.run_id,
        configuration_id=run.configuration_id,
        strategy_id=run.strategy_id,
        strategy_version=run.strategy_version,
        stage=run.stage.value,
        status=run.status.value,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_summary=run.error_summary,
        prefect_flow_run_id=prefect_flow_run_id,
        prefect_api_url=prefect_api_url,
        attempt_count=run.attempt_count,
    )


def _event(record: RunEventRecord) -> RunEvent:
    return RunEvent(
        event_id=record.event_id,
        run_id=record.run_id,
        event_type=record.event_type.value,
        timestamp=record.occurred_at,
        severity=record.severity.value,
        message=record.message,
        source=record.source,
    )


def _numeric_metric(document: dict[str, object], name: str) -> float | int | None:
    candidate = document.get(name)
    if isinstance(candidate, bool):
        return None
    if isinstance(candidate, int):
        return candidate
    if isinstance(candidate, float):
        return candidate if math.isfinite(candidate) else None
    return None


def _top_ranked_metrics(results: tuple[object, ...]) -> tuple[dict[str, float | int | None], str]:
    metrics: dict[str, float | int | None] = {
        "total_return": None,
        "annualized_return": None,
        "sharpe_ratio": None,
        "number_of_trades": None,
    }
    if not results:
        return metrics, "No persisted ranked result"

    selected = results[0]
    try:
        values = json.loads(selected.metrics_json)
    except (AttributeError, TypeError, json.JSONDecodeError):
        return metrics, "Top-ranked metrics unavailable"
    if not isinstance(values, dict):
        return metrics, "Top-ranked metrics unavailable"

    for name in metrics:
        metrics[name] = _numeric_metric(values, name)
    return metrics, f"Rank {selected.ranking_position} result"


def _registered_artifact_status(artifacts: tuple[object, ...]) -> str:
    if not artifacts:
        return "No registered artifacts"
    unavailable = [
        artifact.availability_state.value
        for artifact in artifacts
        if artifact.availability_state != ArtifactAvailability.AVAILABLE
    ]
    if unavailable:
        return "Registered artifacts need attention"
    return f"{len(artifacts)} registered artifacts"


def _registered_evidence_status(artifacts: tuple[object, ...]) -> str:
    evidence_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
    ]
    if not evidence_artifacts:
        return "No validation evidence"
    unavailable = [
        artifact.availability_state.value
        for artifact in evidence_artifacts
        if artifact.availability_state != ArtifactAvailability.AVAILABLE
    ]
    if unavailable:
        return "Validation evidence needs attention"
    return "Validation evidence registered"


def _evidence_outcome_status(
    service: PersistenceService,
    run: ExperimentRunRecord,
    artifacts: tuple[object, ...],
    *,
    artifact_root: str | Path | None,
) -> str:
    if run.stage.value in {"walk_forward", "monte_carlo", "robustness"}:
        if artifact_root is None:
            return "Evidence outcome unavailable"
        try:
            outcome = ValidationEvidenceArtifactService(service).stage_outcome(
                run.run_id,
                artifact_root=artifact_root,
            )
        except (KeyError, RuntimeError, ValueError) as exc:
            return f"Evidence invalid: {exc}"
        return outcome.status.replace("_", " ").title()
    if _registered_evidence_status(artifacts) == "Validation evidence registered":
        return "Evidence registered; outcome not applicable"
    return _registered_evidence_status(artifacts)


def _manifest_status(service: PersistenceService, run_id: str) -> str:
    if service.read_persisted_run_manifest(run_id) is None:
        return "Manifest missing"
    try:
        service.read_persisted_run_manifest_document(run_id)
    except (KeyError, TypeError, ValueError) as exc:
        return f"Manifest invalid: {exc}"
    return "Manifest persisted"


def _stage_label(stage: str) -> str:
    labels = {
        "fixture": "Fixture backtest",
        "walk_forward": "Walk-forward validation",
        "monte_carlo": "Monte Carlo validation",
        "robustness": "Robustness validation",
        "oos": "Out-of-sample evidence",
        "screening": "Screening",
    }
    return labels.get(stage, stage.replace("_", " ").title())


def _status_label(status: str) -> str:
    return status.replace("_", " ").title()


def _review_label(review: str | None) -> str:
    if review is None:
        return "Not reviewed"
    return review.replace("_", " ").title()


class FixtureRunService:
    """Replay-safe fixture launch service backed by ADR 0011 durable claims."""

    def __init__(
        self,
        *,
        database: str | Path | None = None,
        fixture_launcher: FixtureLauncher = run_prefect_fixture_flow,
        dispatcher_instance_id: str | None = None,
    ) -> None:
        self.database_path = database_path(database)
        self._fixture_launcher = fixture_launcher
        self._dispatcher_instance_id = (
            dispatcher_instance_id or _boot_dispatcher_instance_id()
        )

    def launch_fixture(
        self,
        *,
        idempotency_key: str | None = None,
        configuration_id: str,
        operation: ResearchLaunchOperation = ResearchLaunchOperation.RUN_TEST,
        source_run_id: str | None = None,
        source_lineage: dict[str, str] | None = None,
        run_id: str | None = None,
        attempt_marker_path: str | Path | None = None,
        fail_after_run_start: bool = False,
        retry_policy: FixtureRetryPolicy = FixtureRetryPolicy(),
        controlled_transient_failures: int = 0,
        timeout_seconds: float | None = None,
        prefect_timeout_seconds: float | None = None,
        reproduction_metadata: dict[str, object] | None = None,
    ) -> RunLaunchResult:
        if retry_policy.max_attempts != 1 or controlled_transient_failures:
            raise ValueError(
                "outer fixture-launch retries are disabled; Prefect owns retries "
                "inside one acknowledged flow"
            )
        self._validate_timeout(timeout_seconds)
        self._validate_timeout(prefect_timeout_seconds)
        try:
            normalized_operation = ResearchLaunchOperation(operation)
        except (TypeError, ValueError) as exc:
            raise ValueError("unsupported research launch operation") from exc
        if (
            reproduction_metadata is not None
            and normalized_operation != ResearchLaunchOperation.REPRODUCTION
        ):
            raise ValueError("reproduction metadata is valid only for reproduction")
        if idempotency_key is None:
            if run_id is None:
                raise ValueError(
                    "a browser-prepared idempotency key is required when no deterministic "
                    "fixture run ID is supplied"
                )
            digest = hashlib.sha256(
                f"{normalized_operation.value}:{run_id}".encode("utf-8")
            ).hexdigest()
            idempotency_key = f"launch_fixture_{digest}"

        claim_service = DurableResearchLaunchService(
            database=self.database_path,
            run_id_factory=(lambda: run_id) if run_id is not None else None,
        )
        existing = claim_service.get(idempotency_key)
        environment: dict[str, object] | None = None
        if existing is None:
            environment = {
                "prefect_spike": True,
                "runtime_lineage": capture_runtime_lineage_document(),
            }
            if reproduction_metadata is not None:
                environment["reproduction"] = reproduction_metadata
        claim = claim_service.claim(
            idempotency_key=idempotency_key,
            request=ResearchLaunchRequest(
                operation=normalized_operation,
                configuration_id=configuration_id,
                source_run_id=source_run_id,
                source_lineage=source_lineage,
            ),
            environment=environment,
        )

        if claim.submission.state != ResearchSubmissionState.CLAIMED:
            return RunLaunchResult(
                run=_summary(claim.run),
                prefect_result=None,
                submission=claim.submission,
                invoked=False,
            )

        try:
            saved_parameters, saved_execution_assumptions = self._launch_inputs(
                claim.submission.configuration_id
            )
            request_document = json.loads(claim.submission.canonical_request_json)
            persisted_source_lineage = request_document.get("source_lineage")
            if not isinstance(persisted_source_lineage, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in persisted_source_lineage.items()
            ):
                raise ResearchLaunchIntegrityError(
                    "durable research launch has invalid source lineage"
                )
            persisted_source_run_id = request_document.get("source_run_id")
            if persisted_source_run_id is not None and not isinstance(
                persisted_source_run_id, str
            ):
                raise ResearchLaunchIntegrityError(
                    "durable research launch has invalid source-run identity"
                )
            operation_kind = request_document.get("operation_kind")
            if not isinstance(operation_kind, str):
                raise ResearchLaunchIntegrityError(
                    "durable research launch has invalid operation identity"
                )
            run_environment = json.loads(claim.run.environment_json)
            if not isinstance(run_environment, dict):
                raise ResearchLaunchIntegrityError(
                    "durable research launch has invalid run environment"
                )
            frozen_runtime_lineage = run_environment.get("runtime_lineage")
            persisted_reproduction_metadata = run_environment.get("reproduction")
        except Exception as exc:
            raise RunServiceError("fixture launch preparation failed") from exc

        def invoke(submission: ResearchRunSubmissionRecord) -> PrefectFixtureResult:
            launch_kwargs: dict[str, object] = {
                "database_path": self.database_path,
                "idempotency_key": submission.idempotency_key,
                "configuration_id": submission.configuration_id,
                "quant_factory_run_id": submission.run_id,
                "canonical_request_json": submission.canonical_request_json,
                "request_fingerprint": submission.request_fingerprint,
                "operation_kind": operation_kind,
                "source_run_id": persisted_source_run_id,
                "source_lineage": persisted_source_lineage,
                "attempt_marker_path": attempt_marker_path,
                "fail_after_run_start": fail_after_run_start,
                "saved_parameters": saved_parameters,
                "saved_execution_assumptions": saved_execution_assumptions,
                "frozen_runtime_lineage": frozen_runtime_lineage,
            }
            if prefect_timeout_seconds is not None:
                launch_kwargs["timeout_seconds"] = prefect_timeout_seconds
            if persisted_reproduction_metadata is not None:
                launch_kwargs["reproduction_metadata"] = persisted_reproduction_metadata
            prefect_result = self._launch_with_timeout(launch_kwargs, timeout_seconds)
            if prefect_result.quant_factory_run_id != submission.run_id:
                self._record_integrity_error(
                    submission.run_id,
                    "Fixture launcher returned a mismatched Quant Factory run ID.",
                )
                raise ResearchLaunchIntegrityError(
                    "fixture launch returned mismatched Quant Factory run ID: "
                    f"expected {submission.run_id}, got {prefect_result.quant_factory_run_id}"
                )
            return prefect_result

        dispatch = claim_service.dispatch(
            idempotency_key=idempotency_key,
            dispatcher_instance_id=self._dispatcher_instance_id,
            invoke=invoke,
        )
        run = self._get_persisted_run(dispatch.submission.run_id)
        if run is None:
            raise ResearchLaunchIntegrityError(
                "durable research launch references a missing Quant Factory run"
            )
        prefect_result = dispatch.value if dispatch.invoked else None
        if prefect_result is not None and prefect_result.attempt_count != run.attempt_count:
            prefect_result = replace(prefect_result, attempt_count=run.attempt_count)
        return RunLaunchResult(
            run=_summary(run),
            prefect_result=prefect_result,
            submission=dispatch.submission,
            invoked=dispatch.invoked,
        )

    def reproduce_fixture_run(
        self,
        source_run_id: str,
        *,
        idempotency_key: str,
        artifact_root: str | Path,
        run_id: str | None = None,
    ) -> RunReproductionResult:
        """Create a new fixture run from a validated persisted source run."""

        existing = DurableResearchLaunchService(database=self.database_path).get(
            idempotency_key
        )
        metadata = (
            None
            if existing is not None
            else self._reproduction_metadata(
                source_run_id,
                artifact_root=artifact_root,
            )
        )
        configuration_id = (
            existing.configuration_id
            if existing is not None
            else str(metadata["configuration_id"])
        )
        launched = self.launch_fixture(
            idempotency_key=idempotency_key,
            configuration_id=configuration_id,
            operation=ResearchLaunchOperation.REPRODUCTION,
            source_run_id=source_run_id,
            run_id=run_id,
            reproduction_metadata=metadata,
        )
        service = PersistenceService(self.database_path)
        try:
            original = service.runs.get(source_run_id)
            reproduction = service.runs.get(launched.run.run_id)
            if original is None or reproduction is None:
                raise RunServiceError("reproduction result was not durably persisted")
            if (
                launched.invoked
                or service.read_persisted_run_manifest(reproduction.run_id) is None
            ):
                try:
                    service.persist_run_manifest(
                        service.build_run_manifest(reproduction.run_id)
                    )
                except (KeyError, RuntimeError, ValueError) as exc:
                    raise RunServiceError(
                        f"reproduced run lineage could not be persisted: {exc}"
                    ) from exc
            return RunReproductionResult(
                original=_summary(original),
                reproduction=_summary(reproduction),
                comparison=service.compare_runs((source_run_id, reproduction.run_id)),
                notes=(
                    "Configuration, dataset, assumptions, and outputs should match.",
                    (
                        "Allowed differences are new run identity, Prefect identity, "
                        "attempt timestamps, and current runtime identity."
                    ),
                ),
            )
        finally:
            service.close()

    def get_run(self, run_id: str) -> RunSummary | None:
        service = PersistenceService(self.database_path)
        try:
            run = service.runs.get(run_id)
            return _summary(run) if run is not None else None
        finally:
            service.close()

    def recent_runs(self, *, limit: int = 20) -> tuple[RunSummary, ...]:
        if limit < 1:
            raise ValueError("recent run limit must be positive")
        service = PersistenceService(self.database_path)
        try:
            return tuple(_summary(run) for run in service.runs.list()[:limit])
        finally:
            service.close()

    def all_runs(self) -> tuple[RunSummary, ...]:
        """Return lightweight metadata for the complete persisted run history."""
        service = PersistenceService(self.database_path)
        try:
            return tuple(_summary(run) for run in service.runs.list())
        finally:
            service.close()

    def all_history(
        self,
        *,
        artifact_root: str | Path | None = None,
    ) -> tuple[dict[str, object], ...]:
        """Return history metadata and small validation outcomes, without portfolios."""
        service = PersistenceService(self.database_path)
        try:
            rows: list[dict[str, object]] = []
            for run in service.runs.list():
                configuration = service.configurations.get(run.configuration_id)
                configuration_issue: str | None = None
                document: dict[str, object] = {}
                if configuration is None:
                    configuration_issue = "saved configuration is missing"
                else:
                    try:
                        parsed_document = json.loads(configuration.canonical_config_json)
                        if not isinstance(parsed_document, dict):
                            raise ValueError("saved configuration JSON is not an object")
                        experiment_id = parsed_document.get("experiment_id")
                        if not isinstance(experiment_id, str) or not experiment_id.strip():
                            raise ValueError("saved configuration experiment_id is invalid")
                        for key in ("parameters", "execution", "market_data"):
                            value = parsed_document.get(key, {})
                            if not isinstance(value, dict):
                                raise ValueError(
                                    f"saved configuration {key} is not an object"
                                )
                        document = parsed_document
                    except (json.JSONDecodeError, TypeError, ValueError) as exc:
                        configuration_issue = f"saved configuration is invalid: {exc}"
                market_data = document.get("market_data", {})
                strategy = service.strategies.get(run.strategy_id, run.strategy_version)
                review = service.reviews.get_current("run", run.run_id)
                results = service.results.list_parameter_results(run.run_id)
                artifacts = service.results.list_artifact_contracts(run.run_id)
                metrics, metric_basis = _top_ranked_metrics(results)
                evidence = (
                    f"Evidence invalid: {configuration_issue}"
                    if configuration_issue is not None
                    else _evidence_outcome_status(
                        service,
                        run,
                        artifacts,
                        artifact_root=artifact_root,
                    )
                )
                reproducibility = (
                    f"Configuration invalid: {configuration_issue}"
                    if configuration_issue is not None
                    else _manifest_status(service, run.run_id)
                )
                rows.append({
                    "run_id": run.run_id,
                    "created_at": run.created_at,
                    "instrument": (
                        "Configuration unavailable"
                        if configuration_issue is not None
                        else market_data.get("symbol", "Not recorded")
                    ),
                    "strategy": (
                        strategy.display_name
                        if strategy is not None
                        else f"{run.strategy_id} {run.strategy_version}"
                    ),
                    "stage": _stage_label(run.stage.value),
                    "status": _status_label(run.status.value),
                    "review": _review_label(review.state.value if review else None),
                    "evidence": evidence,
                    "metric": metrics["total_return"],
                    "metric_basis": metric_basis,
                    **metrics,
                    "artifact_status": _registered_artifact_status(artifacts),
                    "reproducibility": reproducibility,
                })
            return tuple(rows)
        finally:
            service.close()

    def events_for_run(self, run_id: str) -> tuple[RunEvent, ...]:
        service = PersistenceService(self.database_path)
        try:
            return tuple(_event(event) for event in service.events.list_for_run(run_id))
        finally:
            service.close()

    def recent_events(self, *, limit: int = 20) -> tuple[RunEvent, ...]:
        service = PersistenceService(self.database_path)
        try:
            return tuple(_event(event) for event in service.events.list_recent(limit=limit))
        finally:
            service.close()

    def walk_forward_evidence_for_run(
        self,
        run_id: str,
        *,
        artifact_root: str | Path,
    ) -> object:
        service = PersistenceService(self.database_path)
        try:
            return service.retrieve_walk_forward_evidence(
                run_id,
                artifact_root=artifact_root,
            )
        finally:
            service.close()

    def persist_walk_forward_evidence_for_run(
        self,
        run_id: str,
        *,
        result: object,
        rules: object,
        artifact_root: str | Path,
    ) -> object:
        service = PersistenceService(self.database_path)
        try:
            return service.persist_walk_forward_evidence(
                run_id=run_id,
                result=result,
                rules=rules,
                artifact_root=artifact_root,
            )
        finally:
            service.close()

    def request_fixture_cancellation(self, run_id: str) -> RunSummary:
        """Request cooperative cancellation; the fixture owns acknowledgement."""
        submission = DurableResearchLaunchService(
            database=self.database_path
        ).get_for_run(run_id)
        if (
            submission is not None
            and submission.state != ResearchSubmissionState.ACKNOWLEDGED
        ):
            raise RunServiceError(
                "cancellation is unavailable until the Prefect submission is acknowledged"
            )
        service = PersistenceService(self.database_path)
        try:
            return _summary(service.request_run_cancellation(run_id))
        finally:
            service.close()

    def recover_stale_fixture_runs(self, *, stale_before: str) -> tuple[RunSummary, ...]:
        """Reject age-only recovery; ADR 0011 requires claim-specific evidence."""
        del stale_before
        raise RunServiceError(
            "age-only fixture recovery is disabled; use claim-aware Prefect "
            "reconciliation or an evidenced process-exit barrier"
        )

    def recover_invoking_after_process_exit(
        self,
        *,
        idempotency_key: str,
        departed_dispatcher_instance_id: str,
        process_exit_evidence_reference: str,
    ) -> ResearchRunSubmissionRecord:
        """Apply explicit process-exit evidence without launching replacement work."""

        return DurableResearchLaunchService(
            database=self.database_path
        ).recover_invoking_after_process_exit(
            idempotency_key=idempotency_key,
            departed_dispatcher_instance_id=departed_dispatcher_instance_id,
            process_exit_evidence_reference=process_exit_evidence_reference,
        )

    def _launch_inputs(
        self,
        configuration_id: str,
    ) -> tuple[object, object]:
        service = PersistenceService(self.database_path)
        try:
            configuration = service.configurations.get(configuration_id)
            if configuration is None:
                raise KeyError(f"unknown Quant Factory configuration: {configuration_id}")
            try:
                document = json.loads(configuration.canonical_config_json)
            except json.JSONDecodeError as exc:
                raise RunServiceError(
                    f"saved configuration {configuration_id} has invalid canonical JSON"
                ) from exc
            if (
                document.get("strategy_id") != configuration.strategy_id
                or document.get("strategy_version") != configuration.strategy_version
            ):
                raise RunServiceError(
                    f"saved configuration {configuration_id} has mismatched strategy identity"
                )
            if "parameters" not in document or "execution" not in document:
                raise RunServiceError(
                    f"saved configuration {configuration_id} lacks launch inputs"
                )
            strategy = service.strategies.get(
                configuration.strategy_id,
                configuration.strategy_version,
            )
            if strategy is None:
                raise RunServiceError(
                    f"saved configuration {configuration_id} references an unregistered strategy"
                )
            if not strategy.active or strategy.lifecycle != StrategyLifecycle.INFRASTRUCTURE_FIXTURE:
                raise RunServiceError(
                    f"saved configuration {configuration_id} is not launchable"
                )
            return document["parameters"], document["execution"]
        finally:
            service.close()

    def _reproduction_metadata(
        self,
        source_run_id: str,
        *,
        artifact_root: str | Path,
    ) -> dict[str, object]:
        service = PersistenceService(self.database_path)
        try:
            source = service.runs.get(source_run_id)
            if source is None:
                raise KeyError(f"unknown run {source_run_id}")
            if source.status != RunStatus.SUCCEEDED:
                raise RunServiceError(
                    f"run {source_run_id} is {source.status.value}; only succeeded runs can be reproduced"
                )
            configuration = service.configurations.get(source.configuration_id)
            if configuration is None:
                raise RunServiceError(
                    f"run {source_run_id} references missing configuration"
                )
            manifest = service.read_persisted_run_manifest_document(source_run_id)
            if manifest is None:
                raise RunServiceError(
                    f"run {source_run_id} has no persisted manifest"
                )
            lineage = service.get_run_lineage(source_run_id)
            retrieval = service.retrieve_run_artifacts(
                source_run_id,
                artifact_root=artifact_root,
            )
            invalid = [
                validation
                for validation in retrieval.validations
                if (
                    not validation.valid
                    or validation.availability_state != ArtifactAvailability.AVAILABLE
                )
            ]
            if invalid:
                reasons = ", ".join(
                    f"{item.artifact_id}:{item.reason}" for item in invalid
                )
                raise RunServiceError(
                    f"run {source_run_id} has invalid reproduction artifacts: {reasons}"
                )
            return {
                "source_run_id": source_run_id,
                "configuration_id": source.configuration_id,
                "source_manifest_checksum": retrieval.manifest_checksum,
                "source_runtime_identity": lineage.runtime.runtime_identity,
                "source_dataset_identity": lineage.data.dataset_identity,
                "source_execution_assumptions_identity": (
                    lineage.execution_assumptions.execution_assumptions_identity
                ),
            }
        except (KeyError, RuntimeError, ValueError) as exc:
            if isinstance(exc, RunServiceError):
                raise
            raise RunServiceError(f"run {source_run_id} cannot be reproduced: {exc}") from exc
        finally:
            service.close()

    @staticmethod
    def _validate_timeout(timeout_seconds: float | None) -> None:
        if timeout_seconds is None:
            return
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= MAX_FIXTURE_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "fixture timeout_seconds must be a finite value between 0 and 3600"
            )

    def _launch_with_timeout(
        self,
        launch_kwargs: dict[str, object],
        timeout_seconds: float | None,
    ) -> PrefectFixtureResult:
        if timeout_seconds is None:
            return self._fixture_launcher(**launch_kwargs)

        outcome: dict[str, object] = {}

        def invoke() -> None:
            try:
                outcome["result"] = self._fixture_launcher(**launch_kwargs)
            except BaseException as exc:  # propagated on the launching thread
                outcome["error"] = exc

        thread = threading.Thread(target=invoke, daemon=True)
        thread.start()
        thread.join(timeout_seconds)
        if thread.is_alive():
            raise _FixtureLaunchTimeout
        if "error" in outcome:
            raise outcome["error"]  # type: ignore[misc]
        result = outcome.get("result")
        if not isinstance(result, PrefectFixtureResult):
            raise RunServiceError("fixture launcher returned no Prefect fixture result")
        return result

    def _get_persisted_run(self, run_id: str) -> ExperimentRunRecord | None:
        service = PersistenceService(self.database_path)
        try:
            return service.runs.get(run_id)
        finally:
            service.close()

    def _record_integrity_error(self, run_id: str, message: str) -> None:
        if self._get_persisted_run(run_id) is None:
            return
        service = PersistenceService(self.database_path)
        try:
            service.append_run_event(
                run_id=run_id,
                event_type=RunEventType.SERVICE_INTEGRITY_ERROR,
                severity=EventSeverity.ERROR,
                message=message,
            )
        finally:
            service.close()

class _FixtureLaunchTimeout(Exception):
    """Private control signal for a bounded service-side fixture invocation."""
