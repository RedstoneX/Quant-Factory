"""Technical indicators in qf_rules_v1 (VectorBT PRO / TA-Lib): hand computations, causality, validation, unchanged older specs."""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pandas as pd
import pytest

from research_intake.starter_kit import INDICATOR_EXAMPLE_CONDITION, starter_kit
from rule_language import RuleSpecError, validate_rule_spec
from rule_language.indicators import INDICATORS
from strategies.rule_spec_evaluation import RuleEvaluator, SessionBars

CLOSE = [10, 10.5, 10.2, 10.8, 11.1, 10.9, 11.4, 11.0, 10.7, 11.2, 11.6, 11.3]
HIGH = [c + x for c, x in zip(CLOSE, [0.3, 0.4, 0.2, 0.5, 0.3, 0.4, 0.2, 0.6, 0.3, 0.4, 0.5, 0.2])]
LOW = [c - x for c, x in zip(CLOSE, [0.2, 0.3, 0.4, 0.2, 0.5, 0.3, 0.4, 0.3, 0.5, 0.2, 0.3, 0.4])]
VOLUME = [100.0, 150, 120, 200, 180, 90, 210, 160, 130, 170, 190, 110]


def _spec(node: Any) -> dict[str, Any]:
    return {
        "language": "qf_rules_v1",
        "bar": "5m",
        "tick_size": 0.25,
        "session": {"timezone": "America/New_York", "open": "09:30", "close": "16:00"},
        "flat_at": "15:55",
        "signals": [{"when": {"gt": [node, 0]}, "side": "long"}],
        "max_trades_per_session": 1,
    }


def _normalized(node: Any, variables: dict[str, Any] | None = None) -> Any:
    return validate_rule_spec(_spec(node), variables=variables or {})["signals"][0]["when"]["gt"][0]


def _bars(rows: int = 12, sessions: int = 1, parameters: dict[str, Any] | None = None) -> SessionBars:
    rng = np.random.default_rng(7)
    frames = []
    for session in range(sessions):
        if session == 0 and rows <= 12:
            close, high, low, volume = (np.array(x[:rows], dtype=float) for x in (CLOSE, HIGH, LOW, VOLUME))
        else:
            close = 100 + np.cumsum(rng.normal(0, 0.5, rows))
            high, low = close + rng.random(rows), close - rng.random(rows)
            volume = rng.integers(50, 500, rows).astype(float)
        frames.append(pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume}))
    return SessionBars.from_sessions(frames, tick_size=0.25, parameters=parameters or {})


def _evaluate(node: Any, bars: SessionBars, variables: dict[str, Any] | None = None) -> np.ndarray:
    return RuleEvaluator(bars).series(_normalized(node, variables))


# ---- independent reference implementations (plain Python loops, textbook definitions) ----


def _ema(values: list, n: int) -> list:
    alpha, out, current, seen = 2 / (n + 1), [], None, 0
    for value in values:
        if value is None:
            out.append(None)
            continue
        current = value if current is None else alpha * value + (1 - alpha) * current
        seen += 1
        out.append(current if seen >= n else None)
    return out


def _wilder(values: list, n: int) -> list:
    """VectorBT's Wilder smoothing: seeded with the first valid value, reported once n valid values were seen."""
    out = [None] * len(values)
    first = next((i for i, v in enumerate(values) if v is not None), len(values))
    current = None
    for i in range(first, len(values)):
        current = values[i] if current is None else (current * (n - 1) + values[i]) / n
        out[i] = current if i >= first + n - 1 else None
    return out


def _sma(values: list, n: int) -> list:
    return [
        sum(values[i - n + 1 : i + 1]) / n if i >= n - 1 and None not in values[i - n + 1 : i + 1] else None
        for i in range(len(values))
    ]


def _ratio(num: list, den: list, scale: float = 1.0) -> list:
    return [None if a is None or b is None or b == 0 else scale * a / b for a, b in zip(num, den)]


def _sub(a: list, b: list) -> list:
    return [None if x is None or y is None else x - y for x, y in zip(a, b)]


def _true_range(first_defined: bool) -> list:
    out = [HIGH[0] - LOW[0] if first_defined else None]
    for i in range(1, len(CLOSE)):
        out.append(max(HIGH[i] - LOW[i], abs(HIGH[i] - CLOSE[i - 1]), abs(LOW[i] - CLOSE[i - 1])))
    return out


def _window(values: list, n: int, pick: Any) -> list:
    return [pick(values[i - n + 1 : i + 1]) if i >= n - 1 else None for i in range(len(values))]


