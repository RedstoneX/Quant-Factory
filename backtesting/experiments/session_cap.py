"""The rule language's trade count per session, through VectorBT PRO's documented from_signals callbacks.

No array argument of ``Portfolio.from_signals`` limits entries per session, and the limit depends on
simulation state, so it uses the callback pair the vbt-callbacks skill prescribes for state-dependent
signals: ``signal_func_nb`` drops entry signals, and ``post_order_func_nb`` records fills that open a position
(``vbt.pf_nb.order_opened_position_nb``).  Stops are untouched.

The rule language's meaning (unchanged from the per-session walk it replaces): a trade is taken by an entry
fill and stays "the session's open trade" until a RULE exit of its side (exit_when, opposite signal, at_time,
flat_at) or its max hold (``td_stop``) — a stop exit closes the position but does not free the trade, so the
next entry waits for that rule exit.  No entry fills on the bar a trade ends.  At most ``cap`` trades per
session.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbtpro as vbt
from numba import njit

_SESSION, _COUNT, _SIDE, _SINCE = 0, 1, 2, 3


@njit
def session_cap_signal_nb(c, long_entries, long_exits, short_entries, short_exits, session, hold, cap, state):  # pragma: no cover - compiled
    """state rows: the current session id, trades taken in it, the open trade's side (0 none) and fill time."""
    long_entry = vbt.pf_nb.select_nb(c, long_entries)
    long_exit = vbt.pf_nb.select_nb(c, long_exits)
    short_entry = vbt.pf_nb.select_nb(c, short_entries)
    short_exit = vbt.pf_nb.select_nb(c, short_exits)
    day = vbt.pf_nb.select_nb(c, session)
    max_hold = vbt.pf_nb.select_nb(c, hold)
    col = c.col
    if day != state[_SESSION, col]:
        state[_SESSION, col] = day
        state[_COUNT, col] = 0
        if c.last_position[col] == 0:
            state[_SIDE, col] = 0
    side = state[_SIDE, col]
    if side != 0:
        # The open trade ends on a rule exit of its side or at its max hold; no new entry on this bar.
        if (side > 0 and long_exit) or (side < 0 and short_exit) or (max_hold >= 0 and c.index[c.i] - state[_SINCE, col] >= max_hold):
            state[_SIDE, col] = 0
        long_entry = False
        short_entry = False
    elif state[_COUNT, col] >= cap:
        long_entry = False
        short_entry = False
    position = c.last_position[col]
    if position > 0:
        short_exit = False
    elif position < 0:
        long_exit = False
    else:
        long_exit = False
        short_exit = False
    return long_entry, long_exit, short_entry, short_exit


@njit
def record_trade_nb(c, state):  # pragma: no cover - compiled
    if vbt.pf_nb.order_opened_position_nb(c):
        state[_COUNT, c.col] += 1
        state[_SIDE, c.col] = 1 if c.last_position[c.col] > 0 else -1
        state[_SINCE, c.col] = c.index[c.i]


def session_cap_kwargs(
    session: pd.Series, index: pd.Index, cap: int, columns: int, hold: Any = None
) -> dict[str, Any]:
    """from_signals kwargs for at most ``cap`` trades per session id (``session``: one id per bar).

    ``hold``: the aligned ``td_stop`` (nanoseconds, -1 none) passed to from_signals, or None."""
    state = np.zeros((4, columns), dtype=np.int64)
    state[_SESSION] = -2
    return {
        "signal_func_nb": session_cap_signal_nb,
        "signal_args": (
            vbt.Rep("long_entries"), vbt.Rep("long_exits"), vbt.Rep("short_entries"), vbt.Rep("short_exits"),
            vbt.Rep("session"), vbt.Rep("hold"), int(cap), state,
        ),
        "post_order_func_nb": record_trade_nb,
        "post_order_args": (state,),
        "broadcast_named_args": {
            "session": session.reindex(index).fillna(-1).to_numpy(dtype=np.int64),
            "hold": np.int64(-1) if hold is None else hold,
        },
        # A cacheable copy of the callback simulator, so a new process does not recompile it (vbt-callbacks §4).
        "staticized": {"path": str(Path(tempfile.gettempdir()) / "qf_vbt_session_cap_sim.py")},
    }
