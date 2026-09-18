"""Typed records and lifecycle validation for the experiment database."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class StrategyLifecycle(str, Enum):
    INFRASTRUCTURE_FIXTURE = "infrastructure_fixture"
    CANDIDATE = "candidate"
    REJECTED = "rejected"
    WATCHLIST = "watchlist"
    PAPER_CANDIDATE = "paper_candidate"
    LIVE_TEST_CANDIDATE = "live_test_candidate"
    PAUSED = "paused"
    RETIRED = "retired"


class RunStage(str, Enum):
    FIXTURE = "fixture"
    SCREENING = "screening"
    OOS = "oos"
    WALK_FORWARD = "walk_forward"
    ROBUSTNESS = "robustness"
    MONTE_CARLO = "monte_carlo"


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchLaunchOperation(str, Enum):
    """Operator actions that may own one durable research-launch claim."""

    RUN_TEST = "run_test"
    HISTORICAL_RELAUNCH = "historical_relaunch"
    REPRODUCTION = "reproduction"


class ResearchSubmissionState(str, Enum):
    """Submission handoff state, deliberately separate from ``RunStatus``."""

    CLAIMED = "claimed"
    INVOKING = "invoking"
    ACKNOWLEDGED = "acknowledged"
    SUBMISSION_UNKNOWN = "submission_unknown"
    FAILED_BEFORE_SUBMISSION = "failed_before_submission"
    ABANDONED = "abandoned"


class RunEventType(str, Enum):
    """Bounded operator-visible lifecycle events for one Quant Factory run."""

    RUN_CREATED = "run_created"
    RUN_STARTED = "run_started"
    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    RUN_CANCELLATION_REQUESTED = "run_cancellation_requested"
    RUN_RETRY_SCHEDULED = "run_retry_scheduled"
    RUN_TIMED_OUT = "run_timed_out"
    RUN_STALE_RECOVERED = "run_stale_recovered"
    SERVICE_INTEGRITY_ERROR = "service_integrity_error"


class EventSeverity(str, Enum):
    INFO = "info"
    ERROR = "error"


class ArtifactAvailability(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    CORRUPT = "corrupt"
    UNAVAILABLE = "unavailable"


class ArtifactType(str, Enum):
    RUN_SUMMARY = "run_summary"
    PARAMETER_RESULTS = "parameter_results"
    TRADES_OR_ORDERS = "trades_or_orders"
    METRICS = "metrics"
    EQUITY_CURVE = "equity_curve"
    VALIDATION_EVIDENCE = "validation_evidence"
    DATASET_MANIFEST = "dataset_manifest"
    GENERIC_FIXTURE_EVIDENCE = "generic_fixture_evidence"


class ReviewState(str, Enum):
    UNREVIEWED = "unreviewed"
    REJECT = "reject"
    REVISE = "revise"
    INFRASTRUCTURE_FIXTURE = "infrastructure_fixture"
    WATCHLIST = "watchlist"
    APPROVED_FOR_NEXT_EVIDENCE_STAGE = "approved_for_next_evidence_stage"
    PAPER_CANDIDATE = "paper_candidate"
    LIVE_TEST_CANDIDATE = "live_test_candidate"
    PAUSED = "paused"
    RETIRED = "retired"


TERMINAL_RUN_STATUSES = {
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}
RUN_STATUS_TRANSITIONS = {
    RunStatus.CREATED: {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.RUNNING: {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.SUCCEEDED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}


def coerce_enum(enum_type, value):
    if isinstance(value, enum_type):
        return value
    return enum_type(value)


def validate_run_transition(current: RunStatus, new: RunStatus) -> None:
    current = coerce_enum(RunStatus, current)
    new = coerce_enum(RunStatus, new)
    if new not in RUN_STATUS_TRANSITIONS[current]:
        raise ValueError(f"invalid run-status transition: {current.value} -> {new.value}")


@dataclass(frozen=True)
class StrategyRecord:
    strategy_id: str
    strategy_version: str
    display_name: str
    description: str
    lifecycle: StrategyLifecycle
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ConfigurationRecord:
    configuration_id: str
    experiment_id: str
    strategy_id: str
    strategy_version: str
    canonical_config_json: str
    config_hash: str
    created_at: str


@dataclass(frozen=True)
class ExperimentRunRecord:
    run_id: str
    configuration_id: str
    strategy_id: str
    strategy_version: str
    stage: RunStage
    status: RunStatus
    started_at: str | None
    completed_at: str | None
    error_summary: str | None
    environment_json: str
    created_at: str
    attempt_count: int


@dataclass(frozen=True)
class RunEventRecord:
    """Append-only concise operator event; technical logs remain in Prefect."""

    event_id: int
    run_id: str
    event_type: RunEventType
    occurred_at: str
    severity: EventSeverity
    source: str
    message: str


@dataclass(frozen=True)
class ResearchRunSubmissionRecord:
    """Durable identity and handoff state for one explicit research launch."""

    idempotency_key: str
    run_id: str
    configuration_id: str
    canonical_request_json: str
    request_fingerprint: str
    state: ResearchSubmissionState
    dispatcher_instance_id: str | None
    prefect_flow_run_id: str | None
    prefect_api_url: str | None
    claimed_at: str
    invocation_started_at: str | None
    acknowledged_at: str | None
    unknown_at: str | None
    unknown_evidence_reference: str | None
    resolved_at: str | None
    resolution_evidence_reference: str | None
    updated_at: str
    error_summary: str | None


@dataclass(frozen=True)
class ParameterResultRecord:
    run_id: str
    row_id: str
    normalized_parameters_json: str
    metrics_json: str
    ranking_position: int
    screening_status: str
    rejection_reasons: str


@dataclass(frozen=True)
class DataProvenanceRecord:
    run_id: str
    provider: str
    provider_implementation: str
    symbol: str
    interval: str
    timezone: str
    requested_coverage: str
    actual_coverage: str
    adjusted: bool
    row_count: int
    cache_action: str
    validation_summary_json: str
    manifest_reference: str | None
    checksum: str | None


@dataclass(frozen=True)
class ExecutionAssumptionsRecord:
    run_id: str
    assumptions_json: str


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: int
    run_id: str
    artifact_type: str
    schema_version: int
    path: str
    validation_status: str
    checksum: str | None
    availability: ArtifactAvailability
    created_at: str


@dataclass(frozen=True)
class ArtifactContractRecord:
    artifact_id: int
    run_id: str
    artifact_type: ArtifactType
    logical_name: str
    schema_version: int
    media_type: str
    format: str
    checksum_algorithm: str
    checksum: str
    size_bytes: int
    location: str
    availability_state: ArtifactAvailability
    created_at: str


@dataclass(frozen=True)
class ArtifactValidationResult:
    artifact_id: int
    availability_state: ArtifactAvailability
    valid: bool
    reason: str
    expected_checksum: str
    actual_checksum: str | None
    expected_size_bytes: int
    actual_size_bytes: int | None
    resolved_path: str | None


@dataclass(frozen=True)
class RunArtifactRetrieval:
    run_id: str
    manifest_json: str
    manifest_checksum: str
    artifacts: tuple[ArtifactContractRecord, ...]
    validations: tuple[ArtifactValidationResult, ...]


@dataclass(frozen=True)
class ConfigurationLineage:
    configuration_id: str
    config_hash: str


@dataclass(frozen=True)
class StrategyLineage:
    strategy_id: str
    strategy_version: str


@dataclass(frozen=True)
class DataLineage:
    provenance_record_identity: str
    provider_identity: str
    symbol: str
    timeframe: str
    requested_coverage: str
    actual_coverage: str
    dataset_identity: str
    dataset_manifest_reference: str | None
    dataset_checksum: str | None
    calendar_identity: str | None
    adjustment_mode: str
    normalization_identity: str


@dataclass(frozen=True)
class NormalizationLineage:
    normalization_identity: str
    contract_json: str


@dataclass(frozen=True)
class ExecutionAssumptionLineage:
    execution_assumptions_identity: str
    record_identity: str


@dataclass(frozen=True)
class RuntimeLineage:
    runtime_identity: str
    git_commit_sha: str | None
    git_commit_available: bool
    git_dirty_state: str
    git_dirty_available: bool
    git_dirty_entry_count: int | None
    git_dirty_fingerprint: str | None
    python_implementation: str
    python_version: str
    python_cache_tag: str | None
    vectorbtpro_version: str | None
    vectorbtpro_available: bool
    package_fingerprint: str
    package_count: int
    platform_system: str
    platform_machine: str


@dataclass(frozen=True)
class RunLineage:
    configuration: ConfigurationLineage
    strategy: StrategyLineage
    data: DataLineage
    normalization: NormalizationLineage
    execution_assumptions: ExecutionAssumptionLineage
    runtime: RuntimeLineage


@dataclass(frozen=True)
class RunManifest:
    schema_version: int
    run_id: str
    configuration_id: str
    strategy_id: str
    strategy_version: str
    lineage: RunLineage | None
    artifacts: tuple[ArtifactContractRecord, ...]
    created_at: str


@dataclass(frozen=True)
class ReviewRecord:
    target_type: str
    target_id: str
    state: ReviewState
    note: str
    operator: str
    updated_at: str


def normalized_configuration_document(
    *,
    experiment_id: str,
    strategy_id: str,
    strategy_version: str,
    market_data: Any,
    parameters: Any,
    execution: Any,
    ranking: Any,
    screening: Any,
) -> dict[str, Any]:
    """Build the immutable configuration document used for hashing."""
    return {
        "experiment_id": experiment_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "market_data": market_data,
        "parameters": parameters,
        "execution": execution,
        "ranking": ranking,
        "screening": screening,
    }