def _ref_rsi(n: int) -> list:
    change = [None] + [CLOSE[i] - CLOSE[i - 1] for i in range(1, len(CLOSE))]
    gain = _wilder([None if c is None else max(c, 0.0) for c in change], n)
    loss = _wilder([None if c is None else max(-c, 0.0) for c in change], n)
    total = [None if g is None else g + x for g, x in zip(gain, loss)]
    return _ratio(gain, total, 100.0)


def _ref_macd(fast: int, slow: int, signal: int) -> dict:
    line = _sub(_ema(CLOSE, fast), _ema(CLOSE, slow))
    sig = _ema(line, signal)
    return {"line": line, "signal": sig, "histogram": _sub(line, sig)}


def _ref_bollinger(n: int, mult: float) -> dict:
    middle = _sma(CLOSE, n)
    sd = [None if m is None else (sum((x - m) ** 2 for x in CLOSE[i - n + 1 : i + 1]) / n) ** 0.5 for i, m in enumerate(middle)]
    upper = [None if m is None else m + mult * s for m, s in zip(middle, sd)]
    lower = [None if m is None else m - mult * s for m, s in zip(middle, sd)]
    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "percent_b": _ratio(_sub(CLOSE, lower), _sub(upper, lower)),
        "bandwidth": _ratio(_sub(upper, lower), middle),
    }


def _ref_stochastic(k_length: int, k_smooth: int, d_length: int) -> dict:
    highest, lowest = _window(HIGH, k_length, max), _window(LOW, k_length, min)
    raw = _ratio(_sub(CLOSE, lowest), _sub(highest, lowest), 100.0)
    k = _sma(raw, k_smooth)
    return {"k": k, "d": _sma(k, d_length)}


def _ref_adx(n: int) -> dict:
    size = len(CLOSE)
    plus, minus = [0.0] * size, [0.0] * size  # vbt counts the first bar as zero movement
    for i in range(1, size):
        up, down = HIGH[i] - HIGH[i - 1], LOW[i - 1] - LOW[i]
        plus[i] = up if up > down and up > 0 else 0.0
        minus[i] = down if down > up and down > 0 else 0.0
    tr = _wilder(_true_range(False), n)
    plus_di, minus_di = _ratio(_wilder(plus, n), tr, 100.0), _ratio(_wilder(minus, n), tr, 100.0)
    dx = [None if p is None else 100.0 * abs(p - m) / (p + m) for p, m in zip(plus_di, minus_di)]
    return {"adx": _wilder(dx, n), "plus_di": plus_di, "minus_di": minus_di}


def _ref_cci(n: int) -> list:
    typical = [(h + low + c) / 3 for h, low, c in zip(HIGH, LOW, CLOSE)]
    out = []
    for i in range(len(typical)):
        if i < n - 1:
            out.append(None)
            continue
        window = typical[i - n + 1 : i + 1]
        mean = sum(window) / n
        deviation = sum(abs(x - mean) for x in window) / n
        out.append((typical[i] - mean) / (0.015 * deviation))
    return out


def _ref_obv() -> list:
    out, total = [], 0.0
    for i, volume in enumerate(VOLUME):
        step = 1 if i == 0 else (CLOSE[i] > CLOSE[i - 1]) - (CLOSE[i] < CLOSE[i - 1])
        total += step * volume
        out.append(total)
    return out


def _ref_keltner(n: int, atr_length: int, mult: float) -> dict:
    middle, atr = _ema(CLOSE, n), _wilder(_true_range(False), atr_length)
    return {
        "upper": [None if m is None or a is None else m + mult * a for m, a in zip(middle, atr)],
        "middle": middle,
        "lower": [None if m is None or a is None else m - mult * a for m, a in zip(middle, atr)],
    }


def _ref_donchian(n: int) -> dict:
    upper, lower = _window(HIGH, n, max), _window(LOW, n, min)
    return {"upper": upper, "lower": lower, "middle": [None if u is None else (u + x) / 2 for u, x in zip(upper, lower)]}


def _roc(n: int) -> list:
    return [None if i < n else 100.0 * (CLOSE[i] - CLOSE[i - n]) / CLOSE[i - n] for i in range(len(CLOSE))]


def _williams(n: int) -> list:
    highest, lowest = _window(HIGH, n, max), _window(LOW, n, min)
    return [None if h is None else -100.0 * (h - c) / (h - x) for h, x, c in zip(highest, lowest, CLOSE)]


