"""Select the declared robustness engine for a fixed Candidate contract."""

from __future__ import annotations

from typing import Any

import pandas as pd

from backtesting.robustness import (
    RobustnessConfig, build_neighborhood, run_fixed_rule_robustness,
    run_robustness_pipeline,
)
from strategies import get_strategy


def execute_candidate_robustness(*, plan: Any, screening_result: Any,
                                 experiment: Any, source_lock: Any,
                                 data: pd.DataFrame, audit: Any) -> Any:
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
            data=data,
            audit=audit,
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
            data,
            audit,
        )
    return result
