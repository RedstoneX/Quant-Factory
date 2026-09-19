"""Durable Decision-288 screening for the approved MES opening-range breakout."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import sys
from typing import Any, Callable, Literal, Mapping
from uuid import uuid4

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.experiments import build_portfolio, execute_experiment  # noqa: E402
from backtesting.experiments.models import ExperimentConfig, ExperimentResult  # noqa: E402
from backtesting.run_mes_orb import (  # noqa: E402
    DATASET_ID,
    ROLL_STATUS,
    _config,
    load_mes_data,
)
from market_data import DataAudit  # noqa: E402
from persistence import (  # noqa: E402
    ArtifactAvailability,
    ArtifactType,
    DataProvenanceRecord,
    EventSeverity,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunEventType,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import database_path, transaction  # noqa: E402
from persistence.service import configuration_document_from_experiment_config  # noqa: E402
from strategies import get_strategy  # noqa: E402
from strategies.mes_opening_range_breakout import build_parameter_grid  # noqa: E402

ResearchPlan = Literal["reference", "matrix"]
Direction = Literal["long", "short"]

EXPECTED_DATASET_SHA256 = (
    "fe6bfe4ea3328660e70c2291fc76ea8039249dfb2d5bb35a6390bd8fc7bf4dd1"
)
EXPECTED_DATASET_ROWS = 476_042
EXPECTED_FIRST_TIMESTAMP = "2019-05-05T22:00:00+00:00"
EXPECTED_LAST_TIMESTAMP = "2026-02-13T21:55:00+00:00"
DATASET_MANIFEST_REFERENCE = "data/manifests/futures_MES_5m_databento.json"
ARTIFACT_SCHEMA_VERSION = 1
REFERENCE_PARAMETERS = ({"range_minutes": 30, "breakout_offset_ticks": 0},)
EVIDENCE_LABELS = {
    "reference": "reference_reproduction",
    "matrix": "bounded_matrix_development",
}
PROMOTION_BLOCKERS = (
    "No unseen, out-of-sample, walk-forward, or protected evidence was evaluated.",
    "The already-inspected full catalog extent is development/reference evidence only.",
    "Unadjusted calendar-roll discontinuities can affect ranges, fills, and returns.",
)


@dataclass(frozen=True)
class PreparedDirectionRun:
    direction: Direction
    config: ExperimentConfig
    configuration_id: str
    run_id: str


@dataclass(frozen=True)
class DurableORBOutcome:
    plan: ResearchPlan
    runs: tuple[PreparedDirectionRun, ...]
    failures: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0


def parameter_combinations(plan: ResearchPlan) -> tuple[dict[str, int], ...]:
    """Return only the two predeclared Decision-288 parameter plans."""
    if plan == "reference":
        return tuple(dict(item) for item in REFERENCE_PARAMETERS)
    if plan == "matrix":
        return build_parameter_grid()
    raise ValueError(f"Unsupported MES ORB research plan: {plan}")


def experiment_config(direction: Direction, plan: ResearchPlan) -> ExperimentConfig:
    """Build one direction's immutable baseline-only experiment configuration."""
    legacy_direction = "longonly" if direction == "long" else "shortonly"
    baseline = _config(legacy_direction, "baseline")
    return replace(
        baseline,
        experiment_id=f"decision_288_mes_orb_{plan}_{direction}",
        parameter_combinations=parameter_combinations(plan),
    )


def _configuration_document(
    config: ExperimentConfig,
    *,
    plan: ResearchPlan,
) -> dict[str, Any]:
    spec = get_strategy(config.strategy_id).spec
    document = configuration_document_from_experiment_config(
        config,
        strategy_version=spec.identity.version,
    )
    document["parameters"] = {
        "plan": plan,
        "combinations": [dict(item) for item in config.parameter_combinations],
        "combination_count": len(config.parameter_combinations),
    }
    document["controlled_research"] = {
        "decision": 288,
        "plan": plan,
        "evidence_label": EVIDENCE_LABELS[plan],
        "evidence_scope": "development_reference_only",
        "dataset_id": DATASET_ID,
        "dataset_sha256": EXPECTED_DATASET_SHA256,
        "dataset_extent": {
            "row_count": EXPECTED_DATASET_ROWS,
            "first_timestamp": EXPECTED_FIRST_TIMESTAMP,
            "last_timestamp": EXPECTED_LAST_TIMESTAMP,
        },
        "contract_series": "MES.c.0",
        "roll_rule": "calendar/front-expiry rank zero",
        "price_adjustment": "none",
        "promotion_eligible": False,
        "promotion_blockers": PROMOTION_BLOCKERS,
    }
    return document


