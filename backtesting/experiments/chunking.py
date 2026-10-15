"""Simulate a parameter sweep in column chunks so only one chunk's portfolio is alive."""

from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from backtesting.experiments.metrics import extract_sweep_metrics

SWEEP_CHUNK_SETTINGS = 50


def setting_portfolio(portfolio: Any, position: int) -> Any:
    """One setting's column of a one-pass portfolio (VectorBT PRO pf.iloc[:, i]).

    An engine object without column indexing holds a single setting and is returned as is.
    """
    indexer = getattr(portfolio, "iloc", None)
    return portfolio if indexer is None else indexer[:, position]


def value_columns(portfolio: Any, count: int) -> list[np.ndarray | None]:
    """Each setting's value from one read of the sweep's value; None if the engine has none."""
    value = getattr(portfolio, "value", None)
    value = value() if callable(value) else value
    if not isinstance(value, pd.DataFrame) or value.shape[1] != count:
        return [None] * count
    return [value.iloc[:, position].to_numpy(dtype=float) for position in range(count)]


SWEEP_CHUNK_SETTINGS = 50


def simulate_in_chunks(
    data: pd.DataFrame,
    aligned_settings: Sequence[Any],
    config: Any,
    construct: Callable[..., Any],
    *,
    keep_portfolios: bool,
    chunk_settings: int | None = None,
) -> tuple[list[dict[str, float | int]], list[np.ndarray | None], list[Any]]:
    """Simulate settings in column chunks; keep only each setting's metrics and value.

    Settings are independent columns (no cash sharing), so a chunk's metrics equal the same
    columns of one all-settings call. Only the chunk's portfolio is alive at a time, which caps
    peak memory; the portfolio is retained only when a caller observes it.
    """
    size = chunk_settings or SWEEP_CHUNK_SETTINGS
    metrics: list[dict[str, float | int]] = []
    values: list[np.ndarray | None] = []
    observed: list[Any] = []
    for start in range(0, len(aligned_settings), size):
        chunk = tuple(aligned_settings[start : start + size])
        sweep = construct(data, chunk, config)
        metrics += extract_sweep_metrics(sweep, len(chunk), data=data, config=config)
        values += value_columns(sweep, len(chunk))
        if keep_portfolios:
            observed += [setting_portfolio(sweep, position) for position in range(len(chunk))]
    return metrics, values, observed
