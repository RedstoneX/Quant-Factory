"""Dashboard-facing run detail views backed by persistence services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
from threading import RLock
from typing import Any

from persistence import ArtifactAvailability, ArtifactType, PersistenceService
from persistence.database import database_path
from persistence.serialization import canonical_json
from dashboard.formatting import format_metric
from dashboard.results_model import ResultsDataError, validate_ohlc_rows


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
    table_rows: tuple[dict[str, Any], ...] = ()
    evidence_state: str = "not-available"
    evidence_message: str = ""


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
    source_interval: str | None = None
    price_unit: str | None = None
    pnl_unit: str | None = None
    evidence_classification: str | None = None
    promotion_eligible: bool | None = None


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


def _fields(
    document: dict[str, Any] | list[dict[str, Any]] | None,
) -> tuple[DetailField, ...]:
    if not document:
        return ()
    if isinstance(document, list):
        fields = [DetailField("Parameter Combinations", f"{len(document):,}")]
        names = sorted({str(name) for row in document for name in row})
        for name in names:
            rendered: list[str] = []
            for row in document:
                if name not in row:
                    continue
                value = _display(row[name])
                if value not in rendered:
                    rendered.append(value)
            visible = rendered[:8]
            suffix = (
                f", +{len(rendered) - len(visible):,} more"
                if len(rendered) > len(visible)
                else ""
            )
            fields.append(
                DetailField(
                    name.replace("_", " ").title(),
                    ", ".join(visible) + suffix if visible else MISSING,
                )
            )
        return tuple(fields)
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
        DetailField("Parent/child lineage", "Not recorded for this run"),
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


def _result_summary(
    detail: dict[str, Any] | None,
    *,
    run_id: str,
    registered_artifacts: tuple[Any, ...],
    retrieval: Any | None,
    artifact_root: Path,
    warnings: list[str],
    manifest_document: dict[str, Any] | None = None,
    evidence_classification: str | None = None,
) -> ResultSummaryView:
    parameters = (detail or {}).get("parameters") or ()
    rows = []
    table_rows: list[dict[str, Any]] = []
    persisted_rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    try:
        for row in parameters:
            if not isinstance(row, dict):
                raise ValueError("a persisted parameter row is not an object")
            metrics = json.loads(row.get("metrics_json", "{}"))
            normalized = json.loads(row.get("normalized_parameters_json", "{}"))
            if not isinstance(metrics, dict) or not isinstance(normalized, dict):
                raise ValueError("persisted parameter or metric data is not an object")
            if not isinstance(row.get("row_id"), str) or not row["row_id"].strip():
                raise ValueError("a persisted parameter row has no stable row identity")
            persisted_rows.append((row, normalized, metrics))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        message = f"Parameter-result evidence is invalid: {exc}. Results are hidden."
        warnings.append(message)
        return ResultSummaryView(
            status="invalid",
            message=message,
            rows=(),
            evidence_state="evidence-invalid",
            evidence_message=message,
        )

    evidence_state, evidence_message = _parameter_result_evidence_state(
        persisted_rows,
        registered_artifacts=registered_artifacts,
        retrieval=retrieval,
        artifact_root=artifact_root,
        manifest_document=manifest_document,
    )
    if evidence_state == "evidence-invalid":
        message = f"Parameter-result evidence is invalid: {evidence_message} Results are hidden."
        warnings.append(message)
        return ResultSummaryView(
            status="invalid",
            message=message,
            rows=(),
            evidence_state=evidence_state,
            evidence_message=evidence_message,
        )

    for row, normalized, metrics in persisted_rows:
        fields = [
            DetailField("Rank", _display(row.get("ranking_position"))),
            DetailField("Screening", _display(row.get("screening_status"))),
            DetailField("Parameters", _display(normalized)),
            DetailField("Metrics", _display(metrics)),
        ]
        if row.get("rejection_reasons"):
            fields.append(DetailField("Rejection reasons", _display(row.get("rejection_reasons"))))
        rows.append(tuple(fields))
        table_rows.append(
            {
                **normalized,
                **metrics,
                "parameter_row_id": row["row_id"],
                "variant_key": f"{run_id}:{row['row_id']}",
                "__run_id": run_id,
                "__parameters": normalized,
                "__metrics": metrics,
                "ranking_position": row.get("ranking_position"),
                "screening_status": row.get("screening_status"),
                "screening_reason": row.get("rejection_reasons") or "",
            }
        )
    if not rows:
        return ResultSummaryView(
            status="empty",
            message="No persisted parameter result summary is available for this run.",
            rows=(),
            evidence_state=evidence_state,
            evidence_message=evidence_message,
        )
    run_document = (detail or {}).get("run")
    message = (
        "Persisted deterministic fixture result summary."
        if isinstance(run_document, dict) and run_document.get("stage") == "fixture"
        else "Persisted ranked research result summary."
    )
    if evidence_classification:
        message = f"Persisted ranked screening results. {evidence_classification}."
    message = f"{message} {evidence_message}"
    return ResultSummaryView(
        status="available",
        message=message,
        rows=tuple(rows),
        table_rows=tuple(table_rows),
        evidence_state=evidence_state,
        evidence_message=evidence_message,
    )


_PARAMETER_RESULT_METRICS = (
    "total_return",
    "annualized_return",
    "sharpe_ratio",
    "max_drawdown",
    "number_of_trades",
    "win_rate",
)


def _parameter_result_evidence_state(
    persisted_rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    *,
    registered_artifacts: tuple[Any, ...],
    retrieval: Any | None,
    artifact_root: Path,
    manifest_document: dict[str, Any] | None,
) -> tuple[str, str]:
    artifacts = tuple(
        artifact
        for artifact in registered_artifacts
        if artifact.logical_name == "parameter_results"
    )
    if not artifacts:
        manifest_artifacts = (
            manifest_document.get("artifacts")
            if isinstance(manifest_document, dict)
            else None
        )
        manifest_parameter_results = (
            [
                artifact
                for artifact in manifest_artifacts
                if isinstance(artifact, dict)
                and artifact.get("logical_name") == "parameter_results"
            ]
            if isinstance(manifest_artifacts, list)
            else []
        )
        if manifest_parameter_results:
            return (
                "evidence-invalid",
                "the immutable manifest expects a parameter-results artifact that is missing from the registry.",
            )
        if not persisted_rows:
            return (
                "database-persisted",
                "No persisted parameter-result rows or artifacts are recorded for this run.",
            )
        if retrieval is None:
            return (
                "evidence-invalid",
                "the immutable manifest and registered artifacts could not be retrieved and validated.",
            )
        return (
            "database-persisted",
            "Variants are shown from durable database rows; no parameter-results artifact is registered.",
        )
    if len(artifacts) != 1:
        return (
            "evidence-invalid",
            f"expected exactly one registered parameter-results artifact, found {len(artifacts)}.",
        )
    if retrieval is None:
        return (
            "evidence-invalid",
            "the immutable manifest and registered artifacts could not be retrieved and validated.",
        )
    artifact = artifacts[0]
    if artifact.artifact_type != ArtifactType.PARAMETER_RESULTS:
        return (
            "evidence-invalid",
            "the registered parameter-results artifact has the wrong artifact type.",
        )
    validation = next(
        (
            item
            for item in retrieval.validations
            if item.artifact_id == artifact.artifact_id
        ),
        None,
    )
    if validation is None or not validation.valid:
        reason = validation.reason if validation is not None else "validation_not_run"
        return (
            "evidence-invalid",
            f"the registered parameter-results artifact is not valid ({reason}).",
        )
    if artifact.format != "json":
        return (
            "evidence-invalid",
            "the registered parameter-results artifact is not JSON.",
        )

    try:
        path = _safe_artifact_path(artifact_root, artifact.location)
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return (
            "evidence-invalid",
            f"the registered parameter-results artifact cannot be read ({exc}).",
        )
    if not isinstance(document, dict):
        return "evidence-invalid", "the parameter-results artifact is not an object."
    ranked_results = document.get("ranked_results")
    if not isinstance(ranked_results, list) or not all(
        isinstance(row, dict) for row in ranked_results
    ):
        return (
            "evidence-invalid",
            "the parameter-results artifact ranked_results field is not a row list.",
        )
    if len(ranked_results) != len(persisted_rows):
        return (
            "evidence-invalid",
            "artifact and database parameter-result row counts do not match.",
        )

    for index, ((persisted, normalized, metrics), artifact_row) in enumerate(
        zip(persisted_rows, ranked_results, strict=True),
        start=1,
    ):
        mismatch = _parameter_result_row_mismatch(
            persisted,
            normalized,
            metrics,
            artifact_row,
        )
        if mismatch is not None:
            return (
                "evidence-invalid",
                f"artifact row {index} does not reconcile with its database row: {mismatch}.",
            )
    return (
        "artifact-validated",
        "Variants are reconciled row-for-row with the validated parameter-results artifact.",
    )


def _parameter_result_row_mismatch(
    persisted: dict[str, Any],
    normalized: dict[str, Any],
    metrics: dict[str, Any],
    artifact_row: dict[str, Any],
) -> str | None:
    for identity_key in ("parameter_row_id", "row_id"):
        if identity_key in artifact_row and not _same_json_value(
            artifact_row[identity_key], persisted["row_id"]
        ):
            return f"{identity_key} differs"
    if "ranking_position" in artifact_row and not _same_json_value(
        artifact_row["ranking_position"], persisted.get("ranking_position")
    ):
        return "ranking_position differs"
    for key, expected in normalized.items():
        if key not in artifact_row:
            return f"parameter {key!r} is missing"
        if not _same_json_value(artifact_row[key], expected):
            return f"parameter {key!r} differs"
    for key in _PARAMETER_RESULT_METRICS:
        if key not in metrics:
            return f"database metric {key!r} is missing"
        if key not in artifact_row:
            return f"metric {key!r} is missing"
        if not _same_json_value(artifact_row[key], metrics[key]):
            return f"metric {key!r} differs"
    if "screening_status" in artifact_row and not _same_json_value(
        artifact_row["screening_status"], persisted.get("screening_status")
    ):
        return "screening_status differs"
    for reason_key in (
        "screening_rejection_reasons",
        "rejection_reasons",
        "screening_reason",
    ):
        if reason_key in artifact_row and not _same_json_value(
            artifact_row[reason_key], persisted.get("rejection_reasons") or ""
        ):
            return f"{reason_key} differs"
    return None


def _same_json_value(left: Any, right: Any) -> bool:
    try:
        return canonical_json(left) == canonical_json(right)
    except (TypeError, ValueError):
        return False


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


def _canonical_interval(value: Any) -> str | None:
    normalized = str(value or "").lower().replace("-", " ").strip()
    aliases = {
        "1m": "1m",
        "1 min": "1m",
        "1 minute": "1m",
        "1 minute bars": "1m",
        "5m": "5m",
        "5 min": "5m",
        "5 minute": "5m",
        "5 minute bars": "5m",
        "15m": "15m",
        "15 min": "15m",
        "15 minute": "15m",
        "15 minute bars": "15m",
        "1d": "1D",
        "1 day": "1D",
        "1 day bars": "1D",
        "daily": "1D",
    }
    return aliases.get(normalized)


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


def _calendar_cagr(total_return: Any, actual_coverage: Any) -> float | None:
    """Derive calendar CAGR only from valid persisted return and coverage facts."""

    if isinstance(total_return, bool):
        return None
    try:
        normalized_return = float(total_return)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(normalized_return) or normalized_return <= -1.0:
        return None
    if not isinstance(actual_coverage, str):
        return None
    separator = ".." if ".." in actual_coverage else "/" if "/" in actual_coverage else None
    if separator is None:
        return None
    start_text, end_text = (part.strip() for part in actual_coverage.split(separator, 1))
    try:
        start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_text.replace("Z", "+00:00"))
        elapsed_seconds = (end - start).total_seconds()
    except (TypeError, ValueError):
        return None
    if elapsed_seconds <= 0:
        return None
    elapsed_years = elapsed_seconds / (365.2425 * 24 * 60 * 60)
    try:
        result = (1.0 + normalized_return) ** (1.0 / elapsed_years) - 1.0
    except OverflowError:
        return None
    return result if math.isfinite(result) else None


def _metric_fields(
    metrics: dict[str, Any],
    *,
    actual_coverage: Any = None,
) -> tuple[DetailField, ...]:
    preferred = (
        "total_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "number_of_trades",
        "win_rate",
    )
    fields = [
        DetailField(
            (
                "Annualized return (recorded engine output)"
                if name == "annualized_return"
                else name.replace("_", " ").title()
            ),
            format_metric(name, metrics[name]),
        )
        for name in preferred
        if name in metrics
    ]
    calendar_cagr = _calendar_cagr(metrics.get("total_return"), actual_coverage)
    if calendar_cagr is not None:
        fields.append(
            DetailField(
                "Calendar CAGR (derived from recorded coverage)",
                format_metric("annualized_return", calendar_cagr),
            )
        )
    return tuple(fields)


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


def _candidate_trade_rows(document: Any) -> tuple[dict[str, Any], ...]:
    """Normalize canonical and preserved candidate trade ledgers for the UI."""

    canonical = _table_rows(document, "trades")
    if canonical or not isinstance(document, dict) or "trades" in document:
        return canonical

    manual = _table_rows(document, "manual_trades")
    if manual or "manual_trades" in document:
        contract_count = document.get("contract_count")
        normalized: list[dict[str, Any]] = []
        for row in manual:
            aliases = {
                "Entry Index": row.get("entry_timestamp"),
                "Exit Index": row.get("exit_timestamp"),
                "Avg Entry Price": row.get("entry_fill"),
                "Avg Exit Price": row.get("exit_fill"),
                "Entry Fees": row.get("fee_per_side"),
                "Exit Fees": row.get("fee_per_side"),
                "PnL": row.get("net_pnl"),
                "Direction": row.get("direction"),
                "Status": "Closed",
                "Size": contract_count,
            }
            normalized.append(
                {
                    **row,
                    **{
                        key: value
                        for key, value in aliases.items()
                        if value not in (None, "")
                    },
                }
            )
        return tuple(normalized)

    return _table_rows(document, "vectorbt_trades")


def _candidate_order_rows(document: Any) -> tuple[dict[str, Any], ...]:
    """Normalize canonical and preserved VectorBT candidate order ledgers."""

    canonical = _table_rows(document, "orders")
    if canonical or not isinstance(document, dict) or "orders" in document:
        return canonical
    return _table_rows(document, "vectorbt_orders")


def _validated_equity_curve(
    document: Any,
    *,
    warnings: list[str],
) -> tuple[dict[str, Any], ...]:
    """Return validated equity rows with the dashboard's canonical ``value`` key."""

    if not isinstance(document, dict) or "equity_curve" not in document:
        return ()
    rows = document.get("equity_curve")
    if not isinstance(rows, list):
        warnings.append("Artifact equity_curve field equity_curve is not a list.")
        return ()

    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            warnings.append(
                f"Artifact equity_curve field equity_curve row {index} is not an object."
            )
            return ()
        if not _valid_timestamp(row.get("timestamp")):
            warnings.append(
                f"Artifact equity_curve field equity_curve row {index} has an invalid timestamp."
            )
            return ()

        canonical_value = row.get("value")
        preserved_value = row.get("equity")
        if canonical_value is not None and preserved_value is not None:
            if (
                not _valid_number(canonical_value)
                or not _valid_number(preserved_value)
                or float(canonical_value) != float(preserved_value)
            ):
                warnings.append(
                    "Artifact equity_curve field equity_curve row "
                    f"{index} has conflicting value and equity."
                )
                return ()
        value = canonical_value if canonical_value is not None else preserved_value
        if not _valid_number(value):
            warnings.append(
                f"Artifact equity_curve field equity_curve row {index} has invalid value."
            )
            return ()
        normalized.append({**row, "value": value})
    return tuple(normalized)


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
    source_interval: str | None = None,
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
        valid_rows.append(row)
    if {"open", "high", "low", "close"}.issubset(numeric_fields):
        if source_interval is None:
            warnings.append(
                f"Artifact equity_curve field {key} cannot be used because its source interval was not recorded."
            )
            return ()
        try:
            validate_ohlc_rows(valid_rows, source_interval=source_interval)
        except ResultsDataError as exc:
            warnings.append(f"Artifact equity_curve field {key} is invalid: {exc.reason}")
            return ()
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
    from backtesting.validation.evidence_service import ValidationEvidenceArtifactService

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


