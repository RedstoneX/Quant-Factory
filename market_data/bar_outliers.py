"""Flag suspect one-minute bars (bad prints, one-bar spikes) by a published rule.

Method: the "advanced" outlier rule of ``rmOutliersTrades`` in the R package
highfrequency (Boudt and Cornelissen), which extends Barndorff-Nielsen, Hansen,
Lunde and Shephard (2009), "Realised kernels in practice: trades and quotes",
Econometrics Journal 12(3). Replicated from
https://raw.githubusercontent.com/jonathancornelissen/highfrequency/master/R/dataHandling.R
(rmOutliersTrades) and R/internalDataHandling.R (rollingMedianInclEnds), package
highfrequency 1.0.2 (DESCRIPTION dated 2025-12-06); window = 50, maxi = 10.

What the source does, and what this module copies from it:
- Rows are grouped by (calendar date, symbol); the rolling medians restart each date.
  Here the date is the New York calendar date and every session of that date is one
  sequence. The source's MAD is one number per date, not a rolling MAD: ``mad(PRICE)``
  over that date, i.e. 1.4826 * median(|x - median(x)|).
- criterion = the smallest of three distances |x - median| where the median is taken over
  (1) the centred window of 50 neighbours excluding the value itself (25 each side),
  (2) the 50 preceding values, (3) the 50 following values.
- A value is removed when criterion >= maxi * MAD (the source keeps ``criterion < maxi * MAD``).
- Window edges: the centred window shrinks at both ends of a date (plain median, even counts
  averaged); the preceding window expands from one value at the start (the first value has no
  preceding window); interior windows use RcppRoll's weighted median, which for 50 equal weights
  is the LOWER of the two middle values (RcppRoll 0.4.0, src/RcppRoll.cpp, weighted_median).
- Quirk copied on purpose: in ``rollingMedianInclEnds`` the "following" window for the last 49
  positions of a date is ``x[(i - window):n]`` (it reaches back and contains the value itself),
  not the following values. The last 49 positions of a date therefore get a more lenient
  "following" median; the other two medians still apply.
- Zero MAD (every value on a date identical) makes every bar of that date flagged, as in the source.
  A date with a single bar has no criterion and is not flagged.

Applied separately to high, low and close; a bar is suspect if any is flagged. Pure, vectorised
within each date, no state, original prices are never edited.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

WINDOW = 50
MAXI = 10
MAD_CONSTANT = 1.4826  # R's mad() default scale
SUSPECT_COLUMNS = ("high", "low", "close")
MARKET_TIMEZONE = "America/New_York"
METHOD = (
    "highfrequency::rmOutliersTrades type=advanced window=50 maxi=10 (Barndorff-Nielsen et al. 2009), "
    "per New York date, on high/low/close"
)


def _row_medians(rows: np.ndarray, full: slice) -> np.ndarray:
    """Median of each row. Rows inside ``full`` hold no padding and take the lower median
    (RcppRoll weighted median); the others may hold NaN padding and take the plain median."""
    count = rows.shape[0]
    result = np.full(count, np.nan)
    start, stop = (full.start or 0), min(full.stop, count)
    if stop > start:
        result[start:stop] = np.partition(rows[start:stop], (rows.shape[1] - 1) // 2, axis=1)[
            :, (rows.shape[1] - 1) // 2
        ]
    edge = np.ones(count, dtype=bool)
    edge[start : max(start, stop)] = False
    if edge.any():
        picked = rows[edge]
        ordered = np.sort(picked, axis=1)  # NaN padding sorts last
        valid = (~np.isnan(picked)).sum(axis=1)
        position = np.arange(len(picked))
        lower = ordered[position, np.maximum((valid - 1) // 2, 0)]
        upper = ordered[position, np.maximum(valid // 2, 0)]
        edge_values = (lower + upper) / 2
        edge_values[valid == 0] = np.nan
        result[edge] = edge_values
    return result


def _criterion(values: np.ndarray, window: int) -> np.ndarray:
    """Smallest distance to the centred, preceding and following medians for one date."""
    count, half = len(values), window // 2
    nan = np.nan

    padded = np.concatenate([np.full(half, nan), values, np.full(half, nan)])
    centre_rows = np.delete(sliding_window_view(padded, window + 1), half, axis=1)
    centre = _row_medians(centre_rows, slice(half, count - half))

    padded = np.concatenate([np.full(window, nan), values])
    trail = _row_medians(sliding_window_view(padded, window)[:count], slice(window, count))

    padded = np.concatenate([values, np.full(window, nan)])
    follow = _row_medians(sliding_window_view(padded, window + 1)[:count, 1:], slice(0, count - window))
    quirk_start = max(count - window, 0)
    if count - 1 > quirk_start:  # source's end handling: x[(i - window):n], see module docstring
        padded = np.concatenate([np.full(window, nan), values, np.full(2 * window, nan)])
        rows = sliding_window_view(padded, 2 * window)[quirk_start : count - 1]
        follow[quirk_start : count - 1] = _row_medians(rows, slice(0, 0))
    follow[count - 1] = nan

    distances = np.abs(values[None, :] - np.vstack([centre, trail, follow]))
    with np.errstate(all="ignore"):
        return np.fmin.reduce(distances, axis=0)  # NaN only when every median is NaN


def _flag_column(values: np.ndarray, bounds: np.ndarray, window: int, maxi: float) -> np.ndarray:
    flags = np.zeros(len(values), dtype=bool)
    for start, stop in zip(bounds[:-1], bounds[1:]):
        day = values[start:stop]
        mad = MAD_CONSTANT * np.median(np.abs(day - np.median(day)))
        with np.errstate(invalid="ignore"):
            flags[start:stop] = _criterion(day, window) >= maxi * mad
    return flags


def flag_suspect_bars(
    bars: pd.DataFrame, *, window: int = WINDOW, maxi: float = MAXI
) -> tuple[pd.Series, dict[str, int]]:
    """Return (boolean Series aligned to ``bars``, counts) for suspect bars.

    ``bars`` needs a tz-aware ``timestamp`` column plus ``high``, ``low`` and ``close``.
    Counts hold one entry per price column and ``any`` for bars suspect on at least one.
    """
    if window % 2:
        raise ValueError("window must be even (as in the source)")
    if bars.empty:
        return pd.Series(False, index=bars.index, name="suspect_bar"), {**dict.fromkeys(SUSPECT_COLUMNS, 0), "any": 0}
    timestamps = pd.DatetimeIndex(pd.to_datetime(bars["timestamp"], utc=True))
    order = np.argsort(timestamps.asi8, kind="stable")
    in_order = bool((order == np.arange(len(order))).all())
    days = timestamps.tz_convert(MARKET_TIMEZONE).tz_localize(None).floor("D").asi8
    days = days if in_order else days[order]
    bounds = np.concatenate([[0], np.flatnonzero(np.diff(days)) + 1, [len(days)]])
    per_column: dict[str, np.ndarray] = {}
    for column in SUSPECT_COLUMNS:
        values = bars[column].to_numpy(dtype="float64")
        values = values if in_order else values[order]
        flags = _flag_column(values, bounds, window, maxi)
        per_column[column] = flags if in_order else flags[np.argsort(order)]
    combined = np.logical_or.reduce(list(per_column.values()))
    counts = {column: int(flags.sum()) for column, flags in per_column.items()}
    counts["any"] = int(combined.sum())
    return pd.Series(combined, index=bars.index, name="suspect_bar"), counts
