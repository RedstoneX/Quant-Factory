"""Technical indicators for ``qf_rules_v1``, computed by VectorBT PRO and TA-Lib (no hand-written formulas).

One adapter runs every library indicator: ``vbt.IF.get_indicator(name).run(...)`` with the inputs, parameters and
output its metadata declares (``rule_language.indicators``).  The named operators are aliases of library indicators
(rsi = ``vbt:RSI`` Wilder, macd = ``vbt:MACD``, bollinger = ``vbt:BBANDS`` with population deviation, stochastic =
``vbt:STOCH`` slow k/d, adx = ``vbt:ADX``, obv = ``vbt:OBV``, roc / cci / williams_r = ``talib:ROC`` / ``CCI`` /
``WILLR``), except two combinations of library calls with no single library indicator:
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

from typing import Any, Mapping

import numpy as np
import pandas as pd
from backtesting.vectorbt_runtime import require_vectorbtpro
from rule_language.indicators import INDICATORS, PRICE_INPUTS, library_indicator

_RUN = {"hide_params": True}
Frames = dict[str, pd.DataFrame]


def _run_library(name: str, inputs: Frames, params: Mapping[str, Any], output: str) -> pd.DataFrame:
    """The one adapter: run library indicator ``name`` and return one of its outputs (or output properties)."""
    vbt = require_vectorbtpro()
    return getattr(vbt.IF.get_indicator(name).run(**inputs, **params, **_RUN), output)


def _atr(data: Frames, length: int, wtype: str) -> pd.DataFrame:
    return _run_library("vbt:ATR", {key: data[key] for key in ("high", "low", "close")}, {"window": length, "wtype": wtype}, "atr")


def wilder_atr(data: Frames, length: int) -> pd.DataFrame:
    return _atr(data, length, "wilder")


def _keltner(data: Frames, p: Mapping[str, Any]) -> Frames:
    middle = _run_library("vbt:MA", {"close": data["close"]}, {"window": p["length"], "wtype": "exp"}, "ma")
    band = p["mult"] * wilder_atr(data, p["atr_length"])
    return {"upper": middle + band, "middle": middle, "lower": middle - band}


def _donchian(data: Frames, p: Mapping[str, Any]) -> Frames:
    require_vectorbtpro()
    length = p["length"]
    upper, lower = data["high"].vbt.rolling_max(length, minp=length), data["low"].vbt.rolling_min(length, minp=length)
    return {"upper": upper, "lower": lower, "middle": (upper + lower) / 2.0}


_COMBINED = {"keltner": _keltner, "donchian": _donchian}


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


def _frames(evaluator: Any, scope: _Scope, sources: Mapping[str, np.ndarray]) -> Frames:
    """Price fields as frames, with ``sources`` (input name -> series) replacing those inputs."""
    bars = evaluator.bars
    return {key: scope.frame(sources[key] if key in sources else getattr(bars, key)) for key in {*PRICE_INPUTS, *sources}}


def indicator_series(evaluator: Any, operator: str, node: Mapping[str, Any]) -> np.ndarray:
    """Evaluate one validated named indicator node; ``evaluator`` supplies bars, parameters and the source series."""
    spec = INDICATORS[operator]
    params = {
        key: evaluator.count(node[key]) if kind == "count" else evaluator.amount(node[key])
        for key, kind, _ in spec.params
    }
    scope = _Scope(evaluator.shape, node["across_sessions"])
    output = node["output"] if spec.outputs else "value"
    if not spec.library:
        data = _frames(evaluator, scope, {})
        return scope.array(_COMBINED[operator](data, params)[output])
    library = library_indicator(spec.library)
    sources = {library.inputs[0]: evaluator.series(node[operator])} if spec.takes_series else {}
    data = _frames(evaluator, scope, sources)
    library_params = {**dict(spec.fixed), **{name: params[key] for (key, _, _), name in zip(spec.params, spec.library_params)}}
    library_output = spec.library_outputs[spec.outputs.index(output)] if spec.outputs else spec.library_outputs[0]
    inputs = {key: data[key] for key in library.inputs}
    return scope.array(_run_library(spec.library, inputs, library_params, library_output))


def library_series(evaluator: Any, node: Mapping[str, Any]) -> np.ndarray:
    """Evaluate one validated ``{"indicator": ...}`` node."""
    library = library_indicator(node["indicator"])
    kinds = dict(library.params)
    params = {
        key: evaluator.count(value) if kinds[key] == "count" else evaluator.amount(value)
        for key, value in node["params"].items()
    }
    scope = _Scope(evaluator.shape, node["across_sessions"])
    data = _frames(evaluator, scope, {key: evaluator.series(value) for key, value in node["inputs"].items()})
    inputs = {key: data[key] for key in library.inputs}
    return scope.array(_run_library(node["indicator"], inputs, params, node["output"]))


def atr_series(evaluator: Any, node: Mapping[str, Any]) -> np.ndarray:
    """Series ``atr`` with optional ``smoothing`` ("wilder") and ``across_sessions``; the plain form is the simple mean."""
    length = evaluator.count(node["length"])
    smoothing, across = node.get("smoothing", "sma"), node.get("across_sessions", False)
    if smoothing == "sma" and not across:
        return evaluator.atr(length)
    scope = _Scope(evaluator.shape, across)
    data = _frames(evaluator, scope, {})
    return scope.array(_atr(data, length, "wilder" if smoothing == "wilder" else "simple"))


__all__ = ["atr_series", "indicator_series", "library_series", "wilder_atr"]
