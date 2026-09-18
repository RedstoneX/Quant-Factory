"""Dashboard-facing run detail views backed by persistence services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any

from persistence import ArtifactAvailability, PersistenceService
from persistence.database import database_path
from dashboard.formatting import format_metric


MISSING = "Not recorded"


@dataclass(frozen=True)
class DetailField:
    label: str
    value: str


@dataclass(frozen=True)
class ArtifactInventoryView:
    artifact_id: int | None
    artifact_type: str
    logical_name: str
    schema_version: str
    format: str
    availability: str
    validation_state: str
    checksum: str
    reference: str
    reason: str
    severity: str


@dataclass(frozen=True)
class ResultSummaryView:
    status: str
    message: str
    rows: tuple[tuple[DetailField, ...], ...]


@dataclass(frozen=True)
class RunEvidenceView:
    notices: tuple[str, ...]
    metrics: tuple[DetailField, ...]
    trades: tuple[dict[str, Any], ...]
    orders: tuple[dict[str, Any], ...]
    equity_curve: tuple[dict[str, Any], ...]
    drawdown_curve: tuple[dict[str, Any], ...]
    validation: tuple[DetailField, ...]
    provenance: tuple[DetailField, ...]
    warnings: tuple[str, ...]
    validation_outcome: tuple[DetailField, ...] = ()
    price_series: tuple[dict[str, Any], ...] = ()
    benchmark_curve: tuple[dict[str, Any], ...] = ()
    benchmark: dict[str, Any] | None = None


@dataclass(frozen=True)
class SelectedRunDetailView:
    configuration_fields: tuple[DetailField, ...]
    parameters: tuple[DetailField, ...]
    market_data: tuple[DetailField, ...]
    execution: tuple[DetailField, ...]
    ranking: tuple[DetailField, ...]
    screening: tuple[DetailField, ...]
    lineage_fields: tuple[DetailField, ...]
    manifest_fields: tuple[DetailField, ...]
    artifacts: tuple[ArtifactInventoryView, ...]
    result_summary: ResultSummaryView
    evidence: RunEvidenceView
    warnings: tuple[str, ...]


def _display(value: Any) -> str:
    if value is None or value == "":
        return MISSING
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(_display(item) for item in value) if value else MISSING
    if isinstance(value, dict):
        return "; ".join(
            f"{key}: {_display(value[key])}" for key in sorted(value)
        ) if value else MISSING
    return str(value)


def _fields(document: dict[str, Any] | None) -> tuple[DetailField, ...]:
    if not document:
        return ()
    return tuple(
        DetailField(str(key).replace("_", " ").title(), _display(document[key]))
        for key in sorted(document)
    )


def _manifest_fields(document: dict[str, Any] | None, checksum: str | None) -> tuple[DetailField, ...]:
    if document is None:
        return (DetailField("Manifest", "Not persisted"),)
    return (
        DetailField("Schema version", _display(document.get("manifest_schema_version"))),
        DetailField("Manifest checksum", _display(checksum)),
        DetailField("Run ID", _display(document.get("run_id"))),
        DetailField("Artifact count", _display(len(document.get("artifacts", ())))),
    )


def _lineage_fields(document: dict[str, Any] | None) -> tuple[DetailField, ...]:
    lineage = (document or {}).get("lineage")
    if not isinstance(lineage, dict):
        return (DetailField("Lineage", MISSING),)
    runtime = lineage.get("runtime") if isinstance(lineage.get("runtime"), dict) else {}
    git = runtime.get("git") if isinstance(runtime.get("git"), dict) else {}
    python = runtime.get("python") if isinstance(runtime.get("python"), dict) else {}
    vectorbtpro = runtime.get("vectorbtpro") if isinstance(runtime.get("vectorbtpro"), dict) else {}
    packages = runtime.get("packages") if isinstance(runtime.get("packages"), dict) else {}
    data = lineage.get("data") if isinstance(lineage.get("data"), dict) else {}
    configuration = lineage.get("configuration") if isinstance(lineage.get("configuration"), dict) else {}
    return (
        DetailField("Configuration identity", _display(configuration.get("config_hash"))),
        DetailField("Git commit", _display(git.get("commit_sha"))),
        DetailField("Git dirty state", _display(git.get("dirty_state"))),
        DetailField("Python", _display(python.get("version"))),
        DetailField("VectorBT Pro", _display(vectorbtpro.get("version"))),
        DetailField("Package fingerprint", _display(packages.get("fingerprint"))),
        DetailField("Dataset identity", _display(data.get("dataset_identity"))),
        DetailField("Provider identity", _display(data.get("provider_identity"))),
        DetailField("Symbol", _display(data.get("symbol"))),
        DetailField("Timeframe", _display(data.get("timeframe"))),
        DetailField("Requested coverage", _display(data.get("requested_coverage"))),
        DetailField("Actual coverage", _display(data.get("actual_coverage"))),
        DetailField("Dataset manifest", _display(data.get("dataset_manifest_reference"))),
        DetailField("Dataset checksum", _display(data.get("dataset_checksum"))),
        DetailField("Parent/child lineage", "Not recorded for this fixture run"),
    )


def _artifact_view(artifact, validation_by_id: dict[int, Any]) -> ArtifactInventoryView:
    validation = validation_by_id.get(artifact.artifact_id)
    availability = (
        validation.availability_state.value
        if validation is not None
        else artifact.availability_state.value
    )
    valid = bool(validation.valid) if validation is not None else False
    reason = validation.reason if validation is not None else "validation_not_run"
    severity = "success" if valid and availability == ArtifactAvailability.AVAILABLE.value else (
        "warning" if availability in {ArtifactAvailability.MISSING.value, ArtifactAvailability.UNAVAILABLE.value} else "error"
    )
    validation_state = "valid" if valid else (
        "missing" if availability == ArtifactAvailability.MISSING.value else
        "unavailable" if availability == ArtifactAvailability.UNAVAILABLE.value else
        "corrupt" if availability == ArtifactAvailability.CORRUPT.value else
        "invalid"
    )
    return ArtifactInventoryView(
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type.value,
        logical_name=artifact.logical_name,
        schema_version=str(artifact.schema_version),
        format=artifact.format,
        availability=availability,
        validation_state=validation_state,
        checksum=f"{artifact.checksum_algorithm}:{artifact.checksum}",
        reference=artifact.location,
        reason=reason,
        severity=severity,
    )


def _result_summary(detail: dict[str, Any] | None) -> ResultSummaryView:
    parameters = (detail or {}).get("parameters") or ()
    rows = []
    for row in parameters[:5]:
        metrics = json.loads(row.get("metrics_json", "{}"))
        normalized = json.loads(row.get("normalized_parameters_json", "{}"))
        fields = [
            DetailField("Rank", _display(row.get("ranking_position"))),
            DetailField("Screening", _display(row.get("screening_status"))),
            DetailField("Parameters", _display(normalized)),
            DetailField("Metrics", _display(metrics)),
        ]
        if row.get("rejection_reasons"):
            fields.append(DetailField("Rejection reasons", _display(row.get("rejection_reasons"))))
        rows.append(tuple(fields))
    if not rows:
        return ResultSummaryView(
            status="empty",
            message="No persisted parameter result summary is available for this run.",
            rows=(),
        )
    return ResultSummaryView(
        status="available",
        message="Persisted deterministic fixture result summary.",
        rows=tuple(rows),
    )


def _empty_evidence() -> RunEvidenceView:
    return RunEvidenceView(
        notices=(),
        metrics=(),
        trades=(),
        orders=(),
        equity_curve=(),
        drawdown_curve=(),
        validation=(),
        provenance=(),
        warnings=(),
        price_series=(),
        benchmark_curve=(),
        benchmark=None,
    )


def _safe_artifact_path(root: Path, location: str) -> Path:
    relative = Path(location)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("artifact location is unsafe")
    candidate = (root.resolve() / relative).resolve()
    candidate.relative_to(root.resolve())
    return candidate


def _read_valid_json_artifacts(
    retrieval,
    *,
    artifact_root: Path,
) -> tuple[dict[str, Any], list[str]]:
    validation_by_id = {
        validation.artifact_id: validation
        for validation in retrieval.validations
    }
    documents: dict[str, Any] = {}
    warnings: list[str] = []
    for artifact in retrieval.artifacts:
        validation = validation_by_id.get(artifact.artifact_id)
        if validation is None or not validation.valid:
            warnings.append(
                f"Artifact {artifact.logical_name} is not readable: "
                f"{validation.reason if validation else 'validation_not_run'}."
            )
            continue
        if artifact.format != "json":
            continue
        try:
            path = _safe_artifact_path(artifact_root, artifact.location)
            documents[artifact.logical_name] = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            warnings.append(f"Artifact {artifact.logical_name} content is invalid: {exc}.")
    return documents, warnings


def _metric_fields(metrics: dict[str, Any]) -> tuple[DetailField, ...]:
    preferred = (
        "total_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "number_of_trades",
        "win_rate",
    )
    return tuple(
        DetailField(name.replace("_", " ").title(), format_metric(name, metrics[name]))
        for name in preferred
        if name in metrics
    )


def _flatten_fields(document: dict[str, Any] | None) -> tuple[DetailField, ...]:
    if not isinstance(document, dict):
        return ()
    flattened: list[DetailField] = []
    for key in sorted(document):
        value = document[key]
        if isinstance(value, dict):
            for nested_key in sorted(value):
                flattened.append(
                    DetailField(
                        f"{key.replace('_', ' ').title()} · {nested_key.replace('_', ' ').title()}",
                        _display(value[nested_key]),
                    )
                )
        else:
            flattened.append(
                DetailField(key.replace("_", " ").title(), _display(value))
            )
    return tuple(flattened)


def _drawdown_curve(equity_curve: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    peak: float | None = None
    rows: list[dict[str, Any]] = []
    for row in equity_curve:
        value = row.get("value")
        if not isinstance(value, (int, float)) or value == 0:
            continue
        peak = float(value) if peak is None else max(peak, float(value))
        drawdown = 0.0 if not peak else (float(value) / peak) - 1.0
        rows.append({"timestamp": row.get("timestamp"), "drawdown": drawdown})
    return tuple(rows)


def _table_rows(document: Any, key: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(document, dict):
        return ()
    rows = document.get(key)
    if not isinstance(rows, list):
        return ()
    return tuple(row for row in rows if isinstance(row, dict))


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _valid_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _validated_series_rows(
    document: Any,
    key: str,
    *,
    numeric_fields: tuple[str, ...],
    warnings: list[str],
) -> tuple[dict[str, Any], ...]:
    if not isinstance(document, dict) or key not in document:
        return ()
    rows = document.get(key)
    if not isinstance(rows, list):
        warnings.append(f"Artifact equity_curve field {key} is not a list.")
        return ()
    valid_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            warnings.append(f"Artifact equity_curve field {key} row {index} is not an object.")
            return ()
        if not _valid_timestamp(row.get("timestamp")):
            warnings.append(
                f"Artifact equity_curve field {key} row {index} has an invalid timestamp."
            )
            return ()
        for field in numeric_fields:
            if not _valid_number(row.get(field)):
                warnings.append(
                    f"Artifact equity_curve field {key} row {index} has invalid {field}."
                )
                return ()
        if {"open", "high", "low", "close"}.issubset(numeric_fields):
            high = float(row["high"])
            low = float(row["low"])
            open_value = float(row["open"])
            close = float(row["close"])
            if high < max(open_value, close, low) or low > min(open_value, close, high):
                warnings.append(
                    f"Artifact equity_curve field {key} row {index} has inconsistent OHLC values."
                )
                return ()
        valid_rows.append(row)
    return tuple(valid_rows)


def _validated_benchmark(document: Any, warnings: list[str]) -> dict[str, Any] | None:
    if not isinstance(document, dict) or "benchmark" not in document:
        return None
    benchmark = document.get("benchmark")
    if not isinstance(benchmark, dict):
        warnings.append("Artifact equity_curve field benchmark is not an object.")
        return None
    label = benchmark.get("label")
    instrument = benchmark.get("instrument")
    if not isinstance(label, str) or not label.strip():
        warnings.append("Artifact equity_curve benchmark label is not recorded.")
        return None
    if not isinstance(instrument, str) or not instrument.strip():
        warnings.append("Artifact equity_curve benchmark instrument is not recorded.")
        return None
    for field in ("starting_capital", "fees", "slippage", "fixed_fee_per_order"):
        if field in benchmark and not _valid_number(benchmark[field]):
            warnings.append(f"Artifact equity_curve benchmark {field} is invalid.")
            return None
    return benchmark


def _validation_outcome_fields(
    *,
    service: PersistenceService,
    run_id: str,
    artifact_root: Path,
) -> tuple[DetailField, ...]:
    from persistence.evidence_service import ValidationEvidenceArtifactService

    outcome = ValidationEvidenceArtifactService(service).stage_outcome(
        run_id,
        artifact_root=artifact_root,
    )
    if outcome.status == "not_run" and not outcome.reasons:
        return ()
    return (
        DetailField("Stage", outcome.stage.replace("_", " ").title()),
        DetailField("Normalized status", _display(outcome.status)),
        DetailField("Reasons", _display(outcome.reasons)),
        DetailField("Protected-data state", _display(outcome.protected_data_state)),
        DetailField("Evidence identity", _display(outcome.evidence_identity)),
        DetailField("Artifact identity", _display(outcome.artifact_id)),
        DetailField("Lockbox eligibility", MISSING),
        DetailField(
            "Strategy progression",
            (
                "No strategy progression occurred."
                if outcome.eligible_to_progress is False
                else _display(outcome.eligible_to_progress)
            ),
        ),
    )


def _evidence_view(
    *,
    service: PersistenceService,
    run_id: str,
    detail: dict[str, Any] | None,
    retrieval: Any | None,
    artifact_root: Path,
) -> RunEvidenceView:
    warnings: list[str] = []
    documents: dict[str, Any] = {}
    if retrieval is not None:
        documents, warnings = _read_valid_json_artifacts(
            retrieval,
            artifact_root=artifact_root,
        )

    metrics_doc = documents.get("metrics")
    metrics = metrics_doc.get("metrics", {}) if isinstance(metrics_doc, dict) else {}
    if not metrics and detail:
        parameters = detail.get("parameters") or ()
        if parameters:
            metrics = json.loads(parameters[0].get("metrics_json", "{}"))

    trades_doc = documents.get("trades_and_orders")
    equity_doc = documents.get("equity_curve")
    validation_doc = documents.get("validation_evidence")
    summary_doc = documents.get("run_summary")
    dataset_doc = documents.get("dataset_manifest")

    equity_curve = _table_rows(equity_doc, "equity_curve")
    price_series = _validated_series_rows(
        equity_doc,
        "price_series",
        numeric_fields=("open", "high", "low", "close"),
        warnings=warnings,
    )
    benchmark_curve = _validated_series_rows(
        equity_doc,
        "benchmark_curve",
        numeric_fields=("value",),
        warnings=warnings,
    )
    benchmark = _validated_benchmark(equity_doc, warnings)
    if benchmark is None:
        benchmark_curve = ()
    notices: list[str] = []
    if isinstance(summary_doc, dict) and summary_doc.get("fixture_only") is True:
        notices.append(
            "Infrastructure fixture only: this run proves factory plumbing and is not profitability evidence."
        )
    if isinstance(summary_doc, dict) and summary_doc.get("broker_orders") == "disabled":
        notices.append("Broker orders were disabled; no paper or live orders were submitted.")
    if (
        isinstance(dataset_doc, dict)
        and dataset_doc.get("symbol") == "SPYM"
    ):
        notices.append(
            "SPYM is an ingestion and execution fixture here; it is not selected as the final paper or micro-live instrument."
        )

    provenance_doc = (detail or {}).get("provenance")
    provenance = _fields(provenance_doc) if isinstance(provenance_doc, dict) else ()
    dataset_identity_fields = _flatten_fields(
        {
            key: dataset_doc.get(key)
            for key in (
                "dataset_id",
                "provider",
                "dataset",
                "schema",
                "symbol",
                "earliest_timestamp",
                "latest_timestamp",
                "sha256",
                "status",
            )
            if isinstance(dataset_doc, dict) and key in dataset_doc
        }
    )
    if dataset_identity_fields:
        provenance = provenance + dataset_identity_fields

    validation_outcome = _validation_outcome_fields(
        service=service,
        run_id=run_id,
        artifact_root=artifact_root,
    )

    return RunEvidenceView(
        notices=tuple(notices),
        metrics=_metric_fields(metrics),
        trades=_table_rows(trades_doc, "trades"),
        orders=_table_rows(trades_doc, "orders"),
        equity_curve=equity_curve,
        drawdown_curve=_drawdown_curve(equity_curve),
        validation_outcome=validation_outcome,
        price_series=price_series,
        benchmark_curve=benchmark_curve,
        benchmark=benchmark,
        validation=_flatten_fields(validation_doc if isinstance(validation_doc, dict) else None),
        provenance=provenance,
        warnings=tuple(warnings),
    )


class RunDetailDashboardAdapter:
    """Build immutable dashboard view models from stable persistence services."""

    def __init__(
        self,
        database: str | Path | None = None,
        *,
        artifact_root: str | Path | None = None,
    ) -> None:
        self.database = database_path(database)
        self.artifact_root = Path(artifact_root or Path.cwd())

    def selected_run_detail(self, run_id: str) -> SelectedRunDetailView:
        service = PersistenceService(self.database)
        warnings: list[str] = []
        try:
            run = service.runs.get(run_id)
            if run is None:
                raise KeyError(f"unknown run {run_id}")
            configuration = service.configurations.get(run.configuration_id)
            configuration_document: dict[str, Any] | None = None
            if configuration is None:
                warnings.append("The saved configuration for this run is missing.")
            else:
                try:
                    configuration_document = json.loads(configuration.canonical_config_json)
                except json.JSONDecodeError as exc:
                    warnings.append(f"The saved configuration is invalid JSON: {exc}")

            manifest_document = None
            manifest_checksum = None
            persisted_manifest = service.read_persisted_run_manifest(run_id)
            if persisted_manifest is None:
                warnings.append("No persisted run manifest is available.")
            else:
                manifest_json, manifest_checksum = persisted_manifest
                try:
                    manifest_document = service.read_persisted_run_manifest_document(run_id)
                except (ValueError, TypeError) as exc:
                    warnings.append(f"The persisted run manifest is invalid: {exc}")

            artifacts: tuple[ArtifactInventoryView, ...]
            retrieval = None
            try:
                retrieval = service.retrieve_run_artifacts(
                    run_id,
                    artifact_root=self.artifact_root,
                )
                validation_by_id = {
                    validation.artifact_id: validation
                    for validation in retrieval.validations
                }
                artifacts = tuple(
                    _artifact_view(artifact, validation_by_id)
                    for artifact in retrieval.artifacts
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                warnings.append(f"Artifact retrieval failed: {exc}")
                artifacts = tuple(
                    ArtifactInventoryView(
                        artifact_id=artifact.artifact_id,
                        artifact_type=artifact.artifact_type.value,
                        logical_name=artifact.logical_name,
                        schema_version=str(artifact.schema_version),
                        format=artifact.format,
                        availability=artifact.availability_state.value,
                        validation_state="invalid",
                        checksum=f"{artifact.checksum_algorithm}:{artifact.checksum}",
                        reference=artifact.location,
                        reason=str(exc),
                        severity="error",
                    )
                    for artifact in service.list_run_artifacts(run_id)
                )

            detail = None
            try:
                detail = service.run_detail(run_id)
            except (KeyError, TypeError, ValueError) as exc:
                warnings.append(f"Result summary retrieval failed: {exc}")
            evidence = _evidence_view(
                service=service,
                run_id=run_id,
                detail=detail,
                retrieval=retrieval,
                artifact_root=self.artifact_root,
            )
            warnings.extend(evidence.warnings)

            return SelectedRunDetailView(
                configuration_fields=(
                    (
                        DetailField("Configuration ID", configuration.configuration_id),
                        DetailField("Experiment ID", _display((configuration_document or {}).get("experiment_id"))),
                        DetailField("Strategy", f"{run.strategy_id}@{run.strategy_version}"),
                        DetailField("Configuration checksum", configuration.config_hash),
                    )
                    if configuration is not None
                    else (DetailField("Configuration", "Missing"),)
                ),
                parameters=_fields((configuration_document or {}).get("parameters")),
                market_data=_fields((configuration_document or {}).get("market_data")),
                execution=_fields((configuration_document or {}).get("execution")),
                ranking=_fields((configuration_document or {}).get("ranking")),
                screening=_fields((configuration_document or {}).get("screening")),
                lineage_fields=_lineage_fields(manifest_document),
                manifest_fields=_manifest_fields(manifest_document, manifest_checksum),
                artifacts=artifacts,
                result_summary=_result_summary(detail),
                evidence=evidence,
                warnings=tuple(warnings),
            )
        finally:
            service.close()
