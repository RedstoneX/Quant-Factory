"""Predeclared execution-cost stress for an otherwise immutable strategy."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math

import pandas as pd

from backtesting.experiments import align_signals_for_execution, build_portfolio, execute_experiment
from backtesting.experiments.models import ExperimentConfig
from backtesting.robustness.models import (
    FixedRuleCostStressPlan,
    FixedRuleCostStressResult,
    RegimeConfig,
    RobustnessResult,
    SourceLockEvidence,
    ThresholdResult,
)
from backtesting.robustness.regimes import evaluate_regimes, label_regimes
from backtesting.robustness.runner import combine_statuses
from market_data import DataAudit
from strategies import get_strategy


def run_fixed_rule_cost_stress(
    experiment: ExperimentConfig,
    plan: FixedRuleCostStressPlan,
    data: pd.DataFrame,
    audit: DataAudit,
) -> FixedRuleCostStressResult:
    """Evaluate one locked rule at higher costs; missing evidence never passes."""
    strategy = get_strategy(experiment.strategy_id)
    if strategy.spec.parameters or experiment.parameter_combinations != ({},):
        raise ValueError("fixed-rule cost stress requires one parameter-free strategy")
    baseline = experiment.execution
    if (
        baseline.position_sizing != "fixed_units"
        or baseline.order_size != 1.0
        or baseline.fees != 0
        or baseline.slippage != 0
        or baseline.slippage_points != 0
        or baseline.tick_size is None
        or baseline.slippage_ticks <= 0
        or baseline.fixed_fee_per_contract_per_side <= 0
    ):
        raise ValueError("fixed-rule stress requires one contract and explicit baseline futures costs")
    if (
        plan.fixed_fee_per_contract_per_side <= baseline.fixed_fee_per_contract_per_side
        or plan.slippage_ticks <= baseline.slippage_ticks
    ):
        raise ValueError("predeclared stress must exceed both baseline costs")
    stressed_execution = replace(
        baseline,
        fixed_fee_per_contract_per_side=plan.fixed_fee_per_contract_per_side,
        slippage_ticks=plan.slippage_ticks,
    )
    stressed_experiment = replace(
        experiment,
        experiment_id=f"{experiment.experiment_id}:fixed-rule-cost-stress",
        execution=stressed_execution,
    )
    result = execute_experiment(stressed_experiment, data, audit, write_output=False)
    if len(result.screening_results) != 1 or len(result.ranked_results) != 1:
        raise ValueError("fixed-rule stress did not produce exactly one evaluated rule")
    screening = result.screening_results[0]
    row = result.ranked_results.iloc[0]
    metrics = {
        "number_of_trades": int(row["number_of_trades"]),
        "total_return": float(row["total_return"]),
        "annualized_return": float(row["annualized_return"]),
        "sharpe_ratio": float(row["sharpe_ratio"]),
        "max_drawdown": float(row["max_drawdown"]),
    }
    finite = all(math.isfinite(value) for value in metrics.values())
    thresholds = tuple(
        ThresholdResult(
            rule_id=f"stressed_{rule.rule_id}",
            status="passed" if rule.status == "passed" else "failed",
            observed=rule.observed_value,
            threshold=rule.threshold,
            message=rule.message,
        )
        for rule in screening.rule_results
    )
    status = "passed" if finite and screening.passed and thresholds else "failed"
    reasons = tuple(rule.message for rule in thresholds if rule.status != "passed")
    if not finite:
        status = "insufficient_evidence"
        reasons += ("stressed trade metrics are missing or non-finite",)
    if not thresholds:
        status = "insufficient_evidence"
        reasons += ("stressed screen produced no threshold evidence",)
    return FixedRuleCostStressResult(
        baseline_costs={
            "fixed_fee_per_contract_per_side": baseline.fixed_fee_per_contract_per_side,
            "slippage_ticks": baseline.slippage_ticks,
        },
        stressed_costs={
            "fixed_fee_per_contract_per_side": plan.fixed_fee_per_contract_per_side,
            "slippage_ticks": plan.slippage_ticks,
        },
        stressed_metrics=metrics,
        threshold_results=thresholds,
        status=status,
        reasons=reasons,
    )


def run_fixed_rule_robustness(
    *,
    experiment: ExperimentConfig,
    strategy_version: str,
    source_lock: SourceLockEvidence,
    plan: FixedRuleCostStressPlan,
    regimes: RegimeConfig,
    maximum_drawdown: float,
    minimum_return: float,
    minimum_sharpe: float | None,
    data: pd.DataFrame,
    audit: DataAudit,
) -> RobustnessResult:
    """Require a real cost-stress pass and ordinary regime evidence for fixed rules."""
    strategy = get_strategy(experiment.strategy_id)
    if strategy.spec.identity.version != strategy_version:
        raise ValueError("fixed-rule strategy version does not match the source lock")
    if source_lock.locked_parameters != {} or strategy.spec.parameters:
        raise ValueError("fixed-rule validation cannot vary a Candidate rule")
    if str(data.index[0].date()) != source_lock.source_start or str(data.index[-1].date()) != source_lock.source_end:
        raise ValueError("fixed-rule data boundaries do not match the source lock")
    expected_execution = {
        "execution_mode": experiment.execution.mode,
        "fees": experiment.execution.fees,
        "slippage": experiment.execution.slippage,
        "initial_cash": experiment.execution.initial_cash,
        "direction": experiment.execution.direction,
        "leverage": experiment.execution.leverage,
        "accumulate": experiment.execution.accumulate,
    }
    if any(source_lock.execution_assumptions.get(key) != value for key, value in expected_execution.items()):
        raise ValueError("fixed-rule execution assumptions do not match the source lock")
    signals = strategy.generate_signals(data, {})
    portfolio = build_portfolio(data, signals, experiment)
    returns = pd.Series(portfolio.returns, index=data.index, name="strategy_return")
    aligned = align_signals_for_execution(signals, experiment.execution)
    entries = pd.Series(aligned.entries, index=data.index).astype(bool)
    labels = label_regimes(data["Close"], regimes)
    regime_results = evaluate_regimes(
        returns,
        labels,
        regimes,
        minimum_return=minimum_return,
        maximum_drawdown_limit=maximum_drawdown,
        minimum_sharpe=minimum_sharpe,
        trade_entries=entries,
    )
    stress = run_fixed_rule_cost_stress(experiment, plan, data, audit)
    regime_status = combine_statuses(item.status for item in regime_results) if regime_results else "insufficient_evidence"
    components = {"fixed_rule_cost_stress": stress.status, "regimes": regime_status}
    reasons = [*stress.reasons]
    for item in regime_results:
        if item.status != "passed":
            reasons.extend(f"{item.regime_id}: {reason}" for reason in item.reasons)
    if not regime_results:
        reasons.append("no usable market regimes were available")
    return RobustnessResult(
        schema_version=1,
        status=combine_statuses(components.values()),
        strategy_id=experiment.strategy_id,
        strategy_version=strategy_version,
        experiment_id=experiment.experiment_id,
        source_artifact_id=source_lock.artifact_id,
        locked_parameters={},
        data_provenance=dict(source_lock.data_provenance),
        execution_assumptions=dict(source_lock.execution_assumptions),
        neighborhood_construction=None,
        parameter_points=(),
        neighborhood_summary=None,
        regime_metadata=labels.metadata,
        regime_results=regime_results,
        component_statuses=components,
        reasons=tuple(reasons),
        warnings=("Parameter variation is not applicable to this locked, parameter-free Candidate; it is not counted as a pass.",),
        timestamp=datetime.now(timezone.utc).isoformat(),
        fixed_rule_cost_stress=stress,
    )
