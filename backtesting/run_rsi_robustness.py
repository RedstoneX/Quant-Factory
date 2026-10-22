"""Run RSI robustness only when a valid prior parameter lock exists."""

from dataclasses import replace
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.robustness import (  # noqa: E402
    NeighborhoodConfig,
    ParameterNeighborhoodDefinition,
    RegimeConfig,
    RobustnessConfig,
    build_neighborhood,
    find_valid_lock,
    insufficient_result,
    read_robustness_report,
    run_robustness_pipeline,
    write_robustness_report,
)
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG  # noqa: E402
from market_data import load_market_data  # noqa: E402
from strategies import get_strategy  # noqa: E402

OUTPUT = PROJECT_ROOT / "results" / "rsi_spy_robustness.json"
ARTIFACTS = (
    PROJECT_ROOT / "results" / "rsi_spy_oos.json",
    PROJECT_ROOT / "results" / "rsi_spy_walk_forward.json",
)


def _execution_identity() -> dict[str, object]:
    execution = EXPERIMENT_CONFIG.execution
    return {
        "execution_mode": execution.mode,
        "fees": execution.fees,
        "slippage": execution.slippage,
        "initial_cash": execution.initial_cash,
        "direction": execution.direction,
        "leverage": execution.leverage,
        "accumulate": execution.accumulate,
    }


def _bounded_rsi_neighborhood(locked: dict[str, object]) -> NeighborhoodConfig:
    strategy = get_strategy("rsi_mean_reversion")
    definitions = []
    for name, parameter in strategy.spec.parameter_map.items():
        allowed = parameter.allowed_values
        if allowed is None:
            values = (locked[name],)
        else:
            position = allowed.index(locked[name])
            start = max(0, position - 1)
            end = min(len(allowed), position + 2)
            values = tuple(allowed[start:end])
        definitions.append(
            ParameterNeighborhoodDefinition(
                parameter_name=name,
                method="explicit_values",
                explicit_values=values,
            )
        )
    return NeighborhoodConfig(definitions=tuple(definitions))


def run() -> object:
    valid_lock, inspected = find_valid_lock(
        ARTIFACTS,
        expected_experiment_id=EXPERIMENT_CONFIG.experiment_id,
        expected_strategy_id=EXPERIMENT_CONFIG.strategy_id,
        expected_strategy_version=get_strategy(
            EXPERIMENT_CONFIG.strategy_id
        ).spec.identity.version,
        expected_execution=_execution_identity(),
    )
    if valid_lock is None:
        reasons = tuple(
            f"{Path(item.artifact_path).name}: {reason}"
            for item in inspected
            for reason in item.reasons
        ) or ("no prior lock artifacts were found",)
        return insufficient_result(
            strategy_id="rsi_mean_reversion",
            strategy_version="1.0.0",
            experiment_id=EXPERIMENT_CONFIG.experiment_id,
            artifact_id="inspected:rsi_spy_oos.json,rsi_spy_walk_forward.json",
            reasons=reasons,
        )

    market_data = load_market_data(EXPERIMENT_CONFIG.market_data)
    data = market_data.data.loc[valid_lock.source_start : valid_lock.source_end].copy()
    if data.empty:
        return insufficient_result(
            strategy_id=valid_lock.strategy_id,
            strategy_version=valid_lock.strategy_version,
            experiment_id=valid_lock.experiment_id,
            artifact_id=valid_lock.artifact_id,
            reasons=("locked source boundaries are absent from market-data cache",),
            invalid=True,
        )
    audit = replace(
        market_data.audit,
        actual_first_row_date=str(data.index[0].date()),
        actual_last_row_date=str(data.index[-1].date()),
        row_count=len(data),
        cache_action="robustness source slice",
        cache_decision_reason="validated prior-lock boundaries",
    )
    locked_parameters = dict(valid_lock.locked_parameters or {})
    config = RobustnessConfig(
        strategy_id=valid_lock.strategy_id,
        strategy_version=valid_lock.strategy_version,
        locked_parameters=locked_parameters,
        experiment_id=valid_lock.experiment_id,
        source_artifact_id=valid_lock.artifact_id,
        source_start=valid_lock.source_start or "",
        source_end=valid_lock.source_end or "",
        data_provenance=valid_lock.data_provenance,
        execution_assumptions=valid_lock.execution_assumptions,
        neighborhood=_bounded_rsi_neighborhood(locked_parameters),
        regimes=RegimeConfig(),
    )
    construction = build_neighborhood(
        get_strategy(config.strategy_id),
        locked_parameters,
        config.neighborhood,
    )
    return run_robustness_pipeline(
        config,
        construction,
        EXPERIMENT_CONFIG,
        data,
        audit,
    )


def main() -> None:
    result = run()
    write_robustness_report(OUTPUT, result.to_dict())
    read_robustness_report(OUTPUT)
    print(f"Robustness status: {result.status}")
    print(f"Inspected artifacts: {', '.join(path.name for path in ARTIFACTS)}")
    for reason in result.reasons[:5]:
        print(f"Reason: {reason}")
    if len(result.reasons) > 5:
        print(f"Additional reasons recorded in report: {len(result.reasons) - 5}")
    print(f"Saved report to {OUTPUT}")


if __name__ == "__main__":
    main()
