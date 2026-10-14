"""Strict validation for the ``qf_rules_v1`` declarative rule language.

A rule spec is plain JSON data describing the entries and exits of one
five-minute regular-session strategy.  Nothing in a spec is ever executed:
this module checks every key, type, time and variable reference and returns a
normalized copy; a separate compiler interprets that copy.

Every ``HH:MM`` is a bar END time in America/New_York: the five-minute bar
that starts at 09:40 ends at 09:45.  Signals use completed bars and fill at the
next bar open, so a signal on the bar ending at T fills at T.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping

from rule_language.indicators import ATR_SMOOTHINGS, INDICATOR_OPERATORS, INDICATORS, MAX_MULTIPLIER

RULE_LANGUAGE = "qf_rules_v1"
MAX_RULE_DEPTH = 32
MAX_RULE_NODES = 500
# Per-bar-size geometry; BARS_PER_SESSION and FIRST_BAR_END_MINUTES below are the 5m values, kept for callers.
BAR_MINUTES = {"1m": 1, "5m": 5}
BARS_PER_SESSION = 78
MAX_WINDOW_BARS = 20_000
# Single source for the variable-grid limit; strategies.parameter_governance re-exports it as the warning threshold.
MAX_VARIABLE_GRID = 100
SUPPORTED_BARS = tuple(BAR_MINUTES)
SUPPORTED_SESSION = {"timezone": "America/New_York", "open": "09:30", "close": "16:00"}

PRICE_FIELDS = ("open", "high", "low", "close", "volume")
BINARY_OPERATORS = ("add", "sub", "mul", "div")
UNARY_OPERATORS = ("abs", "sign", "neg", "ticks", "change", "pct_change", "same_sign_run")
ROLLING_OPERATORS = ("sma", "ema", "median", "max", "min", "std", "sum")
SESSION_OPERATORS = ("vwap", "session_open", "bar_index")
RANGE_OPERATORS = ("range_high", "range_low")
SERIES_OPERATORS = (
    "param",
    *BINARY_OPERATORS,
    *UNARY_OPERATORS,
    "prev",
    *ROLLING_OPERATORS,
    "atr",
    *SESSION_OPERATORS,
    "value_at",
    *RANGE_OPERATORS,
    *INDICATOR_OPERATORS,
)
COMPARISON_OPERATORS = ("gt", "gte", "lt", "lte", "eq")
CROSS_OPERATORS = ("crosses_above", "crosses_below")
CONDITION_OPERATORS = (
    *COMPARISON_OPERATORS,
    *CROSS_OPERATORS,
    "all",
    "any",
    "not",
    "time_is",
    "time_between",
)
SIDE_OPERATORS = ("sign_of", "opposite_sign_of")
DISTANCE_KINDS = ("percent", "points", "ticks", "atr")

SESSION_OPEN_MINUTES = 9 * 60 + 30
SESSION_CLOSE_MINUTES = 16 * 60
FIRST_BAR_END_MINUTES = SESSION_OPEN_MINUTES + 5
LAST_EXIT_BAR_END_MINUTES = SESSION_CLOSE_MINUTES - 5


def bars_per_session(bar: str) -> int:
    """Regular-session bars for a supported bar size: 390 for 1m, 78 for 5m."""
    return (SESSION_CLOSE_MINUTES - SESSION_OPEN_MINUTES) // BAR_MINUTES[bar]


def first_bar_end_minutes(bar: str) -> int:
    """Minute of day at which the first regular-session bar ends."""
    return SESSION_OPEN_MINUTES + BAR_MINUTES[bar]

_TOP_LEVEL_KEYS = (
    "language",
    "bar",
    "tick_size",
    "session",
    "flat_at",
    "signals",
    "max_trades_per_session",
)
_EXIT_KEYS = ("after_bars", "at_time", "on_opposite_signal", "stop_loss", "take_profit", "trailing_stop")
# Engine-side stops, each optional and independent; their distances are fixed at entry.
STOP_KEYS = ("stop_loss", "take_profit", "trailing_stop")
_CLOCK = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")


class RuleSpecError(ValueError):
    """An invalid rule spec; ``path`` names the offending element."""

    def __init__(self, path: str, reason: str = "") -> None:
        super().__init__(f"{path}: {reason}" if reason else path)
        self.path = path
        self.reason = reason or path


def canonical_rule_spec_json(spec: Any) -> str:
    """Serialize JSON data with sorted keys and no whitespace."""
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def clock_minutes(value: Any) -> int:
    """Return minutes after midnight for a zero-padded 24-hour ``HH:MM`` string."""
    match = _CLOCK.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"{value!r} is not a valid HH:MM time")
    return int(match.group(1)) * 60 + int(match.group(2))


def validate_rule_spec(spec: Any, *, variables: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate a ``qf_rules_v1`` spec and return a normalized copy.

    ``variables`` maps each packet variable name to ``{"values": [...]}``.
    Every declared variable must be referenced, and every reference must be
    declared.  Raises :class:`RuleSpecError` with a path-qualified message.
    """
    if not isinstance(spec, Mapping):
        raise RuleSpecError("rule_spec", "must be an object")
    if variables is None:
        variables = {}
    if not isinstance(variables, Mapping):
        raise RuleSpecError("variables", 'must be an object mapping names to {"values": [...]}')
    _check_size(spec)
    checker = _Validator(variables)
    normalized = checker.spec(spec)
    unused = sorted(str(name) for name in variables if name not in checker.used)
    if unused:
        raise RuleSpecError(
            f"variables.{unused[0]}",
            f'is declared but rule_spec never uses it; reference it with {{"param": "{unused[0]}"}} or remove it',
        )
    _check_grid_size(variables)
    return normalized