CASES = [
    ({"rsi": "close", "length": 3}, _ref_rsi(3)),
    ({"roc": "close", "length": 3}, _roc(3)),
    *[({"macd": "close", "fast": 2, "slow": 4, "signal": 3, "output": k}, v) for k, v in _ref_macd(2, 4, 3).items()],
    *[({"bollinger": "close", "length": 4, "std_mult": 2, "output": k}, v) for k, v in _ref_bollinger(4, 2).items()],
    *[({"stochastic": {}, "k_length": 4, "k_smooth": 2, "d_length": 3, "output": k}, v) for k, v in _ref_stochastic(4, 2, 3).items()],
    *[({"adx": {}, "length": 3, "output": k}, v) for k, v in _ref_adx(3).items()],
    ({"cci": {}, "length": 4}, _ref_cci(4)),
    ({"williams_r": {}, "length": 4}, _williams(4)),
    ({"obv": {}}, _ref_obv()),
    *[({"keltner": {}, "length": 3, "atr_length": 2, "mult": 1.5, "output": k}, v) for k, v in _ref_keltner(3, 2, 1.5).items()],
    *[({"donchian": {}, "length": 4, "output": k}, v) for k, v in _ref_donchian(4).items()],
    ({"atr": {"length": 3, "smoothing": "wilder"}}, _wilder(_true_range(False), 3)),
]


@pytest.mark.parametrize("node, expected", CASES, ids=[f"{next(iter(n))}-{n.get('output', '')}" for n, _ in CASES])
def test_indicator_matches_hand_computation(node: dict, expected: list) -> None:
    result = _evaluate(node, _bars())[:, 0]
    np.testing.assert_allclose(result, np.array(expected, dtype=float), rtol=1e-9, atol=1e-9, equal_nan=True)
    assert np.isfinite(result).any(), "case must exercise at least one defined value"


def test_every_catalogue_indicator_is_covered_by_a_hand_case() -> None:
    covered = {next(iter(node)) for node, _ in CASES}
    assert set(INDICATORS) <= covered


def test_variable_parameters_equal_literals() -> None:
    node = {"macd": "close", "fast": {"param": "f"}, "slow": 4, "signal": 3, "output": "line"}
    variables = {"f": {"values": [2, 3]}}
    bars = _bars(parameters={"f": 2})
    literal = _evaluate({"macd": "close", "fast": 2, "slow": 4, "signal": 3, "output": "line"}, bars)
    np.testing.assert_array_equal(_evaluate(node, bars, variables), literal)
    boll = {"bollinger": "close", "length": 4, "std_mult": {"param": "k"}, "output": "upper"}
    bars = _bars(parameters={"k": 2.0})
    np.testing.assert_array_equal(
        _evaluate(boll, bars, {"k": {"values": [1.5, 2.0]}}),
        _evaluate({**boll, "std_mult": 2.0}, bars),
    )


def test_indicators_compose_with_existing_operators() -> None:
    bars = _bars(rows=40)
    line = _evaluate({"macd": "close", "fast": 3, "slow": 8, "signal": 3, "output": "line"}, bars)
    fast = RuleEvaluator(bars).series({"ema": "close", "length": 3, "across_sessions": False})
    slow = RuleEvaluator(bars).series({"ema": "close", "length": 8, "across_sessions": False})
    np.testing.assert_allclose(line, fast - slow, equal_nan=True)
    on_rsi = _evaluate({"rsi": {"sma": "close", "length": 2}, "length": 3}, bars)
    assert np.isfinite(on_rsi).any()


@pytest.mark.parametrize("across", [False, True])
def test_indicators_are_causal(across: bool) -> None:
    nodes = [node for node, _ in CASES]
    long_bars, short_bars = _bars(rows=40, sessions=3), None
    for node in nodes:
        node = {**node, "across_sessions": True} if across and "atr" not in node else node
        if "atr" in node and across:
            node = {"atr": {**node["atr"], "across_sessions": True}}
        full = _evaluate(node, long_bars)
        if across:  # appending future SESSIONS must not change earlier sessions
            short_bars = _bars(rows=40, sessions=2)
            np.testing.assert_array_equal(full[:, :2], _evaluate(node, short_bars))
        else:  # appending future BARS must not change earlier bars
            short_bars = SessionBars.from_sessions(
                [pd.DataFrame({"Open": c, "High": h, "Low": lo, "Close": c, "Volume": v})
                 for c, h, lo, v in zip(
                     long_bars.close.T[:, :30], long_bars.high.T[:, :30], long_bars.low.T[:, :30], long_bars.volume.T[:, :30]
                 )],
                tick_size=0.25,
                parameters={},
            )
            np.testing.assert_array_equal(full[:30], _evaluate(node, short_bars))


