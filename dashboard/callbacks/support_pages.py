"""Selection callbacks for the read-only research-support pages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from dash import Dash, Input, Output, State, no_update

from dashboard.pages.market_data import selected_dataset_panel
from dashboard.pages.system_health import selected_provider_panel


def register_support_page_callbacks(app: Dash) -> None:
    @app.callback(
        Output("market-data-selected-record", "children"),
        Input("market-data-catalog-grid", "selectedRows"),
        prevent_initial_call=True,
    )
    def select_dataset(selected_rows: object):
        if not isinstance(selected_rows, Sequence) or not selected_rows:
            return no_update
        record = selected_rows[0]
        if not isinstance(record, Mapping):
            return no_update
        return selected_dataset_panel(record).children

    @app.callback(
        Output("data-source-selected-record", "children"),
        Output("provider-lineage-name", "children"),
        Output("provider-lineage-count", "children"),
        Input("data-source-selector", "value"),
        State("data-source-records", "data"),
    )
    def select_provider(provider: object, records: object):
        if not isinstance(provider, str) or not provider.strip():
            return no_update, no_update, no_update
        available_records = records if isinstance(records, list) else []
        selected = [
            record
            for record in available_records
            if isinstance(record, Mapping)
            and record.get("provider_family") == provider
        ]
        return selected_provider_panel(provider, selected).children, provider, str(len(selected))
