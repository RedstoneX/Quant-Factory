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
- DELIBERATE DEPARTURE from the source: the threshold is maxi * max(MAD, 0.01), not maxi * MAD.
  The source flags every bar when a date's MAD is zero or tiny (thin days where most prints sit on
  one price). US stocks priced at $1 or more quote in whole cents (SEC Regulation NMS Rule 612,
  17 CFR 242.612), so a one-cent MAD floor means no price can be flagged for moving less than
  ten ticks (10 cents).
- A date with a single bar has no criterion and is not flagged.

Applied separately to high, low and close; a bar is suspect if any is flagged. Pure, vectorised
within each date, no state, original prices are never edited.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.ndimage import rank_filter

WINDOW = 50
MAXI = 10
MAD_CONSTANT = 1.4826  # R's mad() default scale
MIN_MAD = 0.01  # one cent: the minimum quote increment at $1 or more (Reg NMS Rule 612)
SUSPECT_COLUMNS = ("high", "low", "close")
MARKET_TIMEZONE = "America/New_York"
# Edge rows gathered per batch: each batch holds about eight (rows x 100) float/int arrays,
# so 10,000 rows stay near 60 MB (50,000 rows reached about 300 MB on SPY's 2.2M bars).
EDGE_BATCH_ROWS = 10_000
METHOD = (
    "highfrequency::rmOutliersTrades type=advanced window=50 maxi=10 (Barndorff-Nielsen et al. 2009), "
    "MAD floored at one cent, per New York date, on high/low/close"
)


def _edge_medians(values: np.ndarray, rows: np.ndarray, offsets: np.ndarray, first: np.ndarray, stop: np.ndarray):
    """Plain median (even counts averaged) of ``values[row + offset]`` clipped to each row's date.

    Rows are gathered for all dates at once; positions outside [first, stop) become NaN and
    the sorted window then gives the plain median of what remains (no values gives NaN)."""
    result = np.full(len(rows), np.nan)
    for lo in range(0, len(rows), EDGE_BATCH_ROWS):  # bounded memory
        part = rows[lo : lo + EDGE_BATCH_ROWS]
        index = part[:, None] + offsets[None, :]
        inside = (index >= first[part, None]) & (index < stop[part, None])
        picked = np.where(inside, values[np.clip(index, 0, len(values) - 1)], np.nan)
        ordered = np.sort(picked, axis=1)  # numpy.sort puts the NaN padding last
        valid = (~np.isnan(picked)).sum(axis=1)
        row = np.arange(len(part))
        middle = (ordered[row, np.maximum((valid - 1) // 2, 0)] + ordered[row, np.maximum(valid // 2, 0)]) / 2
        middle[valid == 0] = np.nan
        result[lo : lo + EDGE_BATCH_ROWS] = middle
    return result


def _criterion(values: np.ndarray, first: np.ndarray, stop: np.ndarray, window: int) -> np.ndarray:
    """Smallest distance to the centred, preceding and following medians, all dates at once.

    ``first``/``stop`` give each row's date bounds. Interior windows (no padding) use
    scipy.ndimage.rank_filter, an exact order statistic (RcppRoll's lower weighted median is
    rank (window - 1) // 2); rows whose window touches a date edge take the plain median of the
    date-clipped window."""
    count, half = len(values), window // 2
    position = np.arange(count)

    # (1) centred window of ``window`` neighbours excluding the value itself: lower median of the
    # window+1 rolling values with the value removed = s[half] if value > s[half-1] else s[half].
    low = rank_filter(values, half - 1, size=window + 1, mode="nearest")
    high = rank_filter(values, half, size=window + 1, mode="nearest")
    centre = np.where(values <= low, high, low)
    del low, high  # full-length temporaries: free before the next ones are built
    edge = ~((position - half >= first) & (position + half < stop))
    rows = position[edge]
    offsets = np.delete(np.arange(-half, half + 1), half)
    centre[rows] = _edge_medians(values, rows, offsets, first, stop)

    # (2) the ``window`` preceding values.
    lower = rank_filter(values, (window - 1) // 2, size=window, mode="nearest", origin=window // 2 - 1)  # ends at i
    trail = np.full(count, np.nan)
    trail[1:] = lower[:-1]
    rows = position[~(position - window >= first)]
    trail[rows] = _edge_medians(values, rows, np.arange(-window, 0), first, stop)

    # (3) the ``window`` following values; the last ``window`` rows copy the source's quirk
    # (window reaches back and holds the value itself, x[(i - window):n]) and the last row has none.
    follow = np.full(count, np.nan)
    if count > window:
        follow[:-window] = lower[window:]
    quirk = (position >= np.maximum(stop - window, first)) & (position < stop - 1)
    follow[quirk] = _edge_medians(values, position[quirk], np.arange(-window, window), first, stop)
    follow[position == stop - 1] = np.nan
    del lower, quirk, edge, rows, position

    # Pairwise fmin equals np.fmin.reduce over the stacked distances, without the 3 x n stack.
    with np.errstate(all="ignore"):
        nearest = np.fmin(np.abs(values - centre), np.abs(values - trail))
        return np.fmin(nearest, np.abs(values - follow), out=nearest)  # NaN only when every median is NaN


def _flag_column(values: np.ndarray, bounds: np.ndarray, window: int, maxi: float) -> np.ndarray:
    sizes = np.diff(bounds)
    first = np.repeat(bounds[:-1], sizes)
    stop = np.repeat(bounds[1:], sizes)
    date = pd.Series(np.repeat(np.arange(len(sizes)), sizes))
    by_date = pd.Series(values).groupby(date)
    deviation = (pd.Series(values) - by_date.transform("median")).abs()
    mad = (MAD_CONSTANT * deviation.groupby(date).transform("median")).clip(lower=MIN_MAD).to_numpy()
    del date, by_date, deviation, sizes
    with np.errstate(invalid="ignore"):
        return _criterion(values, first, stop, window) >= maxi * mad


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
