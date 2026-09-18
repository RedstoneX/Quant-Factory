"""Fail-closed adapters from native validation outputs to shared evidence."""

from __future__ import annotations

from functools import wraps
from typing import Any, Iterable, Mapping

from backtesting.validation.evidence_models import (
    EvidenceStatus,
    NormalizedEvidenceRecord,
    NormalizedThresholdResult,
    ProtectedDataState,
    WalkForwardWindowRules,
)


_VALID_PROTECTED_DATA_STATES = {
    "not_applicable",
    "unspent",
    "gated",
    "spent",
    "invalid",
}
_DEFAULT_PROTECTED_DATA_STATE = object()


def map_native_status(status: object) -> EvidenceStatus:
    """Map native terminal vocabulary without promoting unknown values."""
    return {
        "passed": "passed",
        "failed": "failed",
        "insufficient_evidence": "insufficient_evidence",
        "invalid_input": "invalid",
        "invalid": "invalid",
    }.get(status, "invalid")


def _reasons(values: Iterable[object], fallback: str) -> tuple[str, ...]:
    preserved = tuple(str(value).strip() for value in values if str(value).strip())
    return preserved or (fallback,)


def _protected_state(
    value: object,
) -> tuple[ProtectedDataState, str | None]:
    if value in _VALID_PROTECTED_DATA_STATES:
        return value, None
    return "invalid", f"unsupported protected-data state: {value!r}"


def _invalid(
    stage_identity: str,
    reason: str,
    *,
    protected_data_state: object = "not_applicable",
) -> NormalizedEvidenceRecord:
    state, state_error = _protected_state(protected_data_state)
    reasons = (reason,) if state_error is None else (reason, state_error)
    return NormalizedEvidenceRecord(
        stage_identity=stage_identity,
        status="invalid",
        reasons=reasons,
        protected_data_state=state,
    )


def _fail_closed_adapter(stage_identity: str, default_protected_data_state: str):
    """Turn malformed native objects into a normal invalid evidence record."""

    def decorator(adapter):
        @wraps(adapter)
        def wrapped(
            result: object,
            *,
            protected_data_state: object = default_protected_data_state,
            **kwargs,
        ) -> NormalizedEvidenceRecord:
            try:
                return adapter(
                    result,
                    protected_data_state=protected_data_state,
                    **kwargs,
                )
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                return _invalid(
                    stage_identity,
                    f"malformed {stage_identity} result: {exc}",
                    protected_data_state=protected_data_state,
                )

        return wrapped

    return decorator


def _record(
    *,
    stage_identity: str,
    status: EvidenceStatus,
    reasons: Iterable[object],
    threshold_results: tuple[NormalizedThresholdResult, ...] = (),
    source_identity: str | None = None,
    protected_data_state: object = "not_applicable",
) -> NormalizedEvidenceRecord:
    state, state_error = _protected_state(protected_data_state)
    if state_error is not None:
        return NormalizedEvidenceRecord(
            stage_identity=stage_identity,
            status="invalid",
            reasons=_reasons(tuple(reasons) + (state_error,), "invalid protected-data state"),
            threshold_results=threshold_results,
            source_identity=source_identity,
            protected_data_state=state,
        )
    if status == "passed":
        normalized_reasons = tuple(
            str(reason).strip() for reason in reasons if str(reason).strip()
        )
    else:
        normalized_reasons = _reasons(reasons, f"{stage_identity} returned {status}")
    return NormalizedEvidenceRecord(
        stage_identity=stage_identity,
        status=status,
        reasons=normalized_reasons,
        threshold_results=threshold_results,
        source_identity=source_identity,
        protected_data_state=state,
    )


def _screening_thresholds(
    screening: Any,
) -> tuple[NormalizedThresholdResult, ...]:
    return tuple(
        NormalizedThresholdResult(
            threshold_id=rule.rule_id,
            status="passed" if rule.status == "passed" else "failed",
            observed=rule.observed_value,
            threshold=rule.threshold,
            reason=rule.message,
        )
        for rule in screening.rule_results
    )