def _screening_outcome_fields(document: Any) -> tuple[DetailField, ...]:
    if not isinstance(document, dict) or document.get("stage") != "screening":
        return ()
    screening = document.get("screening")
    if not isinstance(screening, dict):
        return ()
    evaluated = screening.get("evaluated_combinations")
    passed = screening.get("passed")
    screened_out = screening.get("screened_out")
    counts = (evaluated, passed, screened_out)
    if not all(
        isinstance(value, int) and not isinstance(value, bool) for value in counts
    ):
        return ()
    if (
        evaluated <= 0
        or passed < 0
        or screened_out < 0
        or passed + screened_out != evaluated
    ):
        return ()
    status = "passed" if passed else "screened_out"
    blockers = document.get("promotion_blockers")
    reasons = blockers if isinstance(blockers, list) else ()
    protected_data_used = document.get("protected_data_used")
    protected_state = (
        "Not used; development/reference evidence only"
        if protected_data_used is False
        else "Not established; protected-data use was not explicitly recorded"
    )
    return (
        DetailField("Stage", "Screening"),
        DetailField("Normalized status", status),
        DetailField("Reasons", _display(reasons)),
        DetailField(
            "Protected-data state",
            protected_state,
        ),
        DetailField("Evidence identity", _display(document.get("evidence_label"))),
        DetailField("Artifact identity", "validation_evidence"),
        DetailField("Lockbox eligibility", "No"),
        DetailField("Strategy progression", "No strategy progression occurred."),
    )


