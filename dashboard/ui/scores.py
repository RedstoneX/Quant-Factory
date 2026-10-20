"""Recorded-score columns and cards shared by the Ideas and Results pages.

Rolling-test and stress-test results are scores, not gates. A score that would
have failed the old gate shows amber, never red.
"""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc

from dashboard.score_projection import LUCK_OLDER, OLDER_LUCK_LINE
from dashboard.ui.layout import stat_card
from dashboard.ui.theme import COLUMN_DEFAULTS, MUTED, WARNING, grid_options, hide_when_narrow

AMBER = "yellow.5"
STRESS_WORDS = {"passed": "Held up", "failed": "Weak", "insufficient_evidence": "Not enough data"}
_STRESS_JS = "({'passed':'Held up','failed':'Weak','insufficient_evidence':'Not enough data'})[params.value] || '—'"
_AMBER_ROLLING = {"styleConditions": [{"condition": "params.data.rolling_status === 'failed'", "style": {"color": WARNING}}]}
_AMBER_STRESS = {"styleConditions": [{"condition": "params.data.stress_status === 'failed'", "style": {"color": WARNING}}]}
_PERCENT = "params.value == null ? '—' : (params.value * 100).toFixed(0) + '%'"
# Luck scores from the older method (1-minute values) are never ranked with daily-returns ones:
# the row shows "older method" in grey and sorts last in either direction (AG Grid comparator).
_OLDER = f"params.data.luck_basis === '{LUCK_OLDER}'"
_LUCK_TEXT = f"{_OLDER} ? 'older method' : ({_PERCENT})"
_LUCK_ORDER = (
    f"(nodeA.data.luck_basis === '{LUCK_OLDER}') !== (nodeB.data.luck_basis === '{LUCK_OLDER}')"
    f" ? ((nodeA.data.luck_basis === '{LUCK_OLDER}') ? 1 : -1) * (isDescending ? -1 : 1)"
    " : (valueA == null ? -Infinity : valueA) - (valueB == null ? -Infinity : valueB) || 0"
)

SHORTLIST_COLUMNS = [
    {"field": "rank", "headerName": "#", "maxWidth": 56, "sortable": False},
    {"field": "title", "headerName": "Idea", "flex": 2, "minWidth": 160, "tooltipField": "candidate_id", "wrapText": True, "autoHeight": True, "cellStyle": {"whiteSpace": "normal", "lineHeight": "1.3"}},
    {"field": "symbol", "headerName": "Market", "flex": .6},
    {"field": "sharpe", "headerName": "Unseen-data Sharpe", "type": "numericColumn", "flex": 1, "sort": "desc",
     "headerTooltip": "Return per unit of risk on data the idea never saw while being built. Higher is better.",
     "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field": "folds_share", "headerName": "Rolling test: periods profitable", "type": "numericColumn", "flex": 1.1,
     "headerTooltip": "Share of the rolling test periods that made money. Higher is steadier.",
     "valueFormatter": {"function": _PERCENT}, "cellStyle": _AMBER_ROLLING},
    {"field": "fold_sharpe", "headerName": "Rolling test: average Sharpe", "type": "numericColumn", "flex": 1.1,
     "headerTooltip": "Average Sharpe across the rolling test periods.",
     "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2)"}, "cellStyle": _AMBER_ROLLING},
    {"field": "stress_status", "headerName": "Stress test", "flex": 1,
     "headerTooltip": "Whether the idea still worked with worse costs and shuffled trades.",
     "valueFormatter": {"function": _STRESS_JS}, "cellStyle": _AMBER_STRESS},
    {"field": "luck", "headerName": "Luck score", "type": "numericColumn", "flex": .8,
     "headerTooltip": "Chance the result is skill rather than luck from trying many settings (deflated Sharpe, daily returns). Higher is better.",
     "valueFormatter": {"function": _LUCK_TEXT},
     "cellStyle": {"styleConditions": [{"condition": _OLDER, "style": {"color": MUTED}}]},
     "comparator": {"function": _LUCK_ORDER}},
    {"field": "overfitting", "headerName": "Overfitting score", "type": "numericColumn", "flex": .9,
     "headerTooltip": "Chance the best setting only looks good because it was picked from many (backtest overfitting). Lower is better.",
     "valueFormatter": {"function": _PERCENT}},
]


def shortlist_grid(grid_id: str = "shortlist-grid") -> dag.AgGrid:
    return dag.AgGrid(
        id=grid_id, columnDefs=SHORTLIST_COLUMNS, rowData=[], columnSize="responsiveSizeToFit",
        defaultColDef={**COLUMN_DEFAULTS, "suppressHeaderMenuButton": True},
        dashGridOptions=grid_options("No ideas have cleared the unseen-data test yet.", animateRows=False, tooltipShowDelay=300),
        getRowId="params.data.candidate_id", style={"height": "calc(100dvh - 380px)", "minHeight": 360},
        eventListeners=hide_when_narrow("symbol", "fold_sharpe", "luck", "overfitting"),
    )


def _pct(value: Any) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _stress_note(scores: dict[str, Any]) -> str:
    """A failed stress test is a score, not a pass mark; say so and say which check it was."""
    if scores.get("stress_status") != "failed":
        return ""
    failed = " and ".join(scores.get("stress_failed") or [])
    return f"A score, not a pass mark. It slipped on {failed}." if failed else "A score, not a pass mark."


def _luck_card(s: dict[str, Any]) -> dmc.Paper:
    """An older-method Luck score keeps its number, in grey, with the one line saying why."""
    if s.get("luck_basis") == LUCK_OLDER:
        return stat_card("Luck score", _pct(s.get("luck")), OLDER_LUCK_LINE, color="dimmed")
    return stat_card("Luck score", _pct(s.get("luck")), "higher is better" if s.get("luck") is not None else "")


def score_cards(scores: dict[str, Any] | None) -> list[dmc.Paper]:
    """Five stat cards; '—' when a score was not recorded."""
    s = scores or {}
    rolling_color = AMBER if s.get("rolling_status") == "failed" else None
    stress_color = AMBER if s.get("stress_status") == "failed" else None
    folds = "—" if s.get("folds_profitable") is None else f"{s['folds_profitable']} of {s['folds_total']}"
    return [
        stat_card("Rolling test: periods profitable", folds, _pct(s.get("folds_share")) if s.get("folds_profitable") is not None else "", color=rolling_color),
        stat_card("Rolling test: average Sharpe", "—" if s.get("fold_sharpe") is None else f"{s['fold_sharpe']:.2f}", color=rolling_color),
        stat_card("Stress test", STRESS_WORDS.get(str(s.get("stress_status")), "—"), _stress_note(s), color=stress_color),
        _luck_card(s),
        stat_card("Overfitting score", _pct(s.get("overfitting")), "lower is better" if s.get("overfitting") is not None else ""),
    ]


__all__ = ["SHORTLIST_COLUMNS", "shortlist_grid", "score_cards"]
