"""Generic execution, metrics, ranking, and persistence for experiments."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

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
from backtesting.experiments.chunking import setting_portfolio as _setting_portfolio, simulate_in_chunks
from backtesting.experiments.metrics import extract_metrics
from backtesting.experiments.windows import cut_to_window, generate_signals_once
from backtesting.validation.gates import (
    normalize_signals,
    validate_execution,
    validate_market_data,
    validate_signals,
)
from backtesting.validation.models import ValidationResult, raise_for_blocking_failures
from backtesting.screening import ScreeningResult, screen_metrics
from backtesting.screening.deflated_sharpe import DeflatedSharpeResult, deflated_sharpe, grid_returns
from backtesting.screening.overfitting_pbo import (
    PBO_FOLDS, OverfittingPBOResult, probability_of_backtest_overfitting,
)
from backtesting.vectorbt_runtime import require_vectorbtpro

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
            stop_loss=(signals.stop_loss.shift(1) if signals.stop_loss is not None else None),
            take_profit=(signals.take_profit.shift(1) if signals.take_profit is not None else None),
            trailing_stop=(signals.trailing_stop.shift(1) if signals.trailing_stop is not None else None),
            trailing_threshold=(
                signals.trailing_threshold.shift(1) if signals.trailing_threshold is not None else None
            ),
            td_stop=(signals.td_stop.shift(1, fill_value=-1) if signals.td_stop is not None else None),
            upon_opposite_entry=signals.upon_opposite_entry,
            session_entry_cap=signals.session_entry_cap,
            session_id=signals.session_id,  # the fill bar's own session: not shifted
        )
    raise ValueError(f"Unsupported execution mode: {execution.mode}")


_LEADING_ARGS = ("entries", "exits", "short_entries", "short_exits", "price")
_SETTING_FRAMES = (
    "entries", "exits", "short_entries", "short_exits", "price", "sl_stop", "tp_stop", "tsl_stop", "tsl_th", "td_stop",
)


def _setting_args(data: pd.DataFrame, aligned: SignalResult, execution: ExecutionConfig) -> dict[str, Any]:
    """The from_signals inputs that belong to one parameter setting."""
    if execution.direction == "shortonly":
        signal_args = {"entries": aligned.short_entries, "exits": aligned.short_exits}
    elif execution.direction == "longonly":
        signal_args = {"entries": aligned.entries, "exits": aligned.exits}
    else:
        signal_args = {
            "entries": aligned.entries,
            "exits": aligned.exits,
            "short_entries": aligned.short_entries,
            "short_exits": aligned.short_exits,
        }
    return (
        signal_args
        | {"price": build_execution_price(data, aligned, execution)}
        | _stop_args(data, aligned, execution)
    )


def _setting_label(close: pd.Series, args: dict[str, Any]) -> Any:
    # A one-setting run is named after the name all its Series inputs share, else column 0,
    # which VectorBT PRO reads back as "no name" (ArrayWrapper.name). Labelling each column the
    # same way keeps a selected column's trades, orders and value identical to a one-setting run.
    names = {close.name} | {value.name for value in args.values() if isinstance(value, pd.Series)}
    name = names.pop() if len(names) == 1 else None
    return 0 if name is None else name


def _stack_settings(data: pd.DataFrame, close: pd.Series, settings: list[dict[str, Any]]) -> dict[str, Any]:
    """One column per setting for every per-setting input; shared inputs stay as they are.

    VectorBT PRO broadcasts from_signals inputs, so one call simulates every column
    independently (no cash sharing). A stop absent from a setting is NaN, VectorBT's
    "no stop" default; an absent signal is all-False, its default.
    """
    labels = pd.Index([_setting_label(close, args) for args in settings])
    stacked: dict[str, Any] = {}
    for key in dict.fromkeys(key for args in settings for key in args):
        values = [args.get(key) for args in settings]
        if key not in _SETTING_FRAMES:
            stacked[key] = next(value for value in values if value is not None)
        elif all(value is None for value in values):
            stacked[key] = None
        else:
            fill = -1 if key == "td_stop" else np.nan if key.endswith(("_stop", "_th")) else False
            frame = pd.concat(
                [pd.Series(fill, index=data.index) if value is None else value for value in values],
                axis=1,
            )
            frame.columns = labels
            stacked[key] = frame
    return stacked


def _construct_portfolio(
    data: pd.DataFrame,
    aligned: SignalResult | Sequence[SignalResult],
    config: ExperimentConfig,
) -> Any:
    """Call VectorBT only after the caller has passed every blocking gate.

    One SignalResult gives that setting's portfolio. A sequence gives one portfolio with
    one column per setting, simulated by a single Portfolio.from_signals call; select a
    setting back out with _setting_portfolio.
    """
    vbt = require_vectorbtpro()
    execution = config.execution
    close = data["Close"] * execution.price_multiplier
    if isinstance(aligned, (list, tuple)):
        setting_args = _stack_settings(
            data, close, [_setting_args(data, setting, execution) for setting in aligned]
        )
    else:
        setting_args = _setting_args(data, aligned, execution)
    # Stop kwargs keep their place after the cost kwargs, as before the one-pass change.
    leading = {key: value for key, value in setting_args.items() if key in _LEADING_ARGS}
    stops = {key: value for key, value in setting_args.items() if key not in _LEADING_ARGS}
    first = aligned[0] if isinstance(aligned, (list, tuple)) else aligned
    if first.session_entry_cap is not None:
        from backtesting.experiments.session_cap import session_cap_kwargs

        columns = len(aligned) if isinstance(aligned, (list, tuple)) else 1
        stops |= session_cap_kwargs(first.session_id, data.index, first.session_entry_cap, columns)
    return vbt.Portfolio.from_signals(
        close=close,
        **leading,
        size=float("inf") if execution.position_sizing == "all_cash_whole_shares" else execution.order_size,
        direction=None if execution.direction == "both" else execution.direction,
        accumulate=execution.accumulate,
        leverage=execution.leverage,
        init_cash=execution.initial_cash,
        fees=execution.fees,
        slippage=execution_slippage(data, execution),
        fixed_fees=execution.fixed_fee_per_order,
        **stops,
        **_whole_share_args(execution),
    )


def _whole_share_args(execution: ExecutionConfig) -> dict[str, Any]:
    # size=np.inf buys with all cash; size_granularity=1.0 floors each order to whole
    # shares ("granularity of 1.0 makes the quantity to behave like an integer. Placing
    # an order of 12.5 shares (in any direction) will order exactly 12.0 shares" --
    # vectorbt.portfolio.enums.Order.size_granularity, https://vectorbt.dev/api/portfolio/enums/;
    # VectorBT PRO keeps the same from_signals argument).
    return {"size_granularity": 1.0} if execution.position_sizing == "all_cash_whole_shares" else {}


def _stop_args(data: pd.DataFrame, aligned: SignalResult, execution: ExecutionConfig) -> dict[str, Any]:
    """VectorBT stop kwargs for whichever of stop-loss, take-profit and trailing stop are set.

    Each stop is optional and independent; only the ones present are passed (sl_stop, tp_stop, tsl_stop).
    Levels are fractions of the entry fill (Percent), fixed at entry; the trailing stop trails the
    best price since entry. stop_exit_price "Stop" fills at the stop level, except that when a bar
    OPENS beyond the stop (a gap) VectorBT PRO fills at that open, not at the stop
    (https://vectorbt.pro/features/backtesting/stop-loss-and-take-profit/: "If the price opens beyond
    the stop, a real order fills at the open, not at the stop ... "stop", fills at the open after a gap").
    No stop/signal priority is set here, so a stop and a same-bar exit signal resolve by VectorBT's defaults.
    """
    present = {
        name: level
        for name, level in (
            ("sl_stop", aligned.stop_loss),
            ("tp_stop", aligned.take_profit),
            ("tsl_stop", aligned.trailing_stop),
            # tsl_th: the trailing stop activates only once price has gained this fraction from the entry.
            ("tsl_th", aligned.trailing_threshold),
            # VectorBT's own time exit: td_stop, the maximum hold from the fill (-1 disables it).
            ("td_stop", aligned.td_stop),
        )
        if level is not None
    }
    options = {"upon_opposite_entry": aligned.upon_opposite_entry} if aligned.upon_opposite_entry is not None else {}
    if not present:
        return options
    if execution.mode != "next_bar_open":
        raise ValueError("Bar-based stop orders require next-bar-open execution")
    return {
        "open": data["Open"] * execution.price_multiplier,
        "high": data["High"] * execution.price_multiplier,
        "low": data["Low"] * execution.price_multiplier,
        **present,
        "delta_format": "Percent",
        "stop_entry_price": "Open",
        "stop_exit_price": "Stop",
        "use_stops": True,
        **({"time_delta_format": "Index"} if "td_stop" in present else {}),
        **options,
    }


def build_execution_price(
    data: pd.DataFrame,
    aligned: SignalResult,
    execution: ExecutionConfig,
) -> pd.Series:
    """Signal fill price with the contract multiplier; slippage is VectorBT's own (``execution_slippage``)."""
    return data[execution.execution_price_field].astype(float) * execution.price_multiplier


def execution_slippage(data: pd.DataFrame, execution: ExecutionConfig) -> Any:
    """from_signals ``slippage`` (a fraction of each order's price, adverse for buys and sells, every fill
    including stop exits): the configured fraction plus absolute points (ticks x tick size) over the bar's
    execution price, so a signal fill moves by exactly those points and a stop fill by points x stop / open."""
    points = execution.absolute_slippage_points
    if not points:
        return execution.slippage
    return execution.slippage + points / data[execution.execution_price_field].astype(float)


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
) -> Any:
    """Validate, align, and construct one portfolio."""
    aligned, _ = validate_for_simulation(data, signals, config)
    return _construct_portfolio(data, aligned, config)


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
        "slippage_points": execution.slippage_points,
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


