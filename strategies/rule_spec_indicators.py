"""Technical indicators for ``qf_rules_v1``, computed by VectorBT PRO and TA-Lib (no hand-written formulas).

Each operator maps to a library call (value at bar t uses only bars up to and including t):
- rsi, atr, adx: ``vbt.RSI`` / ``vbt.ATR`` / ``vbt.ADX`` (Wilder smoothing; ``vbt.ATR`` with ``wtype="simple"`` for
  the plain-mean ATR).
- macd, bollinger, stochastic, obv: ``vbt.MACD``, ``vbt.BBANDS`` (population standard deviation), ``vbt.STOCH``,
  ``vbt.OBV``.
- cci, williams_r, roc: TA-Lib ``CCI``, ``WILLR``, ``ROC`` through ``vbt.talib_func``.
- keltner: middle = ``vbt.MA`` (exponential) of close, bands = middle +/- mult * Wilder ``vbt.ATR``.
- donchian: rolling highest high / lowest low of the last ``length`` bars INCLUDING the current bar (generic
  accessor ``rolling_max`` / ``rolling_min``), middle = their mean.  For a breakout test compare against the channel
  one bar back (``prev``).

Scope: every indicator restarts at each session unless the node says ``across_sessions``, then it runs through the
bars of earlier traded sessions (overnight gaps included).  The library works column by column, so one column per
session gives the restart.  An undefined value (not enough bars, or a zero denominator) is NaN, which makes
comparisons false; infinities are turned into NaN.  Seeding, warm-up and zero-range results (TA-Lib gives 0, not NaN, for
CCI and Williams %R on a flat window) are the library's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd
from backtesting.vectorbt_runtime import require_vectorbtpro
from rule_language.indicators import INDICATORS

_RUN = {"hide_params": True}


@dataclass(frozen=True)
class _Inputs:
    x: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame


def _atr(data: _Inputs, length: int, wtype: str) -> pd.DataFrame:
    vbt = require_vectorbtpro()
    return vbt.ATR.run(data.high, data.low, data.close, window=length, wtype=wtype, **_RUN).atr


def wilder_atr(data: _Inputs, length: int) -> pd.DataFrame:
    return _atr(data, length, "wilder")


def _rsi(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    return {"value": vbt.RSI.run(data.x, window=p["length"], wtype="wilder", **_RUN).rsi}


def _roc(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    return {"value": vbt.talib_func("ROC")(data.x, timeperiod=p["length"])}


def _macd(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    run = vbt.MACD.run(data.x, fast_window=p["fast"], slow_window=p["slow"], signal_window=p["signal"], **_RUN)
    return {"line": run.macd, "signal": run.signal, "histogram": run.hist}


def _bollinger(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    run = vbt.BBANDS.run(data.x, window=p["length"], alpha=p["std_mult"], **_RUN)
    return {
        "upper": run.upper,
        "middle": run.middle,
        "lower": run.lower,
        "percent_b": run.percent_b,
        "bandwidth": run.bandwidth,
    }


def _stochastic(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    run = vbt.STOCH.run(
        data.high,
        data.low,
        data.close,
        fast_k_window=p["k_length"],
        slow_k_window=p["k_smooth"],
        slow_d_window=p["d_length"],
        **_RUN,
    )
    return {"k": run.slow_k, "d": run.slow_d}


def _adx(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    run = vbt.ADX.run(data.high, data.low, data.close, window=p["length"], **_RUN)
    return {"adx": run.adx, "plus_di": run.plus_di, "minus_di": run.minus_di}


def _cci(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    return {"value": vbt.talib_func("CCI")(data.high, data.low, data.close, timeperiod=p["length"])}


def _williams_r(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    return {"value": vbt.talib_func("WILLR")(data.high, data.low, data.close, timeperiod=p["length"])}


def _obv(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    return {"value": vbt.OBV.run(data.close, data.volume, **_RUN).obv}


def _keltner(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    middle = vbt.MA.run(data.close, window=p["length"], wtype="exp", **_RUN).ma
    band = p["mult"] * wilder_atr(data, p["atr_length"])
    return {"upper": middle + band, "middle": middle, "lower": middle - band}


def _donchian(data: _Inputs, p: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    vbt = require_vectorbtpro()
    length = p["length"]
    upper, lower = data.high.vbt.rolling_max(length, minp=length), data.low.vbt.rolling_min(length, minp=length)
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
        values = np.where(np.isinf(values), np.nan, values)
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
    return scope.array(_atr(data, length, "wilder" if smoothing == "wilder" else "simple"))


__all__ = ["atr_series", "indicator_series", "wilder_atr"]
