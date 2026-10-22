"""Simulate a parameter sweep in column chunks so only one chunk is alive at a time.

Each chunk prepares its own inputs (signals, validation, window cut), simulates them in one
engine call, and keeps only what callers read back: metrics, one closing value per trading day for the Luck test
and, when observed, the portfolio. Nothing bar-level per setting outlives its chunk, so peak
memory follows the chunk size, not the settings count. This module never imports the engine.
"""

from typing import Any, Callable, Sequence

import pandas as pd

from backtesting.experiments.metrics import extract_sweep_metrics

# Settings per chunk, derived per run [measured, QQQ 1-minute, 1.05M bars, 100 settings]:
# a chunk costs ~115 MB per setting while it runs (~110 B per bar per setting); the run's base
# (data, imports) is ~1,400 MB. The 8 B/bar per-setting reserve below was the Luck test's value
# line; since 20 Oct 2026 only daily values are kept, so it is now spare headroom, kept until the
# sizing is re-measured (tests/test_sweep_memory_parity.py pins these chunk sizes).
# chunk budget = 2,500 MB target - 1,400 MB base - bars x 8 B x settings
# settings per chunk = max(1, floor(chunk budget / (bars x 110 B)))
# 1-minute (1.05M bars, 100 settings): (2,500 - 1,400 - 840) MB / 115.5 MB = 2.25 -> 2.
MEMORY_TARGET_BYTES = 2_500_000_000
BASE_BYTES = 1_400_000_000
TRANSIENT_BYTES_PER_BAR = 110
VALUE_BYTES_PER_BAR = 8


def chunk_settings_for(bars: int, settings: int) -> int:
    """Settings per chunk so a run of ``settings`` over ``bars`` bars peaks near the target."""
    budget = MEMORY_TARGET_BYTES - BASE_BYTES - bars * VALUE_BYTES_PER_BAR * settings
    return max(1, budget // max(1, bars * TRANSIENT_BYTES_PER_BAR))


def setting_portfolio(portfolio: Any, position: int) -> Any:
    """One setting's column of a one-pass portfolio (VectorBT PRO pf.iloc[:, i]).

    An engine object without column indexing holds a single setting and is returned as is.
    """
    indexer = getattr(portfolio, "iloc", None)
    return portfolio if indexer is None else indexer[:, position]


def daily_values(portfolio: Any, count: int) -> list[pd.Series | None]:
    """Each setting's closing value per trading day; None if the engine has no value.

    pandas ``resample("1D").last()`` bins by calendar day in the index's own timezone and
    ``dropna(how="all")`` drops days without bars, so daily data comes back unchanged. The Luck
    test (deflated Sharpe, PBO) reads daily returns, its published input (Bailey & Lopez de Prado).
    """
    value = getattr(portfolio, "value", None)
    value = value() if callable(value) else value
    if not isinstance(value, pd.DataFrame) or value.shape[1] != count:
        return [None] * count
    daily = value.astype(float).resample("1D").last().dropna(how="all")
    return [daily.iloc[:, position] for position in range(count)]


def _as_is(data: pd.DataFrame, chunk: Sequence[Any]) -> tuple[pd.DataFrame, list[Any], list[Any]]:
    return data, list(chunk), [None] * len(chunk)


def _no_release() -> None:
    return None


def simulate_in_chunks(
    data: pd.DataFrame,
    settings: Sequence[Any],
    config: Any,
    construct: Callable[..., Any],
    *,
    keep_portfolios: bool,
    chunk_settings: int | None = None,
    prepare: Callable[..., tuple[pd.DataFrame, list[Any], list[Any]]] = _as_is,
    release: Callable[[], None] = _no_release,
) -> tuple[list[dict[str, float | int]], list[pd.Series | None], list[Any], list[Any]]:
    """Simulate settings in column chunks; keep only each setting's metrics and daily value.

    ``prepare(data, chunk) -> (data, aligned signals, extras)`` turns a chunk of settings into
    simulation inputs (by default the settings already are aligned signals), so signals live for
    one chunk only. ``construct`` simulates the chunk in one engine call; ``release()`` then drops
    what the engine keeps after it. Settings are independent columns (no cash sharing), so a
    chunk's metrics equal the same columns of one all-settings call. Returns metrics, daily values,
    daily values, observed portfolios and ``prepare``'s extras, each in settings order.
    """
    size = chunk_settings or chunk_settings_for(len(data), len(settings))
    metrics: list[dict[str, float | int]] = []
    values: list[pd.Series | None] = []
    observed: list[Any] = []
    extras: list[Any] = []
    for start in range(0, len(settings), size):
        chunk_data, aligned, chunk_extras = prepare(data, settings[start : start + size])
        sweep = construct(chunk_data, tuple(aligned), config)
        metrics += extract_sweep_metrics(sweep, len(aligned), data=chunk_data, config=config)
        values += daily_values(sweep, len(aligned))
        if keep_portfolios:
            observed += [setting_portfolio(sweep, position) for position in range(len(aligned))]
        extras += chunk_extras
        del sweep, aligned
        release()
    return metrics, values, observed, extras
