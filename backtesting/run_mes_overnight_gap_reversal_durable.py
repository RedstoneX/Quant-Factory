"""Durably launch and persist the single owner-accepted R11 MES screen."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pandas as pd

from backtesting.run_mes_overnight_gap_reversal import (
    DATASET_ID,
    DATASET_MANIFEST_REFERENCE,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EVIDENCE_CLASSIFICATION,
    EVIDENCE_LABEL,
    EXPECTED_DATASET_ROWS,
    EXPECTED_DATASET_SHA256,
    PROMOTION_BLOCKERS,
    MESGapInputs,
    MESGapScreenExecution,
    assert_exact_mes_manifest,
    execute_mes_overnight_gap_reversal,
    execution_assumptions,
    load_mes_gap_inputs,
    saved_configuration_document,
    verify_mes_vectorbt_runtime,
)
from backtesting.vectorbt_runtime import require_vectorbtpro
from market_data import load_data_locations, load_dataset_manifest, verify_dataset_file
from orchestration import CandidateRunService
from orchestration.candidate_run_service import CandidateScreeningLaunchResult
from orchestration.research_launch_claims import (
    CANDIDATE_SCREENING_LAUNCH_CONTRACT,
    DurableResearchLaunchService,
)
from persistence import (
    ArtifactAvailability,
    ArtifactType,
    DataProvenanceRecord,
    EventSeverity,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunEventType,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import database_path, transaction
from persistence.models import ResearchRunSubmissionRecord
from persistence.service import (
    RUNTIME_LINEAGE_ENVIRONMENT_KEY,
    capture_runtime_lineage_document,
)
from strategies.mes_overnight_gap_reversal import (
    MES_OVERNIGHT_GAP_REVERSAL_SPEC,
    MESMappingInterval,
    mes_mapping_checksum,
    normalize_mes_mapping,
    trade_document,
)

ARTIFACT_SCHEMA_VERSION = 1
SOURCE = "r11_mes_overnight_gap_reversal"
EXPECTED_VECTORBTPRO_VERSION = "2026.4.7"
FAILED_ATTEMPT_IDEMPOTENCY_KEY = "r11_mes_gap_20190506_20231229_v1"
FIXED_IDEMPOTENCY_KEY = "r11_mes_gap_20190506_20231229_v2"
EVIDENCE_SCOPE = "development_reference_only"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_REMOTE = "https://github.com/RedstoneX/Quant-Factory.git"


@dataclass(frozen=True)
class MESGapPreflight:
    configuration_id: str
    mapping_response: Mapping[str, Any]
    mapping_intervals: tuple[MESMappingInterval, ...]
    mapping_checksum: str
    dataset_path: Path
    locations_path: Path | None
    manifest_dir: Path | None
    runtime_lineage: dict[str, Any]
    canonical_git: dict[str, str]


@dataclass(frozen=True)
class MESDurableScreenOutcome:
    run_id: str
    configuration_id: str
    screening_status: str


@dataclass(frozen=True)
class MESDurableLaunch:
    preflight: MESGapPreflight
    launch: CandidateScreeningLaunchResult
    outcome: MESDurableScreenOutcome | None


def _resolve_mapping(api_key: str) -> Mapping[str, Any]:
    import databento as db

    return db.Historical(key=api_key).symbology.resolve(
        dataset="GLBX.MDP3",
        symbols=["MES.c.0"],
        stype_in="continuous",
        stype_out="instrument_id",
        start_date="2019-05-06",
        end_date="2023-12-30",
    )


def _git_stdout(*arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("canonical Git checkout verification failed") from exc
    if completed.returncode != 0:
        raise RuntimeError("canonical Git checkout verification failed")
    return completed.stdout.strip()


def verify_canonical_main_checkout() -> dict[str, str]:
    """Require clean local ``main`` at the live canonical GitHub main SHA."""
    remote_url = _git_stdout("remote", "get-url", "origin")
    if remote_url != CANONICAL_REMOTE:
        raise RuntimeError("screen launch requires the canonical GitHub repository")
    branch = _git_stdout("symbolic-ref", "--short", "HEAD")
    head = _git_stdout("rev-parse", "HEAD")
    origin_main = _git_stdout("rev-parse", "origin/main")
    remote_line = _git_stdout("ls-remote", "--exit-code", "origin", "refs/heads/main")
    remote_parts = remote_line.split()
    if len(remote_parts) != 2 or remote_parts[1] != "refs/heads/main":
        raise RuntimeError("canonical GitHub main reference is invalid")
    remote_main = remote_parts[0]
    if branch != "main" or not head or head != origin_main or head != remote_main:
        raise RuntimeError("screen launch requires the latest canonical main commit")
    return {
        "remote_url": remote_url,
        "branch": branch,
        "head": head,
        "origin_main": origin_main,
        "remote_main": remote_main,
    }


def _require_clean_licensed_runtime(
    runtime_lineage: Mapping[str, Any], canonical_git: Mapping[str, str]
) -> None:
    vectorbt = runtime_lineage.get("vectorbtpro")
    git = runtime_lineage.get("git")
    if not isinstance(vectorbt, Mapping) or not isinstance(git, Mapping):
        raise RuntimeError("runtime lineage is incomplete")
    if vectorbt.get("available") is not True:
        raise RuntimeError("the verified licensed VectorBT Pro runtime is unavailable")
    if vectorbt.get("version") != EXPECTED_VECTORBTPRO_VERSION:
        raise RuntimeError(
            f"VectorBT Pro {EXPECTED_VECTORBTPRO_VERSION} is required for the fixed screen"
        )
    if git.get("commit_available") is not True or git.get("dirty_state") != "clean":
        raise RuntimeError("the fixed screen must launch from a clean committed checkout")
    if git.get("commit_sha") != canonical_git.get("head"):
        raise RuntimeError("runtime lineage does not match the verified canonical commit")


def _preflight_mes_screen(
    *,
    database: str | Path | None = None,
    locations_path: Path | None = None,
    manifest_dir: Path | None = None,
    api_key: str | None = None,
    mapping_resolver: Callable[[str], Mapping[str, Any]] | None = None,
    runtime_lineage_provider: Callable[[], dict[str, Any]] = capture_runtime_lineage_document,
    vectorbt_loader: Callable[[], Any] = require_vectorbtpro,
    vectorbt_probe: Callable[[Any], Any] = verify_mes_vectorbt_runtime,
    canonical_checkout_verifier: Callable[[], dict[str, str]] = verify_canonical_main_checkout,
) -> MESGapPreflight:
    """Prove deterministic prerequisites before consuming the durable claim."""
    manifest = load_dataset_manifest(
        DATASET_ID,
        **({"manifest_dir": manifest_dir} if manifest_dir is not None else {}),
    )
    assert_exact_mes_manifest(manifest)
    locations = load_data_locations(
        **({"path": locations_path} if locations_path is not None else {})
    )
    dataset_path = verify_dataset_file(manifest, locations, require_validated=True)

    selected_key = api_key or os.environ.get("DATABENTO_API_KEY")
    if not selected_key:
        raise RuntimeError(
            "DATABENTO_API_KEY is required for the fixed free symbology resolution"
        )
    engine = vectorbt_loader()
    if getattr(engine, "__version__", None) != EXPECTED_VECTORBTPRO_VERSION:
        raise RuntimeError(
            f"VectorBT Pro {EXPECTED_VECTORBTPRO_VERSION} is required for the fixed screen"
        )
    runtime_lineage = runtime_lineage_provider()
    canonical_git = canonical_checkout_verifier()
    _require_clean_licensed_runtime(runtime_lineage, canonical_git)
    vectorbt_probe(engine)

    resolver = mapping_resolver or _resolve_mapping
    mapping_response = resolver(selected_key)
    intervals = normalize_mes_mapping(mapping_response)
    mapping_digest = mes_mapping_checksum(intervals)

    service = PersistenceService(database_path(database))
    try:
        spec = MES_OVERNIGHT_GAP_REVERSAL_SPEC
        existing_strategy = service.strategies.get(
            spec.identity.strategy_id, spec.identity.version
        )
        if existing_strategy is None:
            service.register_strategy(
                strategy_id=spec.identity.strategy_id,
                strategy_version=spec.identity.version,
                display_name=spec.identity.name,
                description=spec.identity.description,
                lifecycle=StrategyLifecycle.CANDIDATE,
                active=True,
            )
        elif not (
            (
                existing_strategy.lifecycle == StrategyLifecycle.CANDIDATE
                and existing_strategy.active
            )
            or (
                existing_strategy.lifecycle == StrategyLifecycle.REJECTED
                and not existing_strategy.active
            )
        ):
            raise RuntimeError("MES strategy has an incompatible durable lifecycle")
        configuration = service.upsert_configuration(saved_configuration_document())
        stored = service.configurations.get(configuration.configuration_id)
        expected = canonical_json(saved_configuration_document())
        if stored is None or stored.canonical_config_json != expected:
            raise RuntimeError("saved MES configuration differs from the fixed accepted screen")
    finally:
        service.close()
    return MESGapPreflight(
        configuration_id=configuration.configuration_id,
        mapping_response=mapping_response,
        mapping_intervals=intervals,
        mapping_checksum=mapping_digest,
        dataset_path=dataset_path,
        locations_path=locations_path,
        manifest_dir=manifest_dir,
        runtime_lineage=runtime_lineage,
        canonical_git=canonical_git,
    )


def preflight_mes_screen(*, locations_path: Path | None = None) -> MESGapPreflight:
    """Run the fixed production preflight with no replaceable evidence seams."""
    return _preflight_mes_screen(locations_path=locations_path)


def _artifact_root(database: str | Path) -> Path:
    resolved = Path(database).resolve()
    return resolved.parent.parent if resolved.parent.name == "state" else resolved.parent


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return None if isinstance(value, float) and pd.isna(value) else value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _series_records(series: pd.Series, name: str) -> list[dict[str, Any]]:
    return [
        {"timestamp": _json_value(index), name: _json_value(value)}
        for index, value in series.items()
    ]


def _provenance_record(
    run_id: str,
    inputs: MESGapInputs,
    execution: MESGapScreenExecution,
) -> DataProvenanceRecord:
    summary = {
        "dataset_id": DATASET_ID,
        "source_file_sha256": EXPECTED_DATASET_SHA256,
        "source_file_row_count": EXPECTED_DATASET_ROWS,
        "loaded_slice_row_count": len(inputs.data),
        "predicate_start_inclusive": DEVELOPMENT_START.isoformat(),
        "predicate_end_exclusive": DEVELOPMENT_END.isoformat(),
        "mapping_intervals": [item.document() for item in inputs.mapping_intervals],
        "mapping_checksum": inputs.mapping_checksum,
        "scheduled_session_count": len(execution.bundle.scheduled_sessions),
        "completed_trade_count": len(execution.bundle.completed_trades),
        "exclusion_reason_counts": execution.bundle.signals.metadata[
            "exclusion_reason_counts"
        ],
        "evidence_scope": EVIDENCE_SCOPE,
    }
    return DataProvenanceRecord(
        run_id=run_id,
        provider="Databento",
        provider_implementation="GLBX.MDP3 MES.c.0 unadjusted continuous series",
        symbol="MES",
        interval="5m",
        timezone="UTC",
        requested_coverage=(
            f"{DEVELOPMENT_START.isoformat()} <= ts_event < {DEVELOPMENT_END.isoformat()}"
        ),
        actual_coverage=f"{inputs.data.index[0].isoformat()}..{inputs.data.index[-1].isoformat()}",
        adjusted=False,
        row_count=len(inputs.data),
        cache_action="verified source file; predicate-bounded materialization",
        validation_summary_json=canonical_json(summary),
        manifest_reference=DATASET_MANIFEST_REFERENCE,
        checksum=inputs.manifest.sha256,
    )


def _artifact_documents(
    *,
    run_id: str,
    configuration_id: str,
    inputs: MESGapInputs,
    execution: MESGapScreenExecution,
) -> tuple[dict[str, Any], ...]:
    result = execution.result
    row = result.ranked_results.iloc[0].to_dict()
    status = str(row["screening_status"])
    base = f"state/artifacts/{run_id}"
    mapping = {
        "provider": "Databento",
        "request": saved_configuration_document()["market_data"]["symbology_request"],
        "interval_semantics": "[d0,d1)",
        "intervals": [item.document() for item in inputs.mapping_intervals],
        "checksum_algorithm": "sha256:canonical-json:v1",
        "checksum": inputs.mapping_checksum,
    }
    validation = {
        "stage": "screening",
        "screening_status": status,
        "evidence_scope": EVIDENCE_SCOPE,
        "evidence_label": EVIDENCE_LABEL,
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "independent_observation": False,
        "out_of_sample": False,
        "protected_data_used": False,
        "edge_proof": False,
        "automatic_promotion": False,
        "promotion_eligible": False,
        "promotion_blockers": PROMOTION_BLOCKERS,
        "mapping": mapping,
        "session_classification": _json_value(execution.bundle.signals.metadata),
        "engine_manual_cross_checks": _json_value(result.validation_results),
        "accounting_authority": "schedule-complete manual daily equity",
    }
    dataset_manifest = {
        "full_source_manifest": dict(inputs.manifest.metadata),
        "loaded_slice": {
            "row_count": len(inputs.data),
            "first_timestamp": inputs.data.index[0].isoformat(),
            "last_timestamp": inputs.data.index[-1].isoformat(),
            "predicate_start_inclusive": DEVELOPMENT_START.isoformat(),
            "predicate_end_exclusive": DEVELOPMENT_END.isoformat(),
        },
    }
    documents = (
        (
            ArtifactType.RUN_SUMMARY,
            "run_summary",
            {
                "run_id": run_id,
                "configuration_id": configuration_id,
                "experiment_id": result.experiment_id,
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                "run_status": RunStatus.SUCCEEDED.value,
                "screening_status": status,
                "evaluated_combinations": 1,
                "broker_orders": "disabled",
                "evidence_scope": EVIDENCE_SCOPE,
                "promotion_eligible": False,
            },
        ),
        (
            ArtifactType.METRICS,
            "metrics",
            {
                "metrics": {
                    name: _json_value(row[name])
                    for name in (
                        "total_return",
                        "annualized_return",
                        "sharpe_ratio",
                        "max_drawdown",
                        "number_of_trades",
                        "win_rate",
                    )
                },
                "scheduled_session_count": len(execution.bundle.scheduled_sessions),
            },
        ),
        (
            ArtifactType.PARAMETER_RESULTS,
            "parameter_results",
            {"ranked_results": [_json_value(row)], "fixed_parameters": {}},
        ),
        (
            ArtifactType.TRADES_OR_ORDERS,
            "trades_and_orders",
            {
                "instrument": "MES",
                "contract_count": 1,
                "price_unit": "index_points",
                "pnl_unit": "USD",
                "manual_trades": [
                    _json_value(trade_document(item))
                    for item in execution.bundle.completed_trades
                ],
                "vectorbt_trades": _records(
                    execution.portfolio.trades.records_readable
                ),
                "vectorbt_orders": _records(
                    execution.portfolio.orders.records_readable
                ),
            },
        ),
        (
            ArtifactType.EQUITY_CURVE,
            "equity_curve",
            {
                "equity_curve": _series_records(execution.daily_equity, "equity"),
                "daily_returns": _series_records(
                    execution.daily_returns, "daily_return"
                ),
                "basis": "every scheduled NYSE development session",
            },
        ),
        (ArtifactType.VALIDATION_EVIDENCE, "validation_evidence", validation),
        (ArtifactType.VALIDATION_EVIDENCE, "symbology_mapping", mapping),
        (ArtifactType.DATASET_MANIFEST, "dataset_manifest", dataset_manifest),
    )
    return tuple(
        {
            "artifact_type": artifact_type,
            "logical_name": logical_name,
            "location": f"{base}/{logical_name}.json",
            "content": (canonical_json(document) + "\n").encode("utf-8"),
        }
        for artifact_type, logical_name, document in documents
    )


def _persist_success(
    service: PersistenceService,
    *,
    run_id: str,
    configuration_id: str,
    inputs: MESGapInputs,
    execution: MESGapScreenExecution,
    artifact_root: Path,
) -> MESDurableScreenOutcome:
    artifacts = _artifact_documents(
        run_id=run_id,
        configuration_id=configuration_id,
        inputs=inputs,
        execution=execution,
    )
    final_directory = artifact_root / "state" / "artifacts" / run_id
    staging_directory = final_directory.with_name(f".{run_id}.staging")
    if final_directory.exists() or staging_directory.exists():
        raise RuntimeError("run artifact target already exists")
    row = execution.result.ranked_results.iloc[0]
    status = str(row["screening_status"])
    try:
        for artifact in artifacts:
            relative = Path(artifact["location"])
            target = staging_directory / relative.relative_to(
                Path("state") / "artifacts" / run_id
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(artifact["content"])
        final_directory.parent.mkdir(parents=True, exist_ok=True)
        staging_directory.replace(final_directory)
        with transaction(service.connection):
            service.require_active_run_for_completion(run_id)
            service._persist_rows(run_id, execution.result)
            service.results.set_data_provenance(
                _provenance_record(run_id, inputs, execution)
            )
            service.results.set_execution_assumptions(
                ExecutionAssumptionsRecord(
                    run_id=run_id,
                    assumptions_json=canonical_json(execution_assumptions()),
                )
            )
            if status == "screened_out":
                service.strategies.update_lifecycle(
                    MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.strategy_id,
                    MES_OVERNIGHT_GAP_REVERSAL_SPEC.identity.version,
                    lifecycle=StrategyLifecycle.REJECTED,
                    active=False,
                )
            for artifact in artifacts:
                content = artifact["content"]
                artifact_type = ArtifactType(artifact["artifact_type"])
                identity_key = hashlib.sha256(
                    canonical_json(
                        {
                            "run_id": run_id,
                            "artifact_type": artifact_type.value,
                            "logical_name": artifact["logical_name"],
                            "schema_version": ARTIFACT_SCHEMA_VERSION,
                        }
                    ).encode("utf-8")
                ).hexdigest()
                service.results.register_artifact_contract(
                    run_id=run_id,
                    artifact_type=artifact_type,
                    logical_name=artifact["logical_name"],
                    schema_version=ARTIFACT_SCHEMA_VERSION,
                    media_type="application/json",
                    format="json",
                    checksum=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                    location=artifact["location"],
                    availability_state=ArtifactAvailability.AVAILABLE,
                    identity_key=identity_key,
                )
            manifest = service.build_run_manifest(run_id)
            serialized = service.serialize_run_manifest(manifest)
            checksum = service.run_manifest_checksum(manifest)
            service.connection.execute(
                "INSERT INTO run_manifests "
                "(run_id, schema_version, manifest_json, content_checksum, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    manifest.run_id,
                    manifest.schema_version,
                    serialized,
                    checksum,
                    manifest.created_at,
                ),
            )
            completed = service.runs.transition(run_id, RunStatus.SUCCEEDED)
            service.events.append(
                run_id=run_id,
                event_type=RunEventType.RUN_SUCCEEDED,
                severity=EventSeverity.INFO,
                source=SOURCE,
                message=(
                    "Completed the fixed MES overnight-gap reversal development "
                    f"screen with outcome {status}; no promotion was started."
                ),
                occurred_at=completed.completed_at or completed.created_at,
            )
    except Exception:
        if staging_directory.exists():
            shutil.rmtree(staging_directory)
        if final_directory.exists():
            shutil.rmtree(final_directory)
        raise
    return MESDurableScreenOutcome(
        run_id=run_id,
        configuration_id=configuration_id,
        screening_status=status,
    )


def _fail_active_run(service: PersistenceService, run_id: str) -> None:
    run = service.runs.get(run_id)
    if run is None or run.status in {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }:
        return
    message = (
        "The fixed MES development screen failed after acknowledged start; "
        "no candidate result was accepted."
    )
    service.transition_run_with_operator_event(
        run_id=run_id,
        status=RunStatus.FAILED,
        event_type=RunEventType.RUN_FAILED,
        severity=EventSeverity.ERROR,
        source=SOURCE,
        message=message,
        error_summary=message,
    )


class _MESGapDurableRuntime:
    """Candidate-local screening-only runtime for one preflighted request."""

    def __init__(
        self,
        *,
        database: str | Path,
        artifact_root: str | Path,
        preflight: MESGapPreflight,
        loader: Callable[[], MESGapInputs] | None = None,
        executor: Callable[[MESGapInputs], MESGapScreenExecution] | None = None,
        dispatcher_instance_id: str | None = None,
    ) -> None:
        self.database = Path(database)
        self.artifact_root = Path(artifact_root).resolve()
        self.preflight = preflight
        self.loader = loader or self._load_inputs
        self.executor = executor or self._execute
        self.dispatcher_instance_id = dispatcher_instance_id

    def _load_inputs(self) -> MESGapInputs:
        return load_mes_gap_inputs(
            mapping_response=self.preflight.mapping_response,
            manifest_dir=self.preflight.manifest_dir,
            locations_path=self.preflight.locations_path,
        )

    @staticmethod
    def _execute(inputs: MESGapInputs) -> MESGapScreenExecution:
        return execute_mes_overnight_gap_reversal(
            inputs.data,
            inputs.audit,
            inputs.mapping_intervals,
        )

    def _prefect_adapter(
        self,
        submission: ResearchRunSubmissionRecord,
        _claims: DurableResearchLaunchService,
    ) -> MESDurableScreenOutcome:
        from prefect_spike.mes_overnight_gap_reversal_flow import run_mes_gap_screen_flow

        return run_mes_gap_screen_flow(runtime=self, submission=submission)

    def launch(self) -> CandidateScreeningLaunchResult:
        service = CandidateRunService(
            database=self.database,
            screening_adapter=self._prefect_adapter,
            dispatcher_instance_id=self.dispatcher_instance_id,
        )
        return service.launch_screening(
            idempotency_key=FIXED_IDEMPOTENCY_KEY,
            configuration_id=self.preflight.configuration_id,
            environment={
                "candidate": SOURCE,
                "evidence_scope": EVIDENCE_SCOPE,
                "mapping_checksum": self.preflight.mapping_checksum,
                "canonical_git": self.preflight.canonical_git,
                "recovery_of": FAILED_ATTEMPT_IDEMPOTENCY_KEY,
                "recovery_reason": "predicate_loader_index_contract",
                RUNTIME_LINEAGE_ENVIRONMENT_KEY: self.preflight.runtime_lineage,
            },
        )

    def reopen_completed_outcome(self, run_id: str) -> MESDurableScreenOutcome | None:
        service = PersistenceService(self.database)
        try:
            run = service.runs.get(run_id)
            if run is None or run.stage.value != "screening" or run.status != RunStatus.SUCCEEDED:
                return None
            rows = service.results.list_parameter_results(run_id)
            if len(rows) != 1 or rows[0].screening_status not in {
                "passed",
                "screened_out",
            }:
                raise RuntimeError("completed MES screen evidence cannot be reopened safely")
            return MESDurableScreenOutcome(
                run_id=run_id,
                configuration_id=run.configuration_id,
                screening_status=rows[0].screening_status,
            )
        finally:
            service.close()

    def execute_flow(
        self,
        *,
        submission: ResearchRunSubmissionRecord,
        prefect_flow_run_id: str,
    ) -> MESDurableScreenOutcome:
        claims = DurableResearchLaunchService(
            database=self.database,
            launch_contract=CANDIDATE_SCREENING_LAUNCH_CONTRACT,
            initialize_schema=False,
        )
        claims.bind_prefect_identity(
            idempotency_key=submission.idempotency_key,
            run_id=submission.run_id,
            configuration_id=submission.configuration_id,
            canonical_request_json=submission.canonical_request_json,
            request_fingerprint=submission.request_fingerprint,
            prefect_flow_run_id=prefect_flow_run_id,
        )
        service = PersistenceService(self.database)
        try:
            try:
                stored = service.configurations.get(submission.configuration_id)
                if (
                    stored is None
                    or stored.canonical_config_json
                    != canonical_json(saved_configuration_document())
                ):
                    raise RuntimeError(
                        "claimed configuration differs from the fixed accepted screen"
                    )
                inputs = self.loader()
                if inputs.mapping_checksum != self.preflight.mapping_checksum:
                    raise RuntimeError(
                        "loaded symbology mapping differs from the preflighted mapping"
                    )
                execution = self.executor(inputs)
                if (
                    execution.result.evaluated_combinations != 1
                    or len(execution.result.ranked_results) != 1
                ):
                    raise RuntimeError("the fixed screen must produce exactly one result row")
                status = str(
                    execution.result.ranked_results.iloc[0]["screening_status"]
                )
                if status not in {"passed", "screened_out"}:
                    raise RuntimeError("the fixed screen produced an invalid outcome")
                return _persist_success(
                    service,
                    run_id=submission.run_id,
                    configuration_id=submission.configuration_id,
                    inputs=inputs,
                    execution=execution,
                    artifact_root=self.artifact_root,
                )
            except Exception:
                _fail_active_run(service, submission.run_id)
                raise
        finally:
            service.close()


def launch_mes_screen(
    *,
    locations_path: Path | None = None,
) -> MESDurableLaunch:
    resolved_database = database_path(None)
    root = _artifact_root(resolved_database)
    preflight = preflight_mes_screen(
        locations_path=locations_path,
    )
    runtime = _MESGapDurableRuntime(
        database=resolved_database,
        artifact_root=root,
        preflight=preflight,
    )
    launch = runtime.launch()
    value = launch.dispatch.value
    outcome = (
        value
        if isinstance(value, MESDurableScreenOutcome)
        else runtime.reopen_completed_outcome(launch.claim.run.run_id)
    )
    return MESDurableLaunch(preflight=preflight, launch=launch, outcome=outcome)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the one fixed owner-accepted R11 MES development screen."
    )
    parser.add_argument("--locations", type=Path, default=None)
    args = parser.parse_args(argv)
    launched = launch_mes_screen(
        locations_path=args.locations,
    )
    print(launched.launch.claim.run.run_id)
    if launched.outcome is not None:
        print(launched.outcome.screening_status)
        return 0
    print(launched.launch.dispatch.submission.state.value)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
