"""Bound browser chart reads from immutable, checksum-validated artifacts."""

from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
from threading import Lock
from typing import Any

import orjson

_chart_lock = Lock()
_EQUITY_BUCKETS = 1500
_PRICE_WINDOW = 20_000


def detail_cache_key(
    service: Any,
    run_id: str,
    *,
    artifact_root: Path,
    include_chart_data: bool,
) -> tuple[bool, tuple[Any, ...]]:
    """Fingerprint the immutable inputs used by one selected-run view."""

    run = service.runs.get(run_id)
    succeeded = run is not None and run.status == "succeeded"
    persisted_manifest = service.read_persisted_run_manifest(run_id) if succeeded else None
    parameter_results = tuple(
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
    artifacts: list[tuple[Any, ...]] = []
    if succeeded:
        for artifact in service.list_run_artifacts(run_id):
            location = Path(artifact.location)
            path = location if location.is_absolute() else artifact_root / location
            try:
                stat = path.stat()
                observed = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                observed = (None, None)
            artifacts.append(
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
    return succeeded, (
        run_id,
        include_chart_data,
        run.completed_at if run is not None else None,
        persisted_manifest,
        parameter_results,
        tuple(artifacts),
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
    include_chart_data: bool = True,
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
        if artifact.logical_name == "equity_curve" and not include_chart_data:
            continue
        try:
            path = _safe_artifact_path(artifact_root, artifact.location)
            if artifact.logical_name == "equity_curve":
                with _chart_lock:
                    document, notices = _bounded_chart_document(str(path), artifact.checksum)
                documents[artifact.logical_name] = document
                warnings.extend(notices)
            else:
                documents[artifact.logical_name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            warnings.append(f"Artifact {artifact.logical_name} content is invalid: {exc}.")
    return documents, warnings


@lru_cache(maxsize=4)
def _bounded_chart_document(path: str, checksum: str) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Keep full sealed bytes on disk; return a truthful bounded chart view."""
    del checksum  # The caller validated this exact checksum before opening bytes.
    # This artifact can contain hundreds of thousands of equity and OHLC rows.
    # Decode bytes directly with the pinned native parser so the first Results
    # view does not spend seconds creating an intermediate 80+ MB Python string.
    document = orjson.loads(Path(path).read_bytes())
    if not isinstance(document, dict):
        raise ValueError("equity curve artifact must be an object")
    notices: list[str] = []
    equity = document.get("equity_curve")
    if isinstance(equity, list) and len(equity) > _EQUITY_BUCKETS * 2:
        width = math.ceil(len(equity) / _EQUITY_BUCKETS)
        selected = {0, len(equity) - 1}
        for start in range(0, len(equity), width):
            bucket = range(start, min(start + width, len(equity)))
            try:
                selected.add(min(bucket, key=lambda index: float(equity[index]["value"])))
                selected.add(max(bucket, key=lambda index: float(equity[index]["value"])))
            except (KeyError, TypeError, ValueError, OverflowError):
                raise ValueError("equity curve contains an invalid value") from None
        document["equity_curve"] = [equity[index] for index in sorted(selected)]
        notices.append(
            f"Portfolio chart displays {len(document['equity_curve']):,} extrema-preserving points from "
            f"{len(equity):,} checksum-verified observations; aggregate metrics remain the recorded engine output."
        )
    prices = document.get("price_series")
    if isinstance(prices, list) and len(prices) > _PRICE_WINDOW:
        document["price_series"] = prices[-_PRICE_WINDOW:]
        notices.append(
            f"Price chart displays the latest {_PRICE_WINDOW:,} of {len(prices):,} recorded bars. "
            "Earlier bars remain in the sealed artifact and are not plotted in this browser view."
        )
    return document, tuple(notices)
