"""Full-history signals for one evaluation window.

Walk-forward and out-of-sample runs evaluate many windows of one history. Signals are
generated once per parameter set on the full history (``signal_cache``), so indicators keep
their warm-up at every window start; only the window's bars are then simulated and scored.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Sequence

import pandas as pd
from cachetools import LRUCache

from strategies.models import SignalResult

SIGNAL_SERIES = (
    "entries", "exits", "short_entries", "short_exits", "stop_loss", "take_profit", "trailing_stop",
    "trailing_threshold", "td_stop", "session_id",
)

# Signal-cache budget [measured, QQQ 1-minute, 1.05M bars, 2.5 GB cap, 2 settings per chunk]:
# 2,500 MB cap - 1,400 MB base (data + imports) - 230 MB chunk transient (~116 MB/setting x 2)
# - 840 MB Luck-test value lines (8.4 MB/setting x 100) = 30 MB.
SIGNAL_CACHE_BYTES = (2_500 - 1_400 - 230 - 840) * 1_000_000


def _signal_key(normalized: dict[str, Any]) -> str:
    return repr(sorted(normalized.items()))


def generate_signals_once(
    strategy: Any,
    data: pd.DataFrame,
    accepted: Sequence[dict[str, Any]],
    signal_cache: dict[str, SignalResult] | None,
) -> list[SignalResult]:
    """Signals for every setting, reusing those still in ``signal_cache`` for this history.

    A bounded cache may evict entries at any time, so fresh signals are returned directly and
    the cache is only read for hits.
    """
    cache = {} if signal_cache is None else signal_cache
    keys = [_signal_key(normalized) for normalized in accepted]
    hits = {key: cache[key] for key in keys if key in cache}
    missing = [normalized for normalized, key in zip(accepted, keys) if key not in hits]
    batch = getattr(type(strategy), "iter_signals_batch", None)
    if batch is None or not missing:
        fresh = [strategy.generate_signals(data, normalized) for normalized in missing]
    else:
        fresh = list(batch(strategy, data, missing))
    generated = dict(zip((_signal_key(normalized) for normalized in missing), fresh))
    for key, signals in generated.items():
        try:
            cache[key] = signals
        except ValueError:  # cachetools: one setting is larger than the whole budget; not cached
            pass
    return [hits[key] if key in hits else generated[key] for key in keys]


def _signal_bytes(signals: SignalResult) -> int:
    return sum(
        int(getattr(signals, name).nbytes) for name in SIGNAL_SERIES if getattr(signals, name) is not None
    )


def new_signal_cache(maxsize: int | None = None) -> LRUCache:
    """Full-history signals shared by every window of one run, bounded by bytes (cachetools LRU)."""
    return LRUCache(maxsize=SIGNAL_CACHE_BYTES if maxsize is None else maxsize, getsizeof=_signal_bytes)


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
