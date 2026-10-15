"""Starter kit for anyone (human or AI) writing a ``qf_candidate_v1`` research packet."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from rule_language import MAX_VARIABLE_GRID, RULE_LANGUAGE
from rule_language.indicators import library_indicators

_SCHEMA_FILE = Path(__file__).with_name("mes_sma_10_30_candidate.json")

_GUIDE = f"""\
HOW TO WRITE A QF CANDIDATE PACKET (qf_candidate_v1)
Start from "example" and change it. Send it as JSON or YAML.

FIELDS
schema: always "qf_candidate_v1".
candidate: title, one_line summary, family, status.
sources: where the idea came from (a link, a person, or your own observation).
hypothesis: behavior = what you think happens; failure_theory = how it could fail.
market: instruments (MES), timeframe ("5m" or "1m"), session, holding_style, overnight_positions.
data_needs: dataset_id, requested_start, data_as_of, fields, minimum_resolution.
rules: the idea in words (setup, entries, exits, max_trades_per_session).
rule_spec: the same idea as machine-readable {RULE_LANGUAGE} rules. This is what gets tested.
variables: named choices with a values list. rule_spec uses one as {{"param": "name"}}.
fixed: values that never change. exclusions: what this idea must not do.

SUPPORTED
Bar sizes: "5m" (MES futures data; 5-minute bars, 78 per session) and "1m" (US stock/ETF library; 390 per session).
Set rule_spec "bar" and market.timeframe to the same value; the data must match (nothing is resampled).
Entries in the regular session (09:30-16:00 New York). Times are bar END times:
the first 5m bar ends 09:35, the first 1m bar ends 09:31. Lengths and after_bars are bar counts:
30 bars is 150 minutes on 5m but 30 minutes on 1m, so pick them for the bar size.
Positions are simulated on continuous history. Futures (MES) must set "flat_at": "15:55" (flat before the close);
without flat_at a position may be held overnight (stocks).
exit "after_bars" is the maximum hold (VectorBT's own time exit); it may be a variable, so the hold taken from the
idea's source can be swept. max_trades_per_session counts entries filled per session; a trade closed by a stop still
counts and holds its slot until a rule exit (exit_when, opposite signal, at_time, flat_at) or its maximum hold.
MES: trading costs are known, so results include fees and slippage; the 1-tick slippage is charged on every fill,
stop exits included (owner ruling 15 Oct 2026). History ends 2026-02-13.
Optional rule_spec "skip_days": ["cpi", "fomc"] takes no new entries on US CPI release days and/or FOMC decision days.
Numeric variables only, every one used by rule_spec.

NOT SUPPORTED
Options. String variables. Any bar size other than 1m or 5m.
Markets other than MES: no cost data yet, so they cannot be tested honestly.

GRID LIMIT
Multiply the number of values of every variable. The result must not exceed {MAX_VARIABLE_GRID}.

Testing is backtest only. Paper trading needs separate owner approval.
"""

INDICATOR_EXAMPLE_CONDITION = {
    "all": [
        {"lt": [{"rsi": "close", "length": 14}, 30]},
        {"lt": ["close", {"bollinger": "close", "length": 20, "std_mult": 2, "output": "lower"}]},
    ]
}

_INDICATOR_GUIDE = """\
INDICATORS (optional series; the value at a bar uses only that bar and earlier ones)
S = a price field or any series, e.g. "close" or {"sma": "close", "length": 5}.
"across_sessions": true runs through earlier sessions (length up to 20000); default false restarts each session.
{"rsi": S, "length": N} Wilder RSI, 0-100. {"roc": S, "length": N} percent change versus N bars ago.
{"macd": S, "fast": a, "slow": b, "signal": c, "output": "line" | "signal" | "histogram"}
{"bollinger": S, "length": N, "std_mult": k, "output": "upper" | "middle" | "lower" | "percent_b" | "bandwidth"}
These read high, low, close and volume, so they take {} instead of S:
{"stochastic": {}, "k_length": a, "k_smooth": b, "d_length": c, "output": "k" | "d"} 0-100; k_smooth 1 = fast.
{"adx": {}, "length": N, "output": "adx" | "plus_di" | "minus_di"} Wilder, 0-100.
{"cci": {}, "length": N} {"williams_r": {}, "length": N} -100 to 0. {"obv": {}} volume signed by direction.
{"keltner": {}, "length": N, "atr_length": M, "mult": k, "output": "upper" | "middle" | "lower"} EMA +/- k Wilder ATR.
{"donchian": {}, "length": N, "output": "upper" | "lower" | "middle"} includes the current bar;
for a breakout compare with {"prev": {"donchian": ...}, "bars": 1}.
{"atr": {"length": N, "smoothing": "wilder"}} "smoothing" is optional ("sma", the default, is a simple mean).
Example of the "when" of a signal using two indicators:
""" + json.dumps(INDICATOR_EXAMPLE_CONDITION, separators=(",", ":")) + "\n"

LIBRARY_EXAMPLE_SERIES = {"indicator": "talib:CCI", "params": {"timeperiod": 20}, "output": "real"}

_LIBRARY_GUIDE = json.dumps(LIBRARY_EXAMPLE_SERIES, separators=(",", ":")) + """\
 runs any entry of the kit's "indicators" list;
give all its params; "inputs": {"close": S} swaps a price input for any series. "across_sessions" as above.
"""


def _library_entries() -> list[dict[str, Any]]:
    """Reference data: the usable library indicators, read from the installed library (empty without it)."""
    return [
        {"name": s.name, "inputs": list(s.inputs), "params": dict(s.params), "outputs": list(s.outputs)}
        for s in library_indicators()
    ]


STOPS_EXAMPLE_EXIT = {
    "stop_loss": {"ticks": 8},
    "take_profit": {"percent": 0.5},
    "trailing_stop": {"atr": {"length": 14, "multiple": 2}},
}

_STOPS_GUIDE = """\
STOPS (optional, in rule_spec "exit"; use any one, two or all three)
stop_loss: exit when price moves this far against the entry fill.
take_profit: exit when price moves this far in favour of the entry fill.
trailing_stop: exit when price falls back this far from the best price since entry.
Distances: {"percent": x}, {"points": x}, {"ticks": n} or {"atr": {"length": N, "multiple": k}}.
Each distance is fixed when the trade is entered (an ATR distance uses the ATR at the signal bar).
If a bar opens beyond a stop, the exit fills at that open, not at the stop.
Example "exit":
""" + json.dumps(STOPS_EXAMPLE_EXIT, separators=(",", ":")) + "\n" + """\
stop_loss {"level": S}: a price read at the signal bar, e.g. {"range_low": {"from": "09:30", "to": "10:00"}}; entry skipped if its fill is through it.
take_profit {"r_multiple": R}: R x the stop-loss distance. trail_after (a distance or R): gain that switches trailing_stop on;
  breakeven then trail = same distance in both, e.g. {"trailing_stop": {"points": 4}, "trail_after": {"points": 4}}.
exit_when {"long": C, "short": C}: exit at the next open when condition C is true; a later signal may re-enter.
  Trail off the prior N-bar low: {"long": {"lt": ["close", {"prev": {"donchian": {}, "length": N, "output": "lower"}, "bars": 1}]}}.
{"every_minutes": N}: bars ending on an N-minute boundary; with {"time_between": ["09:50", "15:50"]} = every 5m close on 1m bars.
"""


def _example() -> dict[str, Any]:
    packet = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
    packet["candidate"]["title"] = "MES intraday SMA crossover, long only, fast length grid"
    packet["candidate"]["one_line"] = (
        "Go long on the first same-session cross of a fast SMA above the 30-bar SMA; "
        "the fast length is one bounded variable."
    )
    packet["market"]["instruments"] = {"preferred": ["MES"]}
    rules = packet["rules"]
    rules.pop("short_entry", None)
    rules["long_entry"] = [
        "Take the completed-bar cross of the fast SMA above the 30-bar SMA between 09:35 and 15:50 ET; "
        "enter at the next contiguous five-minute open."
    ]
    for key in ("fast_sma_bars", "slow_sma_bars"):
        packet["fixed"].pop(key, None)
    packet["fixed"]["slow_sma_bars"] = 30
    packet["variables"] = {
        "fast_bars": {
            "values": [5, 10, 15, 20],
            "rationale": "Four bounded fast-average lengths; the slow length stays fixed at 30.",
        }
    }
    packet["rule_spec"] = {
        "language": RULE_LANGUAGE,
        "bar": "5m",
        "tick_size": 0.25,
        "session": {"timezone": "America/New_York", "open": "09:30", "close": "16:00"},
        "flat_at": "15:55",
        "signals": [
            {
                "when": {
                    "all": [
                        {
                            "crosses_above": [
                                {"sma": "close", "length": {"param": "fast_bars"}},
                                {"sma": "close", "length": 30},
                            ]
                        },
                        {"time_between": ["09:35", "15:50"]},
                    ]
                },
                "side": "long",
            }
        ],
        "max_trades_per_session": 1,
    }
    packet["exclusions"] = [
        "No overnight position.",
        "No short trades.",
        "No stop, target or hidden filter beyond the rule_spec.",
        "No paper/live trading or automatic promotion.",
    ]
    return packet


def starter_kit() -> dict[str, Any]:
    """Return {"schema", "example", "guide", "indicators"} for writing a valid candidate packet.

    "schema" is what the dashboard's Download schema button serves today: the
    repository-owned qf_candidate_v1 reference packet.
    """
    return {
        "schema": json.loads(_SCHEMA_FILE.read_text(encoding="utf-8")),
        "example": copy.deepcopy(_example()),
        "guide": _GUIDE + _INDICATOR_GUIDE + _LIBRARY_GUIDE + _STOPS_GUIDE,
        "indicators": _library_entries(),
    }


__all__ = ["starter_kit"]
