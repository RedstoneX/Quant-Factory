"""Document-level validation for generic walk-forward evidence artifacts."""

from __future__ import annotations

from typing import Any, Mapping

from backtesting.validation.evidence_models import WalkForwardWindowRules
from backtesting.validation.walk_forward_artifacts.builder import _identity
from backtesting.validation.walk_forward_artifacts.models import (
    WALK_FORWARD_EVIDENCE_SCHEMA_VERSION,
)


def _partition_bounds(
    name: str,
    document: dict[str, Any] | None,
) -> tuple[str, str, int] | None:
    if document is None:
        return None
    if not isinstance(document, dict):
        raise ValueError(f"{name} partition is not an object")
    required = ("name", "start", "end", "row_count")
    missing = tuple(key for key in required if key not in document)
    if missing:
        raise ValueError(f"{name} partition missing fields: {', '.join(missing)}")
    if not isinstance(document["name"], str) or not document["name"].strip():
        raise ValueError(f"{name} partition identity is missing")
    start = document["start"]
    end = document["end"]
    row_count = document["row_count"]
    if not isinstance(start, str) or not start.strip():
        raise ValueError(f"{name} partition start is missing")
    if not isinstance(end, str) or not end.strip():
        raise ValueError(f"{name} partition end is missing")
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 1:
        raise ValueError(f"{name} partition row_count must be a positive integer")
    if start > end:
        raise ValueError(f"{name} partition is not chronological")
    return start, end, row_count


def _validate_folds_document(
    document: dict[str, Any],
    rules: WalkForwardWindowRules,
) -> tuple[str, tuple[str, ...]]:
    folds = document.get("evidence", {}).get("folds")
    if not isinstance(folds, list):
        raise ValueError("walk-forward evidence folds are missing")
    if not folds:
        raise ValueError("walk-forward evidence folds are missing")
    previous_test_end: str | None = None
    previous_train_start: str | None = None
    expected_train_size = rules.training_window_size
    failed_reasons: list[str] = []
    for fold in folds:
        if not isinstance(fold, dict):
            raise ValueError("walk-forward fold is not an object")
        required = (
            "fold_id",
            "train",
            "selection",
            "test",
            "status",
            "failure_reason",
            "parameter_lock_id",
            "selected_parameters",
            "test_metrics",
        )
        missing = tuple(key for key in required if key not in fold)
        if missing:
            raise ValueError(f"walk-forward fold missing fields: {', '.join(missing)}")
        fold_id = fold["fold_id"]
        if not isinstance(fold_id, str) or not fold_id.strip():
            raise ValueError("walk-forward fold identity is missing")
        status = fold["status"]
        if status not in {"successful", "failed"}:
            raise ValueError("walk-forward fold status is unsupported")
        train = _partition_bounds(f"{fold_id}:train", fold["train"])
        test = _partition_bounds(f"{fold_id}:test", fold["test"])
        assert train is not None and test is not None
        train_start, train_end, train_size = train
        test_start, test_end, test_size = test
        if rules.training_mode == "rolling":
            if train_size != rules.training_window_size:
                raise ValueError(
                    f"{fold_id}: rolling train window has {train_size} rows; "
                    f"expected {rules.training_window_size}"
                )
        elif rules.training_mode == "expanding":
            if train_size != expected_train_size:
                raise ValueError(
                    f"{fold_id}: expanding train window has {train_size} rows; "
                    f"expected {expected_train_size}"
                )
            if previous_train_start is not None and train_start != previous_train_start:
                raise ValueError(f"{fold_id}: expanding train window start changed")
            expected_train_size += rules.step_size
        else:
            raise ValueError(f"unsupported walk-forward training mode: {rules.training_mode}")
        if previous_train_start is None:
            previous_train_start = train_start
        if rules.selection_window_size is None:
            if fold["selection"] is not None:
                raise ValueError(f"{fold_id}: selection window is not declared")
            if not train_end < test_start:
                raise ValueError(f"{fold_id}: test overlaps train period")
        else:
            selection = _partition_bounds(f"{fold_id}:selection", fold["selection"])
            if selection is None:
                raise ValueError(f"{fold_id}:selection partition is missing")
            selection_start, selection_end, selection_size = selection
            if selection_size != rules.selection_window_size:
                raise ValueError(
                    f"{fold_id}: selection window has {selection_size} rows; "
                    f"expected {rules.selection_window_size}"
                )
            if not train_end < selection_start:
                raise ValueError(f"{fold_id}: selection overlaps train period")
            if not selection_end < test_start:
                raise ValueError(f"{fold_id}: test overlaps selection period")
        if test_size != rules.test_window_size:
            raise ValueError(
                f"{fold_id}: test window has {test_size} rows; "
                f"expected {rules.test_window_size}"
            )
        if previous_test_end is not None and previous_test_end >= test_start:
            raise ValueError(f"{fold_id}: test window overlaps a prior test window")
        previous_test_end = test_end
        if status == "successful" and fold["selected_parameters"] is not None:
            lock_id = fold["parameter_lock_id"]
            if not isinstance(lock_id, str) or not lock_id.strip():
                raise ValueError(
                    f"{fold_id}: successful fold with selected parameters lacks a parameter lock"
                )
        if status == "failed":
            reason = fold["failure_reason"] or "fold failed without a reason"
            failed_reasons.append(f"{fold_id}: {reason}")
    if failed_reasons:
        return "failed", tuple(failed_reasons)
    return (
        "insufficient_evidence",
        ("successful walk-forward folds do not define an overall acceptance decision",),
    )


