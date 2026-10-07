"""Independent construction proofs for dashboard page and callback components."""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

from dash import Dash, html

from dashboard.callbacks.backtest_results import register_backtest_results_callbacks
from dashboard.pages.backtest_results import layout
from dashboard.results_contracts import ResultsViewServices


def test_dashboard_callbacks_and_pages_import_without_application_module() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import dashboard.callbacks.backtest_results; "
                "import dashboard.callbacks.compare_backtests; "
                "import dashboard.callbacks.results_review; "
                "import dashboard.callbacks.trade_explorer; "
                "import dashboard.pages.backtest_results; "
                "import dashboard.pages.home; "
                "import sys; assert 'dashboard.application' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_backtest_results_page_uses_an_explicit_renderer_contract() -> None:
    captured: dict[str, object] = {}
    rendered = html.Div("independent results page")

    def renderer(**kwargs):
        captured.update(kwargs)
        return rendered

    result = layout(renderer=renderer, selected_run_id="run-1")

    assert result is rendered
    assert captured["selected_run_id"] == "run-1"
    assert captured["recent_runs"] == ()
    assert captured["history_rows"] == ()


def test_results_callbacks_construct_with_an_independent_view_contract(tmp_path) -> None:
    app = Dash(__name__)

    def present(*_args, **_kwargs):
        return html.Div("contract result")

    view = ResultsViewServices(
        backtest_selector_label=present,
        configuration_is_launchable=present,
        operator_message=present,
        parameter_variant_selection=present,
        empty_price_marker_figure=present,
        price_marker_figure=lambda *_args, **_kwargs: ("price figure", "price summary"),
        preferred_backtest_id=present,
        recent_events_panel=present,
        recent_runs_panel=present,
        run_detail_panel=present,
        run_history_grid=present,
        results_report_tab_content=present,
        results_report_tabs=present,
        results_supporting_charts=present,
        results_operator_context=present,
        selector_options=present,
    )

    register_backtest_results_callbacks(
        app,
        runs=SimpleNamespace(),
        detail_adapter=SimpleNamespace(
            artifact_root=tmp_path,
            selected_run_detail=lambda _run_id: SimpleNamespace(
                evidence=SimpleNamespace(price_series=({"Close": 1.0},))
            ),
        ),
        configurations=(),
        readiness_by_id={},
        dashboard_database=tmp_path / "dashboard.sqlite3",
        artifact_root=tmp_path,
        view=view,
    )

    assert "..price-marker-chart.figure...price-marker-summary.children.." in app.callback_map
    assert "results-supporting-charts-content.children" in app.callback_map
    assert app.callback_map["results-supporting-charts-content.children"]["inputs"] == [
        {"id": "results-supporting-charts-toggle", "property": "n_clicks"}
    ]

    callback = app.callback_map[
        "..price-marker-chart.figure...price-marker-summary.children.."
    ]["callback"]
    callback = getattr(callback, "__wrapped__", callback)
    assert callback(
        "5m",
        "1W",
        [],
        1,
        "run-1",
        "/research/backtest-results",
    ) == ("price figure", "price summary")
