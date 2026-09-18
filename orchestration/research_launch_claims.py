"""Durable, fail-closed identity for operator-initiated research launches.

This module deliberately does not own a dashboard callback or a Prefect worker.
It creates the durable claim before external invocation and exposes the narrow
handoff/binding/recovery operations required by ADR 0011.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any, TypeVar
from uuid import UUID, uuid4

from persistence.database import connect, database_path, initialize_database
from persistence.models import (
    EventSeverity,
    ExperimentRunRecord,
    ResearchLaunchOperation,
    ResearchRunSubmissionRecord,
    ResearchSubmissionState,
    RunEventType,
    RunStage,
    RunStatus,
    StrategyLifecycle,
)
from persistence.repositories import (
    ConfigurationRepository,
    ResearchRunSubmissionRepository,
    RunEventRepository,
    RunRepository,
    StrategyRepository,
    utc_now,
)
from persistence.serialization import canonical_json

REQUEST_PROTOCOL_VERSION = 1
ACCEPTED_LAUNCH_POLICY = "milestone23_infrastructure_fixture_only"
DEFAULT_BUSY_TIMEOUT_SECONDS = 0.25
MIN_BUSY_TIMEOUT_SECONDS = 0.01
MAX_BUSY_TIMEOUT_SECONDS = 30.0
LAUNCH_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
ALLOWED_LINEAGE_KEYS = frozenset(
    {
        "parent_run_id",
        "reproduction_of_run_id",
        "source_manifest_checksum",
        "source_runtime_identity",
        "source_dataset_identity",
        "source_execution_assumptions_identity",
    }
)


class ResearchLaunchError(RuntimeError):
    """Base class for durable research-launch failures."""


class ResearchLaunchKeyError(ValueError):
    """Raised when a browser-prepared launch key is malformed."""


class ResearchLaunchConflictError(ResearchLaunchError):
    """Raised when one durable key is reused for a different intent."""


class ResearchLaunchContentionError(ResearchLaunchError):
    """Typed finite SQLite contention outcome; no submission state is implied."""


class ResearchLaunchIntegrityError(ResearchLaunchError):
    """Raised when durable launch identity or state fails closed."""


class ResearchLaunchInvocationUnknownError(ResearchLaunchError):
    """Raised when invocation crossed the marker but acknowledgement is unknown."""


class ResearchLaunchInvocationError(ResearchLaunchError):
    """Raised when an acknowledged invocation still reports a caller-visible error."""


@dataclass(frozen=True)
class ResearchLaunchRequest:
    """Meaning of one explicit operator launch before its claim is created."""

    operation: ResearchLaunchOperation
    configuration_id: str
    source_run_id: str | None = None
    source_lineage: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ResearchLaunchClaim:
    submission: ResearchRunSubmissionRecord
    run: ExperimentRunRecord
    created: bool


@dataclass(frozen=True)
class ResearchDispatchDecision:
    submission: ResearchRunSubmissionRecord
    should_invoke: bool


T = TypeVar("T")


@dataclass(frozen=True)
class ResearchDispatchResult:
    submission: ResearchRunSubmissionRecord
    invoked: bool
    value: Any = None


def new_research_launch_key() -> str:
    """Prepare a non-secret, session-owned idempotency identity."""

    return f"launch_{uuid4().hex}"


def new_dispatcher_instance_id() -> str:
    """Create the random boot-scoped dispatcher identity required by ADR 0011."""

    return str(uuid4())


def _validate_launch_key(value: str) -> str:
    if not isinstance(value, str) or LAUNCH_KEY_PATTERN.fullmatch(value) is None:
        raise ResearchLaunchKeyError(
            "research launch key must contain 16-128 letters, digits, '_' or '-'"
        )
    return value


def _validate_run_id(value: str) -> str:
    if not isinstance(value, str) or RUN_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("research run ID has an invalid format")
    return value


def _validate_dispatcher_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("dispatcher instance ID must be a UUID") from exc
    if str(parsed) != value.lower():
        raise ValueError("dispatcher instance ID must use canonical UUID text")
    return value


def _bounded_text(value: str, *, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{label} must be non-empty printable text up to {maximum} characters")
    return normalized


def _optional_bounded_text(
    value: str | None,
    *,
    label: str,
    maximum: int,
) -> str | None:
    return None if value is None else _bounded_text(value, label=label, maximum=maximum)


def _request_fingerprint(canonical_request_json: str) -> str:
    return hashlib.sha256(canonical_request_json.encode("utf-8")).hexdigest()


def _is_contention(exc: sqlite3.OperationalError) -> bool:
    code = getattr(exc, "sqlite_errorcode", None)
    return code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} or any(
        marker in str(exc).lower() for marker in ("database is locked", "database table is locked")
    )


class DurableResearchLaunchService:
    """Schema-5 claim, dispatch, binding, and explicit recovery primitives.

    ``initialize_schema=False`` is reserved for in-flow binding after startup
    has already proved schema 5. It keeps construction side-effect free so
    ``bind_prefect_identity`` can be the flow's first database operation.
    """

    def __init__(
        self,
        *,
        database: str | Path | None = None,
        busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS,
        run_id_factory: Callable[[], str] | None = None,
        claim_failure_injector: Callable[[str], None] | None = None,
        initialize_schema: bool = True,
    ) -> None:
        if (
            isinstance(busy_timeout_seconds, bool)
            or not isinstance(busy_timeout_seconds, (int, float))
            or not math.isfinite(busy_timeout_seconds)
            or not MIN_BUSY_TIMEOUT_SECONDS
            <= busy_timeout_seconds
            <= MAX_BUSY_TIMEOUT_SECONDS
        ):
            raise ValueError("busy timeout must be a finite value between 0.01 and 30 seconds")
        if not isinstance(initialize_schema, bool):
            raise ValueError("initialize_schema must be a boolean")
        self.database_path = database_path(database)
        self.busy_timeout_seconds = float(busy_timeout_seconds)
        self._busy_timeout_ms = max(1, round(self.busy_timeout_seconds * 1000))
        self._run_id_factory = run_id_factory or (lambda: f"run_{uuid4().hex}")
        self._claim_failure_injector = claim_failure_injector
        if initialize_schema:
            initialized = initialize_database(self.database_path)
            initialized.close()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = connect(self.database_path)
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _immediate(self, connection: sqlite3.Connection) -> Iterator[None]:
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield
            connection.commit()
        except sqlite3.OperationalError as exc:
            connection.rollback()
            if _is_contention(exc):
                raise ResearchLaunchContentionError(
                    f"research launch database remained busy for {self.busy_timeout_seconds:g} seconds"
                ) from exc
            raise
        except BaseException:
            connection.rollback()
            raise

    def _inject_claim_failure(self, step: str) -> None:
        if self._claim_failure_injector is not None:
            self._claim_failure_injector(step)

    @staticmethod
    def _normalize_request(request: ResearchLaunchRequest) -> tuple[ResearchLaunchOperation, str, str | None, dict[str, str]]:
        try:
            operation = ResearchLaunchOperation(request.operation)
        except (TypeError, ValueError) as exc:
            raise ValueError("unsupported research launch operation") from exc
        configuration_id = _bounded_text(
            request.configuration_id,
            label="configuration ID",
            maximum=200,
        )
        source_run_id = _optional_bounded_text(
            request.source_run_id,
            label="source run ID",
            maximum=160,
        )
        lineage = dict(request.source_lineage or {})
        if set(lineage) - ALLOWED_LINEAGE_KEYS:
            raise ValueError("source lineage contains unsupported identity fields")
        normalized_lineage = {
            _bounded_text(key, label="source lineage key", maximum=64): _bounded_text(
                value,
                label=f"source lineage {key}",
                maximum=256,
            )
            for key, value in lineage.items()
        }
        if operation == ResearchLaunchOperation.RUN_TEST:
            if source_run_id is not None or normalized_lineage:
                raise ValueError("run_test cannot carry source-run lineage")
        elif source_run_id is None:
            raise ValueError(f"{operation.value} requires an immutable source run")
        return operation, configuration_id, source_run_id, normalized_lineage

    @staticmethod
    def _manifest_checksum(manifest_json: str) -> tuple[dict[str, Any], str]:
        try:
            document = json.loads(manifest_json)
        except json.JSONDecodeError as exc:
            raise ResearchLaunchIntegrityError(
                "source run manifest is not valid JSON"
            ) from exc
        if not isinstance(document, dict):
            raise ResearchLaunchIntegrityError("source run manifest is not a JSON object")
        immutable = dict(document)
        immutable.pop("created_at", None)
        artifacts = immutable.get("artifacts")
        if not isinstance(artifacts, list):
            raise ResearchLaunchIntegrityError("source run manifest artifacts are invalid")
        immutable_artifacts: list[dict[str, Any]] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise ResearchLaunchIntegrityError(
                    "source run manifest contains an invalid artifact"
                )
            immutable_artifact = dict(artifact)
            immutable_artifact.pop("availability_state", None)
            immutable_artifacts.append(immutable_artifact)
        immutable["artifacts"] = immutable_artifacts
        checksum = hashlib.sha256(canonical_json(immutable).encode("utf-8")).hexdigest()
        return document, checksum

    @staticmethod
    def _derive_source_lineage(
        connection: sqlite3.Connection,
        *,
        operation: ResearchLaunchOperation,
        source_run_id: str | None,
        configuration_id: str,
        strategy_id: str,
        strategy_version: str,
    ) -> dict[str, str]:
        if operation == ResearchLaunchOperation.RUN_TEST:
            return {}
        assert source_run_id is not None
        source = RunRepository(connection).get(source_run_id)
        if source is None:
            raise ResearchLaunchIntegrityError(
                f"source run {source_run_id} does not exist"
            )
        if source.stage != RunStage.FIXTURE:
            raise ResearchLaunchIntegrityError(
                f"source run {source_run_id} is not a fixture run"
            )
        if (
            source.configuration_id != configuration_id
            or source.strategy_id != strategy_id
            or source.strategy_version != strategy_version
        ):
            raise ResearchLaunchIntegrityError(
                "source run identity does not match the requested saved configuration"
            )
        if operation == ResearchLaunchOperation.HISTORICAL_RELAUNCH:
            return {"parent_run_id": source.run_id}
        if source.status != RunStatus.SUCCEEDED:
            raise ResearchLaunchIntegrityError(
                f"source run {source_run_id} is not succeeded and cannot be reproduced"
            )
        stored_manifest = connection.execute(
            "SELECT manifest_json, content_checksum FROM run_manifests WHERE run_id=?",
            (source.run_id,),
        ).fetchone()
        if stored_manifest is None:
            raise ResearchLaunchIntegrityError(
                f"source run {source_run_id} has no persisted manifest"
            )
        manifest, calculated_checksum = DurableResearchLaunchService._manifest_checksum(
            stored_manifest["manifest_json"]
        )
        if calculated_checksum != stored_manifest["content_checksum"]:
            raise ResearchLaunchIntegrityError(
                f"source run {source_run_id} manifest checksum is invalid"
            )
        if (
            manifest.get("run_id") != source.run_id
            or manifest.get("configuration_id") != source.configuration_id
            or manifest.get("strategy_id") != source.strategy_id
            or manifest.get("strategy_version") != source.strategy_version
        ):
            raise ResearchLaunchIntegrityError(
                f"source run {source_run_id} manifest identity is mismatched"
            )
        lineage = manifest.get("lineage")
        if not isinstance(lineage, dict):
            raise ResearchLaunchIntegrityError(
                f"source run {source_run_id} manifest has no complete lineage"
            )
        try:
            configuration_lineage = lineage["configuration"]
            data_lineage = lineage["data"]
            execution_lineage = lineage["execution_assumptions"]
            runtime_lineage = lineage["runtime"]
            if (
                configuration_lineage["configuration_id"] != source.configuration_id
                or not configuration_lineage["config_hash"]
            ):
                raise KeyError("configuration")
            derived = {
                "reproduction_of_run_id": source.run_id,
                "source_manifest_checksum": stored_manifest["content_checksum"],
                "source_runtime_identity": runtime_lineage["runtime_identity"],
                "source_dataset_identity": data_lineage["dataset_identity"],
                "source_execution_assumptions_identity": execution_lineage[
                    "execution_assumptions_identity"
                ],
            }
        except (KeyError, TypeError) as exc:
            raise ResearchLaunchIntegrityError(
                f"source run {source_run_id} manifest lineage is incomplete"
            ) from exc
        for key, value in derived.items():
            _bounded_text(value, label=key, maximum=256)
        return derived

    @staticmethod
    def _canonical_request_for_configuration(
        connection: sqlite3.Connection,
        request: ResearchLaunchRequest,
    ) -> tuple[str, str, str, str, str]:
        operation, configuration_id, source_run_id, expected_source_lineage = (
            DurableResearchLaunchService._normalize_request(request)
        )
        configurations = ConfigurationRepository(connection)
        strategies = StrategyRepository(connection)
        configuration = configurations.get(configuration_id)
        if configuration is None:
            raise KeyError(f"unknown Quant Factory configuration: {configuration_id}")
        expected_hash = hashlib.sha256(
            configuration.canonical_config_json.encode("utf-8")
        ).hexdigest()
        if configuration.config_hash != expected_hash:
            raise ResearchLaunchIntegrityError(
                f"saved configuration {configuration_id} failed its immutable hash check"
            )
        try:
            configuration_document = json.loads(configuration.canonical_config_json)
        except json.JSONDecodeError as exc:
            raise ResearchLaunchIntegrityError(
                f"saved configuration {configuration_id} has invalid canonical JSON"
            ) from exc
        if not isinstance(configuration_document, dict):
            raise ResearchLaunchIntegrityError("saved configuration is not a JSON object")
        if (
            configuration_document.get("strategy_id") != configuration.strategy_id
            or configuration_document.get("strategy_version") != configuration.strategy_version
        ):
            raise ResearchLaunchIntegrityError(
                f"saved configuration {configuration_id} has mismatched strategy identity"
            )
        if "parameters" not in configuration_document or "execution" not in configuration_document:
            raise ResearchLaunchIntegrityError(
                f"saved configuration {configuration_id} lacks launch inputs"
            )
        strategy = strategies.get(configuration.strategy_id, configuration.strategy_version)
        if strategy is None:
            raise ResearchLaunchIntegrityError(
                f"saved configuration {configuration_id} references an unregistered strategy"
            )
        if not strategy.active or strategy.lifecycle != StrategyLifecycle.INFRASTRUCTURE_FIXTURE:
            raise ResearchLaunchError(
                f"saved configuration {configuration_id} is not an approved infrastructure fixture"
            )
        source_lineage = DurableResearchLaunchService._derive_source_lineage(
            connection,
            operation=operation,
            source_run_id=source_run_id,
            configuration_id=configuration.configuration_id,
            strategy_id=configuration.strategy_id,
            strategy_version=configuration.strategy_version,
        )
        if expected_source_lineage and expected_source_lineage != source_lineage:
            raise ResearchLaunchIntegrityError(
                "provided source lineage does not match persisted source evidence"
            )
        document = {
            "protocol_version": REQUEST_PROTOCOL_VERSION,
            "operation_kind": operation.value,
            "configuration_id": configuration.configuration_id,
            "configuration_hash": configuration.config_hash,
            "strategy_id": configuration.strategy_id,
            "strategy_version": configuration.strategy_version,
            "fixture_stage": RunStage.FIXTURE.value,
            "accepted_launch_policy": ACCEPTED_LAUNCH_POLICY,
            "source_run_id": source_run_id,
            "source_lineage": source_lineage,
        }
        serialized = canonical_json(document)
        return (
            serialized,
            _request_fingerprint(serialized),
            configuration.configuration_id,
            configuration.strategy_id,
            configuration.strategy_version,
        )

    def claim(
        self,
        *,
        idempotency_key: str,
        request: ResearchLaunchRequest,
        environment: Mapping[str, Any] | None = None,
    ) -> ResearchLaunchClaim:
        """Atomically create or replay one run, event, and submission claim."""

        key = _validate_launch_key(idempotency_key)
        environment_json = canonical_json(dict(environment or {}))
        with self._connection() as connection:
            with self._immediate(connection):
                submissions = ResearchRunSubmissionRepository(connection)
                existing = submissions.get(key)
                if existing is not None:
                    operation, configuration_id, source_run_id, expected_lineage = (
                        self._normalize_request(request)
                    )
                    try:
                        existing_document = json.loads(existing.canonical_request_json)
                    except json.JSONDecodeError as exc:
                        raise ResearchLaunchIntegrityError(
                            "stored research submission request is invalid JSON"
                        ) from exc
                    if (
                        existing_document.get("operation_kind") != operation.value
                        or existing_document.get("configuration_id") != configuration_id
                        or existing_document.get("source_run_id") != source_run_id
                        or (
                            expected_lineage
                            and existing_document.get("source_lineage") != expected_lineage
                        )
                    ):
                        raise ResearchLaunchConflictError(
                            "research launch key is already bound to a different request"
                        )
                    run = self._validate_persisted_claim(
                        connection,
                        existing,
                        require_created_run=False,
                        require_launchable_configuration=False,
                    )
                    return ResearchLaunchClaim(existing, run, False)
                serialized, fingerprint, configuration_id, strategy_id, strategy_version = (
                    self._canonical_request_for_configuration(connection, request)
                )
                runs = RunRepository(connection)
                events = RunEventRepository(connection)
                run_id = _validate_run_id(self._run_id_factory())
                now = utc_now()
                run = runs.create(
                    run_id=run_id,
                    configuration_id=configuration_id,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    stage=RunStage.FIXTURE,
                    status=RunStatus.CREATED,
                    environment=json.loads(environment_json),
                )
                self._inject_claim_failure("after_run_create")
                events.append(
                    run_id=run.run_id,
                    event_type=RunEventType.RUN_CREATED,
                    severity=EventSeverity.INFO,
                    message="Run created for durable research fixture submission.",
                    occurred_at=run.created_at,
                )
                self._inject_claim_failure("after_run_created_event")
                submission = submissions.create(
                    idempotency_key=key,
                    run_id=run.run_id,
                    configuration_id=run.configuration_id,
                    canonical_request_json=serialized,
                    request_fingerprint=fingerprint,
                    claimed_at=now,
                )
                self._inject_claim_failure("after_submission_create")
                result = ResearchLaunchClaim(submission, run, True)
        return result

    def get(self, idempotency_key: str) -> ResearchRunSubmissionRecord | None:
        key = _validate_launch_key(idempotency_key)
        with self._connection() as connection:
            return ResearchRunSubmissionRepository(connection).get(key)

    def get_for_run(self, run_id: str) -> ResearchRunSubmissionRecord | None:
        run_id = _validate_run_id(run_id)
        with self._connection() as connection:
            return ResearchRunSubmissionRepository(connection).get_for_run(run_id)

    @staticmethod
    def _validate_persisted_claim(
        connection: sqlite3.Connection,
        submission: ResearchRunSubmissionRecord,
        *,
        require_created_run: bool,
        require_launchable_configuration: bool,
    ) -> ExperimentRunRecord:
        if _request_fingerprint(submission.canonical_request_json) != submission.request_fingerprint:
            raise ResearchLaunchIntegrityError(
                "stored research submission fingerprint is invalid"
            )
        try:
            document = json.loads(submission.canonical_request_json)
        except json.JSONDecodeError as exc:
            raise ResearchLaunchIntegrityError(
                "stored research submission request is invalid JSON"
            ) from exc
        if (
            not isinstance(document, dict)
            or canonical_json(document) != submission.canonical_request_json
        ):
            raise ResearchLaunchIntegrityError(
                "stored research submission request is not canonical"
            )
        try:
            operation = ResearchLaunchOperation(document["operation_kind"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchLaunchIntegrityError(
                "stored research submission operation is invalid"
            ) from exc
        if (
            document.get("protocol_version") != REQUEST_PROTOCOL_VERSION
            or document.get("accepted_launch_policy") != ACCEPTED_LAUNCH_POLICY
            or document.get("fixture_stage") != RunStage.FIXTURE.value
            or document.get("configuration_id") != submission.configuration_id
        ):
            raise ResearchLaunchIntegrityError(
                "stored research submission request contract is invalid"
            )
        configuration = ConfigurationRepository(connection).get(
            submission.configuration_id
        )
        if configuration is None:
            raise ResearchLaunchIntegrityError(
                "research submission references a missing saved configuration"
            )
        calculated_config_hash = hashlib.sha256(
            configuration.canonical_config_json.encode("utf-8")
        ).hexdigest()
        if (
            calculated_config_hash != configuration.config_hash
            or document.get("configuration_hash") != configuration.config_hash
            or document.get("strategy_id") != configuration.strategy_id
            or document.get("strategy_version") != configuration.strategy_version
        ):
            raise ResearchLaunchIntegrityError(
                "research submission saved-configuration identity is inconsistent"
            )
        strategy = StrategyRepository(connection).get(
            configuration.strategy_id,
            configuration.strategy_version,
        )
        if strategy is None:
            raise ResearchLaunchIntegrityError(
                "research submission references a missing strategy"
            )
        if require_launchable_configuration and (
            not strategy.active
            or strategy.lifecycle != StrategyLifecycle.INFRASTRUCTURE_FIXTURE
        ):
            raise ResearchLaunchIntegrityError(
                "research submission configuration is no longer launchable"
            )
        run = RunRepository(connection).get(submission.run_id)
        if run is None:
            raise ResearchLaunchIntegrityError(
                "research submission references a missing run"
            )
        if (
            run.configuration_id != submission.configuration_id
            or run.strategy_id != configuration.strategy_id
            or run.strategy_version != configuration.strategy_version
            or run.stage != RunStage.FIXTURE
        ):
            raise ResearchLaunchIntegrityError(
                "research submission run identity is inconsistent"
            )
        if require_created_run and run.status != RunStatus.CREATED:
            raise ResearchLaunchIntegrityError(
                "research submission run is not in Created state"
            )
        source_run_id = document.get("source_run_id")
        source_lineage = document.get("source_lineage")
        if source_run_id is not None and not isinstance(source_run_id, str):
            raise ResearchLaunchIntegrityError(
                "stored research submission source-run identity is invalid"
            )
        if not isinstance(source_lineage, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in source_lineage.items()
        ):
            raise ResearchLaunchIntegrityError(
                "stored research submission source lineage is invalid"
            )
        if operation == ResearchLaunchOperation.RUN_TEST:
            if source_run_id is not None or source_lineage:
                raise ResearchLaunchIntegrityError(
                    "run_test submission contains prohibited source lineage"
                )
        elif source_run_id is None:
            raise ResearchLaunchIntegrityError(
                f"{operation.value} submission has no source run"
            )
        derived_lineage = DurableResearchLaunchService._derive_source_lineage(
            connection,
            operation=operation,
            source_run_id=source_run_id,
            configuration_id=configuration.configuration_id,
            strategy_id=configuration.strategy_id,
            strategy_version=configuration.strategy_version,
        )
        if source_lineage != derived_lineage:
            raise ResearchLaunchIntegrityError(
                "stored research submission source lineage is inconsistent"
            )
        return run

    def begin_dispatch(
        self,
        *,
        idempotency_key: str,
        dispatcher_instance_id: str,
    ) -> ResearchDispatchDecision:
        """Commit the write-ahead marker; exactly one caller receives ``True``."""

        key = _validate_launch_key(idempotency_key)
        dispatcher = _validate_dispatcher_id(dispatcher_instance_id)
        with self._connection() as connection:
            with self._immediate(connection):
                submissions = ResearchRunSubmissionRepository(connection)
                existing = submissions.get(key)
                if existing is None:
                    raise KeyError(f"unknown research launch key: {key}")
                if existing.state == ResearchSubmissionState.CLAIMED:
                    self._validate_persisted_claim(
                        connection,
                        existing,
                        require_created_run=True,
                        require_launchable_configuration=True,
                    )
                won = submissions.set_invoking(
                    key,
                    dispatcher_instance_id=dispatcher,
                    invocation_started_at=utc_now(),
                )
                current = submissions.get(key)
                assert current is not None
        return ResearchDispatchDecision(current, won)

    @staticmethod
    def _binding_mismatch(
        submission: ResearchRunSubmissionRecord,
        *,
        run_id: str,
        configuration_id: str,
        canonical_request_json: str,
        request_fingerprint: str,
    ) -> bool:
        return (
            submission.run_id != run_id
            or submission.configuration_id != configuration_id
            or submission.canonical_request_json != canonical_request_json
            or submission.request_fingerprint != request_fingerprint
            or _request_fingerprint(canonical_request_json) != request_fingerprint
        )

    @staticmethod
    def _append_integrity_event(
        connection: sqlite3.Connection,
        submission: ResearchRunSubmissionRecord,
        message: str,
    ) -> None:
        events = RunEventRepository(connection)
        if any(
            event.event_type == RunEventType.SERVICE_INTEGRITY_ERROR
            and event.message == message
            for event in events.list_for_run(submission.run_id)
        ):
            return
        events.append(
            run_id=submission.run_id,
            event_type=RunEventType.SERVICE_INTEGRITY_ERROR,
            severity=EventSeverity.ERROR,
            message=message,
        )

    def bind_prefect_identity(
        self,
        *,
        idempotency_key: str,
        run_id: str,
        configuration_id: str,
        canonical_request_json: str,
        request_fingerprint: str,
        prefect_flow_run_id: str,
        prefect_api_url: str | None = None,
    ) -> ResearchRunSubmissionRecord:
        """Bind one Prefect identity and atomically move Created to Running."""

        key = _validate_launch_key(idempotency_key)
        run_id = _validate_run_id(run_id)
        configuration_id = _bounded_text(
            configuration_id, label="configuration ID", maximum=200
        )
        prefect_flow_run_id = _bounded_text(
            prefect_flow_run_id, label="Prefect flow-run ID", maximum=200
        )
        prefect_api_url = _optional_bounded_text(
            prefect_api_url, label="Prefect API URL", maximum=2048
        )
        integrity_error: ResearchLaunchIntegrityError | None = None
        with self._connection() as connection:
            with self._immediate(connection):
                submissions = ResearchRunSubmissionRepository(connection)
                runs = RunRepository(connection)
                events = RunEventRepository(connection)
                submission = submissions.get(key)
                if submission is None:
                    raise KeyError(f"unknown research launch key: {key}")
                try:
                    self._validate_persisted_claim(
                        connection,
                        submission,
                        require_created_run=(
                            submission.state != ResearchSubmissionState.ACKNOWLEDGED
                        ),
                        require_launchable_configuration=False,
                    )
                except ResearchLaunchIntegrityError as exc:
                    if runs.get(submission.run_id) is not None:
                        self._append_integrity_event(
                            connection,
                            submission,
                            "Research submission persisted identity failed acknowledgement validation.",
                        )
                    integrity_error = exc
                mismatch = self._binding_mismatch(
                    submission,
                    run_id=run_id,
                    configuration_id=configuration_id,
                    canonical_request_json=canonical_request_json,
                    request_fingerprint=request_fingerprint,
                )
                duplicate_prefect = connection.execute(
                    """
                    SELECT idempotency_key FROM research_run_submissions
                    WHERE prefect_flow_run_id=? AND idempotency_key!=?
                    """,
                    (prefect_flow_run_id, key),
                ).fetchone()
                if integrity_error is not None:
                    current = submission
                elif mismatch or duplicate_prefect is not None:
                    self._append_integrity_event(
                        connection,
                        submission,
                        "Research submission identity did not match the Prefect acknowledgement.",
                    )
                    integrity_error = ResearchLaunchIntegrityError(
                        "Prefect acknowledgement did not match the durable research claim"
                    )
                    current = submission
                elif submission.state == ResearchSubmissionState.ACKNOWLEDGED:
                    if (
                        submission.prefect_flow_run_id != prefect_flow_run_id
                        or submission.prefect_api_url != prefect_api_url
                    ):
                        self._append_integrity_event(
                            connection,
                            submission,
                            "Research submission received a conflicting Prefect acknowledgement.",
                        )
                        integrity_error = ResearchLaunchIntegrityError(
                            "research launch already has a different Prefect identity"
                        )
                    current = submission
                elif submission.state not in {
                    ResearchSubmissionState.INVOKING,
                    ResearchSubmissionState.SUBMISSION_UNKNOWN,
                }:
                    self._append_integrity_event(
                        connection,
                        submission,
                        "Research submission acknowledgement arrived in an invalid state.",
                    )
                    integrity_error = ResearchLaunchIntegrityError(
                        f"cannot acknowledge a {submission.state.value} research submission"
                    )
                    current = submission
                else:
                    run = runs.get(run_id)
                    if run is None or run.status != RunStatus.CREATED:
                        self._append_integrity_event(
                            connection,
                            submission,
                            "Research submission run was not Created at acknowledgement.",
                        )
                        integrity_error = ResearchLaunchIntegrityError(
                            "research claim run is not in Created state"
                        )
                        current = submission
                    else:
                        try:
                            environment = json.loads(run.environment_json)
                        except json.JSONDecodeError:
                            environment = None
                        if not isinstance(environment, dict):
                            self._append_integrity_event(
                                connection,
                                submission,
                                "Research submission run environment was invalid.",
                            )
                            integrity_error = ResearchLaunchIntegrityError(
                                "research claim run environment is invalid"
                            )
                            current = submission
                        else:
                            stored_prefect_id = environment.get("prefect_flow_run_id")
                            if stored_prefect_id not in {None, prefect_flow_run_id}:
                                self._append_integrity_event(
                                    connection,
                                    submission,
                                    "Research submission run had a conflicting Prefect identity.",
                                )
                                integrity_error = ResearchLaunchIntegrityError(
                                    "research claim run has a different Prefect identity"
                                )
                                current = submission
                            else:
                                environment.update(
                                    {
                                        "prefect_identity_storage": "technical_run_environment",
                                        "prefect_flow_run_id": prefect_flow_run_id,
                                        "prefect_reference_source": "durable_research_claim",
                                    }
                                )
                                if prefect_api_url is not None:
                                    environment["prefect_api_url"] = prefect_api_url
                                connection.execute(
                                    "UPDATE experiment_runs SET environment_json=? WHERE run_id=?",
                                    (canonical_json(environment), run_id),
                                )
                                acknowledged_at = utc_now()
                                if not submissions.set_acknowledged(
                                    key,
                                    prefect_flow_run_id=prefect_flow_run_id,
                                    prefect_api_url=prefect_api_url,
                                    acknowledged_at=acknowledged_at,
                                ):
                                    raise ResearchLaunchIntegrityError(
                                        "research submission changed during acknowledgement"
                                    )
                                running = runs.transition(run_id, RunStatus.RUNNING)
                                events.append(
                                    run_id=run_id,
                                    event_type=RunEventType.RUN_STARTED,
                                    severity=EventSeverity.INFO,
                                    message="Run started through acknowledged Prefect fixture execution.",
                                    occurred_at=running.started_at,
                                )
                                current = submissions.get(key)
                                assert current is not None
        if integrity_error is not None:
            raise integrity_error
        return current

    def mark_invocation_unknown(
        self,
        *,
        idempotency_key: str,
        dispatcher_instance_id: str,
        error_summary: str = "Prefect submission acknowledgement could not be confirmed.",
    ) -> ResearchRunSubmissionRecord:
        """Record ambiguity reported by the compare-and-set dispatch winner."""

        key = _validate_launch_key(idempotency_key)
        dispatcher = _validate_dispatcher_id(dispatcher_instance_id)
        summary = _bounded_text(error_summary, label="error summary", maximum=500)
        with self._connection() as connection:
            with self._immediate(connection):
                submissions = ResearchRunSubmissionRepository(connection)
                submission = submissions.get(key)
                if submission is None:
                    raise KeyError(f"unknown research launch key: {key}")
                if submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
                    if (
                        submission.dispatcher_instance_id != dispatcher
                        or submission.error_summary != summary
                        or submission.unknown_evidence_reference is not None
                    ):
                        raise ResearchLaunchConflictError(
                            "unknown-submission replay does not match the recorded ambiguity"
                        )
                    return submission
                if submission.state == ResearchSubmissionState.ACKNOWLEDGED:
                    return submission
                if submission.state != ResearchSubmissionState.INVOKING:
                    raise ResearchLaunchConflictError(
                        f"cannot mark a {submission.state.value} submission unknown"
                    )
                if submission.dispatcher_instance_id != dispatcher:
                    raise ResearchLaunchConflictError(
                        "only the invocation-marker winner may report submission ambiguity"
                    )
                if not submissions.set_unknown(
                    key,
                    unknown_at=utc_now(),
                    error_summary=summary,
                ):
                    raise ResearchLaunchIntegrityError(
                        "research submission changed while recording ambiguity"
                    )
                current = submissions.get(key)
                assert current is not None
                return current

    def recover_invoking_after_process_exit(
        self,
        *,
        idempotency_key: str,
        departed_dispatcher_instance_id: str,
        process_exit_evidence_reference: str,
    ) -> ResearchRunSubmissionRecord:
        """Convert Invoking to Unknown only after a caller-proved exit barrier."""

        key = _validate_launch_key(idempotency_key)
        departed = _validate_dispatcher_id(departed_dispatcher_instance_id)
        evidence = _bounded_text(
            process_exit_evidence_reference,
            label="process-exit evidence reference",
            maximum=500,
        )
        with self._connection() as connection:
            with self._immediate(connection):
                submissions = ResearchRunSubmissionRepository(connection)
                submission = submissions.get(key)
                if submission is None:
                    raise KeyError(f"unknown research launch key: {key}")
                if submission.state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
                    if (
                        submission.dispatcher_instance_id != departed
                        or submission.unknown_evidence_reference != evidence
                    ):
                        raise ResearchLaunchConflictError(
                            "exit-barrier replay does not match the recorded recovery evidence"
                        )
                    return submission
                if submission.state != ResearchSubmissionState.INVOKING:
                    raise ResearchLaunchConflictError(
                        f"cannot recover a {submission.state.value} submission as unknown"
                    )
                if submission.dispatcher_instance_id != departed:
                    raise ResearchLaunchConflictError(
                        "exit evidence does not name the recorded dispatcher generation"
                    )
                if not submissions.set_unknown(
                    key,
                    unknown_at=utc_now(),
                    error_summary=(
                        "The recorded dispatcher exited before Prefect acknowledgement could be confirmed."
                    ),
                    evidence_reference=evidence,
                ):
                    raise ResearchLaunchIntegrityError(
                        "research submission changed during exit-barrier recovery"
                    )
                current = submissions.get(key)
                assert current is not None
                return current

    def fail_before_submission(
        self,
        *,
        idempotency_key: str,
        error_summary: str,
    ) -> ResearchRunSubmissionRecord:
        """Atomically fail a Claimed run known not to have crossed invocation."""

        key = _validate_launch_key(idempotency_key)
        summary = _bounded_text(error_summary, label="error summary", maximum=500)
        with self._connection() as connection:
            with self._immediate(connection):
                submissions = ResearchRunSubmissionRepository(connection)
                runs = RunRepository(connection)
                events = RunEventRepository(connection)
                submission = submissions.get(key)
                if submission is None:
                    raise KeyError(f"unknown research launch key: {key}")
                if submission.state == ResearchSubmissionState.FAILED_BEFORE_SUBMISSION:
                    if submission.error_summary != summary:
                        raise ResearchLaunchConflictError(
                            "terminal research submission has different failure evidence"
                        )
                    return submission
                if submission.state != ResearchSubmissionState.CLAIMED:
                    raise ResearchLaunchConflictError(
                        f"cannot fail a {submission.state.value} submission before invocation"
                    )
                run = self._validate_persisted_claim(
                    connection,
                    submission,
                    require_created_run=True,
                    require_launchable_configuration=False,
                )
                resolved_at = utc_now()
                if not submissions.set_failed_before_submission(
                    key,
                    resolved_at=resolved_at,
                    error_summary=summary,
                ):
                    raise ResearchLaunchIntegrityError(
                        "research submission changed during pre-submission failure"
                    )
                failed = runs.transition(
                    run.run_id,
                    RunStatus.FAILED,
                    error_summary=summary,
                )
                events.append(
                    run_id=run.run_id,
                    event_type=RunEventType.RUN_FAILED,
                    severity=EventSeverity.ERROR,
                    message="Run failed before any Prefect submission occurred.",
                    occurred_at=failed.completed_at,
                )
                current = submissions.get(key)
                assert current is not None
                return current

    def abandon_unknown(
        self,
        *,
        idempotency_key: str,
        resolution_evidence_reference: str,
        error_summary: str = (
            "Submission was abandoned without accepted result evidence after explicit reconciliation."
        ),
    ) -> ResearchRunSubmissionRecord:
        """Apply the only terminal resolution for an unacknowledged ambiguity."""

        key = _validate_launch_key(idempotency_key)
        evidence = _bounded_text(
            resolution_evidence_reference,
            label="resolution evidence reference",
            maximum=500,
        )
        summary = _bounded_text(error_summary, label="error summary", maximum=500)
        with self._connection() as connection:
            with self._immediate(connection):
                submissions = ResearchRunSubmissionRepository(connection)
                runs = RunRepository(connection)
                events = RunEventRepository(connection)
                submission = submissions.get(key)
                if submission is None:
                    raise KeyError(f"unknown research launch key: {key}")
                if submission.state == ResearchSubmissionState.ABANDONED:
                    if (
                        submission.resolution_evidence_reference != evidence
                        or submission.error_summary != summary
                    ):
                        raise ResearchLaunchConflictError(
                            "terminal research submission has different resolution evidence"
                        )
                    return submission
                if submission.state != ResearchSubmissionState.SUBMISSION_UNKNOWN:
                    raise ResearchLaunchConflictError(
                        f"cannot abandon a {submission.state.value} submission"
                    )
                run = self._validate_persisted_claim(
                    connection,
                    submission,
                    require_created_run=True,
                    require_launchable_configuration=False,
                )
                resolved_at = utc_now()
                if not submissions.set_abandoned(
                    key,
                    resolved_at=resolved_at,
                    error_summary=summary,
                    evidence_reference=evidence,
                ):
                    raise ResearchLaunchIntegrityError(
                        "research submission changed during abandonment"
                    )
                failed = runs.transition(
                    run.run_id,
                    RunStatus.FAILED,
                    error_summary=summary,
                )
                events.append(
                    run_id=run.run_id,
                    event_type=RunEventType.RUN_FAILED,
                    severity=EventSeverity.ERROR,
                    message=(
                        "Unresolved submission was abandoned without accepted result evidence."
                    ),
                    occurred_at=failed.completed_at,
                )
                current = submissions.get(key)
                assert current is not None
                return current

    def dispatch(
        self,
        *,
        idempotency_key: str,
        dispatcher_instance_id: str,
        invoke: Callable[[ResearchRunSubmissionRecord], T],
    ) -> ResearchDispatchResult:
        """Invoke once after the marker; the injected callable must bind in-flow."""

        decision = self.begin_dispatch(
            idempotency_key=idempotency_key,
            dispatcher_instance_id=dispatcher_instance_id,
        )
        if not decision.should_invoke:
            return ResearchDispatchResult(decision.submission, False)
        try:
            value = invoke(decision.submission)
        except Exception as exc:
            current = self.mark_invocation_unknown(
                idempotency_key=idempotency_key,
                dispatcher_instance_id=dispatcher_instance_id,
            )
            if current.state == ResearchSubmissionState.SUBMISSION_UNKNOWN:
                raise ResearchLaunchInvocationUnknownError(
                    "research submission outcome is unknown and will not be retried automatically"
                ) from exc
            raise ResearchLaunchInvocationError(
                "research submission was acknowledged but invocation reported an error"
            ) from exc
        current = self.get(idempotency_key)
        assert current is not None
        if current.state == ResearchSubmissionState.INVOKING:
            current = self.mark_invocation_unknown(
                idempotency_key=idempotency_key,
                dispatcher_instance_id=dispatcher_instance_id,
                error_summary="Prefect invocation returned without durable acknowledgement.",
            )
            raise ResearchLaunchInvocationUnknownError(
                "research submission returned without durable acknowledgement"
            )
        return ResearchDispatchResult(current, True, value)
