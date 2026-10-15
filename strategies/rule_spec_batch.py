"""Signals of many settings of one rule strategy in one pass over the data.

Setting-independent work is done once per batch: the session split (``pandas.DatetimeIndex.get_indexer`` on
the whole bar grid), the stacked session bars, and every rule node whose value does not depend on a
setting's parameters (one ``RuleEvaluator`` cache shared by all settings, keyed by the node plus the values
of the parameters it refers to, so settings that agree on them share one array).

The flat/long/short state machine runs once per DISTINCT walk input (signal sides, ``after_bars``, the
valid-stop mask), with distinct walks stacked side by side as columns and stepped bar by bar with NumPy
boolean masks, so one step advances every session of every setting together.  Flags and stop levels are
written by integer-array assignment (``numpy`` fancy indexing) instead of one ``Series.at`` per event.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

from rule_language import BAR_MINUTES
from rule_language.validation import STOP_KEYS
from strategies.mes_opening_range_breakout import SESSION_TIMEZONE
from strategies.rule_spec_evaluation import RuleEvaluator, SessionBars, bar_position

_REGULAR_SESSION = pd.Timedelta(hours=6, minutes=30)
EVENTS = ("entry", "exit", "short_entry", "short_exit")
_ENTRY, _EXIT, _SHORT_ENTRY, _SHORT_EXIT = 1, 2, 3, 4
_WALK_COLUMNS = 200_000  # session columns stepped together (about 80 MB of int8 for 390-bar sessions)
_CACHE_BYTES = 500_000_000  # shared node cache budget; the cache is only an accelerator, so it is just cleared


class _BoundedCache(dict):
    """A dict of arrays that empties itself when it grows past ``_CACHE_BYTES``."""

    nbytes = 0

    def __setitem__(self, key: str, value: np.ndarray) -> None:
        size = int(getattr(value, "nbytes", 0))
        if self.nbytes + size > _CACHE_BYTES:
            self.clear()
            self.nbytes = 0
        self.nbytes += size
        super().__setitem__(key, value)


@dataclass(frozen=True)
class PreparedSessions:
    """Full regular sessions of one data frame: their bar positions in the frame and their stacked bars."""

    index: pd.DatetimeIndex
    positions: np.ndarray  # (bars, sessions) integer rows of ``index``
    bars: SessionBars | None
    sessions_in_schedule: int


def traded_session_positions(index: pd.DatetimeIndex, values: np.ndarray, schedule: pd.DataFrame, bar: str) -> np.ndarray:
    """(bars, sessions) rows of full 09:30-16:00 sessions with every bar present, finite and positive."""
    step = pd.Timedelta(minutes=BAR_MINUTES[bar])
    opens = pd.DatetimeIndex(schedule["market_open"]).tz_convert("UTC")
    closes = pd.DatetimeIndex(schedule["market_close"]).tz_convert("UTC")
    regular = (closes - opens == _REGULAR_SESSION) & (
        opens.tz_convert(SESSION_TIMEZONE).strftime("%H:%M") == "09:30"
    )
    count = int(_REGULAR_SESSION / step)
    starts = opens[np.asarray(regular)].asi8
    grid = starts[:, None] + np.arange(count, dtype=np.int64)[None, :] * step.value
    positions = index.get_indexer(pd.DatetimeIndex(grid.reshape(-1), tz="UTC")).reshape(grid.shape)
    present = (positions >= 0).all(axis=1)
    positions = positions[present]
    day_values = values[positions]  # (sessions, bars, fields)
    usable = np.isfinite(day_values).all(axis=(1, 2)) & (day_values > 0).all(axis=(1, 2))
    return np.ascontiguousarray(positions[usable].T)


def prepare_sessions(
    frame: pd.DataFrame, schedule: pd.DataFrame | None, fields: Sequence[str], *, tick_size: float, bar: str
) -> PreparedSessions:
    if schedule is None:
        return PreparedSessions(frame.index, np.empty((0, 0), dtype=np.intp), None, 0)
    values = frame[list(fields)].to_numpy(dtype=float)
    positions = traded_session_positions(frame.index, values, schedule, bar)
    bars = None
    if positions.shape[1]:
        stacked = {name.lower(): np.ascontiguousarray(values[positions, k]) for k, name in enumerate(fields)}
        bars = SessionBars(**stacked, tick_size=float(tick_size), parameters={}, bar=bar)
    return PreparedSessions(frame.index, positions, bars, len(schedule))


def bar_sides(spec: Mapping[str, Any], evaluator: RuleEvaluator) -> np.ndarray:
    """+1/-1 where the first firing signal (condition true, side non-zero) points; else 0."""
    sides = np.zeros(evaluator.shape)
    undecided = np.ones(evaluator.shape, dtype=bool)
    for signal in spec["signals"]:
        side = evaluator.side(signal["side"])
        fired = evaluator.condition(signal["when"]) & (side != 0)
        take = undecided & fired
        sides[take] = side[take]
        undecided &= ~fired
    return sides


def walk_columns(spec: Mapping[str, Any], sides: np.ndarray, after: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Run the flat/long/short state machine down every column at once.

    ``sides`` and ``valid`` are (bars, columns); ``after`` holds one ``after_bars`` per column (inf = none).
    Returns int8 event codes (bars, columns) and the entries skipped per column for an unusable stop distance.
    """
    exit_rules = spec["exit"]
    flat = bar_position(spec["flat_at"], spec["bar"])
    at_time = bar_position(exit_rules["at_time"], spec["bar"]) if "at_time" in exit_rules else None
    opposite = bool(exit_rules["on_opposite_signal"])
    limit = spec["max_trades_per_session"]
    rows, columns = sides.shape
    codes = np.zeros((rows, columns), dtype=np.int8)
    state = np.zeros(columns)
    entry_row = np.full(columns, -1.0)
    taken = np.zeros(columns, dtype=np.int64)
    skipped = np.zeros(columns, dtype=np.int64)
    for row in range(rows):
        side = sides[row]
        holding = state != 0
        leave = holding & ((row - entry_row >= after) | (opposite & (side == -state)))
        if row == flat or row == at_time:
            leave = holding
        codes[row, leave & (state > 0)] = _EXIT
        codes[row, leave & (state < 0)] = _SHORT_EXIT
        state[leave] = 0.0
        if row >= flat:
            continue
        wants = ~holding & (taken < limit) & (side != 0)
        skipped += wants & ~valid[row]
        enter = wants & valid[row]
        codes[row, enter & (side > 0)] = _ENTRY
        codes[row, enter & (side < 0)] = _SHORT_ENTRY
        state[enter] = side[enter]
        entry_row[enter] = row
        taken += enter
    return codes, skipped


