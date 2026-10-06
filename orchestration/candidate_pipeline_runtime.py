"""Generic runtime composition for one approved candidate research pipeline.

The durable launch service owns submission identity, the filter-chain service
owns ordering and replay, and the existing research engines own computation.
This module only supplies the missing production adapters between them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.experiments import ExecutionConfig, ExperimentConfig, execute_experiment
from backtesting.monte_carlo import MonteCarloConfig, SourceSeries, run_monte_carlo
from backtesting.monte_carlo.models import ExecutionCostScenario
from backtesting.out_of_sample import (
    ChronologicalSplitConfig,
    OutOfSampleConfig,
    OutOfSampleProgressionError,
    execute_out_of_sample,
)
from backtesting.robustness import (
    FixedRuleCostStressPlan,
    NeighborhoodConfig,
    ParameterNeighborhoodDefinition,
    RegimeConfig,
    RobustnessConfig,
    build_neighborhood,
    run_fixed_rule_robustness,
    run_robustness_pipeline,
)
from backtesting.screening import ScreeningConfig
from backtesting.validation import WalkForwardWindowRules
from backtesting.walk_forward import WalkForwardConfig, execute_walk_forward
from market_data import MarketDataConfig, load_market_data
from orchestration.candidate_run_service import (
    CandidateRunService,
    CandidateScreeningLaunchResult,
)
from orchestration.candidate_pipeline_contracts import CandidatePipelineLauncher
from orchestration.filter_chain import (
    FactoryFilterChainService,
    FilterChainOutcome,
    FilterChainReplayIncompleteError,
    FilterStageContext,
    PersistedStageReference,
)
from orchestration.research_launch_claims import (
    CANDIDATE_SCREENING_LAUNCH_CONTRACT,
    DurableResearchLaunchService,
)
from persistence import (
    ArtifactType,
    EventSeverity,
    PersistenceService,
    RunEventType,
    RunStage,
    RunStatus,
    canonical_json,
)
from backtesting.validation.evidence_service import ValidationEvidenceArtifactService
from persistence.models import ResearchLaunchOperation, ResearchRunSubmissionRecord
from persistence.service import (
    RUNTIME_LINEAGE_ENVIRONMENT_KEY,
    capture_runtime_lineage_document,
    configuration_document_from_experiment_config,
)
from strategies import get_strategy


VALIDATION_RUNTIME_KEY = "candidate_validation_runtime"


def _artifact_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def _artifact_records(frame: pd.DataFrame, *, price_multiplier: float = 1.0) -> list[dict[str, Any]]:
    rows = [{str(key): _artifact_value(value) for key, value in row.items()}
            for row in frame.to_dict(orient="records")]
    if price_multiplier != 1.0:
        for row in rows:
            for key, value in row.items():
                if "price" in key.lower() and isinstance(value, Real) and not isinstance(value, bool):
                    row[key] = float(value) / price_multiplier
    return rows


def _screening_artifacts(*, result: Any, portfolio: Any, data: pd.DataFrame,
                         config: ExperimentConfig, parameter_row_id: str) -> tuple[tuple[ArtifactType, str, dict[str, Any]], ...]:
    """Serialize the screened portfolio itself, never a second simulation."""
    if len(result.ranked_results) != 1:
        raise RuntimeError("single-configuration screening must produce one ranked row")
    row = result.ranked_results.iloc[0]
    if row["parameter_row_id"] != parameter_row_id:
        raise RuntimeError("screening portfolio does not match the ranked parameter row")
    trades = portfolio.trades.records_readable
    orders = portfolio.orders.records_readable
    recorded = row["number_of_trades"]
    if not isinstance(recorded, Real) or isinstance(recorded, bool) or not math.isfinite(float(recorded)) or float(recorded) != len(trades):
        raise RuntimeError("ranked trade count does not match the actual trade ledger")
    metrics = {key: _artifact_value(row[key]) for key in (
        "total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
        "number_of_trades", "win_rate")}
    multiplier = config.execution.price_multiplier
    price_unit = "index_points" if multiplier != 1.0 else "currency"
    value = portfolio.value
    if isinstance(value, pd.DataFrame):
        if value.shape[1] != 1:
            raise RuntimeError("expected one-column portfolio equity series")
        value = value.iloc[:, 0]
    return (
        (ArtifactType.RUN_SUMMARY, "run_summary", {
            "strategy_id": result.strategy_id, "strategy_version": result.strategy_version,
            "selected_parameter_row_id": parameter_row_id, "selected_ranking_position": 1,
            "evidence_classification": "Development screening evidence only; not independent, protected, or edge proof",
            "promotion_eligible": False, "broker_orders": "disabled",
        }),
        (ArtifactType.METRICS, "metrics", {
            "parameter_row_id": parameter_row_id, "ranking_position": 1, "metrics": metrics,
        }),
        (ArtifactType.TRADES_OR_ORDERS, "trades_and_orders", {
            "parameter_row_id": parameter_row_id, "ranking_position": 1,
            "instrument": config.market_data.symbol, "price_unit": price_unit,
            "pnl_unit": "USD", "price_multiplier": multiplier,
            "price_normalization": "Trade and order price fields are divided by the execution multiplier for display against source bars; monetary fields are unchanged.",
            "trades": _artifact_records(trades, price_multiplier=multiplier),
            "orders": _artifact_records(orders, price_multiplier=multiplier),
        }),
        (ArtifactType.EQUITY_CURVE, "equity_curve", {
            "parameter_row_id": parameter_row_id, "ranking_position": 1,
            "equity_curve": [{"timestamp": _artifact_value(index), "value": _artifact_value(item)} for index, item in value.items()],
            "price_series": [{"timestamp": _artifact_value(index),
                              **{key.lower(): _artifact_value(item[key]) for key in ("Open", "High", "Low", "Close")}}
                             for index, item in data[["Open", "High", "Low", "Close"]].iterrows()],
            "benchmark_omission": "No benchmark was declared for this bounded screening run.",
        }),
    )


def _strict_object(
    value: Any,
    *,
    path: str,
    keys: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    actual = set(value)
    missing = sorted(keys - actual)
    extra = sorted(actual - keys)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {missing}")
        if extra:
            details.append(f"unexpected {extra}")
        raise ValueError(f"{path} has invalid fields: {', '.join(details)}")
    return value


def _strict_list(value: Any, *, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _strict_text(value: Any, *, path: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be text")
    return value


def _strict_bool(value: Any, *, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _strict_int(value: Any, *, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{path} must be an integer")
    return value


def _strict_number(value: Any, *, path: str) -> float | int:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{path} must be numeric")
    return value


def _optional_number(value: Any, *, path: str) -> float | int | None:
    return None if value is None else _strict_number(value, path=path)


def _optional_int(value: Any, *, path: str) -> int | None:
    return None if value is None else _strict_int(value, path=path)


def _optional_text(value: Any, *, path: str) -> str | None:
    return None if value is None else _strict_text(value, path=path)


@dataclass(frozen=True)
class CandidateValidationPlan:
    """Fixed, serializable boundaries for the existing validation engines."""

    out_of_sample_split: ChronologicalSplitConfig
    out_of_sample_shortlist_size: int
    walk_forward_rules: WalkForwardWindowRules
    walk_forward_shortlist_size: int
    robustness_neighborhood: NeighborhoodConfig | None
    robustness_regimes: RegimeConfig
    robustness_maximum_drawdown: float
    robustness_minimum_return: float
    robustness_minimum_sharpe: float | None
    monte_carlo: MonteCarloConfig
    data_as_of: str | None = None
    fixed_rule_cost_stress: FixedRuleCostStressPlan | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("out_of_sample_shortlist_size", self.out_of_sample_shortlist_size),
            ("walk_forward_shortlist_size", self.walk_forward_shortlist_size),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.data_as_of is not None:
            timestamp = pd.Timestamp(self.data_as_of)
            if timestamp.tzinfo is None:
                raise ValueError("data_as_of must include a timezone")
        if (self.robustness_neighborhood is None) != (self.fixed_rule_cost_stress is not None):
            raise ValueError("fixed-rule cost stress must replace, not accompany, parameter variation")

    def document(self) -> dict[str, Any]:
        return {
            "out_of_sample": {
                "split": asdict(self.out_of_sample_split),
                "shortlist_size": self.out_of_sample_shortlist_size,
            },
            "walk_forward": {
                "rules": asdict(self.walk_forward_rules),
                "shortlist_size": self.walk_forward_shortlist_size,
            },
            "robustness": {
                "neighborhood": asdict(self.robustness_neighborhood) if self.robustness_neighborhood is not None else None,
                "regimes": asdict(self.robustness_regimes),
                "maximum_drawdown": self.robustness_maximum_drawdown,
                "minimum_return": self.robustness_minimum_return,
                "minimum_sharpe": self.robustness_minimum_sharpe,
                **({"fixed_rule_cost_stress": asdict(self.fixed_rule_cost_stress)} if self.fixed_rule_cost_stress is not None else {}),
            },
            "monte_carlo": asdict(self.monte_carlo),
            "data_as_of": self.data_as_of,
            "protected_data_state": "gated",
        }


@dataclass(frozen=True)
class CandidatePipelineDefinition:
    """One approved experiment and its fixed generic validation boundaries."""

    experiment: ExperimentConfig
    strategy_version: str
    validation: CandidateValidationPlan

    def configuration_document(self) -> dict[str, Any]:
        document = configuration_document_from_experiment_config(
            self.experiment,
            strategy_version=self.strategy_version,
        )
        document[VALIDATION_RUNTIME_KEY] = self.validation.document()
        return document

    @classmethod
    def from_configuration_document(
        cls,
        document: dict[str, Any],
        *,
        output_path: str | Path = "candidate-pipeline-runtime-output.csv",
    ) -> "CandidatePipelineDefinition":
        """Rebuild the exact typed runtime definition from one durable document.

        Persisted configuration is executable authority, so this parser accepts
        only the complete current contract.  It deliberately does not coerce
        strings, booleans, or numbers, and proves that typed reconstruction
        serializes back to the byte-equivalent canonical document.
        """

        root = _strict_object(
            document,
            path="candidate configuration",
            keys={
                "experiment_id",
                "strategy_id",
                "strategy_version",
                "market_data",
                "parameters",
                "execution",
                "ranking",
                "screening",
                VALIDATION_RUNTIME_KEY,
            },
        )
        strategy_id = _strict_text(root["strategy_id"], path="strategy_id")
        strategy_version = _strict_text(
            root["strategy_version"], path="strategy_version"
        )
        try:
            installed_strategy = get_strategy(strategy_id)
        except KeyError as exc:
            raise ValueError(
                f"candidate configuration references unavailable strategy {strategy_id}"
            ) from exc
        installed_version = installed_strategy.spec.identity.version
        if installed_version != strategy_version:
            raise ValueError(
                "candidate configuration strategy version does not match the "
                f"installed strategy: {strategy_version} != {installed_version}"
            )

        market_document = _strict_object(
            root["market_data"],
            path="market_data",
            keys=set(MarketDataConfig.__dataclass_fields__),
        )
        market_data = MarketDataConfig(
            symbol=_strict_text(market_document["symbol"], path="market_data.symbol"),
            provider=_strict_text(
                market_document["provider"], path="market_data.provider"
            ),
            provider_implementation=_strict_text(
                market_document["provider_implementation"],
                path="market_data.provider_implementation",
            ),
            interval=_strict_text(
                market_document["interval"], path="market_data.interval"
            ),
            requested_start=_strict_text(
                market_document["requested_start"], path="market_data.requested_start"
            ),
            end_date_policy=_strict_text(
                market_document["end_date_policy"], path="market_data.end_date_policy"
            ),
            adjusted=_strict_bool(
                market_document["adjusted"], path="market_data.adjusted"
            ),
            exchange_calendar=_strict_text(
                market_document["exchange_calendar"],
                path="market_data.exchange_calendar",
            ),
            market_timezone=_strict_text(
                market_document["market_timezone"], path="market_data.market_timezone"
            ),
            cache_path=Path(
                _strict_text(
                    market_document["cache_path"], path="market_data.cache_path"
                )
            ),
            legacy_cache_paths=tuple(
                Path(_strict_text(item, path=f"market_data.legacy_cache_paths[{index}]"))
                for index, item in enumerate(
                    _strict_list(
                        market_document["legacy_cache_paths"],
                        path="market_data.legacy_cache_paths",
                    )
                )
            ),
            cache_schema_version=_strict_int(
                market_document["cache_schema_version"],
                path="market_data.cache_schema_version",
            ),
        )

        execution_document = _strict_object(
            root["execution"],
            path="execution",
            keys=set(ExecutionConfig.__dataclass_fields__),
        )
        execution = ExecutionConfig(
            mode=_strict_text(execution_document["mode"], path="execution.mode"),
            signal_timing=_strict_text(
                execution_document["signal_timing"], path="execution.signal_timing"
            ),
            execution_price_field=_strict_text(
                execution_document["execution_price_field"],
                path="execution.execution_price_field",
            ),
            initial_cash=_strict_number(
                execution_document["initial_cash"], path="execution.initial_cash"
            ),
            fees=_strict_number(execution_document["fees"], path="execution.fees"),
            slippage=_strict_number(
                execution_document["slippage"], path="execution.slippage"
            ),
            position_sizing=_strict_text(
                execution_document["position_sizing"], path="execution.position_sizing"
            ),
            direction=_strict_text(
                execution_document["direction"], path="execution.direction"
            ),
            leverage=_strict_number(
                execution_document["leverage"], path="execution.leverage"
            ),
            accumulate=_strict_bool(
                execution_document["accumulate"], path="execution.accumulate"
            ),
            order_size=_strict_number(
                execution_document["order_size"], path="execution.order_size"
            ),
            price_multiplier=_strict_number(
                execution_document["price_multiplier"],
                path="execution.price_multiplier",
            ),
            fixed_fee_per_contract_per_side=_strict_number(
                execution_document["fixed_fee_per_contract_per_side"],
                path="execution.fixed_fee_per_contract_per_side",
            ),
            slippage_points=_strict_number(
                execution_document["slippage_points"],
                path="execution.slippage_points",
            ),
            slippage_ticks=_strict_number(
                execution_document["slippage_ticks"], path="execution.slippage_ticks"
            ),
            tick_size=_optional_number(
                execution_document["tick_size"], path="execution.tick_size"
            ),
        )

        parameters = tuple(
            _strict_object(
                item,
                path=f"parameters[{index}]",
                keys=set(item) if isinstance(item, dict) else set(),
            )
            for index, item in enumerate(
                _strict_list(root["parameters"], path="parameters")
            )
        )
        ranking_document = _strict_object(
            root["ranking"],
            path="ranking",
            keys={"columns", "ascending", "parameter_output_names"},
        )
        ranking_columns = tuple(
            _strict_text(item, path=f"ranking.columns[{index}]")
            for index, item in enumerate(
                _strict_list(ranking_document["columns"], path="ranking.columns")
            )
        )
        ranking_ascending = tuple(
            _strict_bool(item, path=f"ranking.ascending[{index}]")
            for index, item in enumerate(
                _strict_list(ranking_document["ascending"], path="ranking.ascending")
            )
        )
        output_names: list[tuple[str, str]] = []
        for index, item in enumerate(
            _strict_list(
                ranking_document["parameter_output_names"],
                path="ranking.parameter_output_names",
            )
        ):
            pair = _strict_list(item, path=f"ranking.parameter_output_names[{index}]")
            if len(pair) != 2:
                raise ValueError(
                    f"ranking.parameter_output_names[{index}] must contain two names"
                )
            output_names.append(
                (
                    _strict_text(
                        pair[0], path=f"ranking.parameter_output_names[{index}][0]"
                    ),
                    _strict_text(
                        pair[1], path=f"ranking.parameter_output_names[{index}][1]"
                    ),
                )
            )

        screening_document = _strict_object(
            root["screening"],
            path="screening",
            keys=set(ScreeningConfig.__dataclass_fields__),
        )
        screening = ScreeningConfig(
            minimum_trades=_strict_int(
                screening_document["minimum_trades"], path="screening.minimum_trades"
            ),
            minimum_total_return=_strict_number(
                screening_document["minimum_total_return"],
                path="screening.minimum_total_return",
            ),
            minimum_annualized_return=_strict_number(
                screening_document["minimum_annualized_return"],
                path="screening.minimum_annualized_return",
            ),
            minimum_sharpe_ratio=_strict_number(
                screening_document["minimum_sharpe_ratio"],
                path="screening.minimum_sharpe_ratio",
            ),
            maximum_drawdown=_strict_number(
                screening_document["maximum_drawdown"],
                path="screening.maximum_drawdown",
            ),
            minimum_win_rate=_optional_number(
                screening_document["minimum_win_rate"],
                path="screening.minimum_win_rate",
            ),
        )

        validation_document = _strict_object(
            root[VALIDATION_RUNTIME_KEY],
            path=VALIDATION_RUNTIME_KEY,
            keys={
                "out_of_sample",
                "walk_forward",
                "robustness",
                "monte_carlo",
                "data_as_of",
                "protected_data_state",
            },
        )
        if validation_document["protected_data_state"] != "gated":
            raise ValueError("candidate validation protected_data_state must be gated")
        oos_document = _strict_object(
            validation_document["out_of_sample"],
            path=f"{VALIDATION_RUNTIME_KEY}.out_of_sample",
            keys={"split", "shortlist_size"},
        )
        split_document = _strict_object(
            oos_document["split"],
            path=f"{VALIDATION_RUNTIME_KEY}.out_of_sample.split",
            keys=set(ChronologicalSplitConfig.__dataclass_fields__),
        )
        split = ChronologicalSplitConfig(
            train_fraction=_strict_number(
                split_document["train_fraction"], path="out_of_sample.split.train_fraction"
            ),
            selection_fraction=_strict_number(
                split_document["selection_fraction"],
                path="out_of_sample.split.selection_fraction",
            ),
            test_fraction=_strict_number(
                split_document["test_fraction"], path="out_of_sample.split.test_fraction"
            ),
            minimum_rows_per_partition=_strict_int(
                split_document["minimum_rows_per_partition"],
                path="out_of_sample.split.minimum_rows_per_partition",
            ),
        )

        walk_document = _strict_object(
            validation_document["walk_forward"],
            path=f"{VALIDATION_RUNTIME_KEY}.walk_forward",
            keys={"rules", "shortlist_size"},
        )
        rules_document = _strict_object(
            walk_document["rules"],
            path=f"{VALIDATION_RUNTIME_KEY}.walk_forward.rules",
            keys=set(WalkForwardWindowRules.__dataclass_fields__),
        )
        walk_rules = WalkForwardWindowRules(
            training_window_size=_strict_int(
                rules_document["training_window_size"],
                path="walk_forward.rules.training_window_size",
            ),
            selection_window_size=_optional_int(
                rules_document["selection_window_size"],
                path="walk_forward.rules.selection_window_size",
            ),
            test_window_size=_strict_int(
                rules_document["test_window_size"],
                path="walk_forward.rules.test_window_size",
            ),
            step_size=_strict_int(
                rules_document["step_size"], path="walk_forward.rules.step_size"
            ),
            training_mode=_strict_text(
                rules_document["training_mode"],
                path="walk_forward.rules.training_mode",
            ),
            minimum_rows_per_window=_strict_int(
                rules_document["minimum_rows_per_window"],
                path="walk_forward.rules.minimum_rows_per_window",
            ),
            incomplete_final_window=_strict_text(
                rules_document["incomplete_final_window"],
                path="walk_forward.rules.incomplete_final_window",
            ),
        )

        robustness_document = _strict_object(
            validation_document["robustness"],
            path=f"{VALIDATION_RUNTIME_KEY}.robustness",
            keys={
                "neighborhood",
                "regimes",
                "maximum_drawdown",
                "minimum_return",
                "minimum_sharpe",
            } | ({"fixed_rule_cost_stress"} if "fixed_rule_cost_stress" in validation_document["robustness"] else set()),
        )
        neighborhood_document = (
            None
            if robustness_document["neighborhood"] is None
            else _strict_object(
                robustness_document["neighborhood"],
                path=f"{VALIDATION_RUNTIME_KEY}.robustness.neighborhood",
                keys=set(NeighborhoodConfig.__dataclass_fields__),
            )
        )
        definitions = []
        for index, item in enumerate(
            [] if neighborhood_document is None else _strict_list(
                neighborhood_document["definitions"],
                path="robustness.neighborhood.definitions",
            )
        ):
            definition_document = _strict_object(
                item,
                path=f"robustness.neighborhood.definitions[{index}]",
                keys=set(ParameterNeighborhoodDefinition.__dataclass_fields__),
            )
            definitions.append(
                ParameterNeighborhoodDefinition(
                    parameter_name=_strict_text(
                        definition_document["parameter_name"],
                        path=f"robustness.neighborhood.definitions[{index}].parameter_name",
                    ),
                    method=_strict_text(
                        definition_document["method"],
                        path=f"robustness.neighborhood.definitions[{index}].method",
                    ),
                    explicit_values=tuple(
                        _strict_list(
                            definition_document["explicit_values"],
                            path=f"robustness.neighborhood.definitions[{index}].explicit_values",
                        )
                    ),
                    integer_offsets=tuple(
                        _strict_int(
                            value,
                            path=f"robustness.neighborhood.definitions[{index}].integer_offsets[{offset_index}]",
                        )
                        for offset_index, value in enumerate(
                            _strict_list(
                                definition_document["integer_offsets"],
                                path=f"robustness.neighborhood.definitions[{index}].integer_offsets",
                            )
                        )
                    ),
                    percentage_offsets=tuple(
                        _strict_number(
                            value,
                            path=f"robustness.neighborhood.definitions[{index}].percentage_offsets[{offset_index}]",
                        )
                        for offset_index, value in enumerate(
                            _strict_list(
                                definition_document["percentage_offsets"],
                                path=f"robustness.neighborhood.definitions[{index}].percentage_offsets",
                            )
                        )
                    ),
                )
            )
        neighborhood = None if neighborhood_document is None else NeighborhoodConfig(
            definitions=tuple(definitions),
            minimum_valid_neighbors=_strict_int(
                neighborhood_document["minimum_valid_neighbors"],
                path="robustness.neighborhood.minimum_valid_neighbors",
            ),
            required_pass_proportion=_strict_number(
                neighborhood_document["required_pass_proportion"],
                path="robustness.neighborhood.required_pass_proportion",
            ),
            degradation_mode=_strict_text(
                neighborhood_document["degradation_mode"],
                path="robustness.neighborhood.degradation_mode",
            ),
            maximum_absolute_degradation=_strict_number(
                neighborhood_document["maximum_absolute_degradation"],
                path="robustness.neighborhood.maximum_absolute_degradation",
            ),
            maximum_relative_degradation=_strict_number(
                neighborhood_document["maximum_relative_degradation"],
                path="robustness.neighborhood.maximum_relative_degradation",
            ),
        )
        stress_document = robustness_document.get("fixed_rule_cost_stress")
        stress = None if stress_document is None else FixedRuleCostStressPlan(**_strict_object(
            stress_document,
            path="robustness.fixed_rule_cost_stress",
            keys=set(FixedRuleCostStressPlan.__dataclass_fields__),
        ))
        if stress is not None and (installed_strategy.spec.parameters or parameters != ({},)):
            raise ValueError("fixed-rule cost stress requires one parameter-free Candidate")
        regimes_document = _strict_object(
            robustness_document["regimes"],
            path=f"{VALIDATION_RUNTIME_KEY}.robustness.regimes",
            keys=set(RegimeConfig.__dataclass_fields__),
        )
        regimes = RegimeConfig(
            trend_window=_strict_int(
                regimes_document["trend_window"], path="robustness.regimes.trend_window"
            ),
            trend_neutral_tolerance=_strict_number(
                regimes_document["trend_neutral_tolerance"],
                path="robustness.regimes.trend_neutral_tolerance",
            ),
            volatility_window=_strict_int(
                regimes_document["volatility_window"],
                path="robustness.regimes.volatility_window",
            ),
            volatility_threshold=_strict_number(
                regimes_document["volatility_threshold"],
                path="robustness.regimes.volatility_threshold",
            ),
            annualization_factor=_strict_number(
                regimes_document["annualization_factor"],
                path="robustness.regimes.annualization_factor",
            ),
            minimum_observations=_strict_int(
                regimes_document["minimum_observations"],
                path="robustness.regimes.minimum_observations",
            ),
            minimum_trades=_optional_int(
                regimes_document["minimum_trades"],
                path="robustness.regimes.minimum_trades",
            ),
        )

        monte_document = _strict_object(
            validation_document["monte_carlo"],
            path=f"{VALIDATION_RUNTIME_KEY}.monte_carlo",
            keys=set(MonteCarloConfig.__dataclass_fields__),
        )
        scenarios = []
        for index, item in enumerate(
            _strict_list(
                monte_document["execution_cost_scenarios"],
                path="monte_carlo.execution_cost_scenarios",
            )
        ):
            scenario = _strict_object(
                item,
                path=f"monte_carlo.execution_cost_scenarios[{index}]",
                keys=set(ExecutionCostScenario.__dataclass_fields__),
            )
            scenarios.append(
                ExecutionCostScenario(
                    name=_strict_text(
                        scenario["name"],
                        path=f"monte_carlo.execution_cost_scenarios[{index}].name",
                    ),
                    fee_increase=_strict_number(
                        scenario["fee_increase"],
                        path=f"monte_carlo.execution_cost_scenarios[{index}].fee_increase",
                    ),
                    slippage_increase=_strict_number(
                        scenario["slippage_increase"],
                        path=f"monte_carlo.execution_cost_scenarios[{index}].slippage_increase",
                    ),
                    execution_price_penalty=_strict_number(
                        scenario["execution_price_penalty"],
                        path=f"monte_carlo.execution_cost_scenarios[{index}].execution_price_penalty",
                    ),
                )
            )
        monte_carlo = MonteCarloConfig(
            method=_strict_text(monte_document["method"], path="monte_carlo.method"),
            seed=_strict_int(monte_document["seed"], path="monte_carlo.seed"),
            simulation_count=_strict_int(
                monte_document["simulation_count"], path="monte_carlo.simulation_count"
            ),
            percentiles=tuple(
                _strict_number(value, path=f"monte_carlo.percentiles[{index}]")
                for index, value in enumerate(
                    _strict_list(monte_document["percentiles"], path="monte_carlo.percentiles")
                )
            ),
            minimum_observations=_strict_int(
                monte_document["minimum_observations"],
                path="monte_carlo.minimum_observations",
            ),
            drawdown_threshold=_strict_number(
                monte_document["drawdown_threshold"], path="monte_carlo.drawdown_threshold"
            ),
            maximum_loss_probability=_strict_number(
                monte_document["maximum_loss_probability"],
                path="monte_carlo.maximum_loss_probability",
            ),
            maximum_drawdown_breach_probability=_strict_number(
                monte_document["maximum_drawdown_breach_probability"],
                path="monte_carlo.maximum_drawdown_breach_probability",
            ),
            lower_percentile=_strict_number(
                monte_document["lower_percentile"], path="monte_carlo.lower_percentile"
            ),
            minimum_lower_percentile_return=_strict_number(
                monte_document["minimum_lower_percentile_return"],
                path="monte_carlo.minimum_lower_percentile_return",
            ),
            block_length=_optional_int(
                monte_document["block_length"], path="monte_carlo.block_length"
            ),
            annualization_factor=_optional_number(
                monte_document["annualization_factor"],
                path="monte_carlo.annualization_factor",
            ),
            execution_cost_scenarios=tuple(scenarios),
            persist_paths=_strict_bool(
                monte_document["persist_paths"], path="monte_carlo.persist_paths"
            ),
        )

        result = cls(
            experiment=ExperimentConfig(
                experiment_id=_strict_text(
                    root["experiment_id"], path="experiment_id"
                ),
                strategy_id=strategy_id,
                parameter_combinations=parameters,
                market_data=market_data,
                execution=execution,
                ranking_columns=ranking_columns,
                ranking_ascending=ranking_ascending,
                output_path=Path(output_path),
                screening=screening,
                parameter_output_names=tuple(output_names),
            ),
            strategy_version=strategy_version,
            validation=CandidateValidationPlan(
                out_of_sample_split=split,
                out_of_sample_shortlist_size=_strict_int(
                    oos_document["shortlist_size"],
                    path="out_of_sample.shortlist_size",
                ),
                walk_forward_rules=walk_rules,
                walk_forward_shortlist_size=_strict_int(
                    walk_document["shortlist_size"],
                    path="walk_forward.shortlist_size",
                ),
                robustness_neighborhood=neighborhood,
                robustness_regimes=regimes,
                robustness_maximum_drawdown=_strict_number(
                    robustness_document["maximum_drawdown"],
                    path="robustness.maximum_drawdown",
                ),
                robustness_minimum_return=_strict_number(
                    robustness_document["minimum_return"],
                    path="robustness.minimum_return",
                ),
                robustness_minimum_sharpe=_optional_number(
                    robustness_document["minimum_sharpe"],
                    path="robustness.minimum_sharpe",
                ),
                monte_carlo=monte_carlo,
                data_as_of=_optional_text(
                    validation_document["data_as_of"], path="validation.data_as_of"
                ),
                fixed_rule_cost_stress=stress,
            ),
        )
        if canonical_json(result.configuration_document()) != canonical_json(document):
            raise ValueError(
                "candidate configuration did not survive exact canonical typed round trip"
            )
        return result


@dataclass(frozen=True)
class CandidatePipelineLaunchResult:
    launch: CandidateScreeningLaunchResult
    chain: FilterChainOutcome


class CandidatePipelineReplayIncompleteError(RuntimeError):
    """An acknowledged launch lacks a complete, safely reopenable chain."""


class CandidatePipelineRuntime:
    """Compose the existing durable launch, runners, evidence, and coordinator."""

    def __init__(
        self,
        *,
        database: str | Path,
        artifact_root: str | Path,
        configuration_id: str,
        definition: CandidatePipelineDefinition,
        pipeline_launcher: CandidatePipelineLauncher,
        dispatcher_instance_id: str | None = None,
        cache_only: bool = False,
    ) -> None:
        if not isinstance(cache_only, bool):
            raise ValueError("cache_only must be a boolean")
        self.database = Path(database)
        self.artifact_root = Path(artifact_root)
        self.configuration_id = configuration_id
        self.definition = definition
        self.pipeline_launcher = pipeline_launcher
        self.dispatcher_instance_id = dispatcher_instance_id
        self.cache_only = cache_only

    @classmethod
    def from_saved_configuration(
        cls,
        *,
        database: str | Path,
        artifact_root: str | Path,
        configuration_id: str,
        pipeline_launcher: CandidatePipelineLauncher,
        dispatcher_instance_id: str | None = None,
        cache_only: bool = True,
    ) -> "CandidatePipelineRuntime":
        """Build the dashboard runtime from the immutable saved configuration.

        Dashboard construction is cache-only by default so a click cannot
        silently create a paid or external data acquisition side effect.
        """

        persistence = PersistenceService(database)
        try:
            configuration = persistence.configurations.get(configuration_id)
            if configuration is None:
                raise KeyError(
                    f"unknown approved candidate configuration {configuration_id}"
                )
            try:
                document = json.loads(configuration.canonical_config_json)
            except json.JSONDecodeError as exc:
                raise ValueError("saved candidate configuration is invalid JSON") from exc
            if (
                not isinstance(document, dict)
                or canonical_json(document) != configuration.canonical_config_json
            ):
                raise ValueError("saved candidate configuration is not canonical")
            if (
                hashlib.sha256(
                    configuration.canonical_config_json.encode("utf-8")
                ).hexdigest()
                != configuration.config_hash
            ):
                raise ValueError("saved candidate configuration failed its hash check")
            definition = CandidatePipelineDefinition.from_configuration_document(
                document,
                output_path=Path(artifact_root) / "screening-output.csv",
            )
            if (
                definition.experiment.strategy_id != configuration.strategy_id
                or definition.strategy_version != configuration.strategy_version
            ):
                raise ValueError(
                    "saved candidate configuration metadata does not match its document"
                )
        finally:
            persistence.close()
        return cls(
            database=database,
            artifact_root=artifact_root,
            configuration_id=configuration_id,
            definition=definition,
            pipeline_launcher=pipeline_launcher,
            dispatcher_instance_id=dispatcher_instance_id,
            cache_only=cache_only,
        )

    def launch(
        self,
        *,
        idempotency_key: str,
        operation: ResearchLaunchOperation = ResearchLaunchOperation.RUN_TEST,
        source_run_id: str | None = None,
        source_lineage: Mapping[str, str] | None = None,
    ) -> CandidatePipelineLaunchResult:
        service = CandidateRunService(
            database=self.database,
            screening_adapter=self._dispatch_adapter,
            dispatcher_instance_id=self.dispatcher_instance_id,
        )
        launch = service.launch_screening(
            idempotency_key=idempotency_key,
            configuration_id=self._configuration_id(),
            environment={
                "candidate_pipeline_runtime": "generic_v1",
                RUNTIME_LINEAGE_ENVIRONMENT_KEY: capture_runtime_lineage_document(),
            },
            operation=operation,
            source_run_id=source_run_id,
            source_lineage=source_lineage,
        )
        if launch.dispatch.invoked:
            chain = launch.dispatch.value
            if not isinstance(chain, FilterChainOutcome):
                raise RuntimeError("candidate pipeline flow returned no filter-chain outcome")
        else:
            chain = self._reopen_completed_chain(launch.claim.run.run_id)
        return CandidatePipelineLaunchResult(launch=launch, chain=chain)

    def _configuration_id(self) -> str:
        expected = canonical_json(self.definition.configuration_document())
        persistence = PersistenceService(self.database)
        try:
            configuration = persistence.configurations.get(self.configuration_id)
            if configuration is None:
                raise KeyError(
                    f"unknown approved candidate configuration {self.configuration_id}"
                )
            if configuration.canonical_config_json != expected:
                raise ValueError(
                    "runtime definition differs from the approved candidate configuration"
                )
            return configuration.configuration_id
        finally:
            persistence.close()

    def _dispatch_adapter(
        self,
        submission: ResearchRunSubmissionRecord,
        _claims: DurableResearchLaunchService,
    ) -> FilterChainOutcome:
        return self.pipeline_launcher(runtime=self, submission=submission)

    def execute_flow(
        self,
        *,
        submission: ResearchRunSubmissionRecord,
        prefect_flow_run_id: str,
    ) -> FilterChainOutcome:
        claims = DurableResearchLaunchService(
            database=self.database,
            launch_contract=CANDIDATE_SCREENING_LAUNCH_CONTRACT,
            initialize_schema=False,
        )
        claims.bind_prefect_identity(
            idempotency_key=submission.idempotency_key,
            run_id=submission.run_id,
            configuration_id=submission.configuration_id,
            canonical_request_json=submission.canonical_request_json,
            request_fingerprint=submission.request_fingerprint,
            prefect_flow_run_id=prefect_flow_run_id,
        )

        persistence = PersistenceService(self.database)
        try:
            try:
                execution_document = self._validate_saved_configuration(
                    persistence,
                    submission.configuration_id,
                )
                market = load_market_data(
                    self.definition.experiment.market_data,
                    now=(
                        pd.Timestamp(self.definition.validation.data_as_of)
                        if self.definition.validation.data_as_of is not None
                        else None
                    ),
                    allow_download=not self.cache_only,
                )
                captured_portfolios: dict[str, Any] = {}
                screening_result = execute_experiment(
                    self.definition.experiment,
                    market.data,
                    market.audit,
                    write_output=False,
                    portfolio_observer=(
                        (lambda row_id, portfolio: captured_portfolios.setdefault(row_id, portfolio))
                        if len(self.definition.experiment.parameter_combinations) == 1
                        else None
                    ),
                )
                persistence.persist_experiment_inputs_on_run(
                    run_id=submission.run_id,
                    config=self.definition.experiment,
                    result=screening_result,
                    execution_assumptions=execution_document,
                    include_parameter_results=True,
                )
                if captured_portfolios:
                    if len(captured_portfolios) != 1:
                        raise RuntimeError("single-configuration screening captured multiple portfolios")
                    row_id, portfolio = next(iter(captured_portfolios.items()))
                    for artifact_type, logical_name, document in _screening_artifacts(
                        result=screening_result, portfolio=portfolio, data=market.data,
                        config=self.definition.experiment, parameter_row_id=row_id,
                    ):
                        relative_path = f"state/artifacts/{submission.run_id}/{logical_name}.json"
                        destination = self.artifact_root / relative_path
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        content = (canonical_json(document) + "\n").encode("utf-8")
                        staging = destination.with_suffix(".json.tmp")
                        staging.write_bytes(content)
                        staging.replace(destination)
                        persistence.register_artifact(
                            run_id=submission.run_id, artifact_type=artifact_type,
                            logical_name=logical_name, media_type="application/json",
                            format="json", location=relative_path, content=content,
                        )
                persistence.persist_run_manifest(
                    persistence.build_run_manifest(submission.run_id)
                )
                persistence.transition_run_with_operator_event(
                    run_id=submission.run_id,
                    status=RunStatus.SUCCEEDED,
                    event_type=RunEventType.RUN_SUCCEEDED,
                    severity=EventSeverity.INFO,
                    source="candidate_pipeline_runtime",
                    message="Candidate screening completed through the generic runtime.",
                )
            except Exception as exc:
                current = persistence.runs.get(submission.run_id)
                if current is not None and current.status == RunStatus.RUNNING:
                    persistence.transition_run_with_operator_event(
                        run_id=submission.run_id,
                        status=RunStatus.FAILED,
                        event_type=RunEventType.RUN_FAILED,
                        severity=EventSeverity.ERROR,
                        source="candidate_pipeline_runtime",
                        message="Candidate screening failed closed in the generic runtime.",
                        error_summary=str(exc)[:500],
                    )
                raise

            adapters = self._stage_adapters(
                persistence=persistence,
                screening_result=screening_result,
                data=market.data,
                audit=market.audit,
                execution_document=execution_document,
            )
            return FactoryFilterChainService(
                persistence,
                artifact_root=self.artifact_root,
            ).run(
                screening_run_id=submission.run_id,
                stage_adapters=adapters,
            )
        finally:
            persistence.close()

    def _validate_saved_configuration(
        self,
        persistence: PersistenceService,
        configuration_id: str,
    ) -> dict[str, Any]:
        configuration = persistence.configurations.get(configuration_id)
        if configuration is None:
            raise KeyError(f"unknown candidate configuration {configuration_id}")
        expected = canonical_json(self.definition.configuration_document())
        if configuration.canonical_config_json != expected:
            raise ValueError("runtime definition differs from the durable candidate configuration")
        document = json.loads(configuration.canonical_config_json)
        execution = document.get("execution")
        if not isinstance(execution, dict):
            raise ValueError("candidate configuration execution assumptions are malformed")
        return execution

    def _stage_adapters(
        self,
        *,
        persistence: PersistenceService,
        screening_result: Any,
        data: Any,
        audit: Any,
        execution_document: dict[str, Any],
    ) -> dict[RunStage, Any]:
        evidence = ValidationEvidenceArtifactService(persistence)
        plan = self.definition.validation
        experiment = self.definition.experiment

        def prepare(context: FilterStageContext) -> None:
            persistence.transition_run_with_operator_event(
                run_id=context.run_id,
                status=RunStatus.RUNNING,
                event_type=RunEventType.RUN_STARTED,
                severity=EventSeverity.INFO,
                source="candidate_pipeline_runtime",
                message=f"Started generic {context.stage.value} validation.",
            )
            persistence.persist_experiment_inputs_on_run(
                run_id=context.run_id,
                config=experiment,
                result=screening_result,
                execution_assumptions=execution_document,
                include_parameter_results=False,
            )

        def complete(context: FilterStageContext) -> PersistedStageReference:
            persistence.transition_run_with_operator_event(
                run_id=context.run_id,
                status=RunStatus.SUCCEEDED,
                event_type=RunEventType.RUN_SUCCEEDED,
                severity=EventSeverity.INFO,
                source="candidate_pipeline_runtime",
                message=f"Completed generic {context.stage.value} validation.",
            )
            return PersistedStageReference(stage=context.stage, run_id=context.run_id)

        def persist_oos_report(context: FilterStageContext, path: Path) -> None:
            content = path.read_bytes()
            document = json.loads(content)
            artifact_id = str(document.get("artifact_id") or path.stem)
            location = str(path.relative_to(self.artifact_root))
            persistence.register_artifact(
                run_id=context.run_id,
                artifact_type=ArtifactType.VALIDATION_EVIDENCE,
                logical_name=f"source_lock_evidence:{artifact_id}",
                media_type="application/json",
                format="json",
                location=location,
                content=content,
                schema_version=1,
            )
            persistence.persist_run_manifest(
                persistence.build_run_manifest(context.run_id)
            )

        def oos(context: FilterStageContext) -> PersistedStageReference:
            prepare(context)
            path = self.artifact_root / context.run_id / "out_of_sample.json"
            config = OutOfSampleConfig(
                experiment=experiment,
                split=plan.out_of_sample_split,
                output_path=path,
                shortlist_size=plan.out_of_sample_shortlist_size,
            )
            try:
                execute_out_of_sample(config, data, audit, write_output=True)
            except OutOfSampleProgressionError:
                persist_oos_report(context, path)
                return complete(context)
            persist_oos_report(context, path)
            return complete(context)

        def walk_forward(context: FilterStageContext) -> PersistedStageReference:
            prepare(context)
            rules = plan.walk_forward_rules
            result = execute_walk_forward(
                WalkForwardConfig(
                    experiment=experiment,
                    training_window_size=rules.training_window_size,
                    selection_window_size=rules.selection_window_size,
                    test_window_size=rules.test_window_size,
                    step_size=rules.step_size,
                    training_mode=rules.training_mode,
                    minimum_rows_per_window=rules.minimum_rows_per_window,
                    shortlist_size=plan.walk_forward_shortlist_size,
                    incomplete_final_window=rules.incomplete_final_window,
                    output_path=self.artifact_root / context.run_id / "walk_forward.json",
                ),
                data,
                audit,
                write_output=False,
            )
            evidence.persist_walk_forward(
                run_id=context.run_id,
                result=result,
                rules=rules,
                artifact_root=self.artifact_root,
            )
            return complete(context)

        def robustness(context: FilterStageContext) -> PersistedStageReference:
            prepare(context)
            source_lock = evidence.retrieve_out_of_sample_source_lock(
                context.previous[0].run_id,
                artifact_root=self.artifact_root,
            )
            robustness_data = data.loc[
                source_lock.source_start : source_lock.source_end
            ].copy()
            if robustness_data.empty:
                raise ValueError("source-lock boundaries contain no robustness data")
            robustness_audit = replace(
                audit,
                actual_first_row_date=str(robustness_data.index[0].date()),
                actual_last_row_date=str(robustness_data.index[-1].date()),
                row_count=len(robustness_data),
                cache_action="partition:out_of_sample",
                cache_decision_reason="locked out-of-sample robustness source",
            )
            if plan.fixed_rule_cost_stress is not None:
                result = run_fixed_rule_robustness(
                    experiment=experiment,
                    strategy_version=screening_result.strategy_version,
                    source_lock=source_lock,
                    plan=plan.fixed_rule_cost_stress,
                    regimes=plan.robustness_regimes,
                    maximum_drawdown=plan.robustness_maximum_drawdown,
                    minimum_return=plan.robustness_minimum_return,
                    minimum_sharpe=plan.robustness_minimum_sharpe,
                    data=robustness_data,
                    audit=robustness_audit,
                )
            else:
                config = RobustnessConfig(
                    strategy_id=screening_result.strategy_id,
                    strategy_version=screening_result.strategy_version,
                    locked_parameters=source_lock.locked_parameters,
                    experiment_id=experiment.experiment_id,
                    source_artifact_id=source_lock.artifact_id,
                    source_start=source_lock.source_start,
                    source_end=source_lock.source_end,
                    data_provenance=source_lock.data_provenance,
                    execution_assumptions=source_lock.execution_assumptions,
                    neighborhood=plan.robustness_neighborhood,
                    regimes=plan.robustness_regimes,
                    maximum_drawdown=plan.robustness_maximum_drawdown,
                    minimum_return=plan.robustness_minimum_return,
                    minimum_sharpe=plan.robustness_minimum_sharpe,
                )
                construction = build_neighborhood(
                    get_strategy(experiment.strategy_id),
                    source_lock.locked_parameters,
                    plan.robustness_neighborhood,
                )
                result = run_robustness_pipeline(
                    config,
                    construction,
                    experiment,
                    robustness_data,
                    robustness_audit,
                )
            evidence.persist_robustness(
                run_id=context.run_id,
                result=result,
                artifact_root=self.artifact_root,
                protected_data_state="gated",
            )
            return complete(context)

        def monte_carlo(context: FilterStageContext) -> PersistedStageReference:
            prepare(context)
            source_lock = evidence.retrieve_out_of_sample_source_lock(
                context.previous[0].run_id,
                artifact_root=self.artifact_root,
            )
            walk_reference = next(
                item for item in context.previous if item.stage == RunStage.WALK_FORWARD
            )
            persisted = evidence.retrieve_walk_forward(
                walk_reference.run_id,
                artifact_root=self.artifact_root,
            )
            folds = persisted.document["evidence"]["folds"]
            values = tuple(
                float(fold["test_metrics"]["total_return"])
                for fold in folds
                if fold.get("status") == "successful"
            )
            result = run_monte_carlo(
                SourceSeries(
                    source_id=persisted.evidence_identity,
                    source_kind="fold_endpoint_returns",
                    experiment_id=experiment.experiment_id,
                    strategy_id=screening_result.strategy_id,
                    strategy_version=screening_result.strategy_version,
                    values=values,
                    provenance={
                        "walk_forward_evidence_identity": persisted.evidence_identity
                    },
                    execution_assumptions=source_lock.execution_assumptions,
                    period_frequency="walk-forward-fold",
                ),
                plan.monte_carlo,
            )
            evidence.persist_monte_carlo(
                run_id=context.run_id,
                result=result,
                artifact_root=self.artifact_root,
                protected_data_state="gated",
            )
            return complete(context)

        return {
            RunStage.OOS: oos,
            RunStage.WALK_FORWARD: walk_forward,
            RunStage.ROBUSTNESS: robustness,
            RunStage.MONTE_CARLO: monte_carlo,
        }

    def _reopen_completed_chain(self, screening_run_id: str) -> FilterChainOutcome:
        persistence = PersistenceService(self.database)
        try:
            screening = persistence.runs.get(screening_run_id)
            if screening is None or screening.status != RunStatus.SUCCEEDED:
                raise CandidatePipelineReplayIncompleteError(
                    "candidate screening replay is not a completed successful run"
                )
            try:
                return FactoryFilterChainService(
                    persistence,
                    artifact_root=self.artifact_root,
                ).reopen(screening_run_id=screening_run_id)
            except FilterChainReplayIncompleteError as exc:
                raise CandidatePipelineReplayIncompleteError(str(exc)) from exc
        finally:
            persistence.close()