def _partition_bounds(partition: object) -> tuple[Any, Any]:
    data = getattr(partition, "data", None)
    index = getattr(data, "index", None)
    if index is not None and len(index) > 0:
        return index[0], index[-1]
    return getattr(partition, "start"), getattr(partition, "end")


def _partition_boundary_label(value: object) -> str:
    if hasattr(value, "date"):
        return str(value.date())
    return str(value)


def _partition_index(partition: object) -> object | None:
    data = getattr(partition, "data", None)
    index = getattr(data, "index", None)
    if index is not None and len(index) > 0:
        return index
    return None


def _partition_row_count(partition: object) -> int:
    row_count = getattr(partition, "row_count")
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 1:
        raise ValueError("partition row_count must be a positive integer")
    return row_count


def _require_partition(name: str, partition: object) -> None:
    if partition is None:
        raise ValueError(f"{name} partition is missing")
    if not isinstance(getattr(partition, "name"), str) or not partition.name.strip():
        raise ValueError(f"{name} partition identity is missing")
    if not isinstance(getattr(partition, "start"), str) or not partition.start.strip():
        raise ValueError(f"{name} partition start is missing")
    if not isinstance(getattr(partition, "end"), str) or not partition.end.strip():
        raise ValueError(f"{name} partition end is missing")
    _partition_row_count(partition)
    start, end = _partition_bounds(partition)
    if start > end:
        raise ValueError(f"{name} partition is not chronological")
    index = _partition_index(partition)
    if index is not None:
        if len(index) != partition.row_count:
            raise ValueError(f"{name} partition row_count does not match data length")
        if partition.start != _partition_boundary_label(index[0]):
            raise ValueError(f"{name} partition start does not match data")
        if partition.end != _partition_boundary_label(index[-1]):
            raise ValueError(f"{name} partition end does not match data")


