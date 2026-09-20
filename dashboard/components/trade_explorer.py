"""Read-only selected-backtest trade explorer components."""

from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from typing import Any

import dash_ag_grid as dag
from dash import dcc, html

from dashboard.run_detail_adapter import DetailField


MISSING = "Not recorded"
DATE_BASIS_LABEL = "Date range uses closed trade exit date"


def layout() -> html.Section:
    """Return permanently mounted trade explorer controls and outputs."""

    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.P("BACKTEST TRADES", className="section-eyebrow"),
                            html.H2("Trade explorer"),
                            html.P(
                                (
                                    "Inspect simulated trades from this backtest. "
                                    "Closed rows are the win/loss basis; open rows "
                                    "have unrealized results."
                                ),
                                className="field-help",
                            ),
                            html.Small(DATE_BASIS_LABEL, className="empty-state-note"),
                        ],
                        className="run-section-heading",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        "Outcome",
                                        htmlFor="trade-outcome-filter",
                                        className="field-label",
                                    ),
                                    dcc.Dropdown(
                                        id="trade-outcome-filter",
                                        options=[
                                            {"label": "Win", "value": "Win"},
                                            {"label": "Loss", "value": "Loss"},
                                            {"label": "Flat", "value": "Flat"},
                                            {"label": "Open", "value": "Open"},
                                            {"label": "Unknown", "value": "Unknown"},
                                        ],
                                        value=[],
                                        multi=True,
                                        placeholder="All outcomes",
                                    ),
                                ],
                                className="trade-filter-control",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Direction",
                                        htmlFor="trade-direction-filter",
                                        className="field-label",
                                    ),
                                    dcc.Dropdown(
                                        id="trade-direction-filter",
                                        options=[
                                            {"label": "Long", "value": "Long"},
                                            {"label": "Short", "value": "Short"},
                                            {"label": "Unknown", "value": "Unknown"},
                                        ],
                                        value=[],
                                        multi=True,
                                        placeholder="All directions",
                                    ),
                                ],
                                className="trade-filter-control",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Exit date range",
                                        htmlFor="trade-date-range",
                                        className="field-label",
                                    ),
                                    dcc.DatePickerRange(
                                        id="trade-date-range",
                                        clearable=True,
                                        display_format="YYYY-MM-DD",
                                        minimum_nights=0,
                                        start_date_placeholder_text="Start",
                                        end_date_placeholder_text="End",
                                    ),
                                ],
                                className="trade-filter-control trade-date-filter-control",
                            ),
                        ],
                        className="trade-filter-grid",
                    ),
                ],
                className="trade-explorer-heading",
            ),
            html.Div(
                "Select a persisted backtest to inspect trade rows.",
                id="trade-explorer-summary",
                className="field-help",
            ),
            html.Div(
                "Select a trade to identify its entry and exit on the price chart.",
                id="results-chart-focus-status",
                className="field-help results-chart-focus-status",
                **{"aria-live": "polite"},
            ),
            dag.AgGrid(
                id="selected-trade-grid",
                rowData=[],
                columnDefs=trade_column_definitions(),
                defaultColDef={
                    "sortable": True,
                    "filter": True,
                    "resizable": True,
                    "wrapHeaderText": True,
                    "autoHeaderHeight": True,
                },
                dashGridOptions={
                    "animateRows": False,
                    "pagination": True,
                    "paginationPageSize": 12,
                    "domLayout": "autoHeight",
                    "rowSelection": {
                        "mode": "singleRow",
                        "checkboxes": False,
                        "enableClickSelection": True,
                    },
                    "suppressColumnVirtualisation": False,
                },
                getRowId="params.data.__trade_key",
                selectedRows=[],
                columnSize="autoSize",
                className=(
                    "ag-theme-alpine qf-data-grid qf-trades-grid "
                    "qf-trade-explorer-grid"
                ),
                style={"width": "100%"},
            ),
            html.Div(
                no_trade_selected_message(),
                id="selected-trade-detail",
                className="run-detail-nested trade-detail-panel",
            ),
        ],
        className="panel trade-explorer-panel",
    )


