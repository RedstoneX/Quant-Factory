"""Generic execution, metrics, ranking, and persistence for experiments."""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import vectorbtpro as vbt

from market_data import DataAudit, format_audit, load_market_data
from strategies import get_strategy
from strategies.models import SignalResult
from strategies.parameter_governance import summarize_parameter_plan

from backtesting.experiments.models import (
    ExecutionConfig,
    ExperimentConfig,
    ExperimentResult,
    RejectedParameters,
)
from backtesting.validation import (
    ValidationResult,
    normalize_signals,
    raise_for_blocking_failures,
    validate_execution,
    validate_market_data,
    validate_signals,
)
from backtesting.screening import ScreeningResult, screen_metrics

METRIC_COLUMNS = (
    "total_return",
    "annualized_return",
    "sharpe_ratio",
    "max_drawdown",
    "number_of_trades",
    "win_rate",
)
PROVENANCE_COLUMNS = (
    "data_source",
    "prices_adjusted",
    "data_start_date",
    "data_end_date",
    "row_count",
)
EXECUTION_COLUMNS = (
    "execution_mode",
    "signal_timing",
    "execution_timing",
    "execution_price",
    "initial_cash",
    "fees",
    "slippage",
    "position_sizing",
    "direction",
    "leverage",
    "accumulate",
    "order_size",
    "price_multiplier",
    "fixed_fee_per_contract_per_side",
    "fixed_fee_per_order",
    "slippage_points",
    "slippage_ticks",
    "tick_size",
)
VALIDATION_COLUMNS = ("validation_status", "validation_gate_count")
SCREENING_COLUMNS = (
    "parameter_row_id",
    "screening_status",
    "screening_passed_rule_count",
    "screening_failed_rule_count",
    "screening_rejection_reasons",
)


def _as_float(value: object) -> float:
    if hasattr(value, "iloc"):
        value = value.iloc[0]
    return float(value)


def _shift_signal(signal: pd.Series | None) -> pd.Series | None:
    if signal is None:
        return None
    return signal.shift(1, fill_value=False).astype(bool)


def align_signals_for_execution(
    signals: SignalResult,
    execution: ExecutionConfig,
) -> SignalResult:
    """Align completed-bar signals to their configured execution bar."""
    if execution.mode == "same_bar_close":
        return signals
    if execution.mode == "next_bar_open":
        return SignalResult(
            entries=_shift_signal(signals.entries),
            exits=_shift_signal(signals.exits),
            short_entries=_shift_signal(signals.short_entries),
            short_exits=_shift_signal(signals.short_exits),
            parameters=dict(signals.parameters),
            metadata=dict(signals.metadata),
        )
    raise ValueError(f"Unsupported execution mode: {execution.mode}")


def _construct_portfolio(
    data: pd.DataFrame,
    aligned: SignalResult,
    config: ExperimentConfig,
) -> vbt.Portfolio:
    """Call VectorBT only after the caller has passed every blocking gate."""
    execution = config.execution
    close = data["Close"] * execution.price_multiplier
    signal_args: dict[str, Any]
    if execution.direction == "shortonly":
        signal_args = {
            "entries": aligned.short_entries,
            "exits": aligned.short_exits,
        }
    elif execution.direction == "longonly":
        signal_args = {"entries": aligned.entries, "exits": aligned.exits}
    else:
        signal_args = {
            "entries": aligned.entries,
            "exits": aligned.exits,
            "short_entries": aligned.short_entries,
            "short_exits": aligned.short_exits,
        }
    execution_price = build_execution_price(data, aligned, execution)
    return vbt.Portfolio.from_signals(
        close=close,
        **signal_args,
        price=execution_price,
        size=execution.order_size,
        direction=None if execution.direction == "both" else execution.direction,
        accumulate=execution.accumulate,
        leverage=execution.leverage,
        init_cash=execution.initial_cash,
        fees=execution.fees,
        slippage=execution.slippage,
        fixed_fees=execution.fixed_fee_per_order,
    )


def build_execution_price(
    data: pd.DataFrame,
    aligned: SignalResult,
    execution: ExecutionConfig,
) -> pd.Series:
    """Build adverse absolute-slippage prices and apply the contract multiplier."""
    price = data[execution.execution_price_field].astype(float).copy()
    points = execution.absolute_slippage_points
    if not points:
        return price * execution.price_multiplier

    false = pd.Series(False, index=price.index, dtype=bool)
    long_entries = aligned.entries
    long_exits = aligned.exits
    short_entries = aligned.short_entries if aligned.short_entries is not None else false
    short_exits = aligned.short_exits if aligned.short_exits is not None else false
    buy_orders = long_entries | short_exits
    sell_orders = long_exits | short_entries
    conflicts = buy_orders & sell_orders
    if conflicts.any():
        raise ValueError("absolute slippage cannot price simultaneous buy and sell orders")
    price.loc[buy_orders] += points
    price.loc[sell_orders] -= points
    return price * execution.price_multiplier