@dataclass
class _Setting:
    parameters: dict[str, Any]
    evaluator: RuleEvaluator
    walk: str
    fractions: dict[str, np.ndarray]


def _plan(spec: Mapping[str, Any], prepared: PreparedSessions, parameters: Mapping[str, Any], cache: dict, walks: dict) -> _Setting:
    """Evaluate one setting's rule nodes (through the shared cache) and register its walk input."""
    exit_rules = spec["exit"]
    evaluator = RuleEvaluator(replace(prepared.bars, parameters=dict(parameters)), cache)
    present = [key for key in STOP_KEYS if key in exit_rules]
    fractions = {key: evaluator.distance_fraction(exit_rules[key]) for key in present}
    valid = np.ones(evaluator.shape, dtype=bool)
    with np.errstate(invalid="ignore"):
        for key in present:
            valid &= np.isfinite(fractions[key]) & (fractions[key] > 0)
    after = float(evaluator.count(exit_rules["after_bars"])) if "after_bars" in exit_rules else np.inf
    sides_key = evaluator.key("sides", spec["signals"])
    digest = hashlib.blake2b(np.packbits(valid).tobytes(), digest_size=16).hexdigest()
    walk = f"{sides_key}|{after}|{digest}"
    if walk not in walks:
        walks[walk] = (evaluator.cached("sides", spec["signals"], lambda: bar_sides(spec, evaluator)), after, valid)
    return _Setting(dict(parameters), evaluator, walk, fractions)


def _run_walks(spec: Mapping[str, Any], walks: Mapping[str, tuple[np.ndarray, float, np.ndarray]]) -> dict[str, tuple[np.ndarray, int]]:
    """Step distinct walks together, ``_WALK_COLUMNS`` session columns at a time."""
    results: dict[str, tuple[np.ndarray, int]] = {}
    keys = list(walks)
    sessions = next(iter(walks.values()))[0].shape[1] if walks else 0
    per_chunk = max(1, _WALK_COLUMNS // max(sessions, 1))
    for start in range(0, len(keys), per_chunk):
        chunk = keys[start : start + per_chunk]
        sides = np.hstack([walks[key][0] for key in chunk]).astype(np.int8)
        valid = np.hstack([walks[key][2] for key in chunk])
        after = np.repeat([walks[key][1] for key in chunk], sessions)
        codes, skipped = walk_columns(spec, sides, after, valid)
        for number, key in enumerate(chunk):
            columns = slice(number * sessions, (number + 1) * sessions)
            results[key] = (codes[:, columns], int(skipped[columns].sum()))
    return results


def _signals(prepared: PreparedSessions, setting: _Setting | None, walked: tuple[np.ndarray, int] | None, present: Iterable[str]):
    length = len(prepared.index)
    flags = {name: np.zeros(length, dtype=bool) for name in EVENTS}
    levels = {key: np.full(length, np.nan) for key in present}
    skipped = 0
    if setting is not None and walked is not None:
        codes, skipped = walked
        for code, name in enumerate(EVENTS, start=1):
            flags[name][prepared.positions[codes == code]] = True
        entered = (codes == _ENTRY) | (codes == _SHORT_ENTRY)
        rows = prepared.positions[entered]
        for key, level in levels.items():
            level[rows] = setting.fractions[key][entered]
    return flags, levels, skipped


def iter_batch_signals(
    spec: Mapping[str, Any], prepared: PreparedSessions, settings: Sequence[Mapping[str, Any]], *, chunk: int = 64
) -> Iterator[tuple[dict[str, pd.Series], dict[str, pd.Series], int]]:
    """Yield (flags, stop levels, skipped entries) per setting, in order, ``chunk`` settings at a time."""
    present = [key for key in STOP_KEYS if key in spec["exit"]]
    cache: dict = _BoundedCache()
    for start in range(0, len(settings), chunk):
        walks: dict[str, tuple[np.ndarray, float, np.ndarray]] = {}
        planned = (
            [_plan(spec, prepared, parameters, cache, walks) for parameters in settings[start : start + chunk]]
            if prepared.bars is not None
            else [None] * len(settings[start : start + chunk])
        )
        walked = _run_walks(spec, walks)
        del walks
        for setting in planned:
            flags, levels, skipped = _signals(prepared, setting, walked.get(setting.walk) if setting else None, present)
            yield (
                {name: pd.Series(values, index=prepared.index) for name, values in flags.items()},
                {key: pd.Series(values, index=prepared.index) for key, values in levels.items()},
                skipped,
            )


__all__ = ["EVENTS", "PreparedSessions", "bar_sides", "iter_batch_signals", "prepare_sessions", "walk_columns"]
