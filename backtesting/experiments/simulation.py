"""Simulate many parameter settings: one wide VectorBT run or one-by-one.

The batch path column-stacks every setting's aligned signals, stop levels and
execution prices (one column per setting) and runs ONE simulation; each
setting is then read back as its own column. The one-by-one path is the
reference the batch path must reproduce exactly.
"""

from typing import Any, Callable

import numpy as np
import pandas as pd

from backtesting.experiments.models import ExperimentConfig
from strategies.models import SignalResult

SIMULATION_MODES = ("batch", "one_by_one")
# One-by-one stays the default until the batch path is proven identical on
# the real engine (see the batch smoke script); flipping it is this one word.
DEFAULT_SIMULATION = "one_by_one"
# VectorBT PRO engine options for the one wide (column-per-setting)
# simulation. Columns are independent (no grouping or cash sharing), so
# column-parallel Numba execution cannot change any column's result.
BATCH_ENGINE_OPTIONS: dict[str, Any] = {"jitted": {"parallel": True}}


def _setting_label(index: int) -> str:
    return f"setting_{index:06d}"


def _stack(
    series: list[pd.Series | None], labels: list[str], index: pd.Index, fill: Any
) -> pd.DataFrame | None:
    if all(item is None for item in series):
        return None
    columns = [
        item if item is not None else pd.Series(fill, index=index)
        for item in series
    ]
    return pd.concat(columns, axis=1, keys=labels)


def _value_column(value: Any) -> Any:
    value = value() if callable(value) else value
    if isinstance(value, pd.DataFrame) and value.shape[1] == 1:
        value = value.iloc[:, 0]
    return value.to_numpy(dtype=float) if isinstance(value, pd.Series) else None


def _value_matrix(columns: list[Any]) -> Any:
    """Stack per-setting value arrays as (bars x settings); None if any missing."""
    if not columns or any(column is None for column in columns):
        return None
    return np.column_stack(columns)


def simulate_one_by_one(
    data: pd.DataFrame,
    aligned: list[SignalResult],
    config: ExperimentConfig,
    construct: Callable[..., Any],
    build_price: Callable[..., pd.Series],
) -> tuple[list[Any], Any]:
    """Reference path: one VectorBT simulation per setting."""
    _ = build_price
    portfolios = [construct(data, item, config) for item in aligned]
    return portfolios, _value_matrix(
        [_value_column(getattr(item, "value", None)) for item in portfolios]
    )


def simulate_batch(
    data: pd.DataFrame,
    aligned: list[SignalResult],
    config: ExperimentConfig,
    construct: Callable[..., Any],
    build_price: Callable[..., pd.Series],
) -> tuple[list[Any], Any]:
    """Simulate every setting as one column of one wide VectorBT simulation.

    Settings with and without bar stops run in separate wide calls because
    stop arguments (open/high/low, stop prices) apply to the whole call.
    """
    if len(aligned) <= 1:
        return simulate_one_by_one(data, aligned, config, construct, build_price)
    groups: dict[bool, list[int]] = {}
    for position, item in enumerate(aligned):
        has_stops = item.stop_loss is not None or item.take_profit is not None
        groups.setdefault(has_stops, []).append(position)
    portfolios: list[Any] = [None] * len(aligned)
    values: list[Any] = [None] * len(aligned)
    for positions in groups.values():
        members = [aligned[position] for position in positions]
        labels = [_setting_label(position) for position in positions]
        wide = construct(
            data,
            _wide_signals(data, members, labels, config),
            config,
            prices=[
                build_price(data, item, config.execution) for item in members
            ],
            labels=labels,
        )
        wide_value = getattr(wide, "value", None)
        wide_value = wide_value() if callable(wide_value) else wide_value
        for position, label in zip(positions, labels):
            portfolios[position] = wide[label]
            if isinstance(wide_value, pd.DataFrame):
                values[position] = wide_value[label].to_numpy(dtype=float)
    return portfolios, _value_matrix(values)


def _wide_signals(
    data: pd.DataFrame,
    members: list[SignalResult],
    labels: list[str],
    config: ExperimentConfig,
) -> SignalResult:
    index = data.index
    wide = {
        name: _stack([getattr(item, name) for item in members], labels, index, False)
        for name in ("entries", "exits", "short_entries", "short_exits")
    }
    if config.execution.direction == "both":
        for name in ("short_entries", "short_exits"):
            if wide[name] is None:
                wide[name] = pd.DataFrame(False, index=index, columns=labels)
    stops = {
        name: _stack(
            [getattr(item, name) for item in members], labels, index, float("nan")
        )
        for name in ("stop_loss", "take_profit")
    }
    return SignalResult(parameters={}, **wide, **stops)  # type: ignore[arg-type]