def _check_grid_size(variables: Mapping[str, Any]) -> None:
    """Reject a variable grid (product of value counts) above the governance warning threshold."""

    combinations = 1
    for definition in variables.values():
        combinations *= len(definition["values"])
    if combinations > MAX_VARIABLE_GRID:
        raise RuleSpecError(
            "variables",
            f"grid has {combinations} combinations (product of each variable's value count); "
            f"the limit is {MAX_VARIABLE_GRID}. Remove values or variables",
        )


def _check_size(spec: Mapping[str, Any]) -> None:
    stack: list[tuple[Any, int]] = [(spec, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_RULE_NODES:
            raise RuleSpecError("rule_spec", f"has more than {MAX_RULE_NODES} elements; simplify the rules")
        if depth > MAX_RULE_DEPTH:
            raise RuleSpecError("rule_spec", f"is nested more than {MAX_RULE_DEPTH} levels deep")
        if isinstance(value, Mapping):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, (list, tuple)):
            stack.extend((item, depth + 1) for item in value)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _clock(value: Any, path: str, *, earliest: int, latest: int, step: int = 5) -> str:
    try:
        minutes = clock_minutes(value)
    except ValueError:
        raise RuleSpecError(path, f'{value!r} is not a valid HH:MM time (24-hour, zero-padded, e.g. "09:45")') from None
    if minutes % step:
        raise RuleSpecError(path, f"{value} is not on the {step}-minute bar grid")
    if not earliest <= minutes <= latest:
        raise RuleSpecError(
            path,
            f"{value} must be between {_hhmm(earliest)} and {_hhmm(latest)} "
            f"(times are {step}-minute bar END times in the session)",
        )
    return value


def _object(node: Any, path: str, *, required: tuple[str, ...] = (), optional: tuple[str, ...] = ()) -> Mapping[str, Any]:
    if not isinstance(node, Mapping):
        raise RuleSpecError(path, "must be an object")
    allowed = (*required, *optional)
    for key in node:
        if key not in allowed:
            raise RuleSpecError(path, f"unknown key {key!r} (allowed: {', '.join(sorted(allowed))})")
    for key in required:
        if key not in node:
            raise RuleSpecError(path, f"missing required key {key!r}")
    return node


def _pair(node: Any, path: str) -> tuple[Any, Any]:
    if not isinstance(node, (list, tuple)) or len(node) != 2:
        raise RuleSpecError(path, "must be a list of exactly two items")
    return node[0], node[1]


def _operator(node: Any, path: str, allowed: tuple[str, ...], kind: str) -> str:
    if not isinstance(node, Mapping):
        raise RuleSpecError(path, f"must be a {kind} object")
    heads = [key for key in node if key in allowed]
    if len(heads) > 1:
        raise RuleSpecError(path, f"combines {heads[0]!r} and {heads[1]!r}; use exactly one {kind} operator")
    if not heads:
        if not node:
            raise RuleSpecError(path, f"an empty object is not a {kind}")
        raise RuleSpecError(path, f"unknown {kind} {next(iter(node))!r} (allowed: {', '.join(allowed)})")
    return heads[0]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_count(value: Any, minimum: int, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _is_amount(value: Any, maximum: float | None) -> bool:
    return _is_number(value) and value > 0 and (maximum is None or value < maximum)


class _Validator:
    def __init__(self, variables: Mapping[str, Any]) -> None:
        self.variables = variables
        self.used: set[str] = set()
        self.set_bar("5m")

    def set_bar(self, bar: str) -> None:
        self.step = BAR_MINUTES[bar]
        self.bars_per_session = bars_per_session(bar)
        self.first_end = first_bar_end_minutes(bar)
        self.last_exit = SESSION_CLOSE_MINUTES - self.step

    def spec(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        path = "rule_spec"
        _object(spec, path, required=_TOP_LEVEL_KEYS, optional=("exit",))
        if spec["language"] != RULE_LANGUAGE:
            raise RuleSpecError(f"{path}.language", f"must be {RULE_LANGUAGE!r}")
        bar = spec["bar"]
        if not isinstance(bar, str) or bar not in BAR_MINUTES:
            allowed = " or ".join(f'"{name}"' for name in SUPPORTED_BARS)
            raise RuleSpecError(f"{path}.bar", f"must be {allowed} in {RULE_LANGUAGE}; got {bar!r}")
        self.set_bar(bar)
        if not _is_amount(spec["tick_size"], None):
            raise RuleSpecError(f"{path}.tick_size", "must be a number greater than zero")
        session = _object(spec["session"], f"{path}.session", required=tuple(SUPPORTED_SESSION))
        for key, expected in SUPPORTED_SESSION.items():
            if session[key] != expected:
                raise RuleSpecError(
                    f"{path}.session.{key}",
                    f"{RULE_LANGUAGE} supports only the America/New_York 09:30-16:00 regular session; got {session[key]!r}",
                )
        flat_at = _clock(
            spec["flat_at"], f"{path}.flat_at", earliest=self.first_end + self.step, latest=self.last_exit, step=self.step
        )
        signals = spec["signals"]
        if not isinstance(signals, (list, tuple)) or not signals:
            raise RuleSpecError(f"{path}.signals", 'must be a non-empty list of {"when": ..., "side": ...} objects')
        normalized_signals = []
        for index, signal in enumerate(signals):
            where = f"{path}.signals[{index}]"
            _object(signal, where, required=("when", "side"))
            normalized_signals.append(
                {"when": self.condition(signal["when"], f"{where}.when"), "side": self.side(signal["side"], f"{where}.side")}
            )
        max_trades = spec["max_trades_per_session"]
        if not _is_count(max_trades, 1, self.bars_per_session):
            raise RuleSpecError(f"{path}.max_trades_per_session", f"must be a whole number from 1 to {self.bars_per_session}")
        return {
            "language": RULE_LANGUAGE,
            "bar": bar,
            "tick_size": spec["tick_size"],
            "session": dict(SUPPORTED_SESSION),
            "flat_at": flat_at,
            "signals": normalized_signals,
            "exit": self.exit(spec.get("exit", {}), f"{path}.exit", clock_minutes(flat_at)),
            "max_trades_per_session": max_trades,
        }

    def exit(self, node: Any, path: str, flat_at: int) -> dict[str, Any]:
        _object(node, path, optional=_EXIT_KEYS)
        result: dict[str, Any] = {}
        if "after_bars" in node:
            result["after_bars"] = self.count(node["after_bars"], f"{path}.after_bars", maximum=self.bars_per_session - 1)
        if "at_time" in node:
            result["at_time"] = _clock(node["at_time"], f"{path}.at_time", earliest=self.first_end + self.step, latest=flat_at, step=self.step)
        opposite = node.get("on_opposite_signal", False)
        if not isinstance(opposite, bool):
            raise RuleSpecError(f"{path}.on_opposite_signal", "must be true or false")
        result["on_opposite_signal"] = opposite
        for key in STOP_KEYS:
            if key in node:
                result[key] = self.distance(node[key], f"{path}.{key}")
        return result

    def distance(self, node: Any, path: str) -> dict[str, Any]:
        kind = _operator(node, path, DISTANCE_KINDS, "distance")
        _object(node, path, required=(kind,))
        where = f"{path}.{kind}"
        if kind == "atr":
            atr = _object(node[kind], where, required=("length", "multiple"))
            return {
                "atr": {
                    "length": self.count(atr["length"], f"{where}.length", maximum=self.bars_per_session),
                    "multiple": self.amount(atr["multiple"], f"{where}.multiple"),
                }
            }
        return {kind: self.amount(node[kind], where, maximum=100.0 if kind == "percent" else None)}

    def side(self, node: Any, path: str) -> Any:
        if isinstance(node, str) and node in ("long", "short"):
            return node
        if isinstance(node, Mapping) and len(node) == 1:
            key = next(iter(node))
            if key in SIDE_OPERATORS:
                return {key: self.series(node[key], f"{path}.{key}")}
        raise RuleSpecError(path, 'must be "long", "short", {"sign_of": <series>} or {"opposite_sign_of": <series>}')

    def condition(self, node: Any, path: str) -> dict[str, Any]:
        operator = _operator(node, path, CONDITION_OPERATORS, "condition")
        _object(node, path, required=(operator,))
        value = node[operator]
        where = f"{path}.{operator}"
        if operator in COMPARISON_OPERATORS or operator in CROSS_OPERATORS:
            left, right = _pair(value, where)
            return {operator: [self.series(left, f"{where}[0]"), self.series(right, f"{where}[1]")]}
        if operator in ("all", "any"):
            if not isinstance(value, (list, tuple)) or not value:
                raise RuleSpecError(where, "must be a non-empty list of conditions")
            return {operator: [self.condition(item, f"{where}[{index}]") for index, item in enumerate(value)]}
        if operator == "not":
            return {"not": self.condition(value, where)}
        if operator == "time_is":
            return {"time_is": _clock(value, where, earliest=self.first_end, latest=SESSION_CLOSE_MINUTES, step=self.step)}
        start, end = _pair(value, where)
        start = _clock(start, f"{where}[0]", earliest=self.first_end, latest=SESSION_CLOSE_MINUTES, step=self.step)
        end = _clock(end, f"{where}[1]", earliest=self.first_end, latest=SESSION_CLOSE_MINUTES, step=self.step)
        if clock_minutes(start) > clock_minutes(end):
            raise RuleSpecError(where, f"start {start} is after end {end}")
        return {"time_between": [start, end]}

    def series(self, node: Any, path: str) -> Any:
        if isinstance(node, bool):
            raise RuleSpecError(path, "true/false is not a number or series")
        if isinstance(node, (int, float)):
            if not math.isfinite(node):
                raise RuleSpecError(path, "numbers must be finite")
            return node
        if isinstance(node, str):
            if node not in PRICE_FIELDS:
                raise RuleSpecError(path, f"unknown price field {node!r} (allowed: {', '.join(PRICE_FIELDS)})")
            return node
        operator = _operator(node, path, SERIES_OPERATORS, "series")
        value = node[operator]
        where = f"{path}.{operator}"
        if operator == "prev":
            _object(node, path, required=("prev", "bars"))
            return {"prev": self.series(value, where), "bars": self.count(node["bars"], f"{path}.bars", maximum=self.bars_per_session - 1)}
        if operator in ROLLING_OPERATORS:
            _object(node, path, required=(operator, "length"), optional=("across_sessions",))
            across = node.get("across_sessions", False)
            if not isinstance(across, bool):
                raise RuleSpecError(f"{path}.across_sessions", "must be true or false")
            length = self.count(
                node["length"],
                f"{path}.length",
                minimum=2 if operator == "std" else 1,
                maximum=MAX_WINDOW_BARS if across else self.bars_per_session,
            )
            return {operator: self.series(value, where), "length": length, "across_sessions": across}
        if operator == "value_at":
            _object(node, path, required=("value_at", "time"))
            time = _clock(node["time"], f"{path}.time", earliest=self.first_end, latest=SESSION_CLOSE_MINUTES, step=self.step)
            return {"value_at": self.series(value, where), "time": time}
        if operator in INDICATORS:
            return self.indicator(operator, node, path)
        _object(node, path, required=(operator,))
        if operator == "param":
            return {"param": self.param(value, where, kind="number")}
        if operator in BINARY_OPERATORS:
            left, right = _pair(value, where)
            return {operator: [self.series(left, f"{where}[0]"), self.series(right, f"{where}[1]")]}
        if operator in UNARY_OPERATORS:
            return {operator: self.series(value, where)}
        if operator == "atr":
            return {"atr": self.atr_series(value, where)}
        if operator in SESSION_OPERATORS:
            if not isinstance(value, Mapping) or value:
                raise RuleSpecError(where, "must be an empty object {}")
            return {operator: {}}
        window = _object(value, where, required=("from", "to"))
        start = _clock(window["from"], f"{where}.from", earliest=SESSION_OPEN_MINUTES, latest=self.last_exit, step=self.step)
        end = _clock(window["to"], f"{where}.to", earliest=self.first_end, latest=SESSION_CLOSE_MINUTES, step=self.step)
        if clock_minutes(start) >= clock_minutes(end):
            raise RuleSpecError(where, f"from {start} must be before to {end}")
        return {operator: {"from": start, "to": end}}

    def atr_series(self, value: Any, path: str) -> dict[str, Any]:
        """Series ``atr``: ``smoothing`` and ``across_sessions`` appear only when given (older specs unchanged)."""
        atr = _object(value, path, required=("length",), optional=("smoothing", "across_sessions"))
        result: dict[str, Any] = {}
        across = atr.get("across_sessions", False)
        if not isinstance(across, bool):
            raise RuleSpecError(f"{path}.across_sessions", "must be true or false")
        maximum = MAX_WINDOW_BARS if across else self.bars_per_session
        result["length"] = self.count(atr["length"], f"{path}.length", maximum=maximum)
        if "smoothing" in atr:
            if atr["smoothing"] not in ATR_SMOOTHINGS:
                raise RuleSpecError(f"{path}.smoothing", f"must be one of: {', '.join(ATR_SMOOTHINGS)}")
            result["smoothing"] = atr["smoothing"]
        if "across_sessions" in atr:
            result["across_sessions"] = across
        return result

    def indicator(self, operator: str, node: Any, path: str) -> dict[str, Any]:
        """Validate a technical indicator node against its catalogue entry."""
        spec = INDICATORS[operator]
        required = (operator, *(key for key, _, _ in spec.params), *(("output",) if spec.outputs else ()))
        _object(node, path, required=required, optional=("across_sessions",))
        across = node.get("across_sessions", False)
        if not isinstance(across, bool):
            raise RuleSpecError(f"{path}.across_sessions", "must be true or false")
        where = f"{path}.{operator}"
        if spec.takes_series:
            result: dict[str, Any] = {operator: self.series(node[operator], where)}
        elif isinstance(node[operator], Mapping) and not node[operator]:
            result = {operator: {}}
        else:
            raise RuleSpecError(where, "must be an empty object {} (it reads high, low, close and volume)")
        maximum = MAX_WINDOW_BARS if across else self.bars_per_session
        for key, kind, minimum in spec.params:
            if kind == "count":
                result[key] = self.count(node[key], f"{path}.{key}", minimum=minimum, maximum=maximum)
            else:
                result[key] = self.amount(node[key], f"{path}.{key}", maximum=MAX_MULTIPLIER)
        result["across_sessions"] = across
        if spec.outputs:
            if node["output"] not in spec.outputs:
                raise RuleSpecError(f"{path}.output", f"must be one of: {', '.join(spec.outputs)}")
            result["output"] = node["output"]
        return result

    def count(self, node: Any, path: str, *, minimum: int = 1, maximum: int) -> Any:
        if isinstance(node, Mapping):
            _object(node, path, required=("param",))
            return {"param": self.param(node["param"], f"{path}.param", kind="count", minimum=minimum, maximum=maximum)}
        if not _is_count(node, minimum, maximum):
            raise RuleSpecError(path, f'must be a whole number from {minimum} to {maximum} or {{"param": "<variable>"}}')
        return node

    def amount(self, node: Any, path: str, *, maximum: float | None = None) -> Any:
        if isinstance(node, Mapping):
            _object(node, path, required=("param",))
            return {"param": self.param(node["param"], f"{path}.param", kind="amount", maximum=maximum)}
        if not _is_amount(node, maximum):
            limit = f" and below {maximum:g}" if maximum is not None else ""
            raise RuleSpecError(path, f'must be a number greater than zero{limit} or {{"param": "<variable>"}}')
        return node

    def param(
        self,
        name: Any,
        path: str,
        *,
        kind: str,
        minimum: int = 1,
        maximum: float | None = None,
    ) -> str:
        if not isinstance(name, str) or not name:
            raise RuleSpecError(path, "must be a variable name")
        if name not in self.variables:
            declared = ", ".join(sorted(str(key) for key in self.variables)) or "none"
            raise RuleSpecError(path, f"{name!r} is not a declared packet variable (declared: {declared})")
        definition = self.variables[name]
        values = definition.get("values") if isinstance(definition, Mapping) else None
        if not isinstance(values, (list, tuple)) or not values:
            raise RuleSpecError(path, f'variable {name!r} has no valid non-empty "values" list')
        for value in values:
            if kind == "count":
                valid = _is_count(value, minimum, int(maximum or MAX_WINDOW_BARS))
                requirement = f"whole numbers from {minimum} to {int(maximum or MAX_WINDOW_BARS)}"
            elif kind == "amount":
                valid = _is_amount(value, maximum)
                requirement = "numbers greater than zero" + (f" and below {maximum:g}" if maximum is not None else "")
            else:
                valid = _is_number(value)
                requirement = "finite numbers"
            if not valid:
                raise RuleSpecError(path, f"variable {name!r} value {value!r} cannot be used here; it needs {requirement}")
        if len({float(value) for value in values}) != len(values):
            raise RuleSpecError(path, f"variable {name!r} values must be distinct numbers")
        self.used.add(name)
        return name