def trade_column_definitions() -> list[dict[str, Any]]:
    """Column definitions for normalized, trader-readable trade rows."""

    centered = "qf-table-cell qf-table-cell-center"
    header = "qf-table-header qf-table-header-wrap qf-table-header-center"
    number = f"{centered} qf-table-cell-number"
    compact = f"{centered} qf-table-cell-compact"
    time_cell = f"{centered} qf-table-cell-time"
    return [
        {"field": "__trade_key", "hide": True},
        {"field": "__run_id", "hide": True},
        {"field": "__basis_date", "hide": True},
        {"field": "__date_status", "hide": True},
        {
            "field": "Trade",
            "minWidth": 92,
            "width": 104,
            "cellClass": compact,
            "headerClass": header,
        },
        {
            "field": "Outcome",
            "minWidth": 96,
            "width": 110,
            "cellClass": compact,
            "headerClass": header,
        },
        {
            "field": "Status",
            "minWidth": 96,
            "width": 110,
            "cellClass": compact,
            "headerClass": header,
        },
        {
            "field": "Direction",
            "minWidth": 98,
            "width": 112,
            "cellClass": compact,
            "headerClass": header,
        },
        {
            "field": "Entry timestamp",
            "minWidth": 190,
            "width": 214,
            "cellClass": time_cell,
            "headerClass": header,
        },
        {
            "field": "Exit/valuation timestamp",
            "minWidth": 190,
            "width": 214,
            "cellClass": time_cell,
            "headerClass": header,
        },
        _number_column("Entry price", "price"),
        _number_column("Exit/valuation price", "price"),
        _number_column("Size", "quantity"),
        _number_column("Fees", "money"),
        _number_column("P&L", "money"),
        _number_column("Return", "%"),
    ]


def normalize_trade_rows(
    trades: tuple[dict[str, Any], ...],
    *,
    run_id: str | None,
    price_unit: str = "currency",
    pnl_unit: str = "USD",
) -> tuple[dict[str, Any], ...]:
    """Normalize VectorBT Pro readable trade rows into operator-facing rows."""

    rows: list[dict[str, Any]] = []
    for index, trade in enumerate(trades, start=1):
        pnl = _number(
            _first(trade, ("PnL", "pnl", "Profit", "profit", "Net PnL", "net_pnl"))
        )
        entry_timestamp = _first(
            trade,
            ("Entry Index", "Entry Time", "Entry Timestamp", "Opened At"),
        )
        exit_timestamp = _first(
            trade,
            ("Exit Index", "Exit Time", "Exit Timestamp", "Close Time", "Closed At"),
        )
        basis_date, date_status = _basis_date(exit_timestamp)
        trade_identity = _first(
            trade,
            ("Exit Trade Id", "Trade Id", "Position Id", "Entry Order Id"),
        )
        status = _status(trade)
        if status != "Closed":
            basis_date, date_status = "", "open"
        rows.append(
            {
                "__trade_key": (
                    f"{run_id or 'unselected'}:{index}:"
                    f"{trade_identity if trade_identity not in (None, '') else 'no-source-id'}"
                ),
                "__run_id": run_id,
                "__trade_index": index,
                "__basis_date": basis_date,
                "__date_status": date_status,
                "__price_unit": price_unit,
                "__pnl_unit": pnl_unit,
                "Trade": f"Trade {index}",
                "Outcome": _outcome(pnl, status),
                "Status": status,
                "Direction": _direction(trade),
                "Entry timestamp": _display_timestamp(entry_timestamp),
                "Exit/valuation timestamp": _display_timestamp(exit_timestamp),
                "Entry price": _number(
                    _first(trade, ("Avg Entry Price", "Entry Price", "Open Price"))
                ),
                "Exit/valuation price": _number(
                    _first(trade, ("Avg Exit Price", "Exit Price", "Close Price"))
                ),
                "Size": _number(_first(trade, ("Size", "Quantity", "Qty"))),
                "Fees": _fees(trade),
                "P&L": pnl,
                "Return": _number(
                    _first(trade, ("Return", "return", "Trade Return", "trade_return"))
                ),
            }
        )
    return tuple(rows)


