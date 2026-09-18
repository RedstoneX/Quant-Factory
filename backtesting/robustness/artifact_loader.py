"""Validation of prior OOS and walk-forward parameter-lock artifacts."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from backtesting.robustness.models import SourceLockEvidence
from strategies import get_strategy


def _finite_metrics(metrics: Any) -> bool:
    if not isinstance(metrics, dict):
        return False
    required = ("total_return", "max_drawdown", "number_of_trades")
    for name in required:
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not math.isfinite(float(value)):
            return False
    sharpe = metrics.get("sharpe_ratio")
    return sharpe is None or (
        isinstance(sharpe, (int, float))
        and not isinstance(sharpe, bool)
        and math.isfinite(float(sharpe))
    )


def _failed(path: Path, kind: str, reasons: list[str]) -> SourceLockEvidence:
    return SourceLockEvidence(
        status="invalid_input",
        artifact_path=str(path),
        artifact_kind=kind if kind in {"out_of_sample", "walk_forward"} else "unknown",
        artifact_id=path.stem,
        schema_version=None,
        experiment_id="",
        strategy_id="",
        strategy_version="",
        locked_parameters=None,
        source_start=None,
        source_end=None,
        data_provenance={},
        execution_assumptions={},
        metrics={},
        reasons=tuple(reasons),
    )


def load_lock_artifact(
    path: Path,
    *,
    expected_experiment_id: str,
    expected_strategy_id: str,
    expected_strategy_version: str,
    expected_execution: Mapping[str, Any] | None = None,
) -> SourceLockEvidence:
    """Load one strict schema-v1 lock artifact and validate its evidence."""
    if not path.exists():
        return SourceLockEvidence(
            status="insufficient_evidence",
            artifact_path=str(path),
            artifact_kind="unknown",
            artifact_id=path.stem,
            schema_version=None,
            experiment_id="",
            strategy_id="",
            strategy_version="",
            locked_parameters=None,
            source_start=None,
            source_end=None,
            data_provenance={},
            execution_assumptions={},
            metrics={},
            reasons=("artifact is missing",),
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _failed(path, "unknown", [f"artifact JSON is malformed: {exc}"])
    if not isinstance(payload, dict):
        return _failed(path, "unknown", ["artifact must be a JSON object"])

    kind = payload.get("artifact_kind", "unknown")
    reasons: list[str] = []
    if payload.get("schema_version") != 1:
        reasons.append("unsupported or missing artifact schema version")
    if kind not in {"out_of_sample", "walk_forward"}:
        reasons.append("unsupported or missing artifact kind")
    checks = (
        ("experiment_id", expected_experiment_id),
        ("strategy_id", expected_strategy_id),
        ("strategy_version", expected_strategy_version),
    )
    for name, expected in checks:
        if payload.get(name) != expected:
            reasons.append(f"{name} mismatch")
    artifact_id = payload.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        reasons.append("artifact identity is missing")
    provenance = payload.get("data_provenance")
    execution = payload.get("execution_assumptions")
    if not isinstance(provenance, dict) or not provenance:
        reasons.append("data provenance is missing or malformed")
        provenance = {}
    if not isinstance(execution, dict) or not execution:
        reasons.append("execution assumptions are missing or malformed")
        execution = {}
    if expected_execution is not None:
        for name, expected in expected_execution.items():
            if execution.get(name) != expected:
                reasons.append(f"execution assumption mismatch: {name}")

    source_start = payload.get("source_start")
    source_end = payload.get("source_end")
    if not isinstance(source_start, str) or not isinstance(source_end, str):
        reasons.append("source boundaries are missing")
    else:
        try:
            start_date = date.fromisoformat(source_start)
            end_date = date.fromisoformat(source_end)
        except ValueError:
            reasons.append("source boundaries are malformed")
        else:
            if start_date > end_date:
                reasons.append("source boundaries are reversed")

    lock = payload.get("parameter_lock")
    selection_status = payload.get("selection_status")
    test_status = payload.get("test_status")
    metrics = payload.get("metrics")
    parameter_lock_id: str | None = None
    if kind == "walk_forward":
        folds = payload.get("folds")
        selected_fold_id = payload.get("selected_fold_id")
        if not isinstance(folds, list):
            reasons.append("walk-forward folds are missing or malformed")
            selected_fold = None
        elif not isinstance(selected_fold_id, str) or not selected_fold_id:
            reasons.append("selected walk-forward fold identity is missing")
            selected_fold = None
        else:
            matches = [
                fold
                for fold in folds
                if isinstance(fold, dict) and fold.get("fold_id") == selected_fold_id
            ]
            if len(matches) != 1:
                reasons.append("selected walk-forward fold is missing or duplicated")
                selected_fold = None
            else:
                selected_fold = matches[0]
        if selected_fold is not None:
            if selected_fold.get("status") != "successful":
                reasons.append("selected walk-forward fold did not succeed")
            lock = selected_fold.get("parameter_lock")
            selection_status = selected_fold.get("selection_status")
            test_status = selected_fold.get("test_status")
            metrics = selected_fold.get("test_metrics")
            test_boundary = selected_fold.get("test")
            if not isinstance(test_boundary, dict):
                reasons.append("selected fold test boundary is malformed")
            elif (
                test_boundary.get("start") != source_start
                or test_boundary.get("end") != source_end
            ):
                reasons.append("selected fold boundaries do not match source boundaries")

    if not isinstance(lock, dict):
        reasons.append("parameter lock is missing")
        locked_parameters = None
    else:
        locked_parameters = lock.get("normalized_parameters")
        if not isinstance(lock.get("lock_id"), str) or not lock.get("lock_id"):
            reasons.append("parameter lock identity is missing")
        else:
            parameter_lock_id = lock["lock_id"]
        if not isinstance(locked_parameters, dict) or not locked_parameters:
            reasons.append("locked parameters are missing")
            locked_parameters = None
        else:
            try:
                normalized = get_strategy(expected_strategy_id).validate_parameters(
                    locked_parameters
                )
            except (TypeError, ValueError) as exc:
                reasons.append(f"locked parameters are invalid: {exc}")
            else:
                if normalized != locked_parameters:
                    reasons.append("locked parameters are not normalized")

    if selection_status != "passed":
        reasons.append("selection did not pass")
    if test_status != "passed":
        reasons.append("test did not pass")
    if not _finite_metrics(metrics):
        reasons.append("required metrics are missing or non-finite")
        metrics = {}

    if reasons:
        failed = _failed(path, kind, reasons)
        return SourceLockEvidence(
            **{
                **failed.__dict__,
                "artifact_id": artifact_id if isinstance(artifact_id, str) else path.stem,
                "schema_version": payload.get("schema_version") if isinstance(payload.get("schema_version"), int) else None,
                "experiment_id": payload.get("experiment_id", ""),
                "strategy_id": payload.get("strategy_id", ""),
                "strategy_version": payload.get("strategy_version", ""),
                "locked_parameters": locked_parameters,
                "source_start": source_start if isinstance(source_start, str) else None,
                "source_end": source_end if isinstance(source_end, str) else None,
                "data_provenance": provenance,
                "execution_assumptions": execution,
                "metrics": metrics,
                "parameter_lock_id": parameter_lock_id,
            }
        )
    return SourceLockEvidence(
        status="passed",
        artifact_path=str(path),
        artifact_kind=kind,
        artifact_id=artifact_id,
        schema_version=1,
        experiment_id=expected_experiment_id,
        strategy_id=expected_strategy_id,
        strategy_version=expected_strategy_version,
        locked_parameters=dict(locked_parameters),
        source_start=source_start,
        source_end=source_end,
        data_provenance=provenance,
        execution_assumptions=execution,
        metrics={name: value for name, value in metrics.items() if isinstance(value, (int, float)) and not isinstance(value, bool)},
        reasons=(),
        parameter_lock_id=parameter_lock_id,
    )


def find_valid_lock(
    paths: Iterable[Path],
    **expected: Any,
) -> tuple[SourceLockEvidence | None, tuple[SourceLockEvidence, ...]]:
    """Inspect all candidates and return the first valid pre-robustness lock."""
    inspected = tuple(load_lock_artifact(path, **expected) for path in paths)
    valid = next((item for item in inspected if item.status == "passed"), None)
    return valid, inspected
