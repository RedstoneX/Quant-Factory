"""Starter kit for anyone (human or AI) writing a ``qf_candidate_v1`` research packet."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from rule_language import MAX_VARIABLE_GRID, RULE_LANGUAGE

_SCHEMA_FILE = Path(__file__).with_name("mes_sma_10_30_candidate.json")

_GUIDE = f"""\
HOW TO WRITE A QF CANDIDATE PACKET (qf_candidate_v1)
Start from "example" and change it. Send it as JSON or YAML.

FIELDS
schema: always "qf_candidate_v1".
candidate: title, one_line summary, family, status.
sources: where the idea came from (a link, a person, or your own observation).
hypothesis: behavior = what you think happens; failure_theory = how it could fail.
market: instruments (MES), timeframe (5m), session, holding_style, overnight_positions.
data_needs: dataset_id, requested_start, data_as_of, fields, minimum_resolution.
rules: the idea in words (setup, entries, exits, max_trades_per_session).
rule_spec: the same idea as machine-readable {RULE_LANGUAGE} rules. This is what gets tested.
variables: named choices with a values list. rule_spec uses one as {{"param": "name"}}.
fixed: values that never change. exclusions: what this idea must not do.

SUPPORTED
5-minute bars, regular session only (09:30-16:00 New York, flat before the close).
MES: trading costs are known, so results include fees and slippage.
History ends 2026-02-13.
Numeric variables only, every one used by rule_spec.

NOT SUPPORTED
Options. String variables. Any bar size other than 5m.
Markets other than MES: no cost data yet, so they cannot be tested honestly.

GRID LIMIT
Multiply the number of values of every variable. The result must not exceed {MAX_VARIABLE_GRID}.
Example: 10 values x 10 values = 100 is allowed; 10 x 11 = 110 is rejected.

Testing is backtest only. Paper trading needs separate owner approval.
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
    """Return {"schema", "example", "guide"} for writing a valid candidate packet.

    "schema" is what the dashboard's Download schema button serves today: the
    repository-owned qf_candidate_v1 reference packet.
    """
    return {
        "schema": json.loads(_SCHEMA_FILE.read_text(encoding="utf-8")),
        "example": copy.deepcopy(_example()),
        "guide": _GUIDE,
    }


__all__ = ["starter_kit"]