def validate_for_simulation(
    data: pd.DataFrame,
    signals: SignalResult,
    config: ExperimentConfig,
    required_fields: tuple[str, ...] | None = None,
) -> tuple[SignalResult, tuple[ValidationResult, ...]]:
    """Normalize and validate all inputs, returning aligned execution signals."""
    if required_fields is None:
        required_fields = get_strategy(config.strategy_id).spec.data.required_fields
    market_results = validate_market_data(data, required_fields, config.execution)
    raise_for_blocking_failures(market_results)

    normalized = normalize_signals(signals)
    signal_results = validate_signals(data, normalized, config.execution)
    raise_for_blocking_failures(signal_results)

    aligned = align_signals_for_execution(normalized, config.execution)
    execution_results = validate_execution(
        data, normalized, aligned, config.execution
    )
    combined = market_results + signal_results + execution_results
    raise_for_blocking_failures(combined)
    return aligned, combined


def build_portfolio(
    data: pd.DataFrame,
    signals: SignalResult,
    config: ExperimentConfig,
) -> vbt.Portfolio:
    """Validate, align, and construct one portfolio."""
    aligned, _ = validate_for_simulation(data, signals, config)
    return _construct_portfolio(data, aligned, config)


def extract_metrics(portfolio: vbt.Portfolio) -> dict[str, float | int]:
    """Extract the stable metric set shared by experiment outputs."""
    return {
        "total_return": _as_float(portfolio.total_return),
        "annualized_return": _as_float(portfolio.annualized_return),
        "sharpe_ratio": _as_float(portfolio.sharpe_ratio),
        "max_drawdown": _as_float(portfolio.max_drawdown),
        "number_of_trades": int(_as_float(portfolio.trades.count())),
        "win_rate": _as_float(portfolio.trades.win_rate),
    }


def _provenance(audit: DataAudit) -> dict[str, Any]:
    return {
        "data_source": audit.provider,
        "prices_adjusted": audit.prices_adjusted,
        "data_start_date": audit.actual_first_row_date,
        "data_end_date": audit.actual_last_row_date,
        "row_count": audit.row_count,
    }


def _execution_values(execution: ExecutionConfig) -> dict[str, Any]:
    return {
        "execution_mode": execution.mode,
        "signal_timing": execution.signal_timing,
        "execution_timing": execution.execution_timing,
        "execution_price": execution.execution_price_field,
        "initial_cash": execution.initial_cash,
        "fees": execution.fees,
        "slippage": execution.slippage,
        "position_sizing": execution.position_sizing,
        "direction": execution.direction,
        "leverage": execution.leverage,
        "accumulate": execution.accumulate,
        "order_size": execution.order_size,
        "price_multiplier": execution.price_multiplier,
        "fixed_fee_per_contract_per_side": execution.fixed_fee_per_contract_per_side,
        "fixed_fee_per_order": execution.fixed_fee_per_order,
        "slippage_points": execution.absolute_slippage_points,
        "slippage_ticks": execution.slippage_ticks,
        "tick_size": execution.tick_size,
    }


def _execution_assumptions(config: ExperimentConfig, strategy: Any) -> dict[str, Any]:
    return _execution_values(config.execution) | {
        "signal_timing_label": config.execution.signal_timing_label,
        "execution_timing_label": config.execution.execution_timing_label,
        "strategy": asdict(strategy.spec.assumptions),
    }


def _parameter_row(
    normalized: dict[str, Any], config: ExperimentConfig
) -> dict[str, Any]:
    aliases = config.parameter_name_map
    return {aliases.get(name, name): value for name, value in normalized.items()}


def _result_columns(config: ExperimentConfig, parameter_names: tuple[str, ...]) -> list[str]:
    aliases = config.parameter_name_map
    return (
        [aliases.get(name, name) for name in parameter_names]
        + list(METRIC_COLUMNS)
        + list(PROVENANCE_COLUMNS)
        + list(EXECUTION_COLUMNS)
        + list(VALIDATION_COLUMNS)
        + list(SCREENING_COLUMNS)
    )