def prepare_run_pair(
    service: PersistenceService,
    *,
    plan: ResearchPlan,
    run_ids: Mapping[Direction, str] | None = None,
) -> tuple[PreparedDirectionRun, PreparedDirectionRun]:
    """Atomically prepare both direction identities before data or engine work."""
    configs = {
        direction: experiment_config(direction, plan)
        for direction in ("long", "short")
    }
    selected_ids = {
        direction: (
            str(run_ids[direction])
            if run_ids is not None
            else f"mes_orb_{plan}_{direction}_{uuid4().hex}"
        )
        for direction in ("long", "short")
    }
    if selected_ids["long"] == selected_ids["short"]:
        raise ValueError("MES ORB long and short runs require distinct identities")
    environment = service._freeze_environment(
        {
            "controlled_candidate": "decision_288_mes_orb",
            "research_plan": plan,
            "evidence_label": EVIDENCE_LABELS[plan],
        }
    )
    prepared: list[PreparedDirectionRun] = []
    with transaction(service.connection):
        for direction in ("long", "short"):
            config = configs[direction]
            spec = get_strategy(config.strategy_id).spec
            service.strategies.upsert(
                strategy_id=spec.identity.strategy_id,
                strategy_version=spec.identity.version,
                display_name=spec.identity.name,
                description=spec.identity.description,
                lifecycle=StrategyLifecycle.CANDIDATE,
                active=True,
            )
            configuration = service.configurations.upsert(
                _configuration_document(config, plan=plan)
            )
            run = service.runs.create(
                run_id=selected_ids[direction],
                configuration_id=configuration.configuration_id,
                strategy_id=spec.identity.strategy_id,
                strategy_version=spec.identity.version,
                stage=RunStage.SCREENING,
                status=RunStatus.CREATED,
                environment=environment,
            )
            service.events.append(
                run_id=run.run_id,
                event_type=RunEventType.RUN_CREATED,
                severity=EventSeverity.INFO,
                source="decision_288_mes_orb",
                message=(
                    f"Prepared {direction} MES ORB {EVIDENCE_LABELS[plan]} "
                    "screening run; no computation has started."
                ),
                occurred_at=run.created_at,
            )
            prepared.append(
                PreparedDirectionRun(
                    direction=direction,
                    config=config,
                    configuration_id=configuration.configuration_id,
                    run_id=run.run_id,
                )
            )
    return prepared[0], prepared[1]


def _assert_exact_dataset(metadata: Mapping[str, Any], data: pd.DataFrame) -> None:
    expected = {
        "dataset_id": DATASET_ID,
        "sha256": EXPECTED_DATASET_SHA256,
        "row_count": EXPECTED_DATASET_ROWS,
        "earliest_timestamp": EXPECTED_FIRST_TIMESTAMP,
        "latest_timestamp": EXPECTED_LAST_TIMESTAMP,
        "continuous_symbol": "MES.c.0",
        "roll_rule": "calendar/front-expiry rank zero",
        "contract_series_classification": "confirmed",
    }
    mismatches = {
        key: (metadata.get(key), value)
        for key, value in expected.items()
        if metadata.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"MES dataset identity does not match Decision 288: {mismatches}")
    if len(data) != EXPECTED_DATASET_ROWS:
        raise RuntimeError(
            f"MES dataset row count mismatch: expected {EXPECTED_DATASET_ROWS}, got {len(data)}"
        )
    if not data.index.empty:
        observed_first = pd.Timestamp(data.index[0]).isoformat()
        observed_last = pd.Timestamp(data.index[-1]).isoformat()
        if (observed_first, observed_last) != (
            EXPECTED_FIRST_TIMESTAMP,
            EXPECTED_LAST_TIMESTAMP,
        ):
            raise RuntimeError(
                "MES dataset extent does not match the already-inspected Decision-288 extent"
            )


def _artifact_root(database: str | Path) -> Path:
    resolved = Path(database).resolve()
    return resolved.parent.parent if resolved.parent.name == "state" else resolved.parent


def _json_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _json_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_value(value) for key, value in row.items()}


