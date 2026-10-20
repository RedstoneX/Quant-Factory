"""Simulate a parameter sweep in VectorBT PRO mono-chunks so only one chunk is alive at a time.

``vbt.parameterized(mono_chunk_len=...)`` splits the settings into chunks and calls the chunk
function once per chunk with that chunk's settings as a list. Each chunk prepares its own
inputs (signals, validation, window cut), simulates them in one ``Portfolio.from_signals``
call, and keeps only what callers read back: metrics, the value series and, when observed,
the portfolio. Peak memory therefore follows the chunk size, not the number of settings.
"""

from itertools import chain
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from backtesting.experiments.metrics import extract_sweep_metrics
from backtesting.vectorbt_runtime import require_vectorbtpro

# Settings per chunk. Measured on QQQ 1-minute (1.05M bars): see README "How settings are tested".
SWEEP_CHUNK_SETTINGS = 10


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


def _as_is(data: pd.DataFrame, chunk: Sequence[Any]) -> tuple[pd.DataFrame, list[Any], list[Any]]:
    return data, list(chunk), [None] * len(chunk)


def _simulate_chunk(
    positions: list[int],
    settings: Sequence[Any],
    data: pd.DataFrame,
    config: Any,
    construct: Callable[..., Any],
    prepare: Callable[..., tuple[pd.DataFrame, list[Any], list[Any]]],
    keep_portfolios: bool,
) -> tuple[list, list, list, list]:
    """One mono-chunk: prepare -> one from_signals call -> metrics, values, portfolios."""
    chunk_data, aligned, extras = prepare(data, [settings[position] for position in positions])
    sweep = construct(chunk_data, tuple(aligned), config)
    metrics = extract_sweep_metrics(sweep, len(aligned), data=chunk_data, config=config)
    values = value_columns(sweep, len(aligned))
    observed = [setting_portfolio(sweep, position) for position in range(len(aligned))] if keep_portfolios else []
    # VectorBT PRO 2026.10.5 memoises get_func_signature with an unbounded functools.cache keyed
    # by bound methods (e.g. the returns accessor's sharpe_ratio), which pins each chunk's returns
    # and benchmark returns for the whole run (~17 MB per 1-minute setting, measured). Clearing
    # that memo only drops signatures; it never changes a result. Remove once VBT bounds it.
    from vectorbtpro.utils.parsing import get_func_signature

    get_func_signature.cache_clear()
    return metrics, values, observed, extras


def simulate_in_chunks(
    data: pd.DataFrame,
    settings: Sequence[Any],
    config: Any,
    construct: Callable[..., Any],
    *,
    keep_portfolios: bool,
    chunk_settings: int | None = None,
    prepare: Callable[..., tuple[pd.DataFrame, list[Any], list[Any]]] = _as_is,
) -> tuple[list[dict[str, float | int]], list[np.ndarray | None], list[Any], list[Any]]:
    """Simulate settings in VectorBT PRO mono-chunks; keep only each setting's metrics and value.

    ``prepare(data, chunk) -> (data, aligned signals, extras)`` turns a chunk of settings into
    simulation inputs; by default the settings already are aligned signals. Settings are
    independent columns (no cash sharing), so a chunk's metrics equal the same columns of one
    all-settings call. Returns metrics, values, observed portfolios and ``prepare``'s extras,
    each in settings order.
    """
    if not settings:
        return [], [], [], []
    vbt = require_vectorbtpro()
    run = vbt.parameterized(
        _simulate_chunk,
        mono_chunk_len=chunk_settings or SWEEP_CHUNK_SETTINGS,
        merge_func=None,
        execute_kwargs=dict(show_progress=False),
    )
    chunks = run(vbt.Param(list(range(len(settings)))), settings, data, config, construct, prepare, keep_portfolios)
    return tuple(list(chain.from_iterable(part)) for part in zip(*chunks))  # type: ignore[return-value]
