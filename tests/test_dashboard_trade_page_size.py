"""Trade tables on the Report and Results pages offer an AG Grid page-size selector.

The ideas workbench stays at 50 rows with the selector off.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dashboard.ui import idea_report, results, results_workbench


def _plain(component: Any) -> Any:
    return json.loads(json.dumps(component.to_plotly_json(), default=lambda item: item.to_plotly_json()))


def _grids(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        props = node.get("props") or {}
        if node.get("type") == "AgGrid":
            found.append(props)
        for value in props.values():
            found.extend(_grids(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_grids(item))
    return found


def test_report_trade_grids_keep_every_trade_and_offer_page_sizes() -> None:
    trades = [
        {"trade_id": str(number), "entry_timestamp": f"2024-06-{(number % 28) + 1:02d}T10:{number % 60:02d}:00", "pnl": float(number)}
        for number in range(1, 31)
    ]
    panel = idea_report.trades_panel({"trades": trades, "unseen_trades_saved": True})
    grids = {grid["id"]: grid for grid in _grids(_plain(panel))}
    assert set(grids) == {"idea-report-trades", "idea-report-trades-phone"}
    for grid in grids.values():
        options = grid["dashGridOptions"]
        assert options["pagination"] is True
        assert options["paginationPageSize"] == results.TRADE_PAGE_SIZE == 10
        assert options["paginationPageSizeSelector"] == [10, 25, 50, 100, 100_000]
        assert len(grid["rowData"]) == 30  # the page size is a view, not a cap on the loaded trades


def test_results_trade_grid_offers_the_same_page_sizes() -> None:
    options = results._trade_grid("results-trade-grid").dashGridOptions
    assert options["pagination"] is True
    assert options["paginationPageSize"] == 10
    assert options["paginationPageSizeSelector"] == results.TRADE_PAGE_SIZES


def test_ideas_workbench_page_size_stays_fifty_without_a_selector() -> None:
    source = Path(results_workbench.__file__).read_text(encoding="utf-8")
    assert '"paginationPageSize": 50' in source
    assert '"paginationPageSizeSelector": False' in source
