from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dash import Dash

from dashboard.callbacks.support_pages import register_support_page_callbacks
from dashboard.health import DatasetHealth, HomeHealthReading
from dashboard.pages.market_data import layout as market_data_layout
from dashboard.pages.settings import layout as settings_layout
from dashboard.pages.system_health import layout as system_layout
from dashboard.pages.system_health import provider_layout
from market_data.catalog import DatasetManifest


def _walk(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None:
        yield from _walk(children)


def _text(component) -> str:
    return " ".join(str(item) for item in _walk(component) if isinstance(item, str))


def _manifest(dataset_id: str, symbol: str, provider: str) -> DatasetManifest:
    return DatasetManifest(
        dataset_id=dataset_id,
        status="validated",
        asset_class="futures",
        symbol=symbol,
        provider=provider,
        timeframe="1m",
        format="parquet",
        canonical_relative_path=Path(f"{dataset_id}.parquet"),
        sha256="0" * 64,
        size_bytes=100,
        row_count=25,
        metadata={
            "coverage_start": "2026-01-01",
            "latest_completed_session": "2026-02-01",
            "restrictions": [f"{symbol} research only"],
        },
    )


def _health(dataset_id: str, symbol: str, provider: str) -> DatasetHealth:
    return DatasetHealth(
        _manifest(dataset_id, symbol, provider),
        "Available locally",
        "Verified",
        "Manifest and local file agree.",
    )


def _callback(app: Dash, output_fragment: str):
    entry = next(value for key, value in app.callback_map.items() if output_fragment in key)
    callback = entry["callback"]
    return getattr(callback, "__wrapped__", callback)


def test_market_data_uses_real_selectable_rows_without_spym_default() -> None:
    snapshot = (
        None,
        (
            _health("mes", "MES", "Databento"),
            _health("spym", "SPYM", "databento"),
        ),
        None,
    )

    page = market_data_layout(catalog_snapshot=snapshot)
    by_id = {
        component.id: component
        for component in _walk(page)
        if getattr(component, "id", None) is not None
    }
    grid = by_id["market-data-catalog-grid"]

    assert [row["dataset_id"] for row in grid.rowData] == ["mes", "spym"]
    assert grid.selectedRows[0]["dataset_id"] == "mes"
    assert grid.dashGridOptions["rowSelection"]["mode"] == "singleRow"

    app = Dash(__name__)
    register_support_page_callbacks(app)
    select = _callback(app, "market-data-selected-record.children")
    selected_text = _text(select([grid.rowData[1]]))
    assert "SPYM · 1m" in selected_text
    assert "SPYM research only" in selected_text


def test_data_sources_normalize_labels_and_selection_updates_real_records() -> None:
    snapshot = (
        None,
        (
            _health("mes", "MES", "Databento"),
            _health("mnq", "MNQ", "databento"),
            _health("spy", "SPY", "Alpaca IEX"),
        ),
        None,
    )

    page = provider_layout(catalog_snapshot=snapshot)
    by_id = {
        component.id: component
        for component in _walk(page)
        if getattr(component, "id", None) is not None
    }
    selector = by_id["data-source-selector"]
    records = by_id["data-source-records"].data

    assert [option["value"] for option in selector.options] == ["Alpaca", "Databento"]
    assert sum(record["provider_family"] == "Databento" for record in records) == 2

    app = Dash(__name__)
    register_support_page_callbacks(app)
    select = _callback(app, "data-source-selected-record.children")
    children, name, count = select("Databento", records)
    selected_text = _text(children)
    assert name == "Databento"
    assert count == "2"
    assert "Databento · databento" in selected_text
    assert "MES · 1m" in selected_text
    assert "MNQ · 1m" in selected_text
    assert "Not established" in selected_text


def test_system_status_exposes_observation_and_owner_attention(tmp_path: Path) -> None:
    observed_at = datetime(2026, 10, 5, 12, 30, tzinfo=timezone.utc)
    readings = tuple(
        HomeHealthReading(area, "Not checked", "No current observation.")
        for area in ("database", "artifact", "worker", "cache", "credential")
    )

    page = system_layout(
        tmp_path / "state.sqlite3",
        tmp_path,
        catalog_snapshot=(None, (), "No configured catalog."),
        health_readings=readings,
        observed_at=observed_at,
    )
    text = _text(page)

    assert "Snapshot observed 2026-10-05 12:30 UTC" in text
    assert "6 need attention" in text
    assert "No inferred health" in text
    assert "Requires a fresh check" in text


def test_settings_exposes_only_backed_browser_display_preferences() -> None:
    page = settings_layout()
    ids = {
        component.id
        for component in _walk(page)
        if getattr(component, "id", None) is not None
    }
    text = _text(page)

    assert {"settings-theme", "settings-density"} <= ids
    assert "Default chart interval" not in text
    assert "Trade ledger rows" not in text
    assert "strategy parameter" not in text.casefold()
