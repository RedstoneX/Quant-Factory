"""Full-history signals for one evaluation window.

Walk-forward and out-of-sample runs evaluate many windows of one history. Signals are
generated once per parameter set on the full history (``signal_cache``), so indicators keep
their warm-up at every window start; only the window's bars are then simulated and scored.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Sequence

import pandas as pd

from strategies.models import SignalResult

SIGNAL_SERIES = (
    "entries", "exits", "short_entries", "short_exits", "stop_loss", "take_profit", "trailing_stop",
    "trailing_threshold", "td_stop",
)


def _signal_key(normalized: dict[str, Any]) -> str:
    return repr(sorted(normalized.items()))


def generate_signals_once(
    strategy: Any,
    data: pd.DataFrame,
    accepted: Sequence[dict[str, Any]],
    signal_cache: dict[str, SignalResult] | None,
) -> list[SignalResult]:
    """Signals for every setting, reusing those already in ``signal_cache`` for this history."""
    cache = {} if signal_cache is None else signal_cache
    missing = [normalized for normalized in accepted if _signal_key(normalized) not in cache]
    batch = getattr(type(strategy), "iter_signals_batch", None)
    if batch is None or not missing:
        fresh = (strategy.generate_signals(data, normalized) for normalized in missing)
    else:
        fresh = batch(strategy, data, missing)
    cache.update(zip((_signal_key(normalized) for normalized in missing), fresh))
    return [cache[_signal_key(normalized)] for normalized in accepted]


def signals_in_window(aligned: SignalResult, index: pd.Index) -> SignalResult:
    """Cut full-history signals to one evaluation window (pandas ``.loc``)."""
    return replace(
        aligned,
        **{
            name: getattr(aligned, name).loc[index]
            for name in SIGNAL_SERIES
            if getattr(aligned, name) is not None
        },
    )


def cut_to_window(
    data: pd.DataFrame,
    settings: list[tuple[dict[str, Any], SignalResult, tuple]],
    evaluation_range: tuple[pd.Timestamp, pd.Timestamp] | None,
) -> tuple[pd.DataFrame, list[tuple[dict[str, Any], SignalResult, tuple]]]:
    """The window's bars and signals; the whole history when no range is given."""
    if evaluation_range is None:
        return data, settings
    window = data.loc[evaluation_range[0] : evaluation_range[1]]
    return window, [
        (normalized, signals_in_window(aligned, window.index), results)
        for normalized, aligned, results in settings
    ]
