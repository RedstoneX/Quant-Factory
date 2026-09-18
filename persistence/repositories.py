"""SQL repositories for the local experiment database."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import sqlite3
from typing import Any

from persistence.models import (
    ArtifactAvailability,
    ArtifactContractRecord,
    ArtifactRecord,
    ArtifactType,
    ConfigurationRecord,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    EventSeverity,
    ExperimentRunRecord,
    ParameterResultRecord,
    ReviewRecord,
    ReviewState,
    RunStage,
    RunEventRecord,
    RunEventType,
    RunStatus,
    StrategyLifecycle,
    StrategyRecord,
    coerce_enum,
    validate_run_transition,
)
from persistence.serialization import canonical_json, configuration_hash


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _strategy(row: sqlite3.Row | None) -> StrategyRecord | None:
    if row is None:
        return None
    return StrategyRecord(
        strategy_id=row["strategy_id"],
        strategy_version=row["strategy_version"],
        display_name=row["display_name"],
        description=row["description"],
        lifecycle=StrategyLifecycle(row["lifecycle"]),
        active=bool(row["active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _configuration(row: sqlite3.Row | None) -> ConfigurationRecord | None:
    if row is None:
        return None
    return ConfigurationRecord(**dict(row))


def _run(row: sqlite3.Row | None) -> ExperimentRunRecord | None:
    if row is None:
        return None
    return ExperimentRunRecord(
        run_id=row["run_id"],
        configuration_id=row["configuration_id"],
        strategy_id=row["strategy_id"],
        strategy_version=row["strategy_version"],
        stage=RunStage(row["stage"]),
        status=RunStatus(row["status"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_summary=row["error_summary"],
        environment_json=row["environment_json"],
        created_at=row["created_at"],
        attempt_count=row["attempt_count"],
    )


def _run_event(row: sqlite3.Row) -> RunEventRecord:
    values = dict(row)
    values["event_type"] = RunEventType(values["event_type"])
    values["severity"] = EventSeverity(values["severity"])
    return RunEventRecord(**values)


def _parameter(row: sqlite3.Row) -> ParameterResultRecord:
    return ParameterResultRecord(**dict(row))


def _provenance(row: sqlite3.Row | None) -> DataProvenanceRecord | None:
    if row is None:
        return None
    values = dict(row)
    values["adjusted"] = bool(values["adjusted"])
    return DataProvenanceRecord(**values)


def _execution(row: sqlite3.Row | None) -> ExecutionAssumptionsRecord | None:
    if row is None:
        return None
    return ExecutionAssumptionsRecord(**dict(row))


def _artifact(row: sqlite3.Row) -> ArtifactRecord:
    values = dict(row)
    return ArtifactRecord(
        artifact_id=values["artifact_id"],
        run_id=values["run_id"],
        artifact_type=values["artifact_type"],
        schema_version=values["schema_version"],
        path=values["path"],
        validation_status=values["validation_status"],
        checksum=values["checksum"],
        availability=ArtifactAvailability(values["availability"]),
        created_at=values["created_at"],
    )


def _artifact_contract(row: sqlite3.Row) -> ArtifactContractRecord:
    return ArtifactContractRecord(
        artifact_id=row["artifact_id"],
        run_id=row["run_id"],
        artifact_type=ArtifactType(row["artifact_type"]),
        logical_name=row["logical_name"],
        schema_version=row["schema_version"],
        media_type=row["media_type"],
        format=row["format"],
        checksum_algorithm=row["checksum_algorithm"],
        checksum=row["checksum"],
        size_bytes=row["size_bytes"],
        location=row["location"],
        availability_state=ArtifactAvailability(row["availability"]),
        created_at=row["created_at"],
    )


def _review(row: sqlite3.Row | None) -> ReviewRecord | None:
    if row is None:
        return None
    return ReviewRecord(
        target_type=row["target_type"],
        target_id=row["target_id"],
        state=ReviewState(row["state"]),
        note=row["note"],
        operator=row["operator"],
        updated_at=row["updated_at"],
    )


class StrategyRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        display_name: str,
        description: str,
        lifecycle: StrategyLifecycle,
        active: bool = True,
    ) -> StrategyRecord:
        now = utc_now()
        lifecycle = coerce_enum(StrategyLifecycle, lifecycle)
        existing = self.get(strategy_id, strategy_version)
        if existing is None:
            self.connection.execute(
                """
                INSERT INTO strategies
                (strategy_id, strategy_version, display_name, description, lifecycle,
                 active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strategy_id,
                    strategy_version,
                    display_name,
                    description,
                    lifecycle.value,
                    int(active),
                    now,
                    now,
                ),
            )
        else:
            self.connection.execute(
                """
                UPDATE strategies
                SET display_name=?, description=?, lifecycle=?, active=?, updated_at=?
                WHERE strategy_id=? AND strategy_version=?
                """,
                (
                    display_name,
                    description,
                    lifecycle.value,
                    int(active),
                    now,
                    strategy_id,
                    strategy_version,
                ),
            )
        record = self.get(strategy_id, strategy_version)
        assert record is not None
        return record

    def update_lifecycle(
        self,
        strategy_id: str,
        strategy_version: str,
        *,
        lifecycle: StrategyLifecycle,
        active: bool,
    ) -> StrategyRecord:
        lifecycle = coerce_enum(StrategyLifecycle, lifecycle)
        now = utc_now()
        cursor = self.connection.execute(
            """
            UPDATE strategies
            SET lifecycle=?, active=?, updated_at=?
            WHERE strategy_id=? AND strategy_version=?
            """,
            (lifecycle.value, int(active), now, strategy_id, strategy_version),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown strategy {strategy_id}@{strategy_version}")
        record = self.get(strategy_id, strategy_version)
        assert record is not None
        return record

    def get(self, strategy_id: str, strategy_version: str) -> StrategyRecord | None:
        return _strategy(
            self.connection.execute(
                """
                SELECT * FROM strategies
                WHERE strategy_id=? AND strategy_version=?
                """,
                (strategy_id, strategy_version),
            ).fetchone()
        )

    def list(self, *, active: bool | None = None) -> tuple[StrategyRecord, ...]:
        sql = "SELECT * FROM strategies"
        params: list[Any] = []
        if active is not None:
            sql += " WHERE active=?"
            params.append(int(active))
        sql += " ORDER BY strategy_id, strategy_version"
        return tuple(_strategy(row) for row in self.connection.execute(sql, params))


class ConfigurationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert(self, document: dict[str, Any]) -> ConfigurationRecord:
        canonical = canonical_json(document)
        digest = configuration_hash(document)
        configuration_id = digest
        existing = self.get(configuration_id)
        if existing is not None:
            if (
                existing.config_hash != digest
                or existing.canonical_config_json != canonical
            ):
                raise ValueError("configuration identity collision with different content")
            return existing
        row = self.connection.execute(
            "SELECT * FROM experiment_configurations WHERE config_hash=?",
            (digest,),
        ).fetchone()
        if row is not None:
            return _configuration(row)
        self.connection.execute(
            """
            INSERT INTO experiment_configurations
            (configuration_id, experiment_id, strategy_id, strategy_version,
             canonical_config_json, config_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                configuration_id,
                document["experiment_id"],
                document["strategy_id"],
                document["strategy_version"],
                canonical,
                digest,
                utc_now(),
            ),
        )
        record = self.get(configuration_id)
        assert record is not None
        return record

    def insert_record(self, record: ConfigurationRecord) -> ConfigurationRecord:
        digest = configuration_hash_json(record.canonical_config_json)
        existing = self.get(record.configuration_id)
        if existing is not None:
            if (
                existing.canonical_config_json != record.canonical_config_json
                or existing.config_hash != record.config_hash
            ):
                raise ValueError("configuration identity collision with different content")
            return existing
        if digest != record.config_hash:
            raise ValueError("configuration hash does not match canonical JSON")
        self.connection.execute(
            """
            INSERT INTO experiment_configurations
            (configuration_id, experiment_id, strategy_id, strategy_version,
             canonical_config_json, config_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.configuration_id,
                record.experiment_id,
                record.strategy_id,
                record.strategy_version,
                record.canonical_config_json,
                record.config_hash,
                record.created_at,
            ),
        )
        return record

    def get(self, configuration_id: str) -> ConfigurationRecord | None:
        return _configuration(
            self.connection.execute(
                "SELECT * FROM experiment_configurations WHERE configuration_id=?",
                (configuration_id,),
            ).fetchone()
        )

    def list(self, *, strategy_id: str | None = None) -> tuple[ConfigurationRecord, ...]:
        sql = "SELECT * FROM experiment_configurations"
        params: list[Any] = []
        if strategy_id:
            sql += " WHERE strategy_id=?"
            params.append(strategy_id)
        sql += " ORDER BY created_at, configuration_id"
        return tuple(_configuration(row) for row in self.connection.execute(sql, params))


def configuration_hash_json(canonical: str) -> str:
    import hashlib

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RunRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(
        self,
        *,
        run_id: str,
        configuration_id: str,
        strategy_id: str,
        strategy_version: str,
        stage: RunStage,
        status: RunStatus = RunStatus.CREATED,
        environment: dict[str, Any] | None = None,
    ) -> ExperimentRunRecord:
        stage = coerce_enum(RunStage, stage)
        status = coerce_enum(RunStatus, status)
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO experiment_runs
            (run_id, configuration_id, strategy_id, strategy_version, stage, status,
             started_at, completed_at, error_summary, environment_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                configuration_id,
                strategy_id,
                strategy_version,
                stage.value,
                status.value,
                now if status == RunStatus.RUNNING else None,
                now if status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED} else None,
                None,
                canonical_json(environment or {}),
                now,
            ),
        )
        record = self.get(run_id)
        assert record is not None
        return record

    def transition(
        self,
        run_id: str,
        new_status: RunStatus,
        *,
        error_summary: str | None = None,
    ) -> ExperimentRunRecord:
        current = self.get(run_id)
        if current is None:
            raise KeyError(f"unknown run {run_id}")
        new_status = coerce_enum(RunStatus, new_status)
        validate_run_transition(current.status, new_status)
        now = utc_now()
        started_at = current.started_at or (now if new_status == RunStatus.RUNNING else None)
        completed_at = now if new_status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED} else current.completed_at
        self.connection.execute(
            """
            UPDATE experiment_runs
            SET status=?, started_at=?, completed_at=?, error_summary=?
            WHERE run_id=?
            """,
            (new_status.value, started_at, completed_at, error_summary, run_id),
        )
        record = self.get(run_id)
        assert record is not None
        return record

    def increment_attempt(self, run_id: str) -> ExperimentRunRecord:
        cursor = self.connection.execute(
            """
            UPDATE experiment_runs
            SET attempt_count=attempt_count + 1
            WHERE run_id=?
            """,
            (run_id,),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown run {run_id}")
        record = self.get(run_id)
        assert record is not None
        return record

    def get(self, run_id: str) -> ExperimentRunRecord | None:
        return _run(
            self.connection.execute(
                "SELECT * FROM experiment_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        )

    def list(
        self,
        *,
        strategy_id: str | None = None,
        status: RunStatus | None = None,
        stage: RunStage | None = None,
    ) -> tuple[ExperimentRunRecord, ...]:
        sql = "SELECT * FROM experiment_runs"
        clauses: list[str] = []
        params: list[Any] = []
        if strategy_id:
            clauses.append("strategy_id=?")
            params.append(strategy_id)
        if status:
            clauses.append("status=?")
            params.append(coerce_enum(RunStatus, status).value)
        if stage:
            clauses.append("stage=?")
            params.append(coerce_enum(RunStage, stage).value)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC, run_id"
        return tuple(_run(row) for row in self.connection.execute(sql, params))


class RunEventRepository:
    """Append-only operator events. Prefect technical logs are never copied here."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def append(
        self,
        *,
        run_id: str,
        event_type: RunEventType,
        severity: EventSeverity,
        message: str,
        source: str = "quant_factory",
        occurred_at: str | None = None,
    ) -> RunEventRecord:
        event_type = coerce_enum(RunEventType, event_type)
        severity = coerce_enum(EventSeverity, severity)
        message = message.strip()
        if not message:
            raise ValueError("operator event message must not be empty")
        if len(message) > 500:
            raise ValueError("operator event message must be at most 500 characters")
        timestamp = occurred_at or utc_now()
        cursor = self.connection.execute(
            """
            INSERT INTO run_operator_events
            (run_id, event_type, occurred_at, severity, source, message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, event_type.value, timestamp, severity.value, source, message),
        )
        row = self.connection.execute(
            "SELECT * FROM run_operator_events WHERE event_id=?", (cursor.lastrowid,)
        ).fetchone()
        assert row is not None
        return _run_event(row)

    def list_for_run(self, run_id: str) -> tuple[RunEventRecord, ...]:
        return tuple(
            _run_event(row)
            for row in self.connection.execute(
                """
                SELECT * FROM run_operator_events
                WHERE run_id=?
                ORDER BY occurred_at, event_id
                """,
                (run_id,),
            )
        )

    def list_recent(self, *, limit: int = 20) -> tuple[RunEventRecord, ...]:
        if limit < 1:
            raise ValueError("recent event limit must be positive")
        return tuple(
            _run_event(row)
            for row in self.connection.execute(
                """
                SELECT * FROM run_operator_events
                ORDER BY occurred_at DESC, event_id DESC
                LIMIT ?
                """,
                (limit,),
            )
        )


class ResultRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def add_parameter_result(
        self,
        *,
        run_id: str,
        row_id: str,
        normalized_parameters: dict[str, Any],
        metrics: dict[str, Any],
        ranking_position: int,
        screening_status: str,
        rejection_reasons: str = "",
    ) -> ParameterResultRecord:
        self.connection.execute(
            """
            INSERT INTO parameter_results
            (run_id, row_id, normalized_parameters_json, metrics_json,
             ranking_position, screening_status, rejection_reasons)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                row_id,
                canonical_json(normalized_parameters),
                canonical_json(metrics),
                ranking_position,
                screening_status,
                rejection_reasons,
            ),
        )
        rows = self.list_parameter_results(run_id)
        return next(row for row in rows if row.row_id == row_id)

    def list_parameter_results(self, run_id: str) -> tuple[ParameterResultRecord, ...]:
        return tuple(
            _parameter(row)
            for row in self.connection.execute(
                """
                SELECT * FROM parameter_results
                WHERE run_id=?
                ORDER BY ranking_position, row_id
                """,
                (run_id,),
            )
        )

    def set_data_provenance(self, record: DataProvenanceRecord) -> DataProvenanceRecord:
        self.connection.execute(
            """
            INSERT INTO data_provenance
            (run_id, provider, provider_implementation, symbol, interval, timezone,
             requested_coverage, actual_coverage, adjusted, row_count, cache_action,
             validation_summary_json, manifest_reference, checksum)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run_id,
                record.provider,
                record.provider_implementation,
                record.symbol,
                record.interval,
                record.timezone,
                record.requested_coverage,
                record.actual_coverage,
                int(record.adjusted),
                record.row_count,
                record.cache_action,
                record.validation_summary_json,
                record.manifest_reference,
                record.checksum,
            ),
        )
        loaded = self.get_data_provenance(record.run_id)
        assert loaded is not None
        return loaded

    def get_data_provenance(self, run_id: str) -> DataProvenanceRecord | None:
        return _provenance(
            self.connection.execute(
                "SELECT * FROM data_provenance WHERE run_id=?",
                (run_id,),
            ).fetchone()
        )

    def set_execution_assumptions(
        self, record: ExecutionAssumptionsRecord
    ) -> ExecutionAssumptionsRecord:
        self.connection.execute(
            """
            INSERT INTO execution_assumptions (run_id, assumptions_json)
            VALUES (?, ?)
            """,
            (record.run_id, record.assumptions_json),
        )
        loaded = self.get_execution_assumptions(record.run_id)
        assert loaded is not None
        return loaded

    def get_execution_assumptions(
        self, run_id: str
    ) -> ExecutionAssumptionsRecord | None:
        return _execution(
            self.connection.execute(
                "SELECT * FROM execution_assumptions WHERE run_id=?",
                (run_id,),
            ).fetchone()
        )

    def add_artifact(
        self,
        *,
        run_id: str,
        artifact_type: str,
        schema_version: int,
        path: str,
        validation_status: str,
        availability: ArtifactAvailability,
        checksum: str | None = None,
    ) -> ArtifactRecord:
        availability = coerce_enum(ArtifactAvailability, availability)
        cursor = self.connection.execute(
            """
            INSERT INTO artifact_references
            (run_id, artifact_type, schema_version, path, validation_status,
             checksum, availability, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                artifact_type,
                schema_version,
                path,
                validation_status,
                checksum,
                availability.value,
                utc_now(),
            ),
        )
        return self.get_artifact(int(cursor.lastrowid))

    def get_artifact(self, artifact_id: int) -> ArtifactRecord:
        row = self.connection.execute(
            "SELECT * FROM artifact_references WHERE artifact_id=?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown artifact {artifact_id}")
        return _artifact(row)

    def list_artifacts(self, run_id: str) -> tuple[ArtifactRecord, ...]:
        return tuple(
            _artifact(row)
            for row in self.connection.execute(
                """
                SELECT * FROM artifact_references
                WHERE run_id=?
                ORDER BY artifact_type, artifact_id
                """,
                (run_id,),
            )
        )

    def register_artifact_contract(
        self,
        *,
        run_id: str,
        artifact_type: ArtifactType,
        logical_name: str,
        schema_version: int,
        media_type: str,
        format: str,
        checksum: str,
        size_bytes: int,
        location: str,
        availability_state: ArtifactAvailability,
        identity_key: str,
    ) -> ArtifactContractRecord:
        artifact_type = coerce_enum(ArtifactType, artifact_type)
        availability_state = coerce_enum(ArtifactAvailability, availability_state)
        existing = self.connection.execute(
            "SELECT * FROM artifact_references WHERE identity_key=?", (identity_key,)
        ).fetchone()
        immutable = (
            run_id, artifact_type.value, logical_name, schema_version, media_type,
            format, "sha256", checksum, size_bytes, location,
        )
        if existing is not None:
            existing_immutable = (
                existing["run_id"], existing["artifact_type"], existing["logical_name"],
                existing["schema_version"], existing["media_type"], existing["format"],
                existing["checksum_algorithm"], existing["checksum"], existing["size_bytes"],
                existing["location"],
            )
            if existing_immutable != immutable:
                raise ValueError("immutable artifact identity conflicts with existing artifact")
            return _artifact_contract(existing)
        cursor = self.connection.execute(
            """
            INSERT INTO artifact_references
            (run_id, artifact_type, schema_version, path, validation_status, checksum,
             availability, created_at, logical_name, media_type, format,
             checksum_algorithm, size_bytes, location, identity_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, artifact_type.value, schema_version, location, "registered", checksum,
                availability_state.value, utc_now(), logical_name, media_type, format,
                "sha256", size_bytes, location, identity_key,
            ),
        )
        row = self.connection.execute(
            "SELECT * FROM artifact_references WHERE artifact_id=?", (cursor.lastrowid,)
        ).fetchone()
        assert row is not None
        return _artifact_contract(row)

    def get_artifact_contract(self, artifact_id: int) -> ArtifactContractRecord:
        row = self.connection.execute(
            "SELECT * FROM artifact_references WHERE artifact_id=?", (artifact_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown artifact {artifact_id}")
        return _artifact_contract(row)

    def list_artifact_contracts(self, run_id: str) -> tuple[ArtifactContractRecord, ...]:
        return tuple(
            _artifact_contract(row)
            for row in self.connection.execute(
                """
                SELECT * FROM artifact_references WHERE run_id=? AND identity_key NOT LIKE 'legacy:%'
                ORDER BY artifact_type, logical_name, artifact_id
                """,
                (run_id,),
            )
        )

    def update_artifact_availability(
        self, artifact_id: int, availability: ArtifactAvailability
    ) -> ArtifactContractRecord:
        availability = coerce_enum(ArtifactAvailability, availability)
        cursor = self.connection.execute(
            "UPDATE artifact_references SET availability=? WHERE artifact_id=?",
            (availability.value, artifact_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown artifact {artifact_id}")
        return self.get_artifact_contract(artifact_id)


class ReviewRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def update(
        self,
        *,
        target_type: str,
        target_id: str,
        state: ReviewState,
        note: str,
        operator: str,
    ) -> ReviewRecord:
        state = coerce_enum(ReviewState, state)
        current = self.get_current(target_type, target_id)
        prior = current.state.value if current else None
        now = utc_now()
        self.connection.execute(
            """
            INSERT INTO review_audit_history
            (target_type, target_id, prior_state, new_state, note, operator, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (target_type, target_id, prior, state.value, note, operator, now),
        )
        self.connection.execute(
            """
            INSERT INTO review_current_state
            (target_type, target_id, state, note, operator, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_type, target_id) DO UPDATE SET
                state=excluded.state,
                note=excluded.note,
                operator=excluded.operator,
                updated_at=excluded.updated_at
            """,
            (target_type, target_id, state.value, note, operator, now),
        )
        record = self.get_current(target_type, target_id)
        assert record is not None
        return record

    def get_current(self, target_type: str, target_id: str) -> ReviewRecord | None:
        return _review(
            self.connection.execute(
                """
                SELECT * FROM review_current_state
                WHERE target_type=? AND target_id=?
                """,
                (target_type, target_id),
            ).fetchone()
        )

    def history(self, target_type: str, target_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            dict(row)
            for row in self.connection.execute(
                """
                SELECT * FROM review_audit_history
                WHERE target_type=? AND target_id=?
                ORDER BY audit_id
                """,
                (target_type, target_id),
            )
        )


def record_to_dict(record: Any) -> dict[str, Any]:
    values = asdict(record)
    return {
        key: value.value if isinstance(value, (StrategyLifecycle, RunStage, RunStatus, ArtifactAvailability, ArtifactType, ReviewState)) else value
        for key, value in values.items()
    }