def _rules_from_document(document: dict[str, Any]) -> WalkForwardWindowRules:
    rules = document.get("evidence", {}).get("declared_walk_forward_rules")
    if not isinstance(rules, dict):
        raise ValueError("declared walk-forward rules are missing")
    return WalkForwardWindowRules(
        training_window_size=rules["training_window_size"],
        selection_window_size=rules["selection_window_size"],
        test_window_size=rules["test_window_size"],
        step_size=rules["step_size"],
        training_mode=rules["training_mode"],
        minimum_rows_per_window=rules["minimum_rows_per_window"],
        incomplete_final_window=rules["incomplete_final_window"],
    )


def validate_walk_forward_evidence_document(
    *,
    document: dict[str, Any],
    run_id: str,
    artifact: "ArtifactContractRecord",
) -> None:
    """Validate artifact identity, source lineage, required fields, and rules."""
    if document.get("artifact_schema_version") != WALK_FORWARD_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported walk-forward evidence schema version")
    if document.get("artifact_kind") != "generic_walk_forward_evidence":
        raise ValueError("unsupported walk-forward evidence artifact kind")
    artifact_doc = document.get("artifact")
    if not isinstance(artifact_doc, dict):
        raise ValueError("walk-forward evidence artifact identity is missing")
    if artifact_doc.get("logical_name") != artifact.logical_name:
        raise ValueError("walk-forward evidence logical name mismatch")
    if artifact_doc.get("artifact_type") != artifact.artifact_type.value:
        raise ValueError("walk-forward evidence artifact type mismatch")
    source = document.get("source")
    if not isinstance(source, dict) or source.get("run_id") != run_id:
        raise ValueError("walk-forward evidence source run mismatch")
    rules = _rules_from_document(document)
    try:
        status, reasons = _validate_folds_document(document, rules)
    except ValueError as exc:
        message = str(exc)
        if (
            "expected" in message
            or "overlaps" in message
            or "training mode" in message
            or "selection window is not declared" in message
            or "expanding train window start changed" in message
        ):
            raise ValueError(
                "declared walk-forward rules are inconsistent with persisted folds"
            ) from exc
        raise
    stored = document.get("evidence", {}).get("normalized_evidence")
    if not isinstance(stored, dict):
        raise ValueError("walk-forward normalized evidence is missing")
    if stored.get("status") != status or tuple(stored.get("reasons", ())) != reasons:
        raise ValueError("walk-forward normalized evidence does not match folds")
    expected_identity = _identity(
        {
            "declared_walk_forward_rules": document["evidence"][
                "declared_walk_forward_rules"
            ],
            "folds": document["evidence"]["folds"],
            "normalized_evidence": document["evidence"]["normalized_evidence"],
        }
    )
    if artifact_doc.get("evidence_identity") != expected_identity:
        raise ValueError("walk-forward evidence identity mismatch")


def _validate_source_lineage(
    *,
    document: dict[str, Any],
    expected_source: Mapping[str, Any],
) -> None:
    source = document.get("source")
    if not isinstance(source, dict):
        raise ValueError("walk-forward evidence source lineage is missing")
    for key, expected_value in expected_source.items():
        if source.get(key) != expected_value:
            raise ValueError(f"walk-forward evidence source lineage mismatch: {key}")
