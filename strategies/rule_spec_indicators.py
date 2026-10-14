"""Technical indicators for ``qf_rules_v1``, in pure pandas/numpy.

Definitions (value at bar t uses only bars up to and including t):
- RSI, ATR (Wilder smoothing), ADX / +DI / -DI: J. Welles Wilder, "New Concepts in Technical Trading Systems" (1978).
- MACD: Gerald Appel; line = EMA(fast) - EMA(slow), signal = EMA(line), histogram = line - signal.
- Bollinger Bands: John Bollinger; middle = SMA, bands = middle +/- k * POPULATION standard deviation (ddof 0),
  percent_b = (x - lower) / (upper - lower), bandwidth = (upper - lower) / middle.
- Stochastic oscillator: George Lane; raw %K = 100 * (close - lowest low) / (highest high - lowest low) over k_length,
  k = SMA(raw %K, k_smooth) (k_smooth 1 is the fast stochastic), d = SMA(k, d_length).
- CCI: Donald Lambert (1980); (typical price - SMA) / (0.015 * mean absolute deviation from that SMA).
- Williams %R: Larry Williams; -100 * (highest high - close) / (highest high - lowest low).
- ROC: 100 * (x - x[t-length]) / x[t-length].
- OBV: Joseph Granville (1963); running sum of volume signed by the close-to-close direction.
  The first bar of a scope adds its whole volume (TA-Lib convention).
- Keltner channel: middle = EMA(close, length), bands = middle +/- mult * Wilder ATR(atr_length)
  (Linda Raschke's variant of Chester Keltner's 1960 channel).
- Donchian channel: Richard Donchian; highest high / lowest low of the last ``length`` bars INCLUDING the current
  bar, middle = their mean.  For a breakout test compare against the channel one bar back (``prev``).

Scope: every indicator restarts at each session unless the node says ``across_sessions``, then it runs through the
bars of earlier traded sessions (overnight gaps included).  An undefined value (not enough bars, or a zero
denominator) is NaN, which makes comparisons false.  Wilder smoothing is seeded with the plain mean of the first
``length`` valid values (Wilder's own rule), then ``avg = avg + (value - avg) / length``.  EMA matches the
existing ``ema`` operator: alpha 2/(length+1), seeded at the first bar, valid after ``length`` bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from rule_language.indicators import INDICATORS

_CHUNK_CELLS = 2_000_000


@dataclass(frozen=True)
class _Inputs:
    x: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame


def _div(numerator: pd.DataFrame, denominator: pd.DataFrame) -> pd.DataFrame:
    return numerator.div(denominator.where(denominator != 0))


def _sma(frame: pd.DataFrame, length: int) -> pd.DataFrame:
    return frame.rolling(length, min_periods=length).mean()


def _ema(frame: pd.DataFrame, length: int) -> pd.DataFrame:
    return frame.ewm(span=length, adjust=False, min_periods=length).mean()


def _wilder(frame: pd.DataFrame, length: int) -> pd.DataFrame:
    """Wilder smoothing seeded with the mean of the first ``length`` valid rows (NaN before that)."""
    valid = frame.notna().any(axis=1).to_numpy()
    seed_row = int(np.argmax(valid)) + length - 1 if valid.any() else len(frame)
    if seed_row >= len(frame):
        return pd.DataFrame(np.nan, index=frame.index, columns=frame.columns)
    seeded = frame.copy()
    seeded.iloc[:seed_row] = np.nan
    seeded.iloc[seed_row] = frame.iloc[seed_row - length + 1 : seed_row + 1].mean(skipna=False)
    return seeded.ewm(alpha=1.0 / length, adjust=False).mean()


def _true_range(data: _Inputs, *, first_row_defined: bool) -> pd.DataFrame:
    previous_close = data.close.shift(1)
    gaps = np.fmax((data.high - previous_close).abs(), (data.low - previous_close).abs())
    true_range = pd.DataFrame(np.fmax(data.high - data.low, gaps), index=data.high.index, columns=data.high.columns)
    if not first_row_defined:
        true_range.iloc[0] = np.nan
    return true_range


def _rolling_mean_abs_deviation(frame: pd.DataFrame, length: int) -> pd.DataFrame:
    values = frame.to_numpy(dtype=float)
    result = np.full(values.shape, np.nan)
    if values.shape[0] >= length:
        windows = sliding_window_view(values, length, axis=0)
        step = max(1, _CHUNK_CELLS // max(1, values.shape[1] * length))
        for start in range(0, windows.shape[0], step):
            chunk = windows[start : start + step]
            deviation = np.abs(chunk - chunk.mean(axis=2, keepdims=True)).mean(axis=2)
            result[length - 1 + start : length - 1 + start + len(chunk)] = deviation
    return pd.DataFrame(result, index=frame.index, columns=frame.columns)


def wilder_atr(data: _Inputs, length: int) -> pd.DataFrame:
    return _wilder(_true_range(data, first_row_defined=True), length)


def _rsi(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    change = data.x.diff()
    gain, loss = _wilder(change.clip(lower=0.0), p["length"]), _wilder((-change).clip(lower=0.0), p["length"])
    return {"value": 100.0 * _div(gain, gain + loss)}


def _roc(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    previous = data.x.shift(p["length"])
    return {"value": 100.0 * _div(data.x - previous, previous)}


def _macd(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    line = _ema(data.x, p["fast"]) - _ema(data.x, p["slow"])
    signal = _ema(line, p["signal"])
    return {"line": line, "signal": signal, "histogram": line - signal}


def _bollinger(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    middle = _sma(data.x, p["length"])
    deviation = p["std_mult"] * data.x.rolling(p["length"], min_periods=p["length"]).std(ddof=0)
    upper, lower = middle + deviation, middle - deviation
    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "percent_b": _div(data.x - lower, upper - lower),
        "bandwidth": _div(upper - lower, middle),
    }


def _channel(data: _Inputs, length: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        data.high.rolling(length, min_periods=length).max(),
        data.low.rolling(length, min_periods=length).min(),
    )


def _stochastic(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    highest, lowest = _channel(data, p["k_length"])
    raw = 100.0 * _div(data.close - lowest, highest - lowest)
    k = _sma(raw, p["k_smooth"])
    return {"k": k, "d": _sma(k, p["d_length"])}


def _adx(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    length = p["length"]
    up, down = data.high.diff(), -data.low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0).where(up.notna())
    minus_dm = down.where((down > up) & (down > 0), 0.0).where(down.notna())
    smoothed_range = _wilder(_true_range(data, first_row_defined=False), length)
    plus_di = 100.0 * _div(_wilder(plus_dm, length), smoothed_range)
    minus_di = 100.0 * _div(_wilder(minus_dm, length), smoothed_range)
    dx = 100.0 * _div((plus_di - minus_di).abs(), plus_di + minus_di)
    return {"adx": _wilder(dx, length), "plus_di": plus_di, "minus_di": minus_di}


def _cci(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    typical = (data.high + data.low + data.close) / 3.0
    deviation = _rolling_mean_abs_deviation(typical, p["length"])
    return {"value": _div(typical - _sma(typical, p["length"]), 0.015 * deviation)}


def _williams_r(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    highest, lowest = _channel(data, p["length"])
    return {"value": -100.0 * _div(highest - data.close, highest - lowest)}


def _obv(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    direction = np.sign(data.close.diff())
    direction.iloc[0] = 1.0
    return {"value": (direction * data.volume).cumsum()}


def _keltner(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    middle = _ema(data.close, p["length"])
    band = p["mult"] * wilder_atr(data, p["atr_length"])
    return {"upper": middle + band, "middle": middle, "lower": middle - band}


def _donchian(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    upper, lower = _channel(data, p["length"])
    return {"upper": upper, "lower": lower, "middle": (upper + lower) / 2.0}


_FORMULAS: dict[str, Callable[[_Inputs, Mapping[str, Any]], dict[str, pd.DataFrame]]] = {
    "rsi": _rsi,
    "roc": _roc,
    "macd": _macd,
    "bollinger": _bollinger,
    "stochastic": _stochastic,
    "adx": _adx,
    "cci": _cci,
    "williams_r": _williams_r,
    "obv": _obv,
    "keltner": _keltner,
    "donchian": _donchian,
}


class _Scope:
    """Maps ``(bars, sessions)`` arrays to frames: one column per session, or one long column across sessions."""

    def __init__(self, shape: tuple[int, ...], across_sessions: bool) -> None:
        self.shape = shape
        self.across = across_sessions

    def frame(self, values: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(values.reshape(-1, 1, order="F") if self.across else values)

    def array(self, frame: pd.DataFrame) -> np.ndarray:
        values = frame.to_numpy(dtype=float)
        return values.reshape(self.shape, order="F") if self.across else values


def _inputs(evaluator: Any, scope: _Scope, source: np.ndarray | None) -> _Inputs:
    bars = evaluator.bars
    return _Inputs(
        x=scope.frame(source if source is not None else bars.close),
        high=scope.frame(bars.high),
        low=scope.frame(bars.low),
        close=scope.frame(bars.close),
        volume=scope.frame(bars.volume),
    )


def indicator_series(evaluator: Any, operator: str, node: Mapping[str, Any]) -> np.ndarray:
    """Evaluate one validated indicator node; ``evaluator`` supplies bars, parameters and the source series."""
    spec = INDICATORS[operator]
    params = {
        key: evaluator.count(node[key]) if kind == "count" else evaluator.amount(node[key])
        for key, kind, _ in spec.params
    }
    scope = _Scope(evaluator.shape, node["across_sessions"])
    source = evaluator.series(node[operator]) if spec.takes_series else None
    outputs = _FORMULAS[operator](_inputs(evaluator, scope, source), params)
    return scope.array(outputs[node["output"] if spec.outputs else "value"])


def atr_series(evaluator: Any, node: Mapping[str, Any]) -> np.ndarray:
    """Series ``atr`` with optional ``smoothing`` ("wilder") and ``across_sessions``; the plain form is the simple mean."""
    length = evaluator.count(node["length"])
    smoothing, across = node.get("smoothing", "sma"), node.get("across_sessions", False)
    if smoothing == "sma" and not across:
        return evaluator.atr(length)
    scope = _Scope(evaluator.shape, across)
    data = _inputs(evaluator, scope, None)
    if smoothing == "wilder":
        return scope.array(wilder_atr(data, length))
    return scope.array(_sma(_true_range(data, first_row_defined=True), length))


__all__ = ["atr_series", "indicator_series", "wilder_atr"]
