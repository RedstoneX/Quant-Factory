"""Shared contracts for research-validation specifications and evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import isfinite
from types import MappingProxyType
from typing import Any, Literal, Mapping


EvidenceStatus = Literal["passed", "failed", "insufficient_evidence", "invalid"]
ProtectedDataState = Literal[
    "not_applicable", "unspent", "gated", "spent", "invalid"
]
WalkForwardTrainingMode = Literal["rolling", "expanding"]
IncompleteWindowPolicy = Literal["drop", "include"]
ThresholdComparison = Literal[">=", "<=", "=="]


def _require_non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _parse_date(name: str, value: str) -> date:
    _require_non_blank(name, value)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date") from exc


@dataclass(frozen=True)
class ValidationPeriod:
    """One inclusive chronological period in the validation plan."""

    start: str
    end: str

    def __post_init__(self) -> None:
        if _parse_date("start", self.start) > _parse_date("end", self.end):
            raise ValueError("period start must not be after end")


@dataclass(frozen=True)
class WalkForwardWindowRules:
    """Portable window rules, independent of a particular engine configuration."""

    training_window_size: int
    selection_window_size: int | None
    test_window_size: int
    step_size: int
    training_mode: WalkForwardTrainingMode
    minimum_rows_per_window: int
    incomplete_final_window: IncompleteWindowPolicy

    def __post_init__(self) -> None:
        integer_fields = {
            "training_window_size": self.training_window_size,
            "test_window_size": self.test_window_size,
            "step_size": self.step_size,
            "minimum_rows_per_window": self.minimum_rows_per_window,
        }
        if self.selection_window_size is not None:
            integer_fields["selection_window_size"] = self.selection_window_size
        for name, value in integer_fields.items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.training_mode not in {"rolling", "expanding"}:
            raise ValueError(f"unsupported training_mode: {self.training_mode}")
        if self.incomplete_final_window not in {"drop", "include"}:
            raise ValueError("incomplete_final_window must be 'drop' or 'include'")
        if self.training_window_size < self.minimum_rows_per_window:
            raise ValueError("training_window_size is below the minimum")
        if self.test_window_size < self.minimum_rows_per_window:
            raise ValueError("test_window_size is below the minimum")
        if (
            self.selection_window_size is not None
            and self.selection_window_size < self.minimum_rows_per_window
        ):
            raise ValueError("selection_window_size is below the minimum")
        if self.step_size < self.test_window_size:
            raise ValueError("step_size must not overlap test windows")


@dataclass(frozen=True)
class ExecutionCostAssumptions:
    """Inline cost assumptions or a stable reference to their source."""

    reference_id: str | None = None
    assumptions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.reference_id is not None:
            _require_non_blank("reference_id", self.reference_id)
        if not isinstance(self.assumptions, Mapping):
            raise TypeError("assumptions must be a mapping")
        if self.reference_id is None and not self.assumptions:
            raise ValueError("execution costs require assumptions or a reference_id")
        object.__setattr__(self, "assumptions", MappingProxyType(dict(self.assumptions)))


@dataclass(frozen=True)
class StageAcceptanceThreshold:
    """One predeclared rule that a validation stage may report against."""

    stage_identity: str
    threshold_id: str
    comparison: ThresholdComparison
    value: float | int

    def __post_init__(self) -> None:
        _require_non_blank("stage_identity", self.stage_identity)
        _require_non_blank("threshold_id", self.threshold_id)
        if self.comparison not in {">=", "<=", "=="}:
            raise ValueError("unsupported threshold comparison")
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not isfinite(float(self.value))
        ):
            raise ValueError("threshold value must be finite")


@dataclass(frozen=True)
class ValidationSpecification:
    """The immutable period, walk-forward, cost, and acceptance contract."""

    train_period: ValidationPeriod
    selection_period: ValidationPeriod
    protected_lockbox_period: ValidationPeriod
    walk_forward_rules: WalkForwardWindowRules
    execution_costs: ExecutionCostAssumptions
    stage_acceptance_thresholds: tuple[StageAcceptanceThreshold, ...]
    protected_data_state: ProtectedDataState = "unspent"

    def __post_init__(self) -> None:
        if self.protected_data_state not in {
            "not_applicable",
            "unspent",
            "gated",
            "spent",
            "invalid",
        }:
            raise ValueError("unsupported protected_data_state")
        train_end = _parse_date("train_period.end", self.train_period.end)
        selection_start = _parse_date("selection_period.start", self.selection_period.start)
        selection_end = _parse_date("selection_period.end", self.selection_period.end)
        lockbox_start = _parse_date(
            "protected_lockbox_period.start", self.protected_lockbox_period.start
        )
        if train_end >= selection_start or selection_end >= lockbox_start:
            raise ValueError("validation periods must be chronological and non-overlapping")
        keys = [
            (threshold.stage_identity, threshold.threshold_id)
            for threshold in self.stage_acceptance_thresholds
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("stage acceptance threshold identities must be unique")


@dataclass(frozen=True)
class NormalizedThresholdResult:
    """A stage threshold rendered with the shared evidence vocabulary."""

    threshold_id: str
    status: EvidenceStatus
    observed: Any = None
    threshold: Any = None
    reason: str = ""

    def __post_init__(self) -> None:
        _require_non_blank("threshold_id", self.threshold_id)
        if self.status not in {"passed", "failed", "insufficient_evidence", "invalid"}:
            raise ValueError("unsupported normalized threshold status")


@dataclass(frozen=True)
class NormalizedEvidenceRecord:
    """A conservative, portable view of one native evidence-stage output."""

    stage_identity: str
    status: EvidenceStatus
    reasons: tuple[str, ...]
    threshold_results: tuple[NormalizedThresholdResult, ...] = ()
    source_identity: str | None = None
    protected_data_state: ProtectedDataState = "not_applicable"

    def __post_init__(self) -> None:
        _require_non_blank("stage_identity", self.stage_identity)
        if self.status not in {"passed", "failed", "insufficient_evidence", "invalid"}:
            raise ValueError("unsupported normalized evidence status")
        if self.protected_data_state not in {
            "not_applicable",
            "unspent",
            "gated",
            "spent",
            "invalid",
        }:
            raise ValueError("unsupported protected_data_state")
        if self.source_identity is not None:
            _require_non_blank("source_identity", self.source_identity)
        if self.status in {"failed", "insufficient_evidence", "invalid"} and not self.reasons:
            raise ValueError("non-passing evidence requires at least one reason")
        if any(not isinstance(reason, str) or not reason.strip() for reason in self.reasons):
            raise ValueError("evidence reasons must be non-blank strings")

    @property
    def eligible_to_progress(self) -> bool:
        """Only a passing record with available protected-data state can progress."""
        return self.status == "passed" and self.protected_data_state in {
            "not_applicable",
            "spent",
        }
