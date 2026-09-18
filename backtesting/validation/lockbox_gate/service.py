"""Lockbox prerequisite evaluation from already-validated evidence."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, get_args

from backtesting.validation.evidence_adapters import map_native_status
from backtesting.validation.evidence_models import ProtectedDataState
from backtesting.validation.lockbox_gate.models import (
    LockboxArtifactReference,
    LockboxGateResult,
)
from persistence.serialization import canonical_json

_PROTECTED_DATA_STATES = set(get_args(ProtectedDataState))
_LINEAGE_KEYS = (
    "configuration_id",
    "strategy_id",
    "strategy_version",
    "configuration_hash",
    "data_identity",
    "execution_assumptions_identity",
    "runtime_identity",
)
_SOURCE_LOCK_KEYS = (
    "artifact_id",
    "parameter_lock_id",
    "experiment_id",
    "strategy_id",
    "strategy_version",
    "locked_parameters",
    "data_provenance",
    "execution_assumptions",
)


def _identity(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _reference(stage: str, evidence: Any) -> LockboxArtifactReference:
    return LockboxArtifactReference(
        stage=stage,
        artifact_id=str(evidence.artifact.artifact_id),
        evidence_identity=evidence.evidence_identity,
    )


def _source_lock_reference(source_lock: Any) -> LockboxArtifactReference:
    return LockboxArtifactReference(
        stage="out_of_sample",
        artifact_id=source_lock.artifact_id,
        evidence_identity=None,
    )


def _lineage_payload(source: Mapping[str, Any]) -> dict[str, Any]:
    missing = tuple(key for key in _LINEAGE_KEYS if key not in source)
    if missing:
        raise ValueError(f"lineage is missing fields: {', '.join(missing)}")
    return {key: source[key] for key in _LINEAGE_KEYS}


def _lineage_identity(source: Mapping[str, Any]) -> str:
    return _identity(_lineage_payload(source))


def _source_lock_payload(source_lock: Any | None) -> dict[str, Any] | None:
    if source_lock is None:
        return None
    payload: dict[str, Any] = {}
    for key in _SOURCE_LOCK_KEYS:
        payload[key] = getattr(source_lock, key, None)
    return payload


def _combined_lineage_identity(
    *,
    artifact_lineage_identity: str | None,
    source_lock: Any | None,
) -> str | None:
    if artifact_lineage_identity is None and source_lock is None:
        return None
    return _identity(
        {
            "artifact_lineage_identity": artifact_lineage_identity,
            "source_lock": _source_lock_payload(source_lock),
        }
    )


def _normalized(document: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = document.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("evidence document is malformed")
    normalized = evidence.get("normalized_evidence")
    if not isinstance(normalized, Mapping):
        raise ValueError("normalized evidence is missing")
    return normalized


def _walk_forward_ok(normalized: Mapping[str, Any]) -> bool:
    return (
        normalized.get("status") == "insufficient_evidence"
        and tuple(normalized.get("reasons", ()))
        == (
            "successful walk-forward folds do not define an overall acceptance decision",
        )
    )


def _stage_status(
    *,
    stage: str,
    normalized: Mapping[str, Any],
    reasons: list[str],
) -> str:
    status = normalized.get("status")
    if status == "passed":
        return "passed"
    if stage == "walk_forward" and _walk_forward_ok(normalized):
        return "passed"
    stage_reasons = tuple(normalized.get("reasons", ())) or (
        f"{stage} evidence returned {status}",
    )
    reasons.extend(f"{stage}: {reason}" for reason in stage_reasons)
    return map_native_status(status)


def _source_lock_status(
    source_lock: Any,
    reasons: list[str],
) -> str:
    if source_lock.status == "passed":
        return "passed"
    stage_reasons = source_lock.reasons or (
        f"source lock returned {source_lock.status}",
    )
    reasons.extend(f"out_of_sample: {reason}" for reason in stage_reasons)
    return map_native_status(source_lock.status)


def _fold_lock_ids(document: Mapping[str, Any]) -> tuple[str, ...]:
    evidence = document.get("evidence")
    if not isinstance(evidence, Mapping):
        return ()
    folds = evidence.get("folds")
    if not isinstance(folds, list):
        return ()
    ids: list[str] = []
    for fold in folds:
        if (
            isinstance(fold, dict)
            and fold.get("status") == "successful"
            and fold.get("selected_parameters") is not None
        ):
            lock_id = fold.get("parameter_lock_id")
            ids.append(lock_id if isinstance(lock_id, str) and lock_id.strip() else "")
    return tuple(ids)


def _robustness_parameters(document: Mapping[str, Any]) -> dict[str, Any] | None:
    native = document.get("evidence", {}).get("robustness")  # type: ignore[union-attr]
    if not isinstance(native, Mapping):
        return None
    config = native.get("configuration")
    if not isinstance(config, Mapping):
        return None
    parameters = config.get("locked_parameters")
    return dict(parameters) if isinstance(parameters, Mapping) else None


def _robustness_source_artifact(document: Mapping[str, Any]) -> str | None:
    native = document.get("evidence", {}).get("robustness")  # type: ignore[union-attr]
    if not isinstance(native, Mapping):
        return None
    source = native.get("source")
    if not isinstance(source, Mapping):
        return None
    artifact_id = source.get("source_artifact_id")
    return artifact_id if isinstance(artifact_id, str) and artifact_id.strip() else None


def _robustness_native(document: Mapping[str, Any]) -> Mapping[str, Any] | None:
    native = document.get("evidence", {}).get("robustness")  # type: ignore[union-attr]
    return native if isinstance(native, Mapping) else None


def _validate_source_lock_against_robustness(
    *,
    source_lock: Any,
    robustness: Any | None,
    reasons: list[str],
) -> tuple[str, ...]:
    if robustness is None:
        return ()
    native = _robustness_native(robustness.document)
    if native is None:
        reasons.append("robustness: native evidence is missing")
        return ("invalid",)
    source = native.get("source")
    config = native.get("configuration")
    if not isinstance(source, Mapping) or not isinstance(config, Mapping):
        reasons.append("robustness: source/configuration evidence is missing")
        return ("invalid",)
    statuses: list[str] = []
    comparisons = (
        ("experiment_id", getattr(source_lock, "experiment_id", None), config.get("experiment_id")),
        ("strategy_id", getattr(source_lock, "strategy_id", None), config.get("strategy_id")),
        ("strategy_version", getattr(source_lock, "strategy_version", None), config.get("strategy_version")),
        ("locked_parameters", getattr(source_lock, "locked_parameters", None), config.get("locked_parameters")),
        ("data_provenance", getattr(source_lock, "data_provenance", None), source.get("data_provenance")),
        ("execution_assumptions", getattr(source_lock, "execution_assumptions", None), source.get("execution_assumptions")),
        ("source artifact identity", getattr(source_lock, "artifact_id", None), source.get("source_artifact_id")),
    )
    for label, left, right in comparisons:
        if left != right:
            reasons.append(f"robustness: source-lock {label} mismatch")
            statuses.append("invalid")
    return tuple(statuses)


def _result_status(stage_statuses: tuple[str, ...]) -> str:
    if "invalid" in stage_statuses:
        return "invalid"
    if "failed" in stage_statuses:
        return "failed"
    if "insufficient_evidence" in stage_statuses:
        return "insufficient_evidence"
    return "passed"


def _gate_identity_payload(
    *,
    status: str,
    reasons: tuple[str, ...],
    references: tuple[LockboxArtifactReference, ...],
    parameter_lock_identity: str | None,
    protected_data_state: str,
    lineage_identity: str | None,
    eligible_to_execute_lockbox: bool,
) -> dict[str, Any]:
    return {
        "status": status,
        "reasons": reasons,
        "references": tuple(reference.__dict__ for reference in references),
        "parameter_lock_identity": parameter_lock_identity,
        "protected_data_state": protected_data_state,
        "lineage_identity": lineage_identity,
        "eligible_to_execute_lockbox": eligible_to_execute_lockbox,
        "eligible_to_progress": False,
    }


def lockbox_gate_identity(result: LockboxGateResult) -> str:
    """Canonical identity for the final returned gate result."""
    return _identity(
        _gate_identity_payload(
            status=result.status,
            reasons=result.reasons,
            references=result.referenced_artifacts,
            parameter_lock_identity=result.parameter_lock_identity,
            protected_data_state=result.protected_data_state,
            lineage_identity=result.lineage_identity,
            eligible_to_execute_lockbox=result.eligible_to_execute_lockbox,
        )
    )


def _result(
    *,
    status: str,
    reasons: tuple[str, ...],
    references: tuple[LockboxArtifactReference, ...],
    parameter_lock_identity: str | None,
    protected_data_state: str,
    lineage_identity: str | None,
    eligible_to_execute_lockbox: bool,
) -> LockboxGateResult:
    draft = LockboxGateResult(
        status=status,
        reasons=reasons,
        referenced_artifacts=references,
        parameter_lock_identity=parameter_lock_identity,
        protected_data_state=protected_data_state,  # type: ignore[arg-type]
        lineage_identity=lineage_identity,
        gate_identity="",
        eligible_to_execute_lockbox=eligible_to_execute_lockbox,
        eligible_to_progress=False,
    )
    return LockboxGateResult(
        status=draft.status,
        reasons=draft.reasons,
        referenced_artifacts=draft.referenced_artifacts,
        parameter_lock_identity=draft.parameter_lock_identity,
        protected_data_state=draft.protected_data_state,
        lineage_identity=draft.lineage_identity,
        gate_identity=lockbox_gate_identity(draft),
        eligible_to_execute_lockbox=draft.eligible_to_execute_lockbox,
        eligible_to_progress=False,
    )


def evaluate_lockbox_prerequisites(
    *,
    walk_forward: Any | None,
    monte_carlo: Any | None,
    robustness: Any | None,
    source_lock: Any | None,
    protected_data_state: object,
) -> LockboxGateResult:
    """Evaluate validated prerequisite evidence without executing the lockbox."""
    reasons: list[str] = []
    references: list[LockboxArtifactReference] = []
    stage_statuses: list[str] = []
    state = protected_data_state if protected_data_state in _PROTECTED_DATA_STATES else "invalid"

    if state != "gated":
        reasons.append(
            "protected data state must be gated before lockbox execution"
            if state != "spent"
            else "protected data state is already spent"
        )
        stage_statuses.append("invalid" if state == "invalid" else "failed")

    if source_lock is None:
        reasons.append("out_of_sample: source lock evidence is missing")
        stage_statuses.append("insufficient_evidence")
        parameter_lock_identity = None
    else:
        references.append(_source_lock_reference(source_lock))
        stage_statuses.append(_source_lock_status(source_lock, reasons))
        parameter_lock_identity = None
        if source_lock.locked_parameters is None:
            reasons.append("out_of_sample: locked parameters are missing")
            stage_statuses.append("invalid")
        elif not isinstance(source_lock.artifact_id, str) or not source_lock.artifact_id:
            reasons.append("out_of_sample: artifact identity is missing")
            stage_statuses.append("invalid")
        elif (
            not isinstance(getattr(source_lock, "parameter_lock_id", None), str)
            or not source_lock.parameter_lock_id.strip()
        ):
            reasons.append("out_of_sample: parameter-lock identity is missing")
            stage_statuses.append("invalid")
        else:
            parameter_lock_identity = source_lock.parameter_lock_id

    artifacts = (
        ("walk_forward", walk_forward),
        ("monte_carlo", monte_carlo),
        ("robustness", robustness),
    )
    artifact_lineage_identity: str | None = None
    for stage, evidence in artifacts:
        if evidence is None:
            reasons.append(f"{stage}: evidence artifact is missing")
            stage_statuses.append("insufficient_evidence")
            continue
        references.append(_reference(stage, evidence))
        try:
            source = evidence.document["source"]
            current_lineage = _lineage_identity(source)
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append(f"{stage}: source lineage is invalid: {exc}")
            stage_statuses.append("invalid")
        else:
            if artifact_lineage_identity is None:
                artifact_lineage_identity = current_lineage
            elif artifact_lineage_identity != current_lineage:
                reasons.append(f"{stage}: source lineage mismatch")
                stage_statuses.append("invalid")
        try:
            stage_statuses.append(
                _stage_status(
                    stage=stage,
                    normalized=_normalized(evidence.document),
                    reasons=reasons,
                )
            )
        except ValueError as exc:
            reasons.append(f"{stage}: {exc}")
            stage_statuses.append("invalid")

    if source_lock is not None and source_lock.locked_parameters is not None:
        stage_statuses.extend(
            _validate_source_lock_against_robustness(
                source_lock=source_lock,
                robustness=robustness,
                reasons=reasons,
            )
        )
        fold_locks = _fold_lock_ids(walk_forward.document) if walk_forward else ()
        if fold_locks and any(not lock_id for lock_id in fold_locks):
            reasons.append("walk_forward: parameter-lock identity is missing")
            stage_statuses.append("invalid")

    status = _result_status(tuple(stage_statuses))
    if status == "passed" and not reasons:
        reasons_tuple: tuple[str, ...] = ()
    else:
        reasons_tuple = tuple(reasons) or (f"lockbox gate returned {status}",)
    result_references = tuple(references)
    lineage_identity = _combined_lineage_identity(
        artifact_lineage_identity=artifact_lineage_identity,
        source_lock=source_lock,
    )
    return _result(
        status=status,
        reasons=reasons_tuple,
        references=result_references,
        parameter_lock_identity=parameter_lock_identity,
        protected_data_state=state,  # type: ignore[arg-type]
        lineage_identity=lineage_identity,
        eligible_to_execute_lockbox=status == "passed" and state == "gated",
    )