def _records(
    frame: pd.DataFrame,
    *,
    price_multiplier: float | None = None,
) -> list[dict[str, Any]]:
    records = [_json_record(row) for row in frame.to_dict(orient="records")]
    if price_multiplier is None:
        return records
    for record in records:
        for key, value in tuple(record.items()):
            if (
                "price" in key.lower()
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                record[key] = float(value) / price_multiplier
    return records


def _series_records(series: Any, name: str) -> list[dict[str, Any]]:
    if isinstance(series, pd.DataFrame):
        if series.shape[1] != 1:
            raise RuntimeError("expected one-column portfolio series")
        series = series.iloc[:, 0]
    return [
        {"timestamp": _json_value(index), name: _json_value(value)}
        for index, value in series.items()
    ]


def _price_series_records(data: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": _json_value(index),
            "open": _json_value(row.Open),
            "high": _json_value(row.High),
            "low": _json_value(row.Low),
            "close": _json_value(row.Close),
        }
        for index, row in data[["Open", "High", "Low", "Close"]].iterrows()
    ]


def _metric_subset(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: _json_value(row[name])
        for name in (
            "total_return",
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "number_of_trades",
            "win_rate",
        )
    }


def _provenance_record(
    *,
    run_id: str,
    audit: DataAudit,
    metadata: Mapping[str, Any],
) -> DataProvenanceRecord:
    validation_summary = {
        "dataset_id": DATASET_ID,
        "status": metadata["status"],
        "sha256": EXPECTED_DATASET_SHA256,
        "row_count": EXPECTED_DATASET_ROWS,
        "duplicate_timestamp_count": audit.duplicate_timestamp_count,
        "null_counts": metadata.get("null_counts", {}),
        "ohlc_violation_count": metadata.get("ohlc_violation_count"),
        "contract_series": "MES.c.0",
        "contract_series_classification": "confirmed",
        "roll_rule": "calendar/front-expiry rank zero",
        "price_adjustment": "none",
        "roll_discontinuities": "unadjusted_explicit_limitation",
        "evidence_scope": "development_reference_only",
    }
    return DataProvenanceRecord(
        run_id=run_id,
        provider=audit.provider,
        provider_implementation=audit.provider_implementation,
        symbol=audit.symbol,
        interval=audit.interval,
        timezone="UTC",
        requested_coverage=f"{EXPECTED_FIRST_TIMESTAMP}..{EXPECTED_LAST_TIMESTAMP}",
        actual_coverage=f"{audit.actual_first_row_date}..{audit.actual_last_row_date}",
        adjusted=False,
        row_count=audit.row_count,
        cache_action=audit.cache_action,
        validation_summary_json=canonical_json(validation_summary),
        manifest_reference=DATASET_MANIFEST_REFERENCE,
        checksum=EXPECTED_DATASET_SHA256,
    )