def _record_luck(
    value_columns: list[np.ndarray | None], initial_cash: float, index: pd.Index
) -> tuple[DeflatedSharpeResult | None, OverfittingPBOResult | None]:
    """Record-only Deflated Sharpe and PBO over the whole simulated grid (never screens)."""
    if not value_columns or any(column is None for column in value_columns):
        return None, None
    values = np.column_stack(value_columns)
    luck = deflated_sharpe(values, initial_cash)
    returns = grid_returns(values, initial_cash, index)
    enough = returns.shape[1] >= 2 and returns.shape[0] >= 2 * PBO_FOLDS
    return luck, probability_of_backtest_overfitting(returns) if enough else None


def _with_luck(
    screening_results: list[ScreeningResult], luck: DeflatedSharpeResult
) -> list[ScreeningResult]:
    return [
        replace(result, deflated_sharpe_probability=probability)
        for result, probability in zip(screening_results, luck.trial_probabilities)
    ]


def _validated_settings(
    config: ExperimentConfig,
    strategy: Any,
    data: pd.DataFrame,
    rejections: list[RejectedParameters],
    validation_by_gate: dict[str, ValidationResult], signal_cache: dict | None = None,
) -> list[tuple[dict[str, Any], SignalResult, tuple[ValidationResult, ...]]]:
    """Validate and align every setting (in one pass if the strategy class has ``iter_signals_batch``)."""
    accepted: list[dict[str, Any]] = []
    for supplied in config.parameter_combinations:
        candidate = dict(supplied)
        try:
            accepted.append(strategy.validate_parameters(candidate))
        except (TypeError, ValueError) as exc:
            rejections.append(RejectedParameters(parameters=candidate, error=str(exc)))
    generated = generate_signals_once(strategy, data, accepted, signal_cache)
    settings = []
    for normalized, signals in zip(accepted, generated):
        aligned, validation_results = validate_for_simulation(
            data, signals, config, required_fields=strategy.spec.data.required_fields
        )
        validation_by_gate.update({result.gate_id: result for result in validation_results})
        settings.append((normalized, aligned, validation_results))
    return settings


