"""Deferred persisted-run history grid for Results."""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag


def run_history_grid(rows: tuple[dict[str, object], ...]) -> Any:
    return dag.AgGrid(
        id="run-history-grid",
        rowData=list(rows),
        columnDefs=[
            {"field": "run_id", "headerName": "Run ID", "hide": True},
            {"field": "created_at", "headerName": "Date"},
            {"field": "instrument", "headerName": "Instrument", "filter": "agTextColumnFilter"},
            {"field": "strategy", "headerName": "Strategy", "filter": "agTextColumnFilter"},
            {"field": "stage", "headerName": "Stage", "filter": "agTextColumnFilter"},
            {"field": "status", "headerName": "Status", "filter": "agTextColumnFilter"},
            {"field": "review", "headerName": "Review", "filter": "agTextColumnFilter"},
            {"field": "evidence", "headerName": "Evidence", "filter": "agTextColumnFilter"},
            {"field": "metric_basis", "headerName": "Metric Basis"},
            {"field": "total_return", "headerName": "Total Return", "type": "numericColumn", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : (params.value * 100).toFixed(2) + '%'"}},
            {"field": "annualized_return", "headerName": "Annualized Return", "type": "numericColumn", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : (params.value * 100).toFixed(2) + '%'"}},
            {"field": "sharpe_ratio", "headerName": "Sharpe Ratio", "type": "numericColumn", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : Number(params.value).toFixed(2)"}},
            {"field": "number_of_trades", "headerName": "Number of Trades", "type": "numericColumn", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : Math.round(params.value).toLocaleString()"}},
            {"field": "artifact_status", "headerName": "Artifacts"},
            {"field": "reproducibility", "headerName": "Reproducibility"},
        ],
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True}},
        getRowId="params.data.run_id",
        selectedRows=[],
        columnSize="responsiveSizeToFit",
        columnSizeOptions={"defaultMinWidth": 72},
        style={"height": "360px", "width": "100%"},
    )
