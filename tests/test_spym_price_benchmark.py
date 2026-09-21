"""SPYM price-marker and benchmark evidence coverage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dash import dcc, html

from dashboard.application import (
    _numeric_value,
    _portfolio_value_panel,
    _price_marker_figure,
    _price_marker_panel,
)
from dashboard.run_detail_adapter import (
    ResultSummaryView,
    RunDetailDashboardAdapter,
    RunEvidenceView,
    SelectedRunDetailView,
    _validated_benchmark,
    _validated_series_rows,
)
from orchestration import FixtureRunService
from persistence import PersistenceService
from prefect_spike.fixture_flow import deterministic_fixture_body
from prefect_spike.spym_vectorbt_fixture import ensure_spym_21c_saved_configuration


def _launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def _spym_detail(tmp_path: Path):
    database = tmp_path / "state" / "price-benchmark.sqlite3"
    service = PersistenceService(database)
    try:
        configuration_id = ensure_spym_21c_saved_configuration(service)
    finally:
        service.close()

    FixtureRunService(database=database, fixture_launcher=_launcher).launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-spym-price-benchmark",
    )
    adapter = RunDetailDashboardAdapter(database=database, artifact_root=tmp_path)
    return adapter.selected_run_detail("qf-spym-price-benchmark"), tmp_path


def _graph(component: Any) -> dcc.Graph:
    if isinstance(component, dcc.Graph):
        return component
    children = getattr(component, "children", ())
    if not isinstance(children, list):
        children = [children]
    for child in children:
        found = _graph(child)
        if found is not None:
            return found
    return None


def _empty_detail() -> SelectedRunDetailView:
    return SelectedRunDetailView(
        configuration_fields=(),
        parameters=(),
        market_data=(),
        execution=(),
        ranking=(),
        screening=(),
        lineage_fields=(),
        manifest_fields=(),
        artifacts=(),
        result_summary=ResultSummaryView(status="empty", message="", rows=()),
        evidence=RunEvidenceView(
            notices=(),
            metrics=(),
            trades=(),
            orders=(),
            equity_curve=({"timestamp": "2026-01-01T00:00:00Z", "value": 10000.0},),
            drawdown_curve=(),
            validation=(),
            provenance=(),
            warnings=(),
        ),
        warnings=(),
    )


def test_spym_fixture_persists_price_series_and_vectorbt_benchmark(
    tmp_path: Path,
) -> None:
    detail, root = _spym_detail(tmp_path)
    payload = json.loads(
        (
            root
            / "state"
            / "artifacts"
            / "qf-spym-price-benchmark"
            / "equity_curve.json"
        ).read_text(encoding="utf-8")
    )

    assert set(payload) == {
        "benchmark",
        "benchmark_curve",
        "equity_curve",
        "price_series",
    }
    assert len(payload["price_series"]) == 53528
    assert len(payload["benchmark_curve"]) == 53528
    assert payload["price_series"][0]["timestamp"] == "2025-10-31T13:30:00+00:00"
    assert payload["price_series"][0]["open"] > 0
    assert payload["price_series"][0]["low"] <= payload["price_series"][0]["close"]
    assert payload["price_series"][0]["high"] >= payload["price_series"][0]["close"]

    benchmark = payload["benchmark"]
    assert benchmark["instrument"] == "SPYM"
    assert benchmark["label"] == "SPYM same-instrument buy-and-hold"
    assert benchmark["engine"] == "vectorbtpro.Portfolio.from_holding"
    assert benchmark["starting_capital"] == 10000.0
    assert benchmark["fees"] == 0.0
    assert benchmark["slippage"] == 0.0
    assert benchmark["resampling"].startswith("none; full observed Databento")
    assert "zero configured fees/slippage" in benchmark["limitations"]

    assert len(detail.evidence.price_series) == 53528
    assert len(detail.evidence.benchmark_curve) == 53528
    assert detail.evidence.benchmark == benchmark


def test_price_and_benchmark_renderers_use_persisted_series(tmp_path: Path) -> None:
    detail, _ = _spym_detail(tmp_path)

    price_graph = _graph(_price_marker_panel(detail))
    assert price_graph is not None
    assert price_graph.id == "price-marker-chart"
    assert price_graph.config["scrollZoom"] is True
    counts = []
    for interval in ("1m", "5m", "15m", "1D"):
        figure, _ = _price_marker_figure(detail, interval=interval, view="Full run")
        candlestick = next(trace for trace in figure.data if trace.type == "candlestick")
        counts.append(len(candlestick.x))
    assert counts == [53528, 13340, 4474, 173]

    benchmark_panel = _portfolio_value_panel(detail)
    benchmark_graph = _graph(benchmark_panel)
    assert benchmark_graph is not None
    assert benchmark_graph.id == "portfolio-benchmark-chart"
    assert [trace.name for trace in benchmark_graph.figure.data] == [
        "Portfolio value vs same-instrument buy-and-hold",
        "SPYM same-instrument buy-and-hold",
    ]
    assert [len(trace.x) for trace in benchmark_graph.figure.data] == [1500, 1500]
    assert "representative points are shown" in str(benchmark_panel)
    assert "Starting capital" in str(benchmark_panel)
    assert "$10,000.00" in str(benchmark_panel)
    assert "0.000%" in str(benchmark_panel)


def test_older_equity_artifact_without_price_or_benchmark_fails_closed() -> None:
    detail = _empty_detail()

    price_panel = _price_marker_panel(detail)
    assert isinstance(price_panel, html.Div)
    assert "Evidence not recorded" in str(price_panel)
    assert "approved fixture must be rerun" in str(price_panel)

    benchmark_panel = _portfolio_value_panel(detail)
    assert "No persisted buy-and-hold benchmark is available" in str(benchmark_panel)
    assert _graph(benchmark_panel).figure.layout.title.text == "Portfolio value over time"
    assert len(_graph(benchmark_panel).figure.data) == 1


def test_optional_price_and_benchmark_payload_validation_fails_closed() -> None:
    warnings: list[str] = []
    assert (
        _validated_series_rows(
            {"price_series": [{"timestamp": "not-a-date", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}]},
            "price_series",
            numeric_fields=("open", "high", "low", "close"),
            warnings=warnings,
            source_interval="1m",
        )
        == ()
    )
    assert "invalid timestamp" in warnings[0]

    warnings = []
    assert (
        _validated_series_rows(
            {"benchmark_curve": [{"timestamp": "2026-01-01T00:00:00Z", "value": float("inf")}]},
            "benchmark_curve",
            numeric_fields=("value",),
            warnings=warnings,
        )
        == ()
    )
    assert "invalid value" in warnings[0]

    warnings = []
    assert (
        _validated_series_rows(
            {"price_series": [{"timestamp": "2026-01-01T00:00:00Z", "open": True, "high": 2.0, "low": 1.0, "close": 1.5}]},
            "price_series",
            numeric_fields=("open", "high", "low", "close"),
            warnings=warnings,
            source_interval="1m",
        )
        == ()
    )
    assert "invalid open" in warnings[0]

    warnings = []
    assert _validated_benchmark({"benchmark": {"label": "SPYM buy-and-hold"}}, warnings) is None
    assert "benchmark instrument" in warnings[0]
    assert _numeric_value(True) is None
    assert _numeric_value(float("inf")) is None
