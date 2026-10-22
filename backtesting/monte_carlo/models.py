"""Typed Monte Carlo stress-test contracts."""
from dataclasses import asdict, dataclass
from typing import Any, Literal
import math

Status = Literal["passed", "failed", "insufficient_evidence", "invalid_input"]
Method = Literal["iid_bootstrap", "path_permutation", "moving_block_bootstrap"]

@dataclass(frozen=True)
class ExecutionCostScenario:
    name: str
    fee_increase: float = 0.0
    slippage_increase: float = 0.0
    execution_price_penalty: float = 0.0
    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("execution stress name must not be blank")
        costs = (self.fee_increase, self.slippage_increase, self.execution_price_penalty)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in costs):
            raise ValueError("execution stress costs must be finite numbers")
        if min(costs) < 0:
            raise ValueError("execution stress name is required and costs must be non-negative")

@dataclass(frozen=True)
class ExecutionStressResult:
    scenario_name: str
    source_observation_type: str
    cost_inputs: dict[str, float]
    translation_method: str | None
    original_cumulative_return: float | None
    stressed_cumulative_return: float | None
    difference: float | None
    status: Literal["applied", "insufficient_evidence"]
    reasons: tuple[str, ...]

@dataclass(frozen=True)
class MonteCarloConfig:
    method: Method = "iid_bootstrap"
    seed: int = 42
    simulation_count: int = 1000
    percentiles: tuple[float, ...] = (5, 25, 50, 75, 95)
    minimum_observations: int = 20
    drawdown_threshold: float = 0.35
    maximum_loss_probability: float = 0.25
    maximum_drawdown_breach_probability: float = 0.10
    lower_percentile: float = 5
    minimum_lower_percentile_return: float = -0.10
    block_length: int | None = None
    annualization_factor: float | None = None
    execution_cost_scenarios: tuple[ExecutionCostScenario, ...] = ()
    persist_paths: bool = False
    def __post_init__(self) -> None:
        if self.method not in {"iid_bootstrap", "path_permutation", "moving_block_bootstrap"}: raise ValueError("unsupported Monte Carlo method")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool): raise TypeError("seed must be int")
        for name, value in (("simulation_count", self.simulation_count), ("minimum_observations", self.minimum_observations)):
            if not isinstance(value, int) or isinstance(value, bool): raise TypeError(f"{name} must be int")
        if self.simulation_count < 1: raise ValueError("simulation_count must be positive")
        if self.minimum_observations < 2: raise ValueError("minimum_observations must be at least 2")
        if not self.percentiles or len(set(self.percentiles)) != len(self.percentiles) or any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0 or p > 100 for p in self.percentiles): raise ValueError("percentiles must be unique finite numbers between 0 and 100")
        thresholds = (self.drawdown_threshold, self.maximum_loss_probability, self.maximum_drawdown_breach_probability, self.minimum_lower_percentile_return, self.lower_percentile)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in thresholds): raise ValueError("thresholds must be finite numbers")
        if self.lower_percentile not in self.percentiles: raise ValueError("lower_percentile must be requested")
        if not 0 <= self.drawdown_threshold <= 1: raise ValueError("drawdown_threshold must be between 0 and 1")
        if not 0 <= self.maximum_loss_probability <= 1 or not 0 <= self.maximum_drawdown_breach_probability <= 1: raise ValueError("probability thresholds must be between 0 and 1")
        if self.method == "moving_block_bootstrap" and (self.block_length is None or self.block_length < 1): raise ValueError("moving block bootstrap requires positive block_length")
        if self.block_length is not None and self.block_length < 1: raise ValueError("block_length must be positive")
        if self.block_length is not None and (not isinstance(self.block_length, int) or isinstance(self.block_length, bool)): raise TypeError("block_length must be int")
        if self.annualization_factor is not None and (isinstance(self.annualization_factor, bool) or not isinstance(self.annualization_factor, (int, float)) or not math.isfinite(self.annualization_factor) or self.annualization_factor <= 0): raise ValueError("annualization_factor must be a positive finite number")

@dataclass(frozen=True)
class SourceSeries:
    source_id: str
    source_kind: Literal["period_returns", "trade_returns", "fold_endpoint_returns"]
    experiment_id: str
    strategy_id: str
    strategy_version: str
    values: tuple[float, ...]
    provenance: dict[str, Any]
    execution_assumptions: dict[str, Any]
    period_frequency: str | None = None
    input_status: Status | None = None
    input_reasons: tuple[str, ...] = ()
    def __post_init__(self) -> None:
        if self.source_kind not in {"period_returns", "trade_returns", "fold_endpoint_returns"}: raise ValueError("invalid source kind")
        if not all(isinstance(v, str) and v.strip() for v in (self.source_id, self.experiment_id, self.strategy_id, self.strategy_version)): raise ValueError("source identity fields must not be blank")
        if not isinstance(self.provenance, dict) or not isinstance(self.execution_assumptions, dict): raise TypeError("provenance and execution assumptions must be dictionaries")

@dataclass(frozen=True)
class ThresholdResult:
    rule_id: str
    passed: bool
    observed: float
    threshold: float
    message: str

@dataclass(frozen=True)
class MonteCarloResult:
    schema_version: int
    status: Status
    source: SourceSeries
    config: MonteCarloConfig
    observation_count: int
    original_metrics: dict[str, float]
    distributions: dict[str, dict[str, float]]
    loss_probability: float | None
    drawdown_breach_probability: float | None
    threshold_results: tuple[ThresholdResult, ...]
    execution_stress: tuple[ExecutionStressResult, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    timestamp: str
    paths: tuple[tuple[float, ...], ...] | None = None
    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        values = payload["source"]["values"]
        if any(not math.isfinite(value) for value in values):
            payload["source"]["values"] = []
            payload["source"]["provenance"] = dict(payload["source"]["provenance"])
            payload["source"]["provenance"]["invalid_source_values_omitted_from_json"] = True
        return payload