def _artifact_documents(
    *,
    prepared: PreparedDirectionRun,
    plan: ResearchPlan,
    result: ExperimentResult,
    data: pd.DataFrame,
    metadata: Mapping[str, Any],
    portfolio: Any,
) -> tuple[dict[str, Any], ...]:
    top = result.ranked_results.iloc[0].to_dict()
    top_row_id = str(top["parameter_row_id"])
    evidence_label = EVIDENCE_LABELS[plan]
    base = f"state/artifacts/{prepared.run_id}"
    validation = {
        "stage": RunStage.SCREENING.value,
        "plan": plan,
        "direction": prepared.direction,
        "selected_parameter_row_id": top_row_id,
        "selected_ranking_position": 1,
        "evidence_label": evidence_label,
        "evidence_scope": "development_reference_only",
        "evidence_classification": (
            "development/reference evidence only; not independent, OOS, protected, "
            "or edge proof"
        ),
        "independent_observation": False,
        "out_of_sample": False,
        "protected_data_used": False,
        "edge_proof": False,
        "promotion_eligible": False,
        "promotion_blockers": PROMOTION_BLOCKERS,
        "dataset_manifest": {
            "reference": DATASET_MANIFEST_REFERENCE,
            "sha256": EXPECTED_DATASET_SHA256,
            "row_count": EXPECTED_DATASET_ROWS,
            "status": metadata["status"],
        },
        "result_validation": [asdict(item) for item in result.validation_results],
        "screening": {
            "evaluated_combinations": result.evaluated_combinations,
            "passed": len(result.passing_results),
            "screened_out": len(result.screened_out_results),
        },
        "roll_limitation": (
            "MES.c.0 is confirmed and unadjusted; calendar-roll discontinuities "
            "must not be treated as market returns."
        ),
    }
    summary = {
        "run_id": prepared.run_id,
        "configuration_id": prepared.configuration_id,
        "experiment_id": result.experiment_id,
        "strategy_id": result.strategy_id,
        "strategy_version": result.strategy_version,
        "stage": RunStage.SCREENING.value,
        "status_at_artifact_capture": RunStatus.RUNNING.value,
        "plan": plan,
        "direction": prepared.direction,
        "selected_parameter_row_id": top_row_id,
        "selected_ranking_position": 1,
        "evidence_label": evidence_label,
        "evidence_classification": (
            "development/reference evidence only; not independent, OOS, protected, "
            "or edge proof"
        ),
        "dataset_id": DATASET_ID,
        "dataset_sha256": EXPECTED_DATASET_SHA256,
        "evaluated_combinations": result.evaluated_combinations,
        "broker_orders": "disabled",
        "promotion_eligible": False,
        "promotion_blockers": PROMOTION_BLOCKERS,
        "benchmark_omission": (
            "No truthful futures benchmark is declared for this bounded screening run."
        ),
    }
    documents = (
        (ArtifactType.RUN_SUMMARY, "run_summary", summary),
        (
            ArtifactType.METRICS,
            "metrics",
            {
                "parameter_row_id": top_row_id,
                "ranking_position": 1,
                "metrics": _metric_subset(top),
            },
        ),
        (
            ArtifactType.PARAMETER_RESULTS,
            "parameter_results",
            {
                "ranked_results": [
                    _json_record(row)
                    for row in result.ranked_results.to_dict(orient="records")
                ]
            },
        ),
        (
            ArtifactType.TRADES_OR_ORDERS,
            "trades_and_orders",
            {
                "top_ranked_parameters": {
                    "range_minutes": int(top["range_minutes"]),
                    "breakout_offset_ticks": int(top["breakout_offset_ticks"]),
                },
                "parameter_row_id": top_row_id,
                "ranking_position": 1,
                "instrument": "MES",
                "price_unit": "index_points",
                "pnl_unit": "USD",
                "price_multiplier": prepared.config.execution.price_multiplier,
                "price_normalization": (
                    "VectorBT trade/order price fields are divided by the internal "
                    "$5-per-point multiplier for display against raw MES bars; size, "
                    "fees, P&L, and other monetary fields remain unchanged."
                ),
                "trades": _records(
                    portfolio.trades.records_readable,
                    price_multiplier=prepared.config.execution.price_multiplier,
                ),
                "orders": _records(
                    portfolio.orders.records_readable,
                    price_multiplier=prepared.config.execution.price_multiplier,
                ),
            },
        ),
        (
            ArtifactType.EQUITY_CURVE,
            "equity_curve",
            {
                "parameter_row_id": top_row_id,
                "ranking_position": 1,
                "equity_curve": _series_records(portfolio.value, "value"),
                "price_series": _price_series_records(data),
                "benchmark_omission": (
                    "No truthful futures benchmark is declared for this bounded screening run."
                ),
            },
        ),
        (ArtifactType.VALIDATION_EVIDENCE, "validation_evidence", validation),
        (ArtifactType.DATASET_MANIFEST, "dataset_manifest", dict(metadata)),
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


def _top_portfolio(
    prepared: PreparedDirectionRun,
    result: ExperimentResult,
    data: pd.DataFrame,
) -> Any:
    top = result.ranked_results.iloc[0]
    parameters = {
        "range_minutes": int(top["range_minutes"]),
        "breakout_offset_ticks": int(top["breakout_offset_ticks"]),
    }
    signals = get_strategy(prepared.config.strategy_id).generate_signals(data, parameters)
    return build_portfolio(data, signals, prepared.config)


def _persist_success(
    service: PersistenceService,
    *,
    prepared: PreparedDirectionRun,
    result: ExperimentResult,
    audit: DataAudit,
    metadata: Mapping[str, Any],
    artifacts: tuple[dict[str, Any], ...],
    artifact_root: Path,
) -> None:
    with transaction(service.connection):
        service.require_active_run_for_completion(prepared.run_id)
        service._persist_rows(prepared.run_id, result)
        service.results.set_data_provenance(
            _provenance_record(
                run_id=prepared.run_id,
                audit=audit,
                metadata=metadata,
            )
        )
        service.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=prepared.run_id,
                assumptions_json=canonical_json(asdict(prepared.config.execution)),
            )
        )
        # Absence of a review row is the persistence contract for UNREVIEWED.
        # Creating a review row without a matching evidence-decision artifact
        # would be a dashboard integrity error.

    for artifact in artifacts:
        path = artifact_root / artifact["location"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(artifact["content"])
        service.register_artifact(
            run_id=prepared.run_id,
            artifact_type=artifact["artifact_type"],
            logical_name=artifact["logical_name"],
            media_type="application/json",
            format="json",
            location=artifact["location"],
            content=artifact["content"],
            schema_version=ARTIFACT_SCHEMA_VERSION,
            availability_state=ArtifactAvailability.AVAILABLE,
        )
    service.persist_run_manifest(service.build_run_manifest(prepared.run_id))


def _fail_run(service: PersistenceService, run_id: str, message: str) -> None:
    run = service.runs.get(run_id)
    if run is None or run.status in {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }:
        return
    service.transition_run_with_operator_event(
        run_id=run_id,
        status=RunStatus.FAILED,
        event_type=RunEventType.RUN_FAILED,
        severity=EventSeverity.ERROR,
        source="decision_288_mes_orb",
        message=message,
        error_summary=message,
    )


def run_durable_screening(
    *,
    plan: ResearchPlan = "reference",
    database: str | Path | None = None,
    artifact_root: str | Path | None = None,
    run_ids: Mapping[Direction, str] | None = None,
    data_loader: Callable[[], tuple[pd.DataFrame, DataAudit, dict[str, Any]]] = load_mes_data,
    dataset_validator: Callable[[Mapping[str, Any], pd.DataFrame], None] = _assert_exact_dataset,
    experiment_executor: Callable[..., ExperimentResult] = execute_experiment,
    portfolio_builder: Callable[[PreparedDirectionRun, ExperimentResult, pd.DataFrame], Any] = _top_portfolio,
) -> DurableORBOutcome:
    """Prepare both runs atomically, then execute each direction once in order."""
    resolved_database = database_path(database)
    resolved_artifact_root = (
        Path(artifact_root).resolve()
        if artifact_root is not None
        else _artifact_root(resolved_database)
    )
    service = PersistenceService(resolved_database)
    failures: list[str] = []
    try:
        prepared = prepare_run_pair(service, plan=plan, run_ids=run_ids)
        try:
            data, audit, metadata = data_loader()
            dataset_validator(metadata, data)
        except Exception as exc:
            message = f"MES data verification failed before computation: {exc}"
            for item in prepared:
                _fail_run(service, item.run_id, message)
            return DurableORBOutcome(plan=plan, runs=prepared, failures=(message,))

        expected_rows = 1 if plan == "reference" else 15
        for item in prepared:
            service.transition_run_with_operator_event(
                run_id=item.run_id,
                status=RunStatus.RUNNING,
                event_type=RunEventType.RUN_STARTED,
                severity=EventSeverity.INFO,
                source="decision_288_mes_orb",
                message=(
                    f"Started {item.direction} MES ORB {EVIDENCE_LABELS[plan]} "
                    "computation."
                ),
            )
            try:
                result = experiment_executor(
                    item.config,
                    data,
                    audit,
                    write_output=False,
                )
                if (
                    result.evaluated_combinations != expected_rows
                    or len(result.ranked_results) != expected_rows
                ):
                    raise RuntimeError(
                        f"{plan} plan expected {expected_rows} ranked rows for "
                        f"{item.direction}, got {len(result.ranked_results)}"
                    )
                portfolio = portfolio_builder(item, result, data)
                artifacts = _artifact_documents(
                    prepared=item,
                    plan=plan,
                    result=result,
                    data=data,
                    metadata=metadata,
                    portfolio=portfolio,
                )
                _persist_success(
                    service,
                    prepared=item,
                    result=result,
                    audit=audit,
                    metadata=metadata,
                    artifacts=artifacts,
                    artifact_root=resolved_artifact_root,
                )
                service.transition_run_with_operator_event(
                    run_id=item.run_id,
                    status=RunStatus.SUCCEEDED,
                    event_type=RunEventType.RUN_SUCCEEDED,
                    severity=EventSeverity.INFO,
                    source="decision_288_mes_orb",
                    message=(
                        f"Completed {item.direction} MES ORB {EVIDENCE_LABELS[plan]} "
                        "screening; promotion remains blocked."
                    ),
                )
            except Exception as exc:
                message = f"{item.direction} MES ORB screening failed without retry: {exc}"
                _fail_run(service, item.run_id, message)
                failures.append(message)
        return DurableORBOutcome(plan=plan, runs=prepared, failures=tuple(failures))
    finally:
        service.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Persist one controlled Decision-288 MES ORB screening pair."
    )
    parser.add_argument(
        "--plan",
        choices=("reference", "matrix"),
        default="reference",
        help=(
            "reference is the default 30-minute/zero-offset reproduction; matrix "
            "must be selected explicitly and runs only the approved 5x3 plan."
        ),
    )
    parser.add_argument("--database", type=Path, default=None)
    args = parser.parse_args(argv)
    outcome = run_durable_screening(plan=args.plan, database=args.database)
    for item in outcome.runs:
        print(f"{item.direction}: {item.run_id}")
    for failure in outcome.failures:
        print(f"ERROR: {failure}")
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
