"""Signals of many settings of one rule strategy, for one VectorBT simulation on the continuous bar history.

Rule nodes are evaluated on full regular sessions stacked as columns (indicators such as the opening range are
defined per session), with one ``RuleEvaluator`` cache shared by all settings.  Nothing is simulated here: the
signals are written onto the continuous bar index and VectorBT's ``Portfolio.from_signals`` holds positions,
overnight when the spec has no ``flat_at``.  Time exits are VectorBT's own: ``after_bars`` -> ``td_stop`` (a
duration, so a swept variable sweeps the maximum hold).  ``flat_at`` and ``at_time`` are VectorBT's documented
session pattern: an exit signal on that bar of every session (so the exit pays the same next-open price and slippage
as any other signal exit).
"""

from __future__ import annotations

from pathlib import Path
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


_CALENDAR_DIR = Path(__file__).resolve().parent.parent / "market_data" / "calendars"
_CALENDAR_FILES = {"cpi": "cpi_release_dates.txt", "fomc": "fomc_decision_dates.txt"}


def skipped_sessions(spec: Mapping[str, Any], prepared: PreparedSessions) -> np.ndarray:
    """Per-session bool: the session's New York date is a CPI release or FOMC decision day named by ``skip_days``."""
    dates = pd.DatetimeIndex([])
    for name in spec.get("skip_days", ()):
        dates = dates.append(pd.DatetimeIndex(pd.read_csv(_CALENDAR_DIR / _CALENDAR_FILES[name], header=None, comment="#")[0]))
    opens = prepared.index[prepared.positions[0]].tz_convert(SESSION_TIMEZONE).tz_localize(None).normalize()
    return np.asarray(opens.isin(dates))


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


def _entry_window(spec: Mapping[str, Any], rows: int) -> np.ndarray:
    """(bars, 1) bool: rows whose signal may open a position (before ``flat_at``'s signal row, when it is set)."""
    allowed = np.ones((rows, 1), dtype=bool)
    if "flat_at" in spec:
        allowed[bar_position(spec["flat_at"], spec["bar"]) :] = False
    return allowed


def _first_entries(candidate: np.ndarray, sides: np.ndarray, limit: int) -> np.ndarray:
    """``candidate`` reduced to the first bar of each run of same-side signals, at most ``limit`` runs per session.

    Columns are sessions, so the count restarts every session. It counts signal runs, not fills: VectorBT ignores a
    run that starts while a position is open, and that run still counts.
    """
    signed = np.where(candidate, sides, 0)
    previous = np.vstack([np.zeros((1, signed.shape[1])), signed[:-1]])
    starts = candidate & (signed != previous)
    return starts & (np.cumsum(starts, axis=0) <= limit)


@dataclass
class _Setting:
    parameters: dict[str, Any]
    evaluator: RuleEvaluator
    fractions: dict[str, np.ndarray]


def _plan(spec: Mapping[str, Any], prepared: PreparedSessions, parameters: Mapping[str, Any], cache: dict) -> _Setting:
    """Evaluate one setting's rule nodes through the shared cache."""
    exit_rules = spec["exit"]
    evaluator = RuleEvaluator(replace(prepared.bars, parameters=dict(parameters)), cache)
    present = [key for key in STOP_KEYS if key in exit_rules]
    fractions = {key: evaluator.distance_fraction(exit_rules[key]) for key in present}
    return _Setting(dict(parameters), evaluator, fractions)


def _signals(spec: Mapping[str, Any], prepared: PreparedSessions, setting: _Setting | None, present: Iterable[str]):
    """from_signals inputs of one setting on the continuous bar index (no per-session simulation).

    Entries, exits and each stop's fraction sit on the signal bar; ``td_stop`` (``after_bars`` as a duration from
    the fill) is VectorBT's own time exit.
    """
    length = len(prepared.index)
    flags = {name: np.zeros(length, dtype=bool) for name in EVENTS}
    levels = {key: np.full(length, np.nan) for key in present}
    stops = {"td_stop": np.full(length, -1, dtype=np.int64)}
    if setting is None:
        return flags, levels, stops, 0
    exit_rules = spec["exit"]
    evaluator = setting.evaluator
    sides = evaluator.cached("sides", spec["signals"], lambda: bar_sides(spec, evaluator))
    valid = np.ones(evaluator.shape, dtype=bool)
    with np.errstate(invalid="ignore"):
        for fraction in setting.fractions.values():
            valid &= np.isfinite(fraction) & (fraction > 0)
    allowed = _entry_window(spec, evaluator.shape[0]) & (sides != 0)
    if spec.get("skip_days"):
        allowed &= ~skipped_sessions(spec, prepared)[None, :]  # no new entries on a skipped day; exits still apply
    skipped = int((allowed & ~valid).sum())
    first = _first_entries(allowed & valid, sides, spec["max_trades_per_session"])
    rows = prepared.positions
    flags["entry"][rows[first & (sides > 0)]] = True
    flags["short_entry"][rows[first & (sides < 0)]] = True
    when = exit_rules.get("exit_when", {})
    clock = np.zeros((evaluator.shape[0], 1), dtype=bool)  # the session-end and at_time exit rows
    if "flat_at" in spec:
        clock[bar_position(spec["flat_at"], spec["bar"])] = True
    if "at_time" in exit_rules:
        clock[bar_position(exit_rules["at_time"], spec["bar"])] = True
    for name, side, opposite in (("exit", "long", sides < 0), ("short_exit", "short", sides > 0)):
        leave = evaluator.condition(when[side]) if side in when else np.zeros(evaluator.shape, dtype=bool)
        if exit_rules["on_opposite_signal"]:
            leave = leave | opposite
        leave = leave | clock
        flags[name][rows[leave]] = True
    for key, level in levels.items():
        level[rows[first]] = setting.fractions[key][first]
    if "after_bars" in exit_rules:
        stops["td_stop"][:] = pd.Timedelta(minutes=BAR_MINUTES[spec["bar"]] * evaluator.count(exit_rules["after_bars"])).value
    return flags, levels, stops, skipped


def iter_batch_signals(
    spec: Mapping[str, Any], prepared: PreparedSessions, settings: Sequence[Mapping[str, Any]]
) -> Iterator[tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series], int]]:
    """Yield (flags, stop levels, time stops, skipped entries) per setting, in order."""
    present = [key for key in STOP_KEYS if key in spec["exit"]]
    cache: dict = _BoundedCache()
    for parameters in settings:
        setting = _plan(spec, prepared, parameters, cache) if prepared.bars is not None else None
        flags, levels, stops, skipped = _signals(spec, prepared, setting, present)
        yield (
            {name: pd.Series(values, index=prepared.index) for name, values in flags.items()},
            {key: pd.Series(values, index=prepared.index) for key, values in levels.items()},
            {key: pd.Series(values, index=prepared.index) for key, values in stops.items()},
            skipped,
        )


__all__ = ["EVENTS", "PreparedSessions", "bar_sides", "iter_batch_signals", "prepare_sessions"]