def execute_experiment(
    config: ExperimentConfig,
    data: pd.DataFrame,
    audit: DataAudit,
    *,
    run_timestamp: str | None = None,
    write_output: bool = True,
) -> ExperimentResult:
    """Validate, simulate, rank, and optionally persist one experiment."""
    strategy = get_strategy(config.strategy_id)
    parameter_plan_summary = summarize_parameter_plan(
        strategy.spec, require_approved=True
    )
    market_results = validate_market_data(
        data, strategy.spec.data.required_fields, config.execution
    )
    raise_for_blocking_failures(market_results)
    if config.market_data.adjusted != strategy.spec.data.adjusted_prices:
        raise ValueError("Market-data adjustment does not match strategy requirements")

    rows: list[dict[str, Any]] = []
    normalized_parameters: list[dict[str, Any]] = []
    rejections: list[RejectedParameters] = []
    validation_by_gate = {result.gate_id: result for result in market_results}
    screening_results: list[ScreeningResult] = []
    execution_assumptions = _execution_assumptions(config, strategy)
    parameter_names = tuple(strategy.spec.parameter_map)

    for supplied in config.parameter_combinations:
        candidate = dict(supplied)
        try:
            normalized = strategy.validate_parameters(candidate)
        except (TypeError, ValueError) as exc:
            rejections.append(
                RejectedParameters(parameters=candidate, error=str(exc))
            )
            continue
        signals = strategy.generate_signals(data, normalized)
        aligned, validation_results = validate_for_simulation(
            data,
            signals,
            config,
            required_fields=strategy.spec.data.required_fields,
        )
        validation_by_gate.update(
            {result.gate_id: result for result in validation_results}
        )
        portfolio = _construct_portfolio(data, aligned, config)
        metrics = extract_metrics(portfolio)
        screening = screen_metrics(
            experiment_id=config.experiment_id,
            strategy_id=strategy.spec.identity.strategy_id,
            strategy_version=strategy.spec.identity.version,
            parameters=normalized,
            execution_assumptions=execution_assumptions,
            metrics=metrics,
            config=config.screening,
        )
        screening_results.append(screening)
        rows.append(
            _parameter_row(normalized, config)
            | metrics
            | _provenance(audit)
            | _execution_values(config.execution)
            | {
                "validation_status": "passed",
                "validation_gate_count": len(validation_results),
            }
            | {
                "parameter_row_id": screening.parameter_row_id,
                "screening_status": (
                    "passed" if screening.passed else "screened_out"
                ),
                "screening_passed_rule_count": screening.passed_rule_count,
                "screening_failed_rule_count": screening.failed_rule_count,
                "screening_rejection_reasons": " | ".join(
                    screening.rejection_reasons
                ),
            }
        )
        normalized_parameters.append(dict(normalized))

    columns = _result_columns(config, parameter_names)
    ranked = pd.DataFrame(rows, columns=columns)
    if not ranked.empty:
        unknown_rank_columns = set(config.ranking_columns) - set(ranked.columns)
        if unknown_rank_columns:
            raise ValueError(
                f"Unknown ranking column(s): {sorted(unknown_rank_columns)}"
            )
        tie_breakers = [
            column for column in columns if column not in config.ranking_columns
        ]
        ranked["_screening_order"] = ranked["screening_status"].map(
            {"passed": 0, "screened_out": 1}
        )
        sort_columns = ["_screening_order"] + list(config.ranking_columns) + tie_breakers
        sort_ascending = [True] + list(config.ranking_ascending) + [True] * len(tie_breakers)
        ranked = ranked.sort_values(
            sort_columns, ascending=sort_ascending, kind="mergesort"
        ).drop(columns="_screening_order").reset_index(drop=True)

    passing = ranked.loc[ranked["screening_status"] == "passed"].reset_index(
        drop=True
    )
    screened_out = ranked.loc[
        ranked["screening_status"] == "screened_out"
    ].reset_index(drop=True)

    if write_output:
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        ranked.to_csv(config.output_path, index=False)

    timestamp = run_timestamp or datetime.now(timezone.utc).isoformat()
    return ExperimentResult(
        ranked_results=ranked,
        passing_results=passing,
        screened_out_results=screened_out,
        experiment_id=config.experiment_id,
        strategy_id=strategy.spec.identity.strategy_id,
        strategy_name=strategy.spec.identity.name,
        strategy_version=strategy.spec.identity.version,
        normalized_parameters=tuple(normalized_parameters),
        market_data_audit=audit,
        execution_assumptions=execution_assumptions,
        run_timestamp=timestamp,
        evaluated_combinations=len(rows),
        rejected_combinations=len(rejections),
        rejections=tuple(rejections),
        validation_results=tuple(validation_by_gate.values()),
        screening_config=config.screening,
        screening_results=tuple(screening_results),
        parameter_plan_summary=parameter_plan_summary,
    )


def run_experiment(config: ExperimentConfig) -> ExperimentResult:
    """Load configured market data and execute the experiment."""
    market_data = load_market_data(config.market_data)
    return execute_experiment(config, market_data.data, market_data.audit)


def format_experiment_summary(result: ExperimentResult, output_path: object) -> str:
    """Format the existing demo-oriented console summary."""
    lines = [
        format_audit(result.market_data_audit),
        (
            f"Evaluated {result.evaluated_combinations} valid parameter "
            f"combinations"
        ),
    ]
    if result.rejected_combinations:
        lines.append(f"Rejected {result.rejected_combinations} parameter combinations")
    lines.append(
        f"Screening: {len(result.passing_results)} passed, "
        f"{len(result.screened_out_results)} screened out"
    )
    lines.extend(
        [
            "\nTop 10 combinations:",
            result.ranked_results.head(10).to_string(index=False),
            f"\nSaved complete results to {output_path}",
        ]
    )
    return "\n".join(lines)
