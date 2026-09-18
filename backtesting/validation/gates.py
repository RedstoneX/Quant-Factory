"""Deterministic hygiene gates run before portfolio simulation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

import numpy as np
import pandas as pd

from backtesting.validation.models import GateSeverity, ValidationResult
from strategies.models import SignalResult

if TYPE_CHECKING:
    from backtesting.experiments.models import ExecutionConfig


def _result(
    gate_id: str,
    passed: bool,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    pass_severity: GateSeverity = "info",
) -> ValidationResult:
    return ValidationResult(
        gate_id=gate_id,
        status="passed" if passed else "failed",
        severity=pass_severity if passed else "blocking",
        message=message,
        details=details or {},
    )


def validate_market_data(
    data: pd.DataFrame,
    required_fields: Iterable[str],
    execution: ExecutionConfig,
) -> tuple[ValidationResult, ...]:
    required = set(required_fields) | {"Close", execution.execution_price_field}
    missing = sorted(required - set(data.columns))
    results: list[ValidationResult] = [
        _result("data.non_empty", not data.empty, "Market data must not be empty."),
        _result(
            "data.required_columns",
            not missing,
            "Required market-data columns are present."
            if not missing
            else f"Missing required market-data columns: {missing}",
            details={"missing": missing},
        ),
    ]

    index_has_null = bool(pd.isna(data.index).any())
    results.extend(
        [
            _result(
                "timestamps.non_null",
                not index_has_null,
                "Market-data index contains no null timestamps."
                if not index_has_null
                else "Market-data index contains null timestamps.",
            ),
            _result(
                "timestamps.monotonic",
                data.index.is_monotonic_increasing,
                "Market-data timestamps are monotonic increasing."
                if data.index.is_monotonic_increasing
                else "Market-data timestamps are not monotonic increasing.",
            ),
            _result(
                "timestamps.unique",
                data.index.is_unique,
                "Market-data timestamps are unique."
                if data.index.is_unique
                else "Market-data timestamps contain duplicates.",
            ),
        ]
    )

    available_prices = [
        column for column in ("Open", "High", "Low", "Close") if column in data
    ]
    null_counts = {
        column: int(data[column].isna().sum()) for column in available_prices
    }
    has_null_prices = any(count > 0 for count in null_counts.values())
    results.append(
        _result(
            "prices.non_null",
            not has_null_prices,
            "Required price columns contain no null values."
            if not has_null_prices
            else "Price columns contain null values.",
            details={"null_counts": null_counts},
        )
    )

    invalid_counts: dict[str, int] = {}
    for column in available_prices:
        numeric = pd.to_numeric(data[column], errors="coerce")
        invalid_counts[column] = int((~np.isfinite(numeric) | (numeric <= 0)).sum())
    has_invalid_prices = any(count > 0 for count in invalid_counts.values())
    results.append(
        _result(
            "prices.finite_positive",
            not has_invalid_prices,
            "Price values are finite and positive."
            if not has_invalid_prices
            else "Price columns contain non-finite or non-positive values.",
            details={"invalid_counts": invalid_counts},
        )
    )

    ohlc_columns = {"Open", "High", "Low", "Close"}
    if ohlc_columns.issubset(data.columns):
        valid_rows = data.loc[:, sorted(ohlc_columns)].notna().all(axis=1)
        usable = data.loc[valid_rows]
        violations = {
            "high_below_low": int((usable["High"] < usable["Low"]).sum()),
            "high_below_open": int((usable["High"] < usable["Open"]).sum()),
            "high_below_close": int((usable["High"] < usable["Close"]).sum()),
            "low_above_open": int((usable["Low"] > usable["Open"]).sum()),
            "low_above_close": int((usable["Low"] > usable["Close"]).sum()),
        }
        relationships_valid = not any(violations.values())
        message = (
            "OHLC relationships are internally consistent."
            if relationships_valid
            else "OHLC relationships contain impossible values."
        )
    else:
        violations = {}
        relationships_valid = True
        message = "OHLC relationship checks are not applicable to absent optional fields."
    results.append(
        _result(
            "prices.ohlc_relationships",
            relationships_valid,
            message,
            details={"violations": violations},
        )
    )
    return tuple(results)


def normalize_signal_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series.dtype):
        return series
    if not series.isna().any() and set(series.unique()).issubset({0, 1, False, True}):
        return series.astype(bool)
    return series


def normalize_signals(signals: SignalResult) -> SignalResult:
    return SignalResult(
        entries=normalize_signal_series(signals.entries),
        exits=normalize_signal_series(signals.exits),
        short_entries=(
            normalize_signal_series(signals.short_entries)
            if signals.short_entries is not None
            else None
        ),
        short_exits=(
            normalize_signal_series(signals.short_exits)
            if signals.short_exits is not None
            else None
        ),
        parameters=dict(signals.parameters),
        metadata=dict(signals.metadata),
    )


def _present_signals(signals: SignalResult) -> dict[str, pd.Series]:
    values = {"entries": signals.entries, "exits": signals.exits}
    if signals.short_entries is not None:
        values["short_entries"] = signals.short_entries
    if signals.short_exits is not None:
        values["short_exits"] = signals.short_exits
    return values


def validate_signals(
    data: pd.DataFrame,
    signals: SignalResult,
    execution: ExecutionConfig,
) -> tuple[ValidationResult, ...]:
    present = _present_signals(signals)
    length_failures = {
        name: len(series) for name, series in present.items() if len(series) != len(data)
    }
    index_failures = [
        name for name, series in present.items() if not series.index.equals(data.index)
    ]
    null_counts = {name: int(series.isna().sum()) for name, series in present.items()}
    non_boolean = [
        name
        for name, series in present.items()
        if not pd.api.types.is_bool_dtype(series.dtype)
    ]
    short_pair_valid = (signals.short_entries is None) == (signals.short_exits is None)
    direction_valid = True
    if execution.direction == "longonly":
        direction_valid = not any(
            bool(series.any())
            for series in (signals.short_entries, signals.short_exits)
            if series is not None and not series.isna().any()
        )
    elif execution.direction == "shortonly":
        direction_valid = not bool(signals.entries.any() or signals.exits.any())

    return (
        _result(
            "signals.length",
            not length_failures,
            "Signal lengths match market data."
            if not length_failures
            else "Signal lengths do not match market data.",
            details={"invalid_lengths": length_failures, "data_length": len(data)},
        ),
        _result(
            "signals.index",
            not index_failures,
            "Signal indexes exactly match market data."
            if not index_failures
            else "Signal indexes do not exactly match market data.",
            details={"invalid_series": index_failures},
        ),
        _result(
            "signals.non_null",
            not any(null_counts.values()),
            "Signals contain no null values."
            if not any(null_counts.values())
            else "Signals contain null values.",
            details={"null_counts": null_counts},
        ),
        _result(
            "signals.boolean",
            not non_boolean,
            "Signals have boolean dtype."
            if not non_boolean
            else "Signals cannot be safely normalized to boolean dtype.",
            details={"invalid_series": non_boolean},
        ),
        _result(
            "signals.structure",
            short_pair_valid,
            "Long and short signal structures are internally consistent."
            if short_pair_valid
            else "Short entry and exit signals must either both be present or both absent.",
        ),
        _result(
            "execution.direction_signals",
            direction_valid,
            "Signal types are compatible with configured direction."
            if direction_valid
            else "Signal types contradict configured direction.",
        ),
    )


def validate_execution(
    data: pd.DataFrame,
    raw: SignalResult,
    aligned: SignalResult,
    execution: ExecutionConfig,
) -> tuple[ValidationResult, ...]:
    price_field_exists = execution.execution_price_field in data.columns
    enough_rows = execution.mode != "next_bar_open" or len(data) >= 2
    price_available = True
    missing_execution_rows: list[str] = []
    if price_field_exists:
        active = aligned.entries | aligned.exits
        if aligned.short_entries is not None:
            active = active | aligned.short_entries
        if aligned.short_exits is not None:
            active = active | aligned.short_exits
        price = pd.to_numeric(data[execution.execution_price_field], errors="coerce")
        invalid = price.isna() | ~np.isfinite(price) | (price <= 0)
        missing_execution_rows = [str(value) for value in data.index[active & invalid]]
        price_available = not missing_execution_rows

    exact_alignment = True
    if execution.mode == "next_bar_open":
        for name, raw_series in _present_signals(raw).items():
            aligned_series = _present_signals(aligned).get(name)
            expected = raw_series.shift(1, fill_value=False).astype(bool)
            if aligned_series is None or not aligned_series.equals(expected):
                exact_alignment = False
                break
    elif execution.mode == "same_bar_close":
        exact_alignment = all(
            aligned_series.equals(raw_series)
            for name, raw_series in _present_signals(raw).items()
            if (aligned_series := _present_signals(aligned).get(name)) is not None
        ) and set(_present_signals(raw)) == set(_present_signals(aligned))
    else:
        exact_alignment = False

    assumption_failures: list[str] = []
    expected_price = {
        "next_bar_open": "Open",
        "same_bar_close": "Close",
    }.get(execution.mode)
    if expected_price is None:
        assumption_failures.append("unsupported execution mode")
    elif execution.execution_price_field != expected_price:
        assumption_failures.append("execution mode and price field mismatch")
    if execution.signal_timing != "completed_bar_close":
        assumption_failures.append("unsupported signal timing")
    if execution.position_sizing not in {"all_available_cash", "fixed_units"}:
        assumption_failures.append("unsupported position sizing")
    if execution.position_sizing == "fixed_units" and (
        not np.isfinite(execution.order_size) or execution.order_size <= 0
    ):
        assumption_failures.append("fixed-unit size must be positive and finite")
    if execution.position_sizing == "all_available_cash" and not np.isinf(
        execution.order_size
    ):
        assumption_failures.append("all-available-cash size must be infinite")
    if execution.direction not in {"longonly", "shortonly", "both"}:
        assumption_failures.append("unsupported direction")
    if execution.initial_cash <= 0:
        assumption_failures.append("initial cash must be positive")
    if execution.fees < 0 or execution.slippage < 0:
        assumption_failures.append("fees and slippage must be non-negative")
    if execution.fixed_fee_per_contract_per_side < 0:
        assumption_failures.append("fixed fee must be non-negative")
    if execution.slippage_points < 0 or execution.slippage_ticks < 0:
        assumption_failures.append("absolute slippage must be non-negative")
    if execution.slippage_points and execution.slippage_ticks:
        assumption_failures.append("slippage cannot use points and ticks together")
    if execution.slippage and (
        execution.slippage_points or execution.slippage_ticks
    ):
        assumption_failures.append(
            "percentage and absolute slippage cannot be combined"
        )
    if execution.slippage_ticks and (
        execution.tick_size is None
        or not np.isfinite(execution.tick_size)
        or execution.tick_size <= 0
    ):
        assumption_failures.append("tick slippage requires positive tick size")
    if (
        execution.fixed_fee_per_contract_per_side
        and execution.position_sizing != "fixed_units"
    ):
        assumption_failures.append("fixed fees require fixed-unit sizing")
    if execution.leverage <= 0:
        assumption_failures.append("leverage must be positive")
    if not np.isfinite(execution.price_multiplier) or execution.price_multiplier <= 0:
        assumption_failures.append("price multiplier must be positive and finite")
    if not isinstance(execution.accumulate, bool):
        assumption_failures.append("accumulate must be boolean")

    mode_message = (
        "Same-bar-close is explicitly marked research comparison only."
        if execution.mode == "same_bar_close"
        else "Completed-close signals execute no earlier than the next bar."
    )
    mode_severity = "warning" if execution.mode == "same_bar_close" else "info"
    return (
        _result(
            "execution.price_column",
            price_field_exists,
            "Execution-price column is present."
            if price_field_exists
            else f"Execution-price column is missing: {execution.execution_price_field}",
        ),
        _result(
            "execution.shift_capacity",
            enough_rows,
            "Dataset has enough rows for configured execution alignment."
            if enough_rows
            else "Next-bar execution requires at least two rows.",
        ),
        _result(
            "execution.price_availability",
            price_available,
            "Every generated order has a usable execution price."
            if price_available
            else "Generated orders target rows without usable execution prices.",
            details={"invalid_rows": missing_execution_rows},
        ),
        _result(
            "lookahead.exact_alignment",
            exact_alignment,
            "Execution signals use the exact configured bar alignment."
            if exact_alignment
            else "Completed-bar signals are not aligned exactly one bar forward.",
        ),
        _result(
            "lookahead.execution_mode",
            execution.mode in {"next_bar_open", "same_bar_close"},
            mode_message,
            pass_severity=mode_severity,
        ),
        _result(
            "assumptions.consistency",
            not assumption_failures,
            "Execution assumptions are internally consistent."
            if not assumption_failures
            else "Execution assumptions are contradictory or unsupported.",
            details={"failures": assumption_failures},
        ),
    )