def test_across_sessions_runs_through_the_session_boundary() -> None:
    bars = _bars(rows=10, sessions=2)
    scoped = _evaluate({"rsi": "close", "length": 4}, bars)
    across = _evaluate({"rsi": "close", "length": 4, "across_sessions": True}, bars)
    assert np.isnan(scoped[:4, 1]).all() and np.isfinite(across[:, 1]).all()
    np.testing.assert_array_equal(scoped[:, 0], across[:, 0])


@pytest.mark.parametrize(
    "node, text",
    [
        ({"rsi": "close", "length": 1}, "length"),
        ({"rsi": "close", "length": 79}, "length"),
        ({"rsi": "close", "length": 14.5}, "length"),
        ({"rsi": "close", "length": 14, "output": "x"}, "unknown key"),
        ({"rsi": "close"}, "missing required key 'length'"),
        ({"rsi": {}, "length": 14}, "empty object"),
        ({"rsi": "nope", "length": 14}, "unknown price field"),
        ({"rsi": "close", "length": 14, "across_sessions": "yes"}, "true or false"),
        ({"macd": "close", "fast": 2, "slow": 4, "signal": 3}, "missing required key 'output'"),
        ({"macd": "close", "fast": 2, "slow": 4, "signal": 3, "output": "bar"}, "must be one of"),
        ({"bollinger": "close", "length": 20, "std_mult": 0, "output": "upper"}, "greater than zero"),
        ({"bollinger": "close", "length": 20, "std_mult": 21, "output": "upper"}, "below 20"),
        ({"stochastic": "close", "k_length": 5, "k_smooth": 3, "d_length": 3, "output": "k"}, "empty object"),
        ({"stochastic": {}, "k_length": 5, "k_smooth": 0, "d_length": 3, "output": "k"}, "k_smooth"),
        ({"adx": {}, "length": 14}, "missing required key 'output'"),
        ({"obv": {}, "length": 5}, "unknown key"),
        ({"keltner": {}, "length": 20, "atr_length": 10, "output": "upper"}, "missing required key 'mult'"),
        ({"atr": {"length": 14, "smoothing": "ema"}}, "smoothing"),
        ({"atr": {"length": 14, "across_sessions": 1}}, "true or false"),
    ],
)
def test_validation_rejects_bad_indicator_nodes(node: dict, text: str) -> None:
    with pytest.raises(RuleSpecError, match=text):
        _normalized(node)


def test_validation_limits_follow_scope_and_variables() -> None:
    assert _normalized({"rsi": "close", "length": 20_000, "across_sessions": True})["length"] == 20_000
    with pytest.raises(RuleSpecError, match="length"):
        _normalized({"rsi": "close", "length": 20_001, "across_sessions": True})
    with pytest.raises(RuleSpecError, match="cannot be used here"):
        _normalized({"rsi": "close", "length": {"param": "n"}}, {"n": {"values": [1, 5]}})
    with pytest.raises(RuleSpecError, match="not a declared"):
        _normalized({"rsi": "close", "length": {"param": "missing"}})


def test_normalized_form_of_indicator_and_older_atr() -> None:
    assert _normalized({"adx": {}, "length": 14, "output": "adx"}) == {
        "adx": {},
        "length": 14,
        "across_sessions": False,
        "output": "adx",
    }
    assert _normalized({"atr": {"length": 14}}) == {"atr": {"length": 14}}


def test_existing_spec_normalizes_and_evaluates_unchanged() -> None:
    packet = starter_kit()["example"]
    normalized = validate_rule_spec(copy.deepcopy(packet["rule_spec"]), variables=packet["variables"])
    assert normalized["signals"][0]["when"]["all"][0] == {
        "crosses_above": [
            {"sma": "close", "length": {"param": "fast_bars"}, "across_sessions": False},
            {"sma": "close", "length": 30, "across_sessions": False},
        ]
    }
    bars = _bars(rows=40)
    evaluator = RuleEvaluator(bars)
    np.testing.assert_array_equal(evaluator.series({"atr": {"length": 5}}), evaluator.atr(5))


def test_starter_kit_guide_documents_every_indicator() -> None:
    guide = starter_kit()["guide"]
    for name, spec in INDICATORS.items():
        assert name in guide, name
        for output in spec.outputs:
            assert output in guide, (name, output)


def test_guide_example_condition_is_valid_and_evaluates() -> None:
    spec = _spec(0)
    spec["signals"][0]["when"] = INDICATOR_EXAMPLE_CONDITION
    normalized = validate_rule_spec(spec, variables={})
    mask = RuleEvaluator(_bars(rows=40)).condition(normalized["signals"][0]["when"])
    assert mask.shape == (40, 1)
