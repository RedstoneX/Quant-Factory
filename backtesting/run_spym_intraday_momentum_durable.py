"""Persist the one fixed Decision-296 SPYM intraday-momentum screen."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from numbers import Real
from pathlib import Path
import shutil
import sys
from typing import Any, Callable, Mapping
from uuid import uuid4

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.run_spym_intraday_momentum import (  # noqa: E402
    DATASET_ID, DATASET_MANIFEST_REFERENCE, EVIDENCE_CLASSIFICATION,
    EVIDENCE_LABEL, EXPECTED_DATASET_ROWS, EXPECTED_DATASET_SHA256,
    PROMOTION_BLOCKERS, SPYMMomentumExecution,
    execution_assumptions, execute_spym_intraday_momentum,
    load_spym_intraday_momentum_inputs, saved_configuration_document,
)
from persistence import (  # noqa: E402
    ArtifactAvailability, ArtifactType, DataProvenanceRecord, EventSeverity,
    ExecutionAssumptionsRecord, PersistenceService, RunEventType, RunStage,
    RunStatus, StrategyLifecycle, canonical_json,
)
from persistence.database import database_path, transaction  # noqa: E402
from strategies.spym_intraday_momentum import SPYM_INTRADAY_MOMENTUM_SPEC  # noqa: E402

ARTIFACT_SCHEMA_VERSION = 1
SOURCE = "decision_296_spym_intraday_momentum"


@dataclass(frozen=True)
class PreparedRun:
    configuration_id: str
    run_id: str


@dataclass(frozen=True)
class DurableMomentumOutcome:
    run: PreparedRun
    failures: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0


def prepare_run(service: PersistenceService, *, run_id: str | None = None) -> PreparedRun:
    selected_run_id = run_id or f"spym_intraday_momentum_{uuid4().hex}"
    spec = SPYM_INTRADAY_MOMENTUM_SPEC
    with transaction(service.connection):
        service.strategies.upsert(
            strategy_id=spec.identity.strategy_id, strategy_version=spec.identity.version,
            display_name=spec.identity.name, description=spec.identity.description,
            lifecycle=StrategyLifecycle.CANDIDATE, active=True,
        )
        configuration = service.configurations.upsert(saved_configuration_document())
        run = service.runs.create(
            run_id=selected_run_id, configuration_id=configuration.configuration_id,
            strategy_id=spec.identity.strategy_id, strategy_version=spec.identity.version,
            stage=RunStage.SCREENING, status=RunStatus.CREATED,
            environment=service._freeze_environment({
                "controlled_candidate": "decision_296_spym_intraday_momentum",
                "evidence_scope": "development_reference_only",
            }),
        )
        service.events.append(
            run_id=run.run_id, event_type=RunEventType.RUN_CREATED, severity=EventSeverity.INFO,
            source=SOURCE, message="Prepared one fixed SPYM intraday-momentum development/reference screen; no computation has started.",
            occurred_at=run.created_at,
        )
    return PreparedRun(configuration_id=configuration.configuration_id, run_id=selected_run_id)


def _artifact_root(database: str | Path) -> Path:
    resolved = Path(database).resolve()
    return resolved.parent.parent if resolved.parent.name == "state" else resolved.parent


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    return None if isinstance(value, float) and pd.isna(value) else value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(key): _json_value(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _series_records(series: Any, name: str) -> list[dict[str, Any]]:
    if isinstance(series, pd.DataFrame):
        if series.shape[1] != 1:
            raise RuntimeError("expected one-column portfolio series")
        series = series.iloc[:, 0]
    return [{"timestamp": _json_value(index), name: _json_value(value)} for index, value in series.items()]


def _price_series_records(data: pd.DataFrame) -> list[dict[str, Any]]:
    return [{"timestamp": _json_value(index), "open": _json_value(row.Open), "high": _json_value(row.High), "low": _json_value(row.Low), "close": _json_value(row.Close)} for index, row in data[["Open", "High", "Low", "Close"]].iterrows()]


def _provenance_record(run_id: str, fixture: SPYMMomentumExecution) -> DataProvenanceRecord:
    metadata = fixture.manifest.metadata
    summary = {
        "dataset_id": DATASET_ID, "dataset": metadata["dataset"], "schema": metadata["schema"],
        "sha256": EXPECTED_DATASET_SHA256, "row_count": EXPECTED_DATASET_ROWS,
        "observed_regular_session_bar_count": metadata["observed_regular_session_bar_count"],
        "possible_regular_session_minute_count": metadata["possible_regular_session_minute_count"],
        "missing_regular_session_bar_count": metadata["missing_regular_session_bar_count"],
        "missing_session_count": metadata["missing_session_count"], "synthetic_bar_count": metadata["synthetic_bar_count"],
        "adjustment": "raw", "evidence_scope": "development_reference_only",
    }
    return DataProvenanceRecord(
        run_id=run_id, provider="Databento", provider_implementation=f"{metadata['dataset']} {metadata['schema']}",
        symbol="SPYM", interval="1m", timezone="UTC",
        requested_coverage=f"{metadata['coverage_start']}..{metadata['latest_completed_session']}",
        actual_coverage=f"{metadata['earliest_timestamp']}..{metadata['latest_timestamp']}", adjusted=False,
        row_count=fixture.manifest.row_count, cache_action="verified", validation_summary_json=canonical_json(summary),
        manifest_reference=DATASET_MANIFEST_REFERENCE, checksum=fixture.manifest.sha256,
    )


def _artifact_documents(prepared: PreparedRun, fixture: SPYMMomentumExecution, result: Any, portfolio: Any, bundle: Any) -> tuple[dict[str, Any], ...]:
    row = result.ranked_results.iloc[0].to_dict()
    base = f"state/artifacts/{prepared.run_id}"
    validation = {
        "stage": RunStage.SCREENING.value, "evidence_scope": "development_reference_only",
        "evidence_label": EVIDENCE_LABEL,
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "independent_observation": False, "out_of_sample": False, "protected_data_used": False,
        "edge_proof": False, "promotion_eligible": False, "promotion_blockers": PROMOTION_BLOCKERS,
        "dataset_manifest": {"reference": DATASET_MANIFEST_REFERENCE, "sha256": fixture.manifest.sha256,
                             "row_count": fixture.manifest.row_count, "status": fixture.manifest.status},
        "session_readiness": bundle.signals.metadata,
        "annualization": execution_assumptions()["annualization"],
        "max_drawdown_basis": execution_assumptions()["max_drawdown_basis"],
        "max_drawdown_limitation": execution_assumptions()["max_drawdown_limitation"],
        "result_validation": list(result.validation_results),
        "screening": {
            "evaluated_combinations": result.evaluated_combinations,
            "passed": len(result.passing_results),
            "screened_out": len(result.screened_out_results),
        },
    }
    documents = (
        (ArtifactType.RUN_SUMMARY, "run_summary", {"run_id": prepared.run_id, "configuration_id": prepared.configuration_id,
         "experiment_id": result.experiment_id, "strategy_id": result.strategy_id, "strategy_version": result.strategy_version,
         "status_at_artifact_capture": RunStatus.RUNNING.value, "evaluated_combinations": 1, "broker_orders": "disabled",
         "evidence_label": EVIDENCE_LABEL, "evidence_scope": "development_reference_only",
         "evidence_classification": EVIDENCE_CLASSIFICATION, "promotion_eligible": False,
         "promotion_blockers": PROMOTION_BLOCKERS}),
        (ArtifactType.METRICS, "metrics", {"metrics": {name: _json_value(row[name]) for name in ("total_return", "annualized_return", "sharpe_ratio", "max_drawdown", "number_of_trades", "win_rate")}}),
        (ArtifactType.PARAMETER_RESULTS, "parameter_results", {"ranked_results": [{str(key): _json_value(value) for key, value in row.items()}]}),
        (ArtifactType.TRADES_OR_ORDERS, "trades_and_orders", {"parameter_row_id": row["parameter_row_id"], "ranking_position": 1,
         "instrument": "SPYM", "price_unit": "currency", "pnl_unit": "USD",
         "trades": _records(portfolio.trades.records_readable), "orders": _records(portfolio.orders.records_readable),
         "entry_price": "base price: observed current 15:30 Open; fill applies 0.02% adverse slippage",
         "exit_price": "base price: observed current 15:59 Close; fill applies 0.02% adverse slippage",
         "fee_rate": 0.0005, "adverse_slippage_rate": 0.0002}),
        (ArtifactType.EQUITY_CURVE, "equity_curve", {"equity_curve": _series_records(portfolio.value, "value"), "price_series": _price_series_records(fixture.data)}),
        (ArtifactType.VALIDATION_EVIDENCE, "validation_evidence", validation),
        (ArtifactType.DATASET_MANIFEST, "dataset_manifest", dict(fixture.manifest.metadata)),
    )
    return tuple({"artifact_type": artifact_type, "logical_name": name, "location": f"{base}/{name}.json",
                  "content": (canonical_json(document) + "\n").encode("utf-8")} for artifact_type, name, document in documents)


def _assert_ranked_trade_count_matches_ledger(result: Any, portfolio: Any, bundle: Any) -> None:
    """Do not persist a ranked metric that disagrees with the readable trade ledger."""
    row = result.ranked_results.iloc[0]
    recorded = row.get("number_of_trades")
    if not isinstance(recorded, Real) or isinstance(recorded, bool) or not math.isfinite(float(recorded)):
        raise RuntimeError("ranked result must contain a finite number_of_trades metric")
    if float(recorded) != int(float(recorded)):
        raise RuntimeError("ranked result number_of_trades must be an integer")
    trades = portfolio.trades.records_readable
    if not isinstance(trades, pd.DataFrame):
        raise RuntimeError("readable trade ledger must be a dataframe")
    expected = bundle.signals.metadata.get("eligible_session_count")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected <= 0:
        raise RuntimeError("session readiness must contain a positive eligible_session_count")
    if len(trades) != expected or int(recorded) != len(trades):
        raise RuntimeError(
            "ranked result number_of_trades does not match the readable trade ledger and eligible sessions"
        )


def _persist_success(service: PersistenceService, prepared: PreparedRun, fixture: SPYMMomentumExecution, result: Any, artifacts: tuple[dict[str, Any], ...], artifact_root: Path) -> None:
    """Stage bytes first, then atomically commit all durable success records."""
    final_directory = artifact_root / "state" / "artifacts" / prepared.run_id
    staging_directory = final_directory.with_name(f".{prepared.run_id}.staging")
    if final_directory.exists() or staging_directory.exists():
        raise RuntimeError("run artifact target already exists")
    try:
        for artifact in artifacts:
            relative = Path(artifact["location"])
            target = staging_directory / relative.relative_to(
                Path("state") / "artifacts" / prepared.run_id
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(artifact["content"])
        final_directory.parent.mkdir(parents=True, exist_ok=True)
        staging_directory.replace(final_directory)
        with transaction(service.connection):
            service.require_active_run_for_completion(prepared.run_id)
            service._persist_rows(prepared.run_id, result)
            service.results.set_data_provenance(_provenance_record(prepared.run_id, fixture))
            service.results.set_execution_assumptions(ExecutionAssumptionsRecord(run_id=prepared.run_id, assumptions_json=canonical_json(execution_assumptions())))
            for artifact in artifacts:
                content = artifact["content"]
                artifact_type = ArtifactType(artifact["artifact_type"])
                identity_key = hashlib.sha256(canonical_json({
                    "run_id": prepared.run_id, "artifact_type": artifact_type.value,
                    "logical_name": artifact["logical_name"], "schema_version": ARTIFACT_SCHEMA_VERSION,
                }).encode("utf-8")).hexdigest()
                service.results.register_artifact_contract(
                    run_id=prepared.run_id, artifact_type=artifact_type, logical_name=artifact["logical_name"],
                    schema_version=ARTIFACT_SCHEMA_VERSION, media_type="application/json", format="json",
                    checksum=hashlib.sha256(content).hexdigest(), size_bytes=len(content), location=artifact["location"],
                    availability_state=ArtifactAvailability.AVAILABLE, identity_key=identity_key,
                )
            manifest = service.build_run_manifest(prepared.run_id)
            serialized = service.serialize_run_manifest(manifest)
            checksum = service.run_manifest_checksum(manifest)
            service.connection.execute(
                "INSERT INTO run_manifests (run_id, schema_version, manifest_json, content_checksum, created_at) VALUES (?, ?, ?, ?, ?)",
                (manifest.run_id, manifest.schema_version, serialized, checksum, manifest.created_at),
            )
            completed = service.runs.transition(prepared.run_id, RunStatus.SUCCEEDED)
            service.events.append(
                run_id=prepared.run_id, event_type=RunEventType.RUN_SUCCEEDED,
                severity=EventSeverity.INFO, source=SOURCE,
                message="Completed fixed SPYM intraday-momentum screening; promotion remains blocked.",
                occurred_at=completed.completed_at or completed.created_at,
            )
    except Exception:
        if staging_directory.exists():
            shutil.rmtree(staging_directory)
        if final_directory.exists():
            shutil.rmtree(final_directory)
        raise


def _fail_run(service: PersistenceService, run_id: str, message: str) -> None:
    run = service.runs.get(run_id)
    if run is None or run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
        return
    service.transition_run_with_operator_event(run_id=run_id, status=RunStatus.FAILED, event_type=RunEventType.RUN_FAILED,
                                               severity=EventSeverity.ERROR, source=SOURCE, message=message, error_summary=message)


def run_durable_screening(*, database: str | Path | None = None, artifact_root: str | Path | None = None,
                          run_id: str | None = None,
                          loader: Callable[[], SPYMMomentumExecution] = load_spym_intraday_momentum_inputs,
                          executor: Callable[[pd.DataFrame, Any], tuple[Any, Any, Any]] = execute_spym_intraday_momentum) -> DurableMomentumOutcome:
    resolved_database = database_path(database)
    root = Path(artifact_root).resolve() if artifact_root is not None else _artifact_root(resolved_database)
    service = PersistenceService(resolved_database)
    prepared = prepare_run(service, run_id=run_id)
    try:
        try:
            fixture = loader()
        except Exception as exc:
            message = f"SPYM data verification failed before computation: {exc}"
            _fail_run(service, prepared.run_id, message)
            return DurableMomentumOutcome(prepared, (message,))
        service.transition_run_with_operator_event(run_id=prepared.run_id, status=RunStatus.RUNNING, event_type=RunEventType.RUN_STARTED,
                                                   severity=EventSeverity.INFO, source=SOURCE, message="Started fixed SPYM intraday-momentum computation.")
        try:
            result, portfolio, bundle = executor(fixture.data, fixture.audit)
            if result.evaluated_combinations != 1 or len(result.ranked_results) != 1:
                raise RuntimeError("fixed SPYM intraday momentum rule must produce exactly one result row")
            _assert_ranked_trade_count_matches_ledger(result, portfolio, bundle)
            artifacts = _artifact_documents(prepared, fixture, result, portfolio, bundle)
            _persist_success(service, prepared, fixture, result, artifacts, root)
            return DurableMomentumOutcome(prepared, ())
        except Exception as exc:
            message = f"SPYM intraday-momentum screening failed without retry: {exc}"
            _fail_run(service, prepared.run_id, message)
            return DurableMomentumOutcome(prepared, (message,))
    finally:
        service.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist one fixed Decision-296 SPYM intraday-momentum screening run.")
    parser.add_argument("--database", type=Path, default=None)
    args = parser.parse_args(argv)
    outcome = run_durable_screening(database=args.database)
    print(outcome.run.run_id)
    for failure in outcome.failures:
        print(f"ERROR: {failure}")
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
