"""Catalogue of the technical-indicator operators of ``qf_rules_v1``.

Data only: each entry names the parameters an indicator takes and the outputs
it can return.  ``rule_language.validation`` checks specs against it and
``strategies.rule_spec_indicators`` computes the values.

Node shape (every parameter is a whole number / positive number, or ``{"param": "<variable>"}``):
- indicators that run on one series put it under their own name:
  ``{"rsi": "close", "length": 14}``;
- indicators that read high/low/close/volume take ``{}``:
  ``{"stochastic": {}, "k_length": 14, "k_smooth": 3, "d_length": 3, "output": "k"}``;
- indicators with several outputs need ``"output"``; the others must not give it;
- ``"across_sessions"`` (default false) is the same flag the rolling operators use.
"""

from __future__ import annotations

from typing import NamedTuple

# Largest band / channel multiple accepted for ``std_mult`` and ``mult``.
MAX_MULTIPLIER = 20.0


class IndicatorSpec(NamedTuple):
    """``takes_series``: operand is a series (else ``{}``).  ``params``: (key, kind, minimum) in order."""

    takes_series: bool
    params: tuple[tuple[str, str, int], ...]
    outputs: tuple[str, ...]


INDICATORS: dict[str, IndicatorSpec] = {
    "rsi": IndicatorSpec(True, (("length", "count", 2),), ()),
    "roc": IndicatorSpec(True, (("length", "count", 1),), ()),
    "macd": IndicatorSpec(
        True, (("fast", "count", 1), ("slow", "count", 1), ("signal", "count", 1)), ("line", "signal", "histogram")
    ),
    "bollinger": IndicatorSpec(
        True, (("length", "count", 2), ("std_mult", "amount", 0)), ("upper", "middle", "lower", "percent_b", "bandwidth")
    ),
    "stochastic": IndicatorSpec(
        False, (("k_length", "count", 1), ("k_smooth", "count", 1), ("d_length", "count", 1)), ("k", "d")
    ),
    "adx": IndicatorSpec(False, (("length", "count", 2),), ("adx", "plus_di", "minus_di")),
    "cci": IndicatorSpec(False, (("length", "count", 2),), ()),
    "williams_r": IndicatorSpec(False, (("length", "count", 1),), ()),
    "obv": IndicatorSpec(False, (), ()),
    "keltner": IndicatorSpec(
        False, (("length", "count", 1), ("atr_length", "count", 1), ("mult", "amount", 0)), ("upper", "middle", "lower")
    ),
    "donchian": IndicatorSpec(False, (("length", "count", 1),), ("upper", "lower", "middle")),
}

INDICATOR_OPERATORS = tuple(INDICATORS)
ATR_SMOOTHINGS = ("sma", "wilder")
