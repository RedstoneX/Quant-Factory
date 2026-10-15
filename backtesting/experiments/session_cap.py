"""At most N entry FILLS per session, through VectorBT PRO's documented from_signals callbacks.

No array argument of ``Portfolio.from_signals`` limits entries per session, and the limit depends on
simulation state (an entry signal while a position is open is not a fill), so it uses the callback pair the
vbt-callbacks skill prescribes for state-dependent signals: ``signal_func_nb`` drops entry signals once the
session's count is reached, and ``post_order_func_nb`` counts fills that open a position
(``vbt.pf_nb.order_opened_position_nb``).  Stops are untouched.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbtpro as vbt
from numba import njit


@njit
def session_cap_signal_nb(c, long_entries, long_exits, short_entries, short_exits, session, cap, state):  # pragma: no cover - compiled
    """state[0, col]: the current session id; state[1, col]: entries filled in it.

    A rule exit and a same-side entry signal on one bar resolve by the position, as the rule language defines:
    a held position exits, a flat one may enter (VectorBT's ConflictMode has no mode for exactly that)."""
    long_entry = vbt.pf_nb.select_nb(c, long_entries)
    long_exit = vbt.pf_nb.select_nb(c, long_exits)
    short_entry = vbt.pf_nb.select_nb(c, short_entries)
    short_exit = vbt.pf_nb.select_nb(c, short_exits)
    day = vbt.pf_nb.select_nb(c, session)
    if day != state[0, c.col]:
        state[0, c.col] = day
        state[1, c.col] = 0
    if state[1, c.col] >= cap:
        long_entry = False
        short_entry = False
    position = c.last_position[c.col]
    if position > 0:
        long_entry = False
    elif position < 0:
        short_entry = False
    else:
        long_exit = False
        short_exit = False
    return long_entry, long_exit, short_entry, short_exit


@njit
def count_entry_fills_nb(c, state):  # pragma: no cover - compiled
    if vbt.pf_nb.order_opened_position_nb(c):
        state[1, c.col] += 1


def session_cap_kwargs(session: pd.Series, index: pd.Index, cap: int, columns: int) -> dict[str, Any]:
    """from_signals kwargs that cap entry fills at ``cap`` per session id (``session``: one id per bar)."""
    state = np.full((2, columns), -1, dtype=np.int64)
    return {
        "signal_func_nb": session_cap_signal_nb,
        "signal_args": (
            vbt.Rep("long_entries"), vbt.Rep("long_exits"), vbt.Rep("short_entries"), vbt.Rep("short_exits"),
            vbt.Rep("session"), int(cap), state,
        ),
        "post_order_func_nb": count_entry_fills_nb,
        "post_order_args": (state,),
        "broadcast_named_args": {"session": session.reindex(index).fillna(-1).to_numpy(dtype=np.int64)},
        # A cacheable copy of the callback simulator, so a new process does not recompile it (vbt-callbacks §4).
        "staticized": {"path": str(Path(tempfile.gettempdir()) / "qf_vbt_session_cap_sim.py")},
    }
