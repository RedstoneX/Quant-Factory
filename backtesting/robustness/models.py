"""Typed contracts for parameter and regime robustness evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import math
from typing import Any, Literal, Mapping

Status = Literal["passed", "failed", "insufficient_evidence", "invalid_input"]
NeighborhoodMethod = Literal["explicit_values", "integer_offsets", "percentage_offsets"]
DegradationMode = Literal["absolute", "relative", "both"]
TrendLabel = Literal["bullish", "bearish", "neutral", "unknown"]
VolatilityLabel = Literal["low_volatility", "high_volatility", "unknown"]


def _non_blank(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")


def _positive_int(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _finite_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class ParameterNeighborhoodDefinition:
    parameter_name: str
    method: NeighborhoodMethod
    explicit_values: tuple[Any, ...] = ()
    integer_offsets: tuple[int, ...] = ()
    percentage_offsets: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        _non_blank("parameter_name", self.parameter_name)
        methods = {
            "explicit_values": self.explicit_values,
            "integer_offsets": self.integer_offsets,
            "percentage_offsets": self.percentage_offsets,
        }
        if self.method not in methods:
            raise ValueError(f"unsupported neighborhood method: {self.method}")
        populated = [name for name, values in methods.items() if values]
        if populated != [self.method]:
            raise ValueError("exactly the selected neighborhood method must be populated")
        if self.method == "integer_offsets":
            if any(not isinstance(value, int) or isinstance(value, bool) for value in self.integer_offsets):
                raise TypeError("integer offsets must be integers, not booleans")
        if self.method == "percentage_offsets":
            for value in self.percentage_offsets:
                _finite_number("percentage offset", value)


@dataclass(frozen=True)
class NeighborhoodConfig:
    definitions: tuple[ParameterNeighborhoodDefinition, ...]
    minimum_valid_neighbors: int = 3
    required_pass_proportion: float = 0.60
    degradation_mode: DegradationMode = "both"
    maximum_absolute_degradation: float = 0.25
    maximum_relative_degradation: float = 0.50

    def __post_init__(self) -> None:
        if not self.definitions:
            raise ValueError("neighborhood definitions must not be empty")
        names = [definition.parameter_name for definition in self.definitions]
        if len(set(names)) != len(names):
            raise ValueError("duplicate parameter neighborhood definitions")
        _positive_int("minimum_valid_neighbors", self.minimum_valid_neighbors)
        _finite_number("required_pass_proportion", self.required_pass_proportion)
        if not 0 <= self.required_pass_proportion <= 1:
            raise ValueError("required_pass_proportion must be between zero and one")
        if self.degradation_mode not in {"absolute", "relative", "both"}:
            raise ValueError("unsupported degradation mode")
        _finite_number("maximum_absolute_degradation", self.maximum_absolute_degradation)
        _finite_number("maximum_relative_degradation", self.maximum_relative_degradation)
        if self.maximum_absolute_degradation < 0 or self.maximum_relative_degradation < 0:
            raise ValueError("degradation thresholds must be non-negative")


@dataclass(frozen=True)
class RegimeConfig:
    trend_window: int = 50
    trend_neutral_tolerance: float = 0.01
    volatility_window: int = 20
    volatility_threshold: float = 0.20
    annualization_factor: float = 252.0
    minimum_observations: int = 20
    minimum_trades: int | None = None

    def __post_init__(self) -> None:
        _positive_int("trend_window", self.trend_window)
        _positive_int("volatility_window", self.volatility_window)
        _positive_int("minimum_observations", self.minimum_observations)
        if self.minimum_trades is not None:
            _positive_int("minimum_trades", self.minimum_trades)
        for name, value in (
            ("trend_neutral_tolerance", self.trend_neutral_tolerance),
            ("volatility_threshold", self.volatility_threshold),
            ("annualization_factor", self.annualization_factor),
        ):
            _finite_number(name, value)
        if self.trend_neutral_tolerance < 0:
            raise ValueError("trend_neutral_tolerance must be non-negative")
        if self.volatility_threshold <= 0 or self.annualization_factor <= 0:
            raise ValueError("volatility threshold and annualization factor must be positive")


@dataclass(frozen=True)
class RobustnessConfig:
    strategy_id: str
    strategy_version: str
    locked_parameters: Mapping[str, Any]
    experiment_id: str
    source_artifact_id: str
    source_start: str
    source_end: str
    data_provenance: Mapping[str, Any]
    execution_assumptions: Mapping[str, Any]
    neighborhood: NeighborhoodConfig
    regimes: RegimeConfig
    maximum_drawdown: float = 0.35
    minimum_return: float = 0.0
    minimum_sharpe: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("strategy_id", self.strategy_id),
            ("strategy_version", self.strategy_version),
            ("experiment_id", self.experiment_id),
            ("source_artifact_id", self.source_artifact_id),
        ):
            _non_blank(name, value)
        if not isinstance(self.locked_parameters, Mapping) or not self.locked_parameters:
            raise TypeError("locked_parameters must be a non-empty mapping")
        if not isinstance(self.data_provenance, Mapping):
            raise TypeError("data_provenance must be a mapping")
        if not isinstance(self.execution_assumptions, Mapping):
            raise TypeError("execution_assumptions must be a mapping")
        try:
            start = date.fromisoformat(self.source_start)
            end = date.fromisoformat(self.source_end)
        except (TypeError, ValueError) as exc:
            raise ValueError("source boundaries must be ISO dates") from exc
        if start > end:
            raise ValueError("source_start must not be after source_end")
        for name, value in (
            ("maximum_drawdown", self.maximum_drawdown),
            ("minimum_return", self.minimum_return),
        ):
            _finite_number(name, value)
        if not 0 <= self.maximum_drawdown <= 1:
            raise ValueError("maximum_drawdown must be between zero and one")
        if self.minimum_sharpe is not None:
            _finite_number("minimum_sharpe", self.minimum_sharpe)


@dataclass(frozen=True)
class CandidateDerivation:
    parameter_name: str
    locked_value: Any
    method: str
    source_value: Any
    raw_value: Any
    normalized_value: Any | None
    status: Literal["accepted", "rejected", "duplicate"]
    rejection_reason: str | None = None
    normalization_created_duplicate: bool = False


@dataclass(frozen=True)
class NeighborhoodCandidate:
    normalized_parameters: dict[str, Any]
    derivations: tuple[CandidateDerivation, ...]
    is_locked_point: bool


@dataclass(frozen=True)
class NeighborhoodConstructionResult:
    requested_candidate_count: int
    raw_derived_count: int
    unique_normalized_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    candidates: tuple[NeighborhoodCandidate, ...]
    rejected_derivations: tuple[CandidateDerivation, ...]


@dataclass(frozen=True)
class ThresholdResult:
    rule_id: str
    status: Status
    observed: float | int | None
    threshold: float | int
    message: str


@dataclass(frozen=True)
class EvaluatedParameterPoint:
    normalized_parameters: dict[str, Any]
    derivations: tuple[CandidateDerivation, ...]
    is_locked_point: bool
    status: Status
    total_return: float
    maximum_drawdown: float
    sharpe_ratio: float | None
    trade_count: int
    screening_status: str
    hygiene_status: str
    absolute_degradation: float
    relative_degradation: float | None
    degradation_unit: str
    degradation_interpretation: str
    threshold_results: tuple[ThresholdResult, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    source_run_identity: str


@dataclass(frozen=True)
class NeighborhoodEvaluation:
    points: tuple[EvaluatedParameterPoint, ...]
    locked_returns: Any
    locked_entries: Any
    source_run_identity: str


@dataclass(frozen=True)
class DimensionStability:
    parameter_name: str
    tested_values: tuple[Any, ...]
    locked_value: Any
    pass_count: int
    return_range: float | None
    drawdown_range: float | None
    behavior: Literal["monotonic", "unstable", "insufficient"]


@dataclass(frozen=True)
class NeighborhoodSummary:
    requested_candidate_count: int
    raw_derived_count: int
    unique_normalized_count: int
    rejected_count: int
    duplicate_count: int
    valid_count: int
    evaluated_count: int
    passing_count: int
    passing_proportion: float
    proportion_within_degradation_limit: float
    median_total_return: float | None
    worst_total_return: float | None
    median_maximum_drawdown: float | None
    worst_maximum_drawdown: float | None
    median_sharpe: float | None
    locked_point_rank: int | None
    locked_point_status: Status
    dimension_stability: tuple[DimensionStability, ...]
    threshold_results: tuple[ThresholdResult, ...]
    status: Status
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RegimeLabelMetadata:
    first_usable_timestamp: str | None
    warmup_observation_count: int
    trend_rule: str
    volatility_rule: str
    annualization_factor: float
    attribution_policy: str


@dataclass(frozen=True)
class RegimeLabels:
    labels: Any
    trend: Any
    volatility: Any
    realized_volatility: Any
    metadata: RegimeLabelMetadata


@dataclass(frozen=True)
class RegimeEvaluationResult:
    regime_id: str
    trend_component: str
    volatility_component: str
    first_timestamp: str | None
    last_timestamp: str | None
    observation_count: int
    trade_count: int | None
    total_return: float | None
    maximum_drawdown: float | None
    sharpe_ratio: float | None
    win_rate: float | None
    minimum_observations: int
    minimum_trades: int | None
    threshold_results: tuple[ThresholdResult, ...]
    status: Status
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SourceLockEvidence:
    status: Status
    artifact_path: str
    artifact_kind: Literal["out_of_sample", "walk_forward", "unknown"]
    artifact_id: str
    schema_version: int | None
    experiment_id: str
    strategy_id: str
    strategy_version: str
    locked_parameters: dict[str, Any] | None
    source_start: str | None
    source_end: str | None
    data_provenance: dict[str, Any]
    execution_assumptions: dict[str, Any]
    metrics: dict[str, float | int]
    reasons: tuple[str, ...]
    parameter_lock_id: str | None = None


@dataclass(frozen=True)
class RobustnessResult:
    schema_version: int
    status: Status
    strategy_id: str
    strategy_version: str
    experiment_id: str
    source_artifact_id: str
    locked_parameters: dict[str, Any]
    data_provenance: dict[str, Any]
    execution_assumptions: dict[str, Any]
    neighborhood_construction: NeighborhoodConstructionResult | None
    parameter_points: tuple[EvaluatedParameterPoint, ...]
    neighborhood_summary: NeighborhoodSummary | None
    regime_metadata: RegimeLabelMetadata | None
    regime_results: tuple[RegimeEvaluationResult, ...]
    component_statuses: dict[str, Status]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
