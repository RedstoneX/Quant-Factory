"""Catalogue of the technical-indicator operators of ``qf_rules_v1``.

Data only: ``rule_language.validation`` checks specs against it and ``strategies.rule_spec_indicators`` computes the
values.  Every indicator is a VectorBT PRO / TA-Lib indicator; nothing here is a formula.

Library node (any usable library indicator, looked up in the library's own metadata):
``{"indicator": "talib:CCI", "params": {"timeperiod": 20}, "output": "real"}``.  Every numeric parameter the library
declares is required; ``output`` is required when the indicator has several; inputs named open/high/low/close/volume
read those bars unless ``"inputs": {"close": <series>}`` feeds another series; ``"across_sessions"`` as below.

Named nodes (the original operators, aliases of library indicators; every parameter is a whole number / positive
number, or ``{"param": "<variable>"}``):
- indicators that run on one series put it under their own name: ``{"rsi": "close", "length": 14}``;
- indicators that read high/low/close/volume take ``{}``:
  ``{"stochastic": {}, "k_length": 14, "k_smooth": 3, "d_length": 3, "output": "k"}``;
- indicators with several outputs need ``"output"``; the others must not give it;
- ``"across_sessions"`` (default false) is the same flag the rolling operators use.
"""

from __future__ import annotations

import math
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import Any, NamedTuple

# Largest band / channel multiple accepted for ``std_mult`` and ``mult``.
MAX_MULTIPLIER = 20.0
PRICE_INPUTS = ("open", "high", "low", "close", "volume")
# WorldQuant alphas ("wqa101:") rank across columns, and a column here is a trading session: excluded (look-ahead).
LIBRARY_FAMILIES = ("vbt:", "talib:")
# vbt:VWAP anchors on a datetime index the session frames do not carry; the language has {"vwap": {}} instead.
UNUSABLE = frozenset({"vbt:VWAP"})


class IndicatorSpec(NamedTuple):
    """A named operator.  ``takes_series``: operand is a series (else ``{}``).  ``params``: (key, kind, minimum).

    ``library`` computes it, with ``library_params`` / ``library_outputs`` the library names of ``params`` /
    ``outputs`` (one entry for a single-output indicator) and ``fixed`` extra library arguments.  An empty ``library``
    means a combination of library calls (``strategies.rule_spec_indicators``).
    """

    takes_series: bool
    params: tuple[tuple[str, str, int], ...]
    outputs: tuple[str, ...]
    library: str = ""
    library_params: tuple[str, ...] = ()
    library_outputs: tuple[str, ...] = ()
    fixed: tuple[tuple[str, Any], ...] = ()


INDICATORS: dict[str, IndicatorSpec] = {
    "rsi": IndicatorSpec(True, (("length", "count", 2),), (), "vbt:RSI", ("window",), ("rsi",), (("wtype", "wilder"),)),
    "roc": IndicatorSpec(True, (("length", "count", 1),), (), "talib:ROC", ("timeperiod",), ("real",)),
    "macd": IndicatorSpec(
        True,
        (("fast", "count", 1), ("slow", "count", 1), ("signal", "count", 1)),
        ("line", "signal", "histogram"),
        "vbt:MACD",
        ("fast_window", "slow_window", "signal_window"),
        ("macd", "signal", "hist"),
    ),
    "bollinger": IndicatorSpec(
        True,
        (("length", "count", 2), ("std_mult", "amount", 0)),
        ("upper", "middle", "lower", "percent_b", "bandwidth"),
        "vbt:BBANDS",
        ("window", "alpha"),
        ("upper", "middle", "lower", "percent_b", "bandwidth"),
    ),
    "stochastic": IndicatorSpec(
        False,
        (("k_length", "count", 1), ("k_smooth", "count", 1), ("d_length", "count", 1)),
        ("k", "d"),
        "vbt:STOCH",
        ("fast_k_window", "slow_k_window", "slow_d_window"),
        ("slow_k", "slow_d"),
    ),
    "adx": IndicatorSpec(
        False, (("length", "count", 2),), ("adx", "plus_di", "minus_di"), "vbt:ADX", ("window",), ("adx", "plus_di", "minus_di")
    ),
    "cci": IndicatorSpec(False, (("length", "count", 2),), (), "talib:CCI", ("timeperiod",), ("real",)),
    "williams_r": IndicatorSpec(False, (("length", "count", 1),), (), "talib:WILLR", ("timeperiod",), ("real",)),
    "obv": IndicatorSpec(False, (), (), "vbt:OBV", (), ("obv",)),
    "keltner": IndicatorSpec(
        False, (("length", "count", 1), ("atr_length", "count", 1), ("mult", "amount", 0)), ("upper", "middle", "lower")
    ),
    "donchian": IndicatorSpec(False, (("length", "count", 1),), ("upper", "lower", "middle")),
}

INDICATOR_OPERATORS = tuple(INDICATORS)
ATR_SMOOTHINGS = ("sma", "wilder")


class LibraryIndicator(NamedTuple):
    """A library indicator as its metadata declares it.  ``params``: (name, "count" for int / "number" for float)."""

    name: str
    inputs: tuple[str, ...]
    params: tuple[tuple[str, str], ...]
    outputs: tuple[str, ...]


def _library() -> ModuleType | None:
    """VectorBT PRO when installed (separately licensed); the named operators validate without it."""
    try:
        return import_module("vectorbtpro")
    except ModuleNotFoundError as exc:
        if exc.name != "vectorbtpro":
            raise
        return None


def library_available() -> bool:
    return _library() is not None


def _param_kind(default: Any) -> str | None:
    if isinstance(default, bool) or not isinstance(default, (int, float)) or not math.isfinite(default):
        return None
    return "count" if isinstance(default, int) else "number"


@lru_cache(maxsize=None)
def library_indicator(name: str) -> LibraryIndicator | None:
    """Metadata of a usable library indicator, or None.

    Usable: a "talib:" indicator or a "vbt:" one from the library's indicators (not its label generators, which look
    ahead, nor its signal generators), whose inputs are all price fields and whose parameters all have defaults.
    Numeric parameters are settable and required in a spec; the others stay at the library default.
    """
    vbt = _library()
    if vbt is None or not name.startswith(LIBRARY_FAMILIES) or name in UNUSABLE:
        return None
    if name not in vbt.IF.list_indicators():
        return None
    cls = vbt.IF.get_indicator(name)
    if name.startswith("vbt:") and not cls.__module__.startswith("vectorbtpro.indicators."):
        return None
    defaults = cls.param_defaults
    if not cls.input_names or not set(cls.input_names) <= set(PRICE_INPUTS) or set(cls.param_names) - set(defaults):
        return None
    params = tuple((key, kind) for key in cls.param_names if (kind := _param_kind(defaults[key])) is not None)
    return LibraryIndicator(name, tuple(cls.input_names), params, tuple(cls.output_names))


@lru_cache(maxsize=1)
def library_indicators() -> tuple[LibraryIndicator, ...]:
    """Every usable library indicator (empty without VectorBT PRO)."""
    vbt = _library()
    names = vbt.IF.list_indicators() if vbt is not None else ()
    return tuple(spec for spec in map(library_indicator, names) if spec is not None)