def execute_experiment(
    config: ExperimentConfig,
    data: pd.DataFrame,
    audit: DataAudit,
    *,
    run_timestamp: str | None = None,
    write_output: bool = True,
    portfolio_observer: Callable[[str, Any], None] | None = None,
    evaluation_range: tuple | None = None, signal_cache: dict | None = None,  # see experiments.windows
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
    required_adjustment = strategy.spec.data.adjusted_prices
    if required_adjustment is not None and config.market_data.adjusted != required_adjustment:
        raise ValueError("Market-data adjustment does not match strategy requirements")

    rows: list[dict[str, Any]] = []
    normalized_parameters: list[dict[str, Any]] = []
    rejections: list[RejectedParameters] = []
    validation_by_gate = {result.gate_id: result for result in market_results}
    screening_results: list[ScreeningResult] = []
    execution_assumptions = _execution_assumptions(config, strategy)
    parameter_names = tuple(strategy.spec.parameter_map)

    settings = _validated_settings(config, strategy, data, rejections, validation_by_gate, signal_cache)
    data, settings = cut_to_window(data, settings, evaluation_range)

    # Every validated setting is one column of a single VectorBT simulation.
    aligned_settings = tuple(aligned for _, aligned, _ in settings)
    sweep_metrics, value_columns, observed = simulate_in_chunks(
        data, aligned_settings, config, _construct_portfolio, keep_portfolios=portfolio_observer is not None
    )
    for position, (normalized, _, validation_results) in enumerate(settings):
        metrics = sweep_metrics[position]
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
        if portfolio_observer is not None:
            portfolio_observer(screening.parameter_row_id, observed[position])
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

    luck, pbo = _record_luck(value_columns, config.execution.initial_cash, data.index)
    if luck is not None:
        screening_results = _with_luck(screening_results, luck)
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
        deflated_sharpe=luck, overfitting_pbo=pbo,
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
