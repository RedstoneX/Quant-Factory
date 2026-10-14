"""Vectorised evaluation of validated ``qf_rules_v1`` series and conditions.

Every array is shaped ``(bars, sessions)``: row ``p`` is the bar (1 or 5 minutes,
the spec's ``bar``) ending at 09:30 + (p+1) bar-lengths New York time, and column ``j`` is the j-th
traded regular session.  Only complete regular sessions reach this module, so
a row always means the same clock time.

Semantics that the language leaves to the compiler:
- comparisons involving NaN are false; ``not`` inverts that boolean result;
- ``prev``, ``change``, ``pct_change``, crosses, ``atr``, ``vwap`` and
  ``same_sign_run`` are session-scoped (NaN or restarted at each session);
- rolling windows include the current bar and need ``length`` values
  (``ema`` uses alpha 2/(length+1), seeded at the window scope's first bar;
  ``std`` is the sample deviation); ``across_sessions`` windows run through
  the bars of earlier traded sessions;
- ``atr`` is the simple mean of true range; a session's first bar uses high-low;
- ``same_sign_run`` is 0 when the sign is 0 or NaN.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from rule_language import (
    BAR_MINUTES,
    BARS_PER_SESSION,
    canonical_rule_spec_json,
    clock_minutes,
    first_bar_end_minutes,
)

_MODIFIERS = frozenset({"length", "across_sessions", "bars", "time"})


def bar_position(hhmm: str, bar: str = "5m") -> int:
    """Row of the ``bar``-sized bar ending at ``hhmm`` (09:30 maps to -1: no bar ends there)."""
    return (clock_minutes(hhmm) - first_bar_end_minutes(bar)) // BAR_MINUTES[bar]


@dataclass(frozen=True)
class SessionBars:
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    tick_size: float
    parameters: Mapping[str, Any]
    bar: str = "5m"

    @classmethod
    def from_sessions(
        cls, days: Sequence[pd.DataFrame], *, tick_size: float, parameters: Mapping[str, Any], bar: str = "5m"
    ) -> "SessionBars":
        def stack(column: str) -> np.ndarray:
            return np.column_stack([day[column].to_numpy(dtype=float) for day in days])

        return cls(
            open=stack("Open"),
            high=stack("High"),
            low=stack("Low"),
            close=stack("Close"),
            volume=stack("Volume"),
            tick_size=float(tick_size),
            parameters=dict(parameters),
            bar=bar,
        )


def shift_bars(values: np.ndarray, bars: int) -> np.ndarray:
    """Session-scoped lag: the value ``bars`` rows earlier, NaN at the session start."""
    result = np.full(values.shape, np.nan)
    if bars < values.shape[0]:
        result[bars:] = values[: values.shape[0] - bars]
    return result


def _window(obj: pd.Series | pd.DataFrame, operator: str, length: int) -> pd.Series | pd.DataFrame:
    if operator == "ema":
        return obj.ewm(span=length, adjust=False, min_periods=length).mean()
    window = obj.rolling(length, min_periods=length)
    if operator == "sma":
        return window.mean()
    if operator == "std":
        return window.std(ddof=1)
    return getattr(window, operator)()


def rolling(values: np.ndarray, operator: str, length: int, *, across_sessions: bool) -> np.ndarray:
    if across_sessions:
        flat = pd.Series(values.reshape(-1, order="F"))
        return _window(flat, operator, length).to_numpy(dtype=float).reshape(values.shape, order="F")
    return _window(pd.DataFrame(values), operator, length).to_numpy(dtype=float)


def _divide(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.divide(left, right)
    result[(right == 0) | ~np.isfinite(result)] = np.nan
    return result


def _signs(values: np.ndarray) -> np.ndarray:
    signs = np.sign(values)
    signs[~np.isfinite(signs)] = 0.0
    return signs


class RuleEvaluator:
    """Evaluate normalized rule nodes against the stacked bars of traded sessions."""

    def __init__(self, bars: SessionBars) -> None:
        self.bars = bars
        self.shape = bars.close.shape
        self.bar = bars.bar
        self._cache: dict[str, np.ndarray] = {}

    def count(self, node: Any) -> int:
        return int(self.bars.parameters[node["param"]]) if isinstance(node, Mapping) else int(node)

    def amount(self, node: Any) -> float:
        return float(self.bars.parameters[node["param"]]) if isinstance(node, Mapping) else float(node)

    def series(self, node: Any) -> np.ndarray:
        if isinstance(node, str):
            return getattr(self.bars, node)
        if isinstance(node, (int, float)):
            return np.full(self.shape, float(node))
        key = canonical_rule_spec_json(node)
        if key not in self._cache:
            operator = next(name for name in node if name not in _MODIFIERS)
            self._cache[key] = self._operator(operator, node)
        return self._cache[key]

    def _operator(self, operator: str, node: Mapping[str, Any]) -> np.ndarray:
        value = node[operator]
        bars = self.bars
        if operator == "param":
            return np.full(self.shape, self.amount(node))
        if operator in ("add", "sub", "mul", "div"):
            left, right = self.series(value[0]), self.series(value[1])
            if operator == "div":
                return _divide(left, right)
            return {"add": np.add, "sub": np.subtract, "mul": np.multiply}[operator](left, right)
        if operator in ("abs", "sign", "neg", "ticks"):
            operand = self.series(value)
            if operator == "ticks":
                return operand / bars.tick_size
            return {"abs": np.abs, "sign": np.sign, "neg": np.negative}[operator](operand)
        if operator == "prev":
            return shift_bars(self.series(value), self.count(node["bars"]))
        if operator in ("change", "pct_change"):
            operand = self.series(value)
            previous = shift_bars(operand, 1)
            change = operand - previous
            return change if operator == "change" else _divide(change, previous)
        if operator in ("sma", "ema", "median", "max", "min", "std", "sum"):
            length = self.count(node["length"])
            return rolling(self.series(value), operator, length, across_sessions=node["across_sessions"])
        if operator == "atr":
            return self.atr(self.count(value["length"]))
        if operator == "vwap":
            typical = (bars.high + bars.low + bars.close) / 3.0
            return np.cumsum(typical * bars.volume, axis=0) / np.cumsum(bars.volume, axis=0)
        if operator == "session_open":
            return np.broadcast_to(bars.open[0], self.shape).copy()
        if operator == "bar_index":
            return np.broadcast_to(np.arange(1.0, self.shape[0] + 1.0)[:, None], self.shape).copy()
        if operator == "value_at":
            return self._from_row(self.series(value)[bar_position(node["time"], self.bar)], bar_position(node["time"], self.bar))
        if operator in ("range_high", "range_low"):
            first, last = bar_position(value["from"], self.bar) + 1, bar_position(value["to"], self.bar)
            if operator == "range_high":
                extreme = bars.high[first : last + 1].max(axis=0)
            else:
                extreme = bars.low[first : last + 1].min(axis=0)
            return self._from_row(extreme, last)
        return self.same_sign_run(self.series(value))

    def _from_row(self, row_values: np.ndarray, row: int) -> np.ndarray:
        result = np.full(self.shape, np.nan)
        result[row:] = row_values
        return result

    def atr(self, length: int) -> np.ndarray:
        bars = self.bars
        previous_close = shift_bars(bars.close, 1)
        gaps = np.fmax(np.abs(bars.high - previous_close), np.abs(bars.low - previous_close))
        true_range = np.fmax(bars.high - bars.low, gaps)
        return rolling(true_range, "sma", length, across_sessions=False)

    @staticmethod
    def same_sign_run(values: np.ndarray) -> np.ndarray:
        signs = _signs(values)
        runs = np.zeros(values.shape)
        for row in range(values.shape[0]):
            current = signs[row]
            started = (current != 0).astype(float)
            if row == 0:
                runs[row] = started
                continue
            continuing = (current != 0) & (current == signs[row - 1])
            runs[row] = np.where(continuing, runs[row - 1] + 1.0, started)
        return runs

    def condition(self, node: Mapping[str, Any]) -> np.ndarray:
        operator, value = next(iter(node.items()))
        if operator in ("gt", "gte", "lt", "lte", "eq", "crosses_above", "crosses_below"):
            left, right = self.series(value[0]), self.series(value[1])
            with np.errstate(invalid="ignore"):
                if operator == "crosses_above":
                    return (shift_bars(left, 1) <= shift_bars(right, 1)) & (left > right)
                if operator == "crosses_below":
                    return (shift_bars(left, 1) >= shift_bars(right, 1)) & (left < right)
                compare = {"gt": np.greater, "gte": np.greater_equal, "lt": np.less, "lte": np.less_equal, "eq": np.equal}
                return np.broadcast_to(compare[operator](left, right), self.shape).copy()
        if operator == "all":
            return np.logical_and.reduce([self.condition(item) for item in value])
        if operator == "any":
            return np.logical_or.reduce([self.condition(item) for item in value])
        if operator == "not":
            return ~self.condition(value)
        mask = np.zeros(self.shape, dtype=bool)
        if operator == "time_is":
            mask[bar_position(value, self.bar)] = True
        else:
            mask[bar_position(value[0], self.bar) : bar_position(value[1], self.bar) + 1] = True
        return mask

    def side(self, node: Any) -> np.ndarray:
        if node == "long":
            return np.ones(self.shape)
        if node == "short":
            return -np.ones(self.shape)
        operator, value = next(iter(node.items()))
        signs = _signs(self.series(value))
        return signs if operator == "sign_of" else -signs

    def distance_fraction(self, node: Mapping[str, Any]) -> np.ndarray:
        """Stop or target distance as a fraction of the signal-bar close."""
        kind, value = next(iter(node.items()))
        if kind == "percent":
            return np.full(self.shape, self.amount(value) / 100.0)
        if kind == "points":
            distance = np.full(self.shape, self.amount(value))
        elif kind == "ticks":
            distance = np.full(self.shape, self.amount(value) * self.bars.tick_size)
        else:
            distance = self.amount(value["multiple"]) * self.atr(self.count(value["length"]))
        return _divide(distance, self.bars.close)


__all__ = ["BARS_PER_SESSION", "RuleEvaluator", "SessionBars", "bar_position", "rolling", "shift_bars"]