def _validate_walk_forward_windows(
    result: object,
    rules: WalkForwardWindowRules | None,
) -> tuple[str, ...]:
    if rules is None:
        return ()
    folds = tuple(getattr(result, "folds"))
    previous_test_end = None
    previous_train_start = None
    previous_train_index = None
    expected_train_size = rules.training_window_size
    for fold in folds:
        fold_id = getattr(fold, "fold_id")
        if not isinstance(fold_id, str) or not fold_id.strip():
            raise ValueError("walk-forward fold identity is missing")
        window = getattr(fold, "window")
        if window is None:
            raise ValueError(f"{fold_id}: window information is missing")
        if getattr(window, "fold_id") != fold_id:
            raise ValueError(f"{fold_id}: window fold identity does not match fold")
        train = getattr(window, "train")
        selection = getattr(window, "selection")
        test = getattr(window, "test")
        _require_partition(f"{fold_id}:train", train)
        _require_partition(f"{fold_id}:test", test)
        train_start, train_end = _partition_bounds(train)
        train_size = _partition_row_count(train)
        test_start, test_end = _partition_bounds(test)
        if rules.training_mode == "rolling":
            if train_size != rules.training_window_size:
                raise ValueError(
                    f"{fold_id}: rolling train window has {train_size} rows; "
                    f"expected {rules.training_window_size}"
            )
            if previous_train_index is not None:
                if rules.step_size < len(previous_train_index):
                    expected_start = previous_train_index[rules.step_size]
                    if train_start != expected_start:
                        raise ValueError(
                            f"{fold_id}: rolling train window advanced by a different step"
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
        previous_train_index = _partition_index(train)
        if rules.selection_window_size is None:
            if selection is not None:
                raise ValueError(f"{fold_id}: selection window is not declared")
            if not train_end < test_start:
                raise ValueError(f"{fold_id}: test overlaps train period")
        else:
            _require_partition(f"{fold_id}:selection", selection)
            selection_start, selection_end = _partition_bounds(selection)
            selection_size = _partition_row_count(selection)
            if selection_size != rules.selection_window_size:
                raise ValueError(
                    f"{fold_id}: selection window has {selection_size} rows; "
                    f"expected {rules.selection_window_size}"
                )
            if not train_end < selection_start:
                raise ValueError(f"{fold_id}: selection overlaps train period")
            if not selection_end < test_start:
                raise ValueError(f"{fold_id}: test overlaps selection period")
        test_size = _partition_row_count(test)
        if test_size != rules.test_window_size:
            is_short_final = (
                fold is folds[-1]
                and rules.incomplete_final_window == "include"
                and rules.minimum_rows_per_window <= test_size < rules.test_window_size
            )
            if not is_short_final:
                raise ValueError(
                    f"{fold_id}: test window has {test_size} rows; "
                    f"expected {rules.test_window_size}"
                )
        if previous_test_end is not None and previous_test_end >= test_start:
            raise ValueError(f"{fold_id}: test window overlaps a prior test window")
        previous_test_end = test_end
        selected_parameters = getattr(fold, "selected_parameters")
        if getattr(fold, "status") == "successful" and selected_parameters is not None:
            lock = getattr(fold, "parameter_lock")
            lock_id = getattr(lock, "lock_id", None)
            if not isinstance(lock_id, str) or not lock_id.strip():
                raise ValueError(
                    f"{fold_id}: successful fold with selected parameters lacks a parameter lock"
                )
    return ()


@_fail_closed_adapter("out_of_sample", "spent")
def normalize_out_of_sample_evidence(
    result: object,
    *,
    protected_data_state: object = "spent",
) -> NormalizedEvidenceRecord:
    """Normalize the locked test stage; absent lock/test evidence is invalid."""
    stage = "out_of_sample"
    from backtesting.out_of_sample.models import OutOfSampleResult
    from backtesting.screening.models import ScreeningResult

    if not isinstance(result, OutOfSampleResult):
        return _invalid(stage, "unsupported out-of-sample result", protected_data_state=protected_data_state)
    if not isinstance(result.selected_parameters, Mapping):
        return _invalid(stage, "out-of-sample selected parameters are malformed", protected_data_state=protected_data_state)
    screenings = getattr(result.test_result, "screening_results", None)
    if not isinstance(screenings, tuple):
        return _invalid(stage, "out-of-sample test screening evidence is missing", protected_data_state=protected_data_state)
    matches = tuple(
        screening
        for screening in screenings
        if isinstance(screening, ScreeningResult)
        and screening.normalized_parameters == result.selected_parameters
    )
    if len(matches) != 1:
        return _invalid(stage, "out-of-sample selected test screening result is unavailable", protected_data_state=protected_data_state)
    screening = matches[0]
    status: EvidenceStatus = "passed" if screening.passed else "failed"
    failed_rule_reasons = tuple(
        rule.message for rule in screening.rule_results if rule.status == "failed"
    )
    reasons = () if screening.passed else screening.rejection_reasons + failed_rule_reasons
    lock_id = getattr(result.parameter_lock, "lock_id", None)
    if not isinstance(lock_id, str) or not lock_id.strip():
        return _invalid(
            stage,
            "out-of-sample parameter-lock identity is missing",
            protected_data_state=protected_data_state,
        )
    return _record(
        stage_identity=stage,
        status=status,
        reasons=reasons,
        threshold_results=_screening_thresholds(screening),
        source_identity=lock_id,
        protected_data_state=protected_data_state,
    )


@_fail_closed_adapter("walk_forward", "not_applicable")
def normalize_walk_forward_evidence(
    result: object,
    *,
    protected_data_state: object = "not_applicable",
    window_rules: WalkForwardWindowRules | None = None,
) -> NormalizedEvidenceRecord:
    """Treat successful folds as execution evidence, not an acceptance decision."""
    stage = "walk_forward"
    from backtesting.walk_forward.models import WalkForwardResult

    if not isinstance(result, WalkForwardResult):
        return _invalid(stage, "unsupported walk-forward result", protected_data_state=protected_data_state)
    if not result.folds:
        return _invalid(stage, "walk-forward result contains no folds", protected_data_state=protected_data_state)
    _validate_walk_forward_windows(result, window_rules)
    unsupported = tuple(
        fold.fold_id for fold in result.folds if fold.status not in {"successful", "failed"}
    )
    if unsupported:
        return _invalid(
            stage,
            f"walk-forward result has unsupported fold statuses: {', '.join(unsupported)}",
            protected_data_state=protected_data_state,
        )
    failed = tuple(fold for fold in result.folds if fold.status == "failed")
    if failed:
        reasons = tuple(
            f"{fold.fold_id}: {fold.failure_reason or 'fold failed without a reason'}"
            for fold in failed
        )
        return _record(
            stage_identity=stage,
            status="failed",
            reasons=reasons,
            source_identity="walk_forward_folds",
            protected_data_state=protected_data_state,
        )
    return _record(
        stage_identity=stage,
        status="insufficient_evidence",
        reasons=("successful walk-forward folds do not define an overall acceptance decision",),
        source_identity="walk_forward_folds",
        protected_data_state=protected_data_state,
    )


@_fail_closed_adapter("low_frequency_walk_forward", "not_applicable")
def normalize_low_frequency_walk_forward_evidence(
    result: object,
    *,
    protected_data_state: object = "not_applicable",
) -> NormalizedEvidenceRecord:
    stage = "low_frequency_walk_forward"
    from backtesting.walk_forward.low_frequency import LowFrequencyEvidenceResult

    if not isinstance(result, LowFrequencyEvidenceResult):
        return _invalid(stage, "unsupported low-frequency walk-forward result", protected_data_state=protected_data_state)
    aggregate = result.aggregate
    status = map_native_status(aggregate.status)
    thresholds = (
        NormalizedThresholdResult(
            threshold_id="sufficient_evidence_folds",
            status="passed"
            if aggregate.sufficient_evidence_fold_count >= aggregate.required_sufficient_folds
            else "insufficient_evidence",
            observed=aggregate.sufficient_evidence_fold_count,
            threshold=aggregate.required_sufficient_folds,
        ),
        NormalizedThresholdResult(
            threshold_id="passing_sufficient_evidence_folds",
            status="passed"
            if aggregate.passing_percentage >= aggregate.required_passing_percentage
            else "failed",
            observed=aggregate.passing_percentage,
            threshold=aggregate.required_passing_percentage,
        ),
        NormalizedThresholdResult(
            threshold_id="worst_drawdown",
            status="passed"
            if aggregate.worst_drawdown is not None
            and abs(aggregate.worst_drawdown) <= aggregate.maximum_allowed_drawdown
            else "insufficient_evidence"
            if aggregate.worst_drawdown is None
            else "failed",
            observed=aggregate.worst_drawdown,
            threshold=aggregate.maximum_allowed_drawdown,
        ),
    )
    return _record(
        stage_identity=stage,
        status=status,
        reasons=aggregate.reasons,
        threshold_results=thresholds,
        source_identity=result.experiment_id,
        protected_data_state=protected_data_state,
    )


@_fail_closed_adapter("monte_carlo", "not_applicable")
def normalize_monte_carlo_evidence(
    result: object,
    *,
    protected_data_state: object = "not_applicable",
) -> NormalizedEvidenceRecord:
    stage = "monte_carlo"
    from backtesting.monte_carlo.models import MonteCarloResult

    if not isinstance(result, MonteCarloResult):
        return _invalid(stage, "unsupported Monte Carlo result", protected_data_state=protected_data_state)
    status = map_native_status(result.status)
    source_id = result.source.source_id
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("Monte Carlo source identity is missing")
    thresholds = tuple(
        NormalizedThresholdResult(
            threshold_id=rule.rule_id,
            status="passed" if rule.passed else "failed",
            observed=rule.observed,
            threshold=rule.threshold,
            reason=rule.message,
        )
        for rule in result.threshold_results
    )
    return _record(
        stage_identity=stage,
        status=status,
        reasons=result.reasons,
        threshold_results=thresholds,
        source_identity=source_id,
        protected_data_state=protected_data_state,
    )


@_fail_closed_adapter("robustness", "not_applicable")
def normalize_robustness_evidence(
    result: object,
    *,
    protected_data_state: object = "not_applicable",
) -> NormalizedEvidenceRecord:
    stage = "robustness"
    from backtesting.robustness.models import RobustnessResult

    if not isinstance(result, RobustnessResult):
        return _invalid(stage, "unsupported robustness result", protected_data_state=protected_data_state)
    if not isinstance(result.source_artifact_id, str) or not result.source_artifact_id.strip():
        raise ValueError("robustness source artifact identity is missing")
    thresholds: list[NormalizedThresholdResult] = []
    if result.neighborhood_summary is not None:
        thresholds.extend(
            NormalizedThresholdResult(
                threshold_id=rule.rule_id,
                status=map_native_status(rule.status),
                observed=rule.observed,
                threshold=rule.threshold,
                reason=rule.message,
            )
            for rule in result.neighborhood_summary.threshold_results
        )
    for regime in result.regime_results:
        thresholds.extend(
            NormalizedThresholdResult(
                threshold_id=f"{regime.regime_id}:{rule.rule_id}",
                status=map_native_status(rule.status),
                observed=rule.observed,
                threshold=rule.threshold,
                reason=rule.message,
            )
            for rule in regime.threshold_results
        )
    return _record(
        stage_identity=stage,
        status=map_native_status(result.status),
        reasons=result.reasons,
        threshold_results=tuple(thresholds),
        source_identity=result.source_artifact_id,
        protected_data_state=protected_data_state,
    )


def normalize_evidence(
    result: object,
    *,
    protected_data_state: object = _DEFAULT_PROTECTED_DATA_STATE,
    walk_forward_rules: WalkForwardWindowRules | None = None,
) -> NormalizedEvidenceRecord:
    """Dispatch a supported native output, returning invalid for all other input."""
    from backtesting.monte_carlo.models import MonteCarloResult
    from backtesting.out_of_sample.models import OutOfSampleResult
    from backtesting.robustness.models import RobustnessResult
    from backtesting.walk_forward.low_frequency import LowFrequencyEvidenceResult
    from backtesting.walk_forward.models import WalkForwardResult

    if isinstance(result, OutOfSampleResult):
        if protected_data_state is _DEFAULT_PROTECTED_DATA_STATE:
            return normalize_out_of_sample_evidence(result)
        return normalize_out_of_sample_evidence(
            result, protected_data_state=protected_data_state
        )
    state = (
        "not_applicable"
        if protected_data_state is _DEFAULT_PROTECTED_DATA_STATE
        else protected_data_state
    )
    if isinstance(result, WalkForwardResult):
        return normalize_walk_forward_evidence(
            result, protected_data_state=state, window_rules=walk_forward_rules
        )
    if isinstance(result, LowFrequencyEvidenceResult):
        return normalize_low_frequency_walk_forward_evidence(
            result, protected_data_state=state
        )
    if isinstance(result, MonteCarloResult):
        return normalize_monte_carlo_evidence(
            result, protected_data_state=state
        )
    if isinstance(result, RobustnessResult):
        return normalize_robustness_evidence(
            result, protected_data_state=state
        )
    return _invalid(
        "unknown_validation_stage",
        f"unsupported validation evidence type: {type(result).__name__}",
        protected_data_state=state,
    )