def _is_legacy_spym_fixture_notice(
    summary_document: Any,
    dataset_document: Any,
    detail: dict[str, Any] | None,
) -> bool:
    """Keep the historical SPYM fixture notice off the Decision-296 candidate."""
    if not isinstance(dataset_document, dict) or dataset_document.get("symbol") != "SPYM":
        return False
    strategy_id = (
        summary_document.get("strategy_id")
        if isinstance(summary_document, dict)
        else None
    )
    if not isinstance(strategy_id, str) and isinstance(detail, dict):
        run = detail.get("run")
        if isinstance(run, dict):
            strategy_id = run.get("strategy_id")
    return strategy_id != "spym_intraday_momentum"


def _persisted_annualization_notice(document: Any) -> str | None:
    if not isinstance(document, dict):
        return None
    annualization = document.get("annualization")
    if not isinstance(annualization, dict):
        return None
    sessions = annualization.get("sessions_per_year")
    risk_free = annualization.get("risk_free_rate")
    basis = annualization.get("basis")
    if (
        not isinstance(sessions, int)
        or isinstance(sessions, bool)
        or sessions <= 0
        or not isinstance(risk_free, (int, float))
        or isinstance(risk_free, bool)
        or not math.isfinite(float(risk_free))
        or not isinstance(basis, str)
        or not basis.strip()
    ):
        return None
    return (
        f"Annualized return uses the persisted {sessions} sessions/year and "
        f"{float(risk_free):g} risk-free basis from {basis.strip()}."
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

    provenance_doc = (detail or {}).get("provenance")
    source_interval = _canonical_interval(
        provenance_doc.get("interval") if isinstance(provenance_doc, dict) else None
    )
    equity_curve = _validated_equity_curve(equity_doc, warnings=warnings)
    price_series = _validated_series_rows(
        equity_doc,
        "price_series",
        numeric_fields=("open", "high", "low", "close"),
        warnings=warnings,
        source_interval=source_interval,
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
    evidence_classification = None
    promotion_eligible = None
    for document in (summary_doc, validation_doc):
        if not isinstance(document, dict):
            continue
        classification = document.get("evidence_classification")
        if (
            evidence_classification is None
            and isinstance(classification, str)
            and classification.strip()
        ):
            evidence_classification = classification.strip().rstrip(".")
        if promotion_eligible is None and isinstance(document.get("promotion_eligible"), bool):
            promotion_eligible = document["promotion_eligible"]
    if evidence_classification:
        notices.append(f"Evidence classification: {evidence_classification}.")
    calendar_cagr = _calendar_cagr(
        metrics.get("total_return") if isinstance(metrics, dict) else None,
        provenance_doc.get("actual_coverage")
        if isinstance(provenance_doc, dict)
        else None,
    )
    if isinstance(metrics, dict) and "annualized_return" in metrics:
        notices.append(
            _persisted_annualization_notice(validation_doc)
            or "Annualized return is the recorded engine output. Its frequency, annualization, and risk-free basis were not persisted; do not treat it as a separately calculated calendar growth rate."
        )
    if calendar_cagr is not None:
        notices.append(
            "Calendar CAGR is derived separately from recorded total return and actual coverage; it is not the engine annualization or a new screening metric."
        )
    if promotion_eligible is False:
        notices.append(
            "Promotion blocked: this screening run cannot qualify an edge or advance to paper trading."
        )
    if isinstance(summary_doc, dict) and summary_doc.get("fixture_only") is True:
        notices.append(
            "Infrastructure fixture only: this run proves factory plumbing and is not profitability evidence."
        )
    if isinstance(summary_doc, dict) and summary_doc.get("broker_orders") == "disabled":
        notices.append("Broker orders were disabled; no paper or live orders were submitted.")
    if _is_legacy_spym_fixture_notice(summary_doc, dataset_doc, detail):
        notices.append(
            "SPYM is an ingestion and execution fixture here; it is not selected as the final paper or micro-live instrument."
        )

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
    if not validation_outcome:
        validation_outcome = _screening_outcome_fields(validation_doc)

    price_unit: str | None = None
    pnl_unit: str | None = None
    if isinstance(trades_doc, dict):
        recorded_price_unit = trades_doc.get("price_unit")
        if recorded_price_unit in {"currency", "index_points"}:
            price_unit = recorded_price_unit
        elif recorded_price_unit not in (None, ""):
            warnings.append(
                f"Artifact trades_and_orders price_unit {recorded_price_unit!r} is unsupported."
            )
        recorded_pnl_unit = trades_doc.get("pnl_unit")
        if isinstance(recorded_pnl_unit, str) and recorded_pnl_unit.strip():
            pnl_unit = recorded_pnl_unit.strip()

    return RunEvidenceView(
        notices=tuple(notices),
        metrics=_metric_fields(
            metrics,
            actual_coverage=(
                provenance_doc.get("actual_coverage")
                if isinstance(provenance_doc, dict)
                else None
            ),
        ),
        trades=_candidate_trade_rows(trades_doc),
        orders=_candidate_order_rows(trades_doc),
        equity_curve=equity_curve,
        drawdown_curve=_drawdown_curve(equity_curve),
        validation_outcome=validation_outcome,
        price_series=price_series,
        benchmark_curve=benchmark_curve,
        benchmark=benchmark,
        source_interval=source_interval,
        price_unit=price_unit,
        pnl_unit=pnl_unit,
        evidence_classification=evidence_classification,
        promotion_eligible=promotion_eligible,
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
        self._successful_detail_cache: tuple[tuple[Any, ...], SelectedRunDetailView] | None = None
        self._successful_detail_cache_lock = RLock()

    def selected_run_detail(self, run_id: str) -> SelectedRunDetailView:
        service = PersistenceService(self.database)
        try:
            run = service.runs.get(run_id)
            succeeded = run is not None and run.status == "succeeded"
            persisted_manifest = (
                service.read_persisted_run_manifest(run_id) if succeeded else None
            )
            parameter_result_fingerprint = tuple(
                (
                    row.row_id,
                    row.normalized_parameters_json,
                    row.metrics_json,
                    row.ranking_position,
                    row.screening_status,
                    row.rejection_reasons,
                )
                for row in service.results.list_parameter_results(run_id)
            )
            artifact_fingerprint: list[tuple[Any, ...]] = []
            if succeeded:
                for artifact in service.list_run_artifacts(run_id):
                    location = Path(artifact.location)
                    path = location if location.is_absolute() else self.artifact_root / location
                    try:
                        stat = path.stat()
                        observed = (stat.st_size, stat.st_mtime_ns)
                    except OSError:
                        observed = (None, None)
                    artifact_fingerprint.append(
                        (
                            artifact.artifact_id,
                            artifact.run_id,
                            artifact.artifact_type.value,
                            artifact.logical_name,
                            artifact.schema_version,
                            artifact.media_type,
                            artifact.format,
                            artifact.checksum_algorithm,
                            artifact.checksum,
                            artifact.size_bytes,
                            artifact.location,
                            artifact.availability_state.value,
                            artifact.created_at,
                            *observed,
                        )
                    )
            cache_key = (
                run_id,
                run.completed_at if run is not None else None,
                persisted_manifest,
                parameter_result_fingerprint,
                tuple(artifact_fingerprint),
            )
        finally:
            service.close()
        if not succeeded:
            return self._selected_run_detail(run_id)
        with self._successful_detail_cache_lock:
            cached = self._successful_detail_cache
            if cached is not None and cached[0] == cache_key:
                return cached[1]
            detail = self._selected_run_detail(run_id)
            self._successful_detail_cache = (cache_key, detail)
            return detail

    def _selected_run_detail(self, run_id: str) -> SelectedRunDetailView:
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

            registered_artifacts = service.list_run_artifacts(run_id)
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
                    for artifact in registered_artifacts
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
                result_summary=_result_summary(
                    detail,
                    run_id=run_id,
                    registered_artifacts=registered_artifacts,
                    retrieval=retrieval,
                    artifact_root=self.artifact_root,
                    warnings=warnings,
                    manifest_document=manifest_document,
                    evidence_classification=evidence.evidence_classification,
                ),
                evidence=evidence,
                warnings=tuple(warnings),
            )
        finally:
            service.close()