def filter_trade_rows(
    rows: tuple[dict[str, Any], ...],
    *,
    outcomes: list[str] | tuple[str, ...] | None,
    directions: list[str] | tuple[str, ...] | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[tuple[dict[str, Any], ...], str]:
    """Apply dashboard trade filters and return filtered rows plus summary text."""

    selected_outcomes = {value for value in outcomes or () if value}
    selected_directions = {value for value in directions or () if value}
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    has_date_filter = start is not None or end is not None
    unavailable_date_count = sum(
        1 for row in rows if row.get("__date_status") != "available"
    )

    filtered: list[dict[str, Any]] = []
    for row in rows:
        if selected_outcomes and row.get("Outcome") not in selected_outcomes:
            continue
        if selected_directions and row.get("Direction") not in selected_directions:
            continue
        if has_date_filter:
            basis = _parse_date(str(row.get("__basis_date") or ""))
            if basis is None:
                continue
            if start is not None and basis < start:
                continue
            if end is not None and basis > end:
                continue
        filtered.append(row)

    summary = (
        f"Showing {len(filtered)} of {len(rows)} persisted backtest trade rows. "
        f"{DATE_BASIS_LABEL}."
    )
    if has_date_filter and unavailable_date_count:
        summary += (
            f" {unavailable_date_count} open, unconfirmed or undated trades are "
            "outside the date filter because no confirmed closed exit date is recorded."
        )
    if (start_date and start is None) or (end_date and end is None):
        summary += " One entered date could not be read, so that date bound was ignored."
    return tuple(filtered), summary


def selected_trade_detail(
    selected_rows: list[dict[str, Any]] | None,
    *,
    run_id: str | None,
    execution_fields: tuple[DetailField, ...],
    visible_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> Any:
    """Render the focused selected-trade panel."""

    if not selected_rows:
        if visible_rows == []:
            return html.P(
                (
                    "No trade rows are available for this selected backtest "
                    "and current evidence view."
                ),
                className="empty-state-copy",
            )
        return no_trade_selected_message()

    row = selected_rows[0]
    if row.get("__run_id") != run_id:
        return html.P(
            "Select a trade from the currently selected backtest.",
            className="empty-state-copy",
        )

    fields = (
        DetailField("Trade", _display(row.get("Trade"))),
        DetailField("Outcome", _display(row.get("Outcome"))),
        DetailField("Status", _display(row.get("Status"))),
        DetailField("Direction", _display(row.get("Direction"))),
        DetailField("Entry timestamp", _display(row.get("Entry timestamp"))),
        DetailField(
            "Entry price",
            _price(
                row.get("Entry price"),
                unit=str(row.get("__price_unit") or "currency"),
            ),
        ),
        DetailField(
            _exit_label(row, "timestamp"),
            _display(row.get("Exit/valuation timestamp")),
        ),
        DetailField(
            _exit_label(row, "price"),
            _price(
                row.get("Exit/valuation price"),
                unit=str(row.get("__price_unit") or "currency"),
            ),
        ),
        DetailField("Size", _quantity(row.get("Size"))),
        DetailField(
            "Fees",
            _money_unit(row.get("Fees"), unit=str(row.get("__pnl_unit") or "not_recorded")),
        ),
        DetailField(
            "P&L",
            _money_unit(row.get("P&L"), unit=str(row.get("__pnl_unit") or "not_recorded")),
        ),
        DetailField("Return", _percent(row.get("Return"))),
    )
    assumption_map = {field.label: field.value for field in execution_fields}
    assumption_fields = (
        DetailField("Execution basis", "Theoretical backtest execution"),
        DetailField("Signal timing", assumption_map.get("Signal Timing", MISSING)),
        DetailField(
            "Execution timing",
            assumption_map.get("Execution Timing", MISSING),
        ),
        DetailField("Execution price", assumption_map.get("Execution Price", MISSING)),
        DetailField("Position sizing", assumption_map.get("Position Sizing", MISSING)),
        DetailField("Order size", assumption_map.get("Order Size", MISSING)),
        DetailField("Fees assumption", assumption_map.get("Fees", MISSING)),
        DetailField("Slippage assumption", assumption_map.get("Slippage", MISSING)),
        DetailField("Actual broker fills", "Not recorded for this research backtest"),
    )
    return html.Div(
        [
            html.H3("Selected trade detail"),
            html.P(
                (
                    "This detail comes from the persisted VectorBT Pro trade artifact. "
                    "Wins and losses apply only to closed rows; no per-trade "
                    "realized broker slippage is recorded here."
                ),
                className="field-help",
            ),
            _field_list(fields),
            html.H4("Execution assumptions"),
            _field_list(assumption_fields),
        ]
    )


def no_trade_selected_message() -> html.P:
    return html.P(
        "Select a trade row to inspect entry, exit, P&L, fees and assumptions.",
        className="empty-state-copy",
    )


def _number_column(field: str, formatter: str) -> dict[str, Any]:
    function = "params.value == null ? 'Not recorded' : Number(params.value).toFixed(2)"
    if formatter == "$":
        function = "params.value == null ? 'Not recorded' : '$' + Number(params.value).toFixed(2)"
    elif formatter == "money":
        function = (
            "params.value == null ? 'Not recorded' : "
            "(params.data && params.data.__pnl_unit === 'USD' ? "
            "'$' + Number(params.value).toFixed(2) : "
            "Number(params.value).toFixed(2) + ' (unit not recorded)')"
        )
    elif formatter == "price":
        function = (
            "params.value == null ? 'Not recorded' : "
            "(params.data && params.data.__price_unit === 'index_points' ? "
            "Number(params.value).toFixed(2) + ' index points' : "
            "(params.data && params.data.__price_unit === 'currency' ? "
            "'$' + Number(params.value).toFixed(2) : "
            "Number(params.value).toFixed(2) + ' (unit not recorded)'))"
        )
    elif formatter == "%":
        function = (
            "params.value == null ? 'Not recorded' : "
            "(Number(params.value) * 100).toFixed(2) + '%'"
        )
    elif formatter == "quantity":
        function = (
            "params.value == null ? 'Not recorded' : "
            "Number(params.value).toLocaleString(undefined, {maximumFractionDigits: 6})"
        )
    return {
        "field": field,
        "minWidth": 96,
        "width": 116,
        "type": "numericColumn",
        "cellClass": "qf-table-cell qf-table-cell-center qf-table-cell-number",
        "headerClass": "qf-table-header qf-table-header-wrap qf-table-header-center",
        "valueFormatter": {"function": function},
    }


def _field_list(fields: tuple[DetailField, ...]) -> html.Dl:
    return html.Dl(
        [
            html.Div([html.Dt(field.label), html.Dd(field.value)])
            for field in fields
        ],
        className="run-detail-fields",
    )


def _first(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _price(value: Any, *, unit: str) -> str:
    number = _number(value)
    if number is None:
        return MISSING
    if unit == "index_points":
        return f"{number:,.2f} index points"
    if unit == "currency":
        return f"${number:,.2f}"
    return f"{number:,.2f} (unit not recorded)"


def _money_unit(value: Any, *, unit: str) -> str:
    number = _number(value)
    if number is None:
        return MISSING
    if unit == "USD":
        return f"${number:,.2f}"
    return f"{number:,.2f} (unit not recorded)"


def _fees(row: dict[str, Any]) -> float | None:
    entry = _number(row.get("Entry Fees"))
    exit_ = _number(row.get("Exit Fees"))
    has_entry_exit_fee = "Entry Fees" in row or "Exit Fees" in row
    if has_entry_exit_fee:
        if entry is not None and exit_ is not None:
            return entry + exit_
        return None
    return _number(_first(row, ("Fees", "Fee", "Commissions", "Commission")))


def _status(row: dict[str, Any]) -> str:
    raw = _first(row, ("Status", "Trade Status", "status"))
    if raw is None:
        return "Unknown"
    normalized = str(raw).strip().lower()
    if normalized == "closed":
        return "Closed"
    if normalized == "open":
        return "Open"
    return "Unknown"


def _exit_label(row: dict[str, Any], value_kind: str) -> str:
    if row.get("Status") == "Open":
        return f"Valuation {value_kind}"
    return f"Exit {value_kind}"


def _outcome(pnl: float | None, status: str) -> str:
    if status == "Open":
        return "Open"
    if status != "Closed":
        return "Unknown"
    if pnl is None:
        return "Unknown"
    if pnl > 0:
        return "Win"
    if pnl < 0:
        return "Loss"
    return "Flat"


def _direction(row: dict[str, Any]) -> str:
    raw = _first(row, ("Direction", "Side", "Position Side"))
    if raw is None:
        return "Unknown"
    normalized = str(raw).strip().lower()
    if normalized in {"long", "buy", "longonly"}:
        return "Long"
    if normalized in {"short", "sell", "shortonly"}:
        return "Short"
    return "Unknown"


def _display_timestamp(value: Any) -> str:
    if value in (None, ""):
        return MISSING
    parsed = _parse_datetime(value)
    if parsed is None:
        return MISSING
    return parsed.isoformat()


def _basis_date(value: Any) -> tuple[str, str]:
    if value in (None, ""):
        return "", "open"
    parsed = _parse_datetime(value)
    if parsed is None:
        return "", "invalid"
    return parsed.date().isoformat(), "available"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _display(value: Any) -> str:
    if value in (None, ""):
        return MISSING
    return str(value)


def _money(value: Any) -> str:
    number = _number(value)
    return MISSING if number is None else f"${number:,.2f}"


def _quantity(value: Any) -> str:
    number = _number(value)
    if number is None:
        return MISSING
    return f"{number:,.6f}".rstrip("0").rstrip(".")


def _percent(value: Any) -> str:
    number = _number(value)
    return MISSING if number is None else f"{number:.2%}"
