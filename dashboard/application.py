"""Plotly Dash entry point for local experiment review."""

from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any

import dash_ag_grid as dag
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.experiments import execute_experiment  # noqa: E402
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG  # noqa: E402
from dashboard.adapter import SelectedPortfolioData, reconstruct_selected_portfolio  # noqa: E402
from dashboard.formatting import format_assumption, format_metric  # noqa: E402
from dashboard.pages.common import (  # noqa: E402
    not_found_page as _not_found_page,
    page_heading as _page_heading,
    pending_page as _pending_page,
)
from dashboard.components.trade_explorer import (  # noqa: E402
    layout as _trade_explorer_layout,
    normalize_trade_rows as _normalize_trade_rows,
)
from dashboard.components.operator_context import (  # noqa: E402
    OperatorContextViewModel,
    operator_context,
)
from dashboard.project_status import PROJECT_STATUS, DashboardProjectStatus  # noqa: E402
from dashboard.health import inspect_catalog  # noqa: E402
from dashboard.routing import (  # noqa: E402
    NAVIGATION_LINKS,
    ROUTE_CONTAINER_IDS,
    ROUTE_REGISTRY,
    active_route as _active_route,
    navigation_classes_for_path,
    navigation_link_id as _navigation_link_id,
    route_container_styles_for_path,
    route_container_id as _route_container_id,
)
from dashboard.run_adapter import (  # noqa: E402
    SavedConfigurationView,
    list_saved_configurations,
)
from dashboard.run_detail_adapter import (  # noqa: E402
    ArtifactInventoryView,
    DetailField,
    ResultSummaryView,
    RunEvidenceView,
    RunDetailDashboardAdapter,
    SelectedRunDetailView,
)
from market_data import DataAudit, load_market_data  # noqa: E402
from market_data.equity_contract import (  # noqa: E402
    load_spym_manifest,
    spym_dashboard_health,
)
from orchestration import (  # noqa: E402
    FixtureRunService,
    RunEvent,
    RunServiceError,
    RunSummary,
)
from persistence import ArtifactType, PersistenceService, ReviewState  # noqa: E402
from persistence.database import database_path  # noqa: E402
from persistence.evidence_service import ValidationEvidenceArtifactService  # noqa: E402
from strategies import get_strategy  # noqa: E402
from backtesting.validation.evidence_decision_artifacts import (  # noqa: E402
    EVIDENCE_DECISION_LOGICAL_NAME,
)
from dashboard.shell import create_dashboard_layout, navigation as _navigation  # noqa: E402

REVIEWER = "dashboard-operator"
RECENT_RUN_DISPLAY_LIMIT = 4
RECENT_EVENT_DISPLAY_LIMIT = 5
INITIAL_PATH_COOKIE = "qf_dash_initial_pathname"

RESEARCH_PATH_STYLE = {
    "alignItems": "stretch",
    "display": "flex",
    "flexWrap": "wrap",
    "gap": "10px",
}
RESEARCH_PATH_CARD_STYLE = {
    "alignItems": "center",
    "backgroundColor": "#ffffff",
    "border": "1px solid #bfdbfe",
    "borderRadius": "8px",
    "boxShadow": "0 8px 20px rgba(15, 23, 42, 0.08)",
    "display": "flex",
    "flex": "1 1 180px",
    "gap": "10px",
    "minHeight": "64px",
    "padding": "12px 14px",
}
RESEARCH_PATH_STEP_STYLE = {
    "alignItems": "center",
    "backgroundColor": "#2357d9",
    "borderRadius": "999px",
    "color": "#ffffff",
    "display": "inline-flex",
    "fontSize": "0.8rem",
    "fontWeight": 800,
    "height": "28px",
    "justifyContent": "center",
    "minWidth": "28px",
}
RESEARCH_PATH_CONNECTOR_STYLE = {
    "alignItems": "center",
    "color": "#2357d9",
    "display": "inline-flex",
    "fontWeight": 800,
    "padding": "0 2px",
}
RECENT_ACTIVITY_TIMELINE_STYLE = {
    "borderLeft": "2px solid #bfdbfe",
    "display": "grid",
    "gap": "12px",
    "listStyle": "none",
    "margin": "0",
    "padding": "2px 0 2px 18px",
}
RECENT_ACTIVITY_ITEM_STYLE = {
    "backgroundColor": "#ffffff",
    "border": "1px solid #e2e8f0",
    "borderRadius": "8px",
    "display": "grid",
    "gap": "4px",
    "padding": "10px 12px",
    "position": "relative",
}
RECENT_ACTIVITY_DOT_STYLE = {
    "border": "2px solid #ffffff",
    "borderRadius": "999px",
    "height": "12px",
    "left": "-25px",
    "position": "absolute",
    "top": "14px",
    "width": "12px",
}
RECENT_ACTIVITY_TIMESTAMP_STYLE = {
    "color": "#64748b",
    "fontSize": "0.82rem",
}
RECENT_ACTIVITY_EMPTY_STYLE = {
    "backgroundColor": "#f8fafc",
    "border": "1px dashed #94a3b8",
    "borderRadius": "8px",
    "color": "#475569",
    "padding": "14px",
}

OPERATOR_LABEL_OVERRIDES = {
    "config_hash": "Configuration checksum",
    "configuration_id": "Configuration ID",
    "dataset_id": "Dataset ID",
    "dataset_identity": "Dataset identity",
    "experiment_id": "Experiment",
    "fees_bps": "Fees",
    "id": "ID",
    "run_id": "Run ID",
    "same_bar_limitation": "Same-bar limitation",
    "slippage_bps": "Slippage",
    "strategy_id": "Strategy ID",
}

OPERATOR_VALUE_LABELS = {
    "fixed_bps": "Fixed basis points",
    "infrastructure_fixture": "Infrastructure fixture",
    "none": "None",
    "prefect_fixture": "Prefect fixture",
    "same_bar_close": "Same-bar close",
    "screened_out": "Screened out",
}


@contextmanager
def _dashboard_persistence(database: str | Path):
    """Open a callback-local connection; Dash may invoke callbacks on another thread."""
    service = PersistenceService(database)
    try:
        yield service
    finally:
        service.close()


def _request_pathname_for_initial_layout() -> str:
    try:
        from flask import request
    except RuntimeError:
        return "/"
    if not request:
        return "/"
    return request.cookies.get(INITIAL_PATH_COOKIE) or "/"


def _register_initial_path_cookie(app: Dash) -> None:
    @app.server.after_request
    def _remember_initial_dashboard_path(response):
        from flask import request

        if request.method == "GET" and not request.path.startswith(
            (
                "/_dash-",
                "/assets/",
                "/_favicon.ico",
            )
        ):
            response.set_cookie(
                INITIAL_PATH_COOKIE,
                request.path or "/",
                max_age=30,
                samesite="Lax",
            )
        return response


@dataclass(frozen=True)
class DashboardContext:
    ranked_results: pd.DataFrame
    data: pd.DataFrame
    audit: DataAudit


def _review_options() -> list[dict[str, str]]:
    return [
        {"label": state.value.replace("_", " ").title(), "value": state.value}
        for state in ReviewState
    ]


def load_dashboard_context() -> DashboardContext:
    market_data = load_market_data(EXPERIMENT_CONFIG.market_data)
    ranked: pd.DataFrame | None = None
    if EXPERIMENT_CONFIG.output_path.is_file():
        candidate = pd.read_csv(EXPERIMENT_CONFIG.output_path)
        execution = EXPERIMENT_CONFIG.execution
        if (
            not candidate.empty
            and "execution_mode" in candidate
            and "execution_price" in candidate
            and "validation_status" in candidate
            and "screening_status" in candidate
            and "parameter_row_id" in candidate
            and candidate["execution_mode"].eq(execution.mode).all()
            and candidate["execution_price"]
            .eq(execution.execution_price_field)
            .all()
            and candidate["validation_status"].eq("passed").all()
            and candidate["screening_status"]
            .isin({"passed", "screened_out"})
            .all()
        ):
            ranked = candidate
    if ranked is None:
        result = execute_experiment(
            EXPERIMENT_CONFIG,
            market_data.data,
            market_data.audit,
        )
        ranked = result.ranked_results
    return DashboardContext(ranked, market_data.data, market_data.audit)


def parameters_from_row(row: dict[str, Any]) -> dict[str, Any]:
    strategy = get_strategy(EXPERIMENT_CONFIG.strategy_id)
    return {
        name: row[EXPERIMENT_CONFIG.parameter_name_map.get(name, name)]
        for name in strategy.spec.parameter_map
    }


def _figure(
    series: pd.Series,
    title: str,
    color: str,
    percent: bool = False,
    *,
    markers: bool = False,
    emphasize_min: bool = False,
) -> go.Figure:
    values = list(series.values)
    yaxis_options: dict[str, Any] = {
        "tickformat": "$,.0f",
    }
    if percent:
        finite_values = [
            abs(float(value))
            for value in values
            if pd.notna(value) and abs(float(value)) > 0
        ]
        smallest_non_zero = min(finite_values) if finite_values else 0.0
        yaxis_options = {
            "tickformat": ".3%" if 0 < smallest_non_zero < 0.001 else ".2%",
        }
    figure = go.Figure(
        go.Scatter(
            x=series.index,
            y=values,
            mode="lines+markers" if markers else "lines",
            line={"color": color, "width": 3},
            marker=(
                {
                    "size": 5,
                    "color": "#ffffff",
                    "line": {"color": color, "width": 1.5},
                }
                if markers
                else None
            ),
            name=title,
            hovertemplate=(
                "%{x}<br>%{y:.2%}<extra></extra>"
                if percent
                else "%{x}<br>%{y:$,.2f}<extra></extra>"
            ),
        )
    )
    if emphasize_min and values:
        min_position = int(pd.Series(values).idxmin())
        figure.add_trace(
            go.Scatter(
                x=[series.index[min_position]],
                y=[values[min_position]],
                mode="markers",
                marker={
                    "size": 11,
                    "color": "#ef4444",
                    "line": {"color": "#7f1d1d", "width": 2},
                },
                name="Maximum drawdown",
                hovertemplate="%{x}<br>Maximum drawdown %{y:.2%}<extra></extra>",
            )
        )
    figure.update_layout(
        title=title,
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 45, "r": 20, "t": 55, "b": 40},
        hovermode="x unified",
        autosize=True,
        yaxis=yaxis_options,
    )
    return figure


def _metric_cards(selected: SelectedPortfolioData) -> list[Any]:
    labels = {
        "total_return": "Total return",
        "annualized_return": "Annualized return",
        "sharpe_ratio": "Sharpe ratio",
        "max_drawdown": "Maximum drawdown",
        "number_of_trades": "Trades",
        "win_rate": "Win rate",
    }
    return [
        html.Div(
            [
                html.Span(label, className="metric-label"),
                html.Strong(format_metric(name, selected.metrics[name])),
            ],
            className="metric-card",
        )
        for name, label in labels.items()
    ]


def _details(selected: SelectedPortfolioData) -> tuple[list[Any], list[Any]]:
    provenance = [
        html.Li(f"Provider: {selected.provenance['provider']}"),
        html.Li(
            f"Dates: {selected.provenance['start_date']} to "
            f"{selected.provenance['end_date']}"
        ),
        html.Li(
            "Adjusted prices: "
            + ("Yes" if selected.provenance["prices_adjusted"] else "No")
        ),
        html.Li(f"Rows: {selected.provenance['row_count']:,}"),
    ]
    assumptions = selected.execution_assumptions
    strategy_assumptions = assumptions["strategy"]
    execution = [
        html.Li(assumptions["signal_timing_label"]),
        html.Li(assumptions["execution_timing_label"]),
        html.Li(f"Execution price: {assumptions['execution_price']}"),
        html.Li(
            "Initial cash: "
            + format_assumption("initial_cash", assumptions["initial_cash"])
        ),
        html.Li(f"Fees: {format_assumption('fees', assumptions['fees'])}"),
        html.Li(f"Slippage: {format_assumption('slippage', assumptions['slippage'])}"),
        html.Li(f"Direction: {assumptions['direction']}"),
        html.Li(
            f"Leverage: {format_assumption('leverage', assumptions['leverage'])}"
        ),
        html.Li(f"Position sizing: {assumptions['position_sizing'].replace('_', ' ')}"),
    ]
    if assumptions["execution_mode"] == "same_bar_close":
        execution.append(
            html.Li(
                f"Research limitation: {strategy_assumptions['same_bar_limitation']}"
            )
        )
    return provenance, execution


PERCENT_RESULT_FIELDS = {
    "total_return",
    "annualized_return",
    "max_drawdown",
    "win_rate",
}

INTEGER_RESULT_FIELDS = {
    "rsi_window",
    "entry_threshold",
    "exit_threshold",
    "number_of_trades",
}

RESULT_COLUMN_LABELS = {
    "rsi_window": "RSI Window",
    "entry_threshold": "Entry",
    "exit_threshold": "Exit",
    "total_return": "Total Return",
    "annualized_return": "Annual Return",
    "sharpe_ratio": "Sharpe",
    "max_drawdown": "Max Drawdown",
    "number_of_trades": "Trades",
    "win_rate": "Win Rate",
    "screening_status": "Screening",
}

RESULT_COLUMN_WIDTHS = {
    "rsi_window": 90,
    "entry_threshold": 80,
    "exit_threshold": 80,
    "total_return": 105,
    "annualized_return": 110,
    "sharpe_ratio": 85,
    "max_drawdown": 115,
    "number_of_trades": 80,
    "win_rate": 90,
    "screening_status": 105,
}


def _grid_alignment_classes(*extra: str) -> tuple[str, str]:
    suffix = " ".join(extra)
    cell_class = "qf-table-cell qf-table-cell-center"
    header_class = "qf-table-header qf-table-header-wrap qf-table-header-center"
    if suffix:
        cell_class = f"{cell_class} {suffix}"
        header_class = f"{header_class} {suffix}"
    return cell_class, header_class


def _grid_profile_definition(
    field: str,
    *,
    header: str,
    profile: str,
    dtype: Any | None = None,
) -> dict[str, Any]:
    definition: dict[str, Any] = {
        "field": field,
        "headerName": header,
        "headerTooltip": header,
        "minWidth": 100,
        "flex": 1,
    }
    normalized = field.lower().replace("_", " ")
    cell_class, header_class = _grid_alignment_classes()
    definition.update(cellClass=cell_class, headerClass=header_class)

    if profile == "ranked":
        compact_fields = {
            "rsi_window",
            "entry_threshold",
            "exit_threshold",
            "total_return",
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "number_of_trades",
            "win_rate",
        }
        descriptive_fields = {
            "screening_status",
            "screening_reason",
            "validation_status",
            "validation_outcome",
            "outcome",
        }
        if field in compact_fields:
            definition.update(minWidth=86, width=104, flex=0.62)
        elif field in descriptive_fields or "reason" in normalized:
            definition.update(minWidth=170, width=220, flex=1.35)
        elif dtype is not None and pd.api.types.is_numeric_dtype(dtype):
            definition.update(minWidth=92, width=110, flex=0.68)
        else:
            definition.update(minWidth=122, width=150, flex=0.95)
        return definition

    if profile == "trades":
        if "index" in normalized or "time" in normalized or "date" in normalized:
            definition.update(minWidth=168, width=190, flex=1.15)
        elif normalized in {
            "side",
            "direction",
            "status",
            "column",
            "type",
        } or normalized.endswith(" id"):
            definition.update(minWidth=82, width=104, flex=0.55)
        elif any(
            token in normalized
            for token in (
                "price",
                "pnl",
                "return",
                "fees",
                "size",
                "qty",
                "quantity",
            )
        ):
            definition.update(minWidth=104, width=126, flex=0.72)
        else:
            definition.update(minWidth=118, width=140, flex=0.85)
        return definition

    return definition


def _ranked_column_definitions(
    ranked_results: pd.DataFrame,
) -> list[dict[str, Any]]:
    hidden_fields = {
        "data_source",
        "prices_adjusted",
        "data_start_date",
        "data_end_date",
        "row_count",
        "execution_mode",
        "signal_timing",
        "execution_timing",
        "execution_price",
        "initial_cash",
        "fees",
        "slippage",
        "position_sizing",
        "direction",
        "leverage",
        "accumulate",
        "validation_gate_count",
        "parameter_row_id",
        "screening_passed_rule_count",
        "screening_failed_rule_count",
    }

    definitions: list[dict[str, Any]] = []

    for field in ranked_results.columns:
        if field in hidden_fields:
            continue

        definition = _grid_profile_definition(
            field,
            header=RESULT_COLUMN_LABELS.get(
                field,
                field.replace("_", " ").title(),
            ),
            profile="ranked",
            dtype=ranked_results[field],
        )

        if field in PERCENT_RESULT_FIELDS:
            definition.update(
                {
                    "valueFormatter": {
                        "function": (
                            "params.value == null ? '' : "
                            "(params.value * 100).toFixed(2) + '%'"
                        )
                    },
                }
            )
        elif field in INTEGER_RESULT_FIELDS:
            definition.update(
                {
                    "valueFormatter": {
                        "function": (
                            "params.value == null ? '' : "
                            "Math.round(params.value).toLocaleString()"
                        )
                    },
                }
            )
        elif pd.api.types.is_numeric_dtype(ranked_results[field]):
            definition.update(
                {
                    "valueFormatter": {
                        "function": (
                            "params.value == null ? '' : "
                            "Number(params.value).toFixed(2)"
                        )
                    },
                }
            )

        definitions.append(definition)

    return definitions


def _review_run_columns() -> list[dict[str, Any]]:
    return [
        {"field": "rank", "headerName": "Rank", "maxWidth": 96},
        {"field": "screening", "headerName": "Screening", "minWidth": 150},
        {"field": "parameters", "headerName": "Parameters", "minWidth": 230, "flex": 1.2},
        {"field": "metrics", "headerName": "Metrics", "minWidth": 260, "flex": 1.4},
        {"field": "reason", "headerName": "Outcome reason", "minWidth": 220, "flex": 1.1},
    ]


def _review_run_options(runs: tuple[RunSummary, ...]) -> list[dict[str, str]]:
    return [
        {"label": _backtest_selector_label(run), "value": run.run_id}
        for run in _ordered_backtests(runs)
        if run.status == "succeeded"
    ] or _selector_options(_ordered_backtests(runs))


def _review_initial_run_id(runs: tuple[RunSummary, ...]) -> str | None:
    options = _review_run_options(runs)
    return options[0]["value"] if options else None


def _fields_to_map(fields: tuple[DetailField, ...]) -> dict[str, str]:
    return {field.label: field.value for field in fields}


def _review_metric_cards(
    run: RunSummary | None,
    detail: SelectedRunDetailView | None,
) -> list[Any]:
    metrics = _fields_to_map(detail.evidence.metrics if detail else ())
    lineage = _fields_to_map(detail.lineage_fields if detail else ())
    provenance = _fields_to_map(detail.evidence.provenance if detail else ())
    validation = _validation_outcome_value(detail)
    return [
        html.Article(
            [
                html.Span("Strategy", className="metric-label"),
                html.Strong(
                    _strategy_display_name(run.strategy_id) if run is not None else "—"
                ),
                html.Small(run.strategy_version if run is not None else "No selection"),
            ],
            className="metric-card",
        ),
        html.Article(
            [
                html.Span("Instrument", className="metric-label"),
                html.Strong(
                    _display_or_dash(
                        provenance.get("Symbol")
                        or lineage.get("Symbol")
                    )
                ),
                html.Small(_display_or_dash(lineage.get("Timeframe"))),
            ],
            className="metric-card",
        ),
        html.Article(
            [
                html.Span("Validation result", className="metric-label"),
                html.Strong(_display_or_dash(validation)),
                html.Small(run.status.replace("_", " ").title() if run else "No status"),
            ],
            className="metric-card",
        ),
        html.Article(
            [
                html.Span("Total return", className="metric-label"),
                html.Strong(_display_or_dash(metrics.get("Total Return"))),
                html.Small("Persisted metric"),
            ],
            className="metric-card",
        ),
        html.Article(
            [
                html.Span("Max drawdown", className="metric-label"),
                html.Strong(
                    _display_or_dash(
                        metrics.get("Maximum Drawdown") or metrics.get("Max Drawdown")
                    )
                ),
                html.Small("Persisted metric"),
            ],
            className="metric-card",
        ),
        html.Article(
            [
                html.Span("Trades", className="metric-label"),
                html.Strong(
                    _display_or_dash(
                        metrics.get("Number Of Trades") or metrics.get("Trades")
                    )
                ),
                html.Small("Completed trades"),
            ],
            className="metric-card",
        ),
    ]


def _review_result_rows(detail: SelectedRunDetailView | None) -> list[dict[str, str]]:
    if detail is None or not detail.result_summary.rows:
        return []
    rows: list[dict[str, str]] = []
    for row in detail.result_summary.rows:
        values = _fields_to_map(row)
        rows.append(
            {
                "rank": values.get("Rank", "—"),
                "screening": values.get("Screening", "—"),
                "parameters": values.get("Parameters", "—"),
                "metrics": values.get("Metrics", "—"),
                "reason": values.get("Rejection reasons", detail.result_summary.message),
            }
        )
    return rows


def _review_summary(
    run: RunSummary | None,
    detail: SelectedRunDetailView | None,
) -> html.Div:
    if run is None:
        return html.Div(
            "Select an evidence-backed persisted backtest to review.",
            className="empty-state-copy",
        )
    config = _fields_to_map(detail.configuration_fields if detail else ())
    lineage = _fields_to_map(detail.lineage_fields if detail else ())
    fields = (
        DetailField("Experiment", config.get("Experiment ID", "—")),
        DetailField("Configuration", run.configuration_id),
        DetailField("Backtest ID", run.run_id),
        DetailField("Test period", lineage.get("Actual coverage", "—")),
        DetailField("Dataset identity", lineage.get("Dataset identity", "—")),
        DetailField("Runtime", lineage.get("Git commit", "—")),
    )
    return html.Dl(
        [
            html.Div(
                [
                    html.Dt(field.label),
                    html.Dd(_operator_value(field.value)),
                ]
            )
            for field in fields
        ],
        className="run-detail-fields experiment-review-summary",
    )


def _review_artifact_summary(detail: SelectedRunDetailView | None) -> html.Ul:
    if detail is None or not detail.artifacts:
        return html.Ul([html.Li("No persisted artifacts are available.")])
    return html.Ul(
        [
            html.Li(
                (
                    f"{artifact.logical_name}: {artifact.validation_state} · "
                    f"{artifact.reference}"
                )
            )
            for artifact in detail.artifacts[:8]
        ],
        className="artifact-reference-list",
    )


def create_review_page(
    context: DashboardContext | None,
    *,
    recent_runs: tuple[RunSummary, ...] = (),
) -> html.Div:
    initial_run_id = _review_initial_run_id(recent_runs)
    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P("RESEARCH", className="page-eyebrow"),
                            html.H1("Strategy Review", className="page-title"),
                            html.P(
                                "Review a strategy's results, checks, and decision.",
                                className="page-description",
                            ),
                        ],
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Filters",
                                className="secondary-action page-action",
                                disabled=True,
                            ),
                            html.Button(
                                "Refresh",
                                id="refresh-experiments",
                                n_clicks=0,
                                className="primary-action page-action",
                                title="Refresh persisted experiment and backtest choices.",
                            ),
                        ],
                        className="page-actions",
                    ),
                ],
                className="page-heading page-heading-with-actions",
            ),
            dcc.Store(id="selected-review-identity", data=initial_run_id),
            dcc.Store(id="selected-parameters", data={}),
            html.Section(
                [
                    html.Label(
                        "Selected backtest for review",
                        htmlFor="review-run-selector",
                        className="field-label",
                    ),
                    dcc.Dropdown(
                        id="review-run-selector",
                        options=_review_run_options(recent_runs),
                        value=initial_run_id,
                        clearable=False,
                        placeholder="No persisted backtests available for review",
                    ),
                    html.P(
                        "The decision is recorded against the selected backtest.",
                        className="field-help compact-field-help",
                    ),
                ],
                className="panel experiment-selector-panel",
            ),
            html.Section(id="metric-cards", className="metric-grid experiment-kpi-grid"),
            html.Div(
                [
                    html.Section(
                        [
                            html.H2("Strategy checks"),
                            html.P(
                                "Ranked parameter combinations or persisted result evidence for the selected backtest.",
                                className="section-description",
                            ),
                            dag.AgGrid(
                                id="ranked-table",
                                columnDefs=_review_run_columns(),
                                rowData=[],
                                selectedRows=[],
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
                                    "paginationPageSize": 10,
                                    "rowSelection": {
                                        "mode": "singleRow",
                                        "enableClickSelection": True,
                                        "checkboxes": False,
                                    },
                                },
                                columnSize="responsiveSizeToFit",
                                columnSizeOptions={
                                    "defaultMinWidth": 92,
                                    "skipHeader": False,
                                },
                                className=(
                                    "ag-theme-alpine qf-data-grid "
                                    "qf-ranked-grid"
                                ),
                                style={"height": "320px", "width": "100%"},
                            ),
                        ],
                        className="panel table-panel experiment-matrix-panel",
                    ),
                    html.Section(
                        [
                            html.H2("Strategy decision"),
                            html.Label(
                                "Validation result",
                                htmlFor="review-status",
                                className="field-label",
                            ),
                            dcc.Dropdown(
                                id="review-status",
                                options=_review_options(),
                                value=ReviewState.UNREVIEWED.value,
                                clearable=False,
                            ),
                            dcc.Textarea(
                                id="review-note",
                                placeholder="Required reason for the durable evidence decision",
                                maxLength=500,
                            ),
                            html.Button(
                                "Save evidence decision",
                                id="save-review",
                                n_clicks=0,
                                className="primary-action",
                                disabled=True,
                                title=REVIEW_CONTEXT_UNAVAILABLE_MESSAGE,
                            ),
                            html.Div(
                                _review_context_unavailable_notice(),
                                id="review-message",
                                className="save-message",
                            ),
                            html.H3("Selected checks"),
                            html.Div(id="selected-parameter-display"),
                        ],
                        className="panel review-panel experiment-decision-panel",
                    ),
                ],
                className="two-column review-workspace experiment-review-workspace",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.H2("Supporting research"),
                            html.Div(id="provenance"),
                        ],
                        className="panel",
                    ),
                    html.Section(
                        [
                            html.H2("Trading assumptions and research history"),
                            html.Div(id="assumptions"),
                        ],
                        className="panel",
                    ),
                ],
                className="two-column",
            ),
        ],
        className="page-container review-page experiment-overview-page",
    )


def _home_next_action_card(title: str, description: str, href: str) -> dcc.Link:
    return dcc.Link(
        [
            html.Strong(title),
            html.P(description),
        ],
        href=href,
        className="summary-card home-action-card",
    )


def _strategy_research_path(current_path: str = "/") -> html.Div:
    stages = (
        ("Home", "/"),
        ("Ideas", "/research/ideas"),
        ("Set up", "/research/setup"),
        ("Run test", "/research/run-test"),
        ("Results", "/research/backtest-results"),
        ("Compare", "/research/compare-backtests"),
    )
    children: list[Any] = []
    for index, (stage, href) in enumerate(stages):
        if index:
            children.append(
                html.Span(
                    "->",
                    className="research-path-connector",
                    style=RESEARCH_PATH_CONNECTOR_STYLE,
                )
            )
        children.append(
            dcc.Link(
                [
                    html.Span(
                        str(index + 1),
                        className="research-path-step",
                        style=RESEARCH_PATH_STEP_STYLE,
                    ),
                    html.Strong(stage),
                ],
                href=href,
                className=(
                    "research-path-card research-path-card-active"
                    if href == current_path
                    else "research-path-card"
                ),
                style=RESEARCH_PATH_CARD_STYLE,
                title=(f"Current step: {stage}" if href == current_path else stage),
            )
        )
    return html.Div(
        children,
        className="strategy-research-path",
        style=RESEARCH_PATH_STYLE,
    )


def _activity_dot_style(status: str) -> dict[str, str]:
    colors = {
        "succeeded": "#16a34a",
        "success": "#16a34a",
        "failed": "#dc2626",
        "error": "#dc2626",
        "cancelled": "#f97316",
        "warning": "#f97316",
        "running": "#2357d9",
        "info": "#2357d9",
    }
    return {
        **RECENT_ACTIVITY_DOT_STYLE,
        "backgroundColor": colors.get(status, "#64748b"),
    }


def _recent_research_activity(
    recent_runs: tuple[RunSummary, ...],
    recent_events: tuple[RunEvent, ...],
) -> html.Div:
    activity_items: list[Any] = []
    for run in recent_runs[:3]:
        activity_items.append(
            html.Li(
                [
                    html.Span(
                        "",
                        className=f"activity-dot activity-dot-{run.status}",
                        style=_activity_dot_style(run.status),
                    ),
                    html.Strong(_backtest_selector_label(run)),
                    html.Span(
                        run.completed_at or run.started_at or run.created_at,
                        style=RECENT_ACTIVITY_TIMESTAMP_STYLE,
                    ),
                ],
                className="recent-activity-item",
                style=RECENT_ACTIVITY_ITEM_STYLE,
            )
        )
    for event in recent_events[:2]:
        activity_items.append(
            html.Li(
                [
                    html.Span(
                        "",
                        className=f"activity-dot activity-dot-{event.severity}",
                        style=_activity_dot_style(event.severity),
                    ),
                    html.Strong(event.event_type.replace("_", " ").title()),
                    html.Span(event.message),
                    html.Span(
                        event.timestamp,
                        style=RECENT_ACTIVITY_TIMESTAMP_STYLE,
                    ),
                ],
                className="recent-activity-item",
                style=RECENT_ACTIVITY_ITEM_STYLE,
            )
        )

    if not activity_items:
        return html.Div(
            "No recent research activity is available yet.",
            className="empty-state-copy",
            style=RECENT_ACTIVITY_EMPTY_STYLE,
        )
    return html.Ul(
        activity_items,
        className="recent-activity-timeline",
        style=RECENT_ACTIVITY_TIMELINE_STYLE,
    )


def _overview_page(
    recent_runs: tuple[RunSummary, ...] = (),
    recent_events: tuple[RunEvent, ...] = (),
    project_status: DashboardProjectStatus = PROJECT_STATUS,
) -> html.Div:
    return html.Div(
        [
            _page_heading(
                "RESEARCH / HOME",
                "Home",
                project_status.home_subtitle,
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Current milestone", className="summary-label"),
                            html.Strong(
                                (
                                    f"{project_status.current_milestone_number} - "
                                    f"{project_status.current_milestone_title}"
                                )
                            ),
                            html.P(
                                project_status.current_milestone_status,
                                className="summary-detail",
                            ),
                        ],
                        className="summary-card",
                    ),
                    html.Div(
                        [
                            html.Span("Strategy status", className="summary-label"),
                            html.Strong("Research only"),
                            html.P(
                                project_status.strategy_status,
                                className="summary-detail",
                            ),
                        ],
                        className="summary-card",
                    ),
                    html.Div(
                        [
                            html.Span("Workspace status", className="summary-label"),
                            html.Strong("Research workspace"),
                            html.P(
                                project_status.workspace_status,
                                className="summary-detail",
                            ),
                        ],
                        className="summary-card",
                    ),
                ],
                className="summary-grid",
            ),
            html.Section(
                [
                    html.H2("Next actions"),
                    html.Div(
                        [
                            _home_next_action_card(
                                "Capture an idea",
                                "Record a safe browser-session draft. Nothing will run.",
                                "/research/ideas",
                            ),
                            _home_next_action_card(
                                "Set up a test",
                                "Choose an approved immutable fixture setup.",
                                "/research/setup",
                            ),
                            _home_next_action_card(
                                "Inspect results",
                                "Review persisted evidence from completed tests.",
                                "/research/backtest-results",
                            ),
                        ],
                        className="summary-grid",
                    ),
                ],
                className="panel",
            ),
            html.Section(
                [
                    html.H2("Strategy research path"),
                    _strategy_research_path("/"),
                ],
                className="panel",
            ),
            html.Section(
                [
                    html.H2("Recent research activity"),
                    _recent_research_activity(recent_runs, recent_events),
                ],
                className="panel",
            ),
        ],
        className="page-container",
    )


def _configuration_preview(
    configuration: SavedConfigurationView,
) -> html.Div:
    readiness_class = (
        "configuration-status configuration-status-ready"
        if configuration.launchable
        else "configuration-status configuration-status-blocked"
    )
    readiness_text = (
        "Approved for infrastructure launch"
        if configuration.launchable
        else "Not approved for launch"
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Span(readiness_text, className=readiness_class),
                    html.Code(
                        configuration.configuration_id,
                        className="configuration-identity",
                    ),
                ],
                className="configuration-preview-header",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Strategy", className="summary-label"),
                            html.Strong(configuration.strategy_name),
                            html.P(
                                (
                                    f"{configuration.strategy_id}@"
                                    f"{configuration.strategy_version}"
                                ),
                                className="summary-detail",
                            ),
                        ],
                        className="summary-card",
                    ),
                    html.Div(
                        [
                            html.Span("Experiment", className="summary-label"),
                            html.Strong(configuration.experiment_id),
                            html.P(
                                configuration.lifecycle.replace("_", " ").title(),
                                className="summary-detail",
                            ),
                        ],
                        className="summary-card",
                    ),
                    html.Div(
                        [
                            html.Span("Execution", className="summary-label"),
                            html.Strong(
                                str(
                                    configuration.execution.get(
                                        "kind",
                                        configuration.execution.get(
                                            "mode",
                                            "Not specified",
                                        ),
                                    )
                                ).replace("_", " ").title()
                            ),
                            html.P(
                                f"Config hash {configuration.config_hash[:12]}…",
                                className="summary-detail",
                            ),
                        ],
                        className="summary-card",
                    ),
                ],
                className="summary-grid configuration-summary-grid",
            ),
            html.Div(
                [
                    html.Section(
                        [
                            html.H3("Parameters"),
                            _operator_mapping_fields(
                                configuration.parameters,
                                empty="No parameters recorded.",
                            ),
                        ],
                        className="panel configuration-detail-panel",
                    ),
                    html.Section(
                        [
                            html.H3("Execution assumptions"),
                            _operator_mapping_fields(
                                configuration.execution,
                                empty="No execution assumptions recorded.",
                            ),
                        ],
                        className="panel configuration-detail-panel",
                    ),
                ],
                className="two-column configuration-detail-grid",
            ),
        ],
        id="configuration-preview",
    )


def _run_monitor_card(run: RunSummary) -> html.Article:
    return html.Article(
        [
            html.Div(
                [
                    html.Strong(run.run_id),
                    html.Span(
                        run.status,
                        className=f"run-status run-status-{run.status}",
                    ),
                ],
                className="run-monitor-heading",
            ),
            html.P(
                (
                    f"{_operator_value(run.stage)} · "
                    f"{run.strategy_id}@{run.strategy_version} · "
                    f"created {run.created_at}"
                ),
                className="run-monitor-summary",
            ),
            html.Details(
                [
                    html.Summary("Run metadata"),
                    html.Dl(
                        [
                            html.Div(
                                [
                                    html.Dt("Configuration"),
                                    html.Dd(run.configuration_id),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Dt("Attempt"),
                                    html.Dd(str(run.attempt_count)),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Dt("Prefect"),
                                    html.Dd(
                                        run.prefect_flow_run_id or "Not available"
                                    ),
                                ]
                            ),
                        ],
                        className="run-monitor-details",
                    ),
                ],
                className="operator-details",
            ),
            (
                _operator_message(
                    "Run failed.",
                    run.error_summary,
                    tone="error",
                )
                if run.error_summary
                else None
            ),
        ],
        className="run-monitor-card",
    )


def _recent_runs_panel(runs: tuple[RunSummary, ...]) -> html.Section:
    if not runs:
        content: Any = html.P(
            "No backtests have been recorded yet.",
            className="empty-state-copy",
        )
    else:
        visible = runs[:RECENT_RUN_DISPLAY_LIMIT]
        hidden = runs[RECENT_RUN_DISPLAY_LIMIT:]
        items: list[Any] = [_run_monitor_card(run) for run in visible]
        if hidden:
            items.append(
                html.Details(
                    [
                        html.Summary(f"Show {len(hidden)} older runs"),
                        html.Div(
                            [_run_monitor_card(run) for run in hidden],
                            className="run-monitor-list run-monitor-list-collapsed",
                        ),
                    ],
                    className="history-overflow",
                )
            )
        content = html.Div(
            items,
            className="run-monitor-list",
        )

    return html.Section(
        [
            html.H2("Recent backtests"),
            html.P(
                (
                    "Latest selectable backtest records, newest first. Older records stay "
                    "collapsed by default."
                ),
                className="field-help",
            ),
            content,
        ],
        className="panel run-monitor-panel",
    )


def _run_event_item(event: RunEvent) -> html.Li:
    return html.Li(
        [
            html.Div(
                [
                    html.Strong(_operator_label(event.event_type)),
                    html.Span(event.severity),
                ],
                className="run-event-heading",
            ),
            html.P(event.message),
            html.Small(
                f"{event.timestamp} · {event.run_id} · {event.source}"
            ),
        ],
        className=f"run-event run-event-{event.severity}",
    )


def _recent_events_panel(events: tuple[RunEvent, ...]) -> html.Section:
    if not events:
        content: Any = html.P(
            "No operator events have been recorded yet.",
            className="empty-state-copy",
        )
    else:
        visible = events[:RECENT_EVENT_DISPLAY_LIMIT]
        hidden = events[RECENT_EVENT_DISPLAY_LIMIT:]
        items = [_run_event_item(event) for event in visible]
        if hidden:
            items.append(
                html.Li(
                    html.Details(
                        [
                            html.Summary(f"Show {len(hidden)} older events"),
                            html.Ol(
                                [_run_event_item(event) for event in hidden],
                                className="run-event-list run-event-list-collapsed",
                            ),
                        ],
                        className="history-overflow",
                    ),
                    className="run-event-overflow",
                )
            )
        content = html.Ol(
            items,
            className="run-event-list",
        )

    return html.Section(
        [
            html.H2("Operator events"),
            html.P(
                "Concise lifecycle events; Prefect technical logs remain external.",
                className="field-help",
            ),
            content,
        ],
        className="panel run-monitor-panel",
    )


def _callback_triggered_id() -> str | None:
    try:
        return ctx.triggered_id
    except Exception:
        return None


def _detail_fields(fields: tuple[DetailField, ...], *, empty: str) -> Any:
    if not fields:
        return html.P(empty, className="empty-state-copy")
    return html.Dl(
        [
            html.Div([html.Dt(field.label), html.Dd(_operator_value(field.value))])
            for field in fields
        ],
        className="run-detail-fields run-detail-subfields",
    )


def _operator_mapping_fields(document: dict[str, Any], *, empty: str) -> Any:
    return _detail_fields(
        tuple(
            DetailField(_operator_label(key), document[key])
            for key in sorted(document)
        ),
        empty=empty,
    )


def _operator_label(value: Any) -> str:
    raw = str(value).strip()
    if raw in OPERATOR_LABEL_OVERRIDES:
        return OPERATOR_LABEL_OVERRIDES[raw]
    text = raw.replace("_", " ").replace("-", " ")
    words = []
    for word in text.split():
        words.append(word.upper() if word.lower() in {"id", "api", "utc"} else word)
    return " ".join(words).capitalize() if words else "Value"


def _technical_value(raw: str) -> html.Span:
    friendly = OPERATOR_VALUE_LABELS.get(raw, raw.replace("_", " ").replace("-", " ").title())
    if friendly == raw:
        return html.Span(raw)
    return html.Span(
        [
            friendly,
            html.Small(raw, className="technical-value"),
        ],
        className="operator-value-with-raw",
    )


def _operator_value(value: Any) -> Any:
    if hasattr(value, "to_plotly_json") and hasattr(value, "children"):
        return value
    if value is None or value == "":
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict):
        if not value:
            return "Not recorded"
        return html.Dl(
            [
                html.Div(
                    [
                        html.Dt(_operator_label(key)),
                        html.Dd(_operator_value(value[key])),
                    ]
                )
                for key in sorted(value)
            ],
            className="operator-value-list",
        )
    if isinstance(value, (list, tuple)):
        if not value:
            return "Not recorded"
        return html.Ul(
            [html.Li(_operator_value(item)) for item in value],
            className="operator-value-list operator-value-sequence",
        )
    if isinstance(value, str) and (
        value in OPERATOR_VALUE_LABELS
        or (value.islower() and "_" in value and len(value) <= 40)
    ):
        return _technical_value(value)
    return str(value)


def _operator_message(summary: str, detail: str | None = None, *, tone: str) -> html.Div:
    children: list[Any] = [html.Strong(summary)]
    if detail:
        children.append(html.P(detail, className="operator-message-detail"))
    return html.Div(
        children,
        className=f"operator-message operator-message-{tone}",
    )


def _detail_subsection(title: str, content: Any, class_name: str = "") -> html.Div:
    classes = "run-detail-subsection"
    if class_name:
        classes += f" {class_name}"
    body = list(content) if isinstance(content, (list, tuple)) else [content]
    return html.Div([html.H3(title), *body], className=classes)


def _metric_value_map(fields: tuple[DetailField, ...]) -> dict[str, str]:
    return {field.label: str(field.value) for field in fields}


def _detail_field_value(fields: tuple[DetailField, ...], *labels: str) -> str | None:
    values = _metric_value_map(fields)
    for label in labels:
        if label in values and values[label] not in {"", "Not recorded"}:
            return values[label]
    return None


def _validation_outcome_value(detail: SelectedRunDetailView | None) -> str:
    if detail is None:
        return "Not recorded"
    return (
        _detail_field_value(
            detail.evidence.validation_outcome,
            "Normalized status",
            "Status",
            "Validation Status",
            "Outcome",
        )
        or "Not recorded"
    )


def _results_operator_context(
    run: RunSummary | None,
    detail: SelectedRunDetailView | None = None,
    *,
    component_id: str = "results-operator-context",
) -> html.Section:
    """Build truthful context from the selected persisted run and evidence."""

    if run is None:
        return operator_context(component_id=component_id)
    evidence_outcome = _validation_outcome_value(detail)
    if evidence_outcome in {"", "Not recorded", "Not available"}:
        evidence_outcome = None
    run_status = run.status.replace("_", " ").title()
    next_actions = {
        "created": "Wait for completion",
        "queued": "Wait for completion",
        "running": "Wait for completion",
        "retrying": "Wait for completion",
        "failed": "Review failure",
        "cancelled": "Review failure",
        "timed_out": "Review failure",
        "succeeded": "Inspect evidence",
    }
    return operator_context(
        OperatorContextViewModel(
            selected_run=True,
            run_status=run_status,
            evidence_outcome=evidence_outcome,
            human_decision=None,
            next_safe_action=next_actions.get(run.status),
        ),
        component_id=component_id,
    )


def _display_or_dash(value: str | None) -> str:
    if value in (None, "", "Not recorded", "Not available", "Not started", "Not completed"):
        return "—"
    return str(value)


def _run_identity_strip(
    run: RunSummary,
    detail: SelectedRunDetailView | None,
) -> html.Div:
    instrument = (
        _detail_field_value(
            detail.evidence.provenance if detail else (),
            "Symbol",
            "Data · Symbol",
        )
        or _detail_field_value(detail.market_data if detail else (), "Symbol")
        or None
    )
    timeframe = (
        _detail_field_value(detail.lineage_fields if detail else (), "Timeframe")
        or _detail_field_value(detail.market_data if detail else (), "Timeframe")
        or None
    )
    date_range = (
        _detail_field_value(
            detail.lineage_fields if detail else (),
            "Actual coverage",
            "Requested coverage",
        )
        or _detail_field_value(
            detail.evidence.provenance if detail else (),
            "Earliest Timestamp",
            "Start",
            "Start Date",
        )
        or None
    )
    initial_capital = (
        _detail_field_value(
            detail.execution if detail else (),
            "Initial Cash",
            "Initial Capital",
            "Cash",
        )
        or None
    )
    costs = (
        _detail_field_value(detail.execution if detail else (), "Fees", "Fees Bps")
        or None
    )
    slippage = (
        _detail_field_value(
            detail.execution if detail else (),
            "Slippage",
            "Slippage Bps",
        )
        or None
    )
    primary_fields = (
        DetailField("Instrument", _display_or_dash(instrument)),
        DetailField("Timeframe", _display_or_dash(timeframe)),
        DetailField("Test period", _display_or_dash(date_range)),
        DetailField("Validation result", _display_or_dash(_validation_outcome_value(detail))),
    )
    metadata_fields = (
        DetailField("Experiment", "Research fixture"),
        DetailField("Configuration", _display_or_dash(run.configuration_id[:12])),
        DetailField("Strategy version", _display_or_dash(run.strategy_version)),
        DetailField("Initial capital", _display_or_dash(initial_capital)),
        DetailField("Costs", _display_or_dash(costs)),
        DetailField("Slippage", _display_or_dash(slippage)),
        DetailField("Completion status", _display_or_dash(run.status)),
        DetailField("Attempt", _display_or_dash(str(run.attempt_count))),
    )
    trace_fields = (
        DetailField("Backtest ID", run.run_id),
        DetailField("Configuration ID", run.configuration_id),
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Fixture-only", className="fixture-chip"),
                    *[
                        html.Div(
                            [
                                html.Span(field.label, className="run-identity-label"),
                                html.Strong(_operator_value(field.value)),
                            ],
                            className="run-identity-item run-identity-primary-item",
                        )
                        for field in primary_fields
                    ],
                ],
                className="run-identity-primary",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(field.label, className="run-identity-label"),
                            html.Strong(_operator_value(field.value)),
                        ],
                        className="run-identity-item",
                    )
                    for field in metadata_fields
                ],
                className="run-identity-metadata",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(field.label, className="run-identity-label"),
                            html.Strong(_operator_value(field.value)),
                        ],
                        className="run-identity-item run-identity-trace",
                    )
                    for field in trace_fields
                ],
                className="run-identity-trace-row",
            ),
        ],
        className="run-identity-strip",
    )


def _outcome_badge(outcome: str, status: str) -> html.Div:
    normalized = outcome.lower().replace("_", "-").replace(" ", "-")
    if normalized not in {"passed", "failed", "invalid", "insufficient-evidence"}:
        normalized = status.lower().replace("_", "-")
    return html.Div(
        [
            html.Span("Validation outcome", className="metric-label"),
            html.Strong(outcome),
            html.Small("Passed, failed, invalid, or insufficient evidence."),
        ],
        className=f"run-outcome-card run-outcome-card-{normalized}",
    )


def _strategy_display_name(strategy_id: str) -> str:
    labels = {
        "spym_rsi_mean_reversion_fixture": "SPYM RSI Mean Reversion Fixture",
        "prefect_fixture_strategy": "Infrastructure Fixture",
    }
    return labels.get(
        strategy_id,
        strategy_id.replace("_", " ").replace("-", " ").title(),
    )


def _backtest_selector_label(run: RunSummary) -> str:
    status = run.status.replace("_", " ").title()
    stage_labels = {
        "fixture": "Fixture backtest",
        "walk_forward": "Walk-forward validation",
        "monte_carlo": "Monte Carlo validation",
        "robustness": "Robustness validation",
        "oos": "Out-of-sample evidence",
    }
    stage = stage_labels.get(
        run.stage,
        run.stage.replace("_", " ").title(),
    )
    if run.strategy_id == "spym_rsi_mean_reversion_fixture":
        return (
            f"{_strategy_display_name(run.strategy_id)} · SPYM · 1m · "
            f"{stage} · {status}"
        )
    return f"{_strategy_display_name(run.strategy_id)} · {stage} · {status}"


def _ordered_backtests(runs: tuple[RunSummary, ...]) -> tuple[RunSummary, ...]:
    """Put successful executable backtests ahead of validation companions."""
    preferred_ids = {
        run.run_id
        for run in runs
        if run.status == "succeeded" and run.stage == "fixture"
    }
    return tuple(run for run in runs if run.run_id in preferred_ids) + tuple(
        run for run in runs if run.run_id not in preferred_ids
    )


def _selector_options(runs: tuple[RunSummary, ...]) -> list[dict[str, str]]:
    return [
        {
            "label": _backtest_selector_label(run),
            "value": run.run_id,
        }
        for run in _ordered_backtests(runs)
    ]


def _default_comparison_values(runs: tuple[RunSummary, ...]) -> list[str]:
    succeeded = [run.run_id for run in runs if run.status == "succeeded"]
    if len(succeeded) >= 2:
        return succeeded[:2]
    return [run.run_id for run in runs[:2]]


def _comparison_backtest_cards(
    runs: tuple[RunSummary, ...],
    selected_ids: list[str],
) -> list[html.Article]:
    by_id = {run.run_id: run for run in runs}
    cards = []
    for index, run_id in enumerate(selected_ids[:4], start=1):
        run = by_id.get(run_id)
        label = _backtest_selector_label(run) if run is not None else "Selected backtest"
        status = run.status.replace("_", " ").title() if run is not None else "Unknown"
        cards.append(
            html.Article(
                [
                    html.Span(f"Backtest {index}", className="metric-label"),
                    html.Strong(label),
                    html.Small(f"Trace ID: {run_id} · Status: {status}"),
                ],
                className="comparison-selected-card",
            )
        )
    if cards:
        return cards
    return [
        html.Article(
            [
                html.Span("Backtests", className="metric-label"),
                html.Strong("No comparable backtests selected"),
                html.Small("Use the selector to choose at least two persisted backtests."),
            ],
            className="comparison-selected-card comparison-selected-card-empty",
        )
    ]


def _detail_has_backtest_evidence(detail: SelectedRunDetailView | None) -> bool:
    if detail is None:
        return False
    evidence = detail.evidence
    return bool(
        evidence.metrics
        and evidence.equity_curve
        and evidence.trades
        and evidence.validation
    )


def _select_initial_backtest(
    runs: tuple[RunSummary, ...],
    adapter: RunDetailDashboardAdapter,
) -> tuple[RunSummary | None, SelectedRunDetailView | None]:
    ordered_runs = _ordered_backtests(runs)
    preferred_fixture = next(
        (
            run
            for run in ordered_runs
            if run.status == "succeeded" and run.stage == "fixture"
        ),
        None,
    )
    if preferred_fixture is not None:
        try:
            return preferred_fixture, adapter.selected_run_detail(preferred_fixture.run_id)
        except (KeyError, RuntimeError, ValueError):
            return preferred_fixture, None

    fallback: tuple[RunSummary | None, SelectedRunDetailView | None] = (
        ordered_runs[0],
        None,
    ) if ordered_runs else (None, None)
    for run in ordered_runs:
        if run.status != "succeeded":
            continue
        try:
            detail = adapter.selected_run_detail(run.run_id)
        except (KeyError, RuntimeError, ValueError):
            continue
        if _detail_has_backtest_evidence(detail):
            return run, detail
        if fallback[0] is run and fallback[1] is None:
            fallback = (run, detail)
    return fallback


def _preferred_backtest_id(
    runs: tuple[RunSummary, ...],
    adapter: RunDetailDashboardAdapter,
) -> str | None:
    selected, _ = _select_initial_backtest(runs, adapter)
    return selected.run_id if selected is not None else None


def _primary_metric_cards(detail: SelectedRunDetailView | None) -> Any:
    values = _metric_value_map(detail.evidence.metrics) if detail else {}
    metric_slots = (
        ("Total Return", ("Total Return",), False),
        ("Annualized", ("Annualized Return",), False),
        ("Max Drawdown", ("Maximum Drawdown", "Max Drawdown"), True),
        ("Win Rate", ("Win Rate",), False),
        ("Profit Factor", ("Profit Factor",), False),
        ("Trades", ("Number Of Trades", "Trades"), False),
        ("Avg Win", ("Average Win",), False),
        ("Avg Loss", ("Average Loss",), True),
        ("Exposure", ("Exposure",), False),
        ("Avg Hold", ("Average Holding Time",), False),
    )

    return html.Div(
        [
            html.Article(
                [
                    html.Span(label, className="metric-label"),
                    html.Strong(
                        next(
                            (
                                values[candidate]
                                for candidate in candidates
                                if candidate in values
                            ),
                            "—",
                        )
                    ),
                    (
                        html.Small("Unavailable", className="metric-unavailable")
                        if not any(candidate in values for candidate in candidates)
                        else None
                    ),
                ],
                className=(
                    "metric-card run-primary-metric-card"
                    + (" run-primary-metric-negative" if negative else "")
                ),
            )
            for label, candidates, negative in metric_slots
        ],
        className="metric-grid run-primary-metric-grid",
    )


def _trade_pnl(trade: dict[str, Any]) -> float | None:
    normalized = _normalize_trade_rows((trade,), run_id="trade-summary")
    if not normalized or normalized[0].get("Status") != "Closed":
        return None
    value = normalized[0].get("P&L")
    return value if isinstance(value, float) else None


def _trade_return(trade: dict[str, Any]) -> float | None:
    normalized = _normalize_trade_rows((trade,), run_id="trade-summary")
    if not normalized or normalized[0].get("Status") != "Closed":
        return None
    value = normalized[0].get("Return")
    return value if isinstance(value, float) else None


def _trade_close_time(trade: dict[str, Any]) -> str:
    normalized = _normalize_trade_rows((trade,), run_id="trade-summary")
    if not normalized or normalized[0].get("Status") != "Closed":
        return "—"
    return str(normalized[0].get("Exit/valuation timestamp") or "—")


def _trade_review_summary(trades: tuple[dict[str, Any], ...]) -> Any:
    if not trades:
        return html.P(
            "Completed trades appear here when the run has a persisted trades artifact.",
            className="empty-state-copy",
        )

    normalized = _normalize_trade_rows(trades, run_id="trade-summary")
    closed_rows = tuple(row for row in normalized if row.get("Status") == "Closed")
    wins = sum(1 for row in closed_rows if row.get("Outcome") == "Win")
    losses = sum(1 for row in closed_rows if row.get("Outcome") == "Loss")
    neutral = sum(1 for row in closed_rows if row.get("Outcome") in {"Flat", "Unknown"})
    open_or_unconfirmed = len(normalized) - len(closed_rows)

    return html.Div(
        [
            html.Article(
                [
                    html.Span("Closed trades", className="metric-label"),
                    html.Strong(str(len(closed_rows))),
                ],
                className="trade-summary-card",
            ),
            html.Article(
                [
                    html.Span("Wins", className="metric-label"),
                    html.Strong(str(wins)),
                ],
                className="trade-summary-card trade-summary-card-win",
            ),
            html.Article(
                [
                    html.Span("Losses", className="metric-label"),
                    html.Strong(str(losses)),
                ],
                className="trade-summary-card trade-summary-card-loss",
            ),
            html.Article(
                [
                    html.Span("Flat/unknown", className="metric-label"),
                    html.Strong(str(neutral)),
                ],
                className="trade-summary-card",
            ),
            html.Article(
                [
                    html.Span("Open/unconfirmed", className="metric-label"),
                    html.Strong(str(open_or_unconfirmed)),
                ],
                className="trade-summary-card",
            ),
        ],
        className="trade-summary-grid",
    )


def _closed_trade_rows(trades: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    normalized = _normalize_trade_rows(trades, run_id="trade-summary")
    rows: list[dict[str, Any]] = []
    for source, row in zip(trades, normalized, strict=True):
        pnl = row.get("P&L")
        if row.get("Status") != "Closed" or not isinstance(pnl, float):
            continue
        rows.append(
            {
                "source": source,
                "pnl": pnl,
                "return": row.get("Return"),
                "close_time": row.get("Exit/valuation timestamp") or "—",
            }
        )
    return tuple(rows)


def _trade_pnl_figures(trades: tuple[dict[str, Any], ...]) -> Any:
    closed_trades = _closed_trade_rows(trades)
    pnl_values = [row["pnl"] for row in closed_trades]
    if not pnl_values:
        return html.P(
            "Trade P&L charts appear when closed trades include persisted P&L values.",
            className="empty-state-copy",
        )
    cumulative = pd.Series(pnl_values).cumsum()
    pnl_series = pd.Series(pnl_values)
    cumulative_figure = go.Figure(
        go.Scatter(
            x=list(range(1, len(cumulative) + 1)),
            y=cumulative.values,
            mode="lines+markers",
            line={"color": "#2357d9"},
            marker={"size": 7},
            name="Cumulative P&L",
        )
    )
    cumulative_figure.update_layout(
        title="Cumulative trade P&L",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 45, "r": 20, "t": 55, "b": 40},
        hovermode="x unified",
        yaxis_tickformat="$,.2f",
        xaxis_title="Trade",
    )
    distribution_figure = go.Figure(
        go.Histogram(
            x=pnl_series.values,
            marker={"color": "#16a34a", "line": {"color": "#0f766e", "width": 1}},
            name="Trade P&L",
        )
    )
    distribution_figure.update_layout(
        title="Trade-return distribution",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 45, "r": 20, "t": 55, "b": 40},
        yaxis_title="Trades",
        xaxis_tickformat="$,.2f",
    )
    return html.Div(
        [
            dcc.Graph(
                figure=cumulative_figure,
                responsive=True,
                style={"width": "100%", "minWidth": 0},
            ),
            dcc.Graph(
                figure=distribution_figure,
                responsive=True,
                style={"width": "100%", "minWidth": 0},
            ),
        ],
        className="run-secondary-chart-grid",
    )


def _artifact_inventory(artifacts: tuple[ArtifactInventoryView, ...]) -> Any:
    if not artifacts:
        return html.P(
            "No artifact inventory is available for this run.",
            className="empty-state-copy",
        )
    return html.Div(
        [
            html.Article(
                [
                    html.Div(
                        [
                            html.Strong(artifact.logical_name),
                            html.Span(
                                artifact.validation_state,
                                className=(
                                    "artifact-status "
                                    f"artifact-status-{artifact.severity}"
                                ),
                            ),
                        ],
                        className="artifact-card-heading",
                    ),
                    _detail_fields(
                        (
                            DetailField("Type", artifact.artifact_type),
                            DetailField("Schema", artifact.schema_version),
                            DetailField("Format", artifact.format),
                            DetailField("Availability", artifact.availability),
                            DetailField("Checksum", artifact.checksum),
                            DetailField("Reference", artifact.reference),
                            DetailField("Reason", artifact.reason),
                        ),
                        empty="Artifact metadata is unavailable.",
                    ),
                ],
                className=f"artifact-card artifact-card-{artifact.severity}",
            )
            for artifact in artifacts
        ],
        className="artifact-inventory",
    )


def _result_summary(summary: ResultSummaryView) -> Any:
    if not summary.rows:
        return html.P(summary.message, className="empty-state-copy")
    return html.Div(
        [
            html.P(summary.message, className="field-help"),
            html.Div(
                [
                    html.Article(
                        _detail_fields(row, empty="Result row is unavailable."),
                        className="result-summary-card",
                    )
                    for row in summary.rows
                ],
                className="result-summary-grid",
            ),
        ]
    )


def _artifact_column_definition(key: str, *, profile: str | None = None) -> dict[str, Any]:
    header = key.replace("_", " ").replace(" Id", " ID").title()
    definition = _grid_profile_definition(
        key,
        header=header,
        profile=profile or "artifact",
    )
    if profile != "trades":
        return definition

    normalized = key.lower().replace("_", " ")
    if "index" in normalized or "time" in normalized or "date" in normalized:
        definition.update(
            cellClass="qf-table-cell qf-table-cell-center qf-table-cell-time",
            headerClass=(
                "qf-table-header qf-table-header-wrap "
                "qf-table-header-center"
            ),
        )
    elif normalized in {
        "side",
        "direction",
        "status",
        "column",
        "type",
    } or normalized.endswith(" id"):
        definition.update(
            cellClass="qf-table-cell qf-table-cell-center qf-table-cell-compact",
            headerClass=(
                "qf-table-header qf-table-header-wrap "
                "qf-table-header-center"
            ),
        )
    elif any(
        token in normalized
        for token in (
            "price",
            "pnl",
            "return",
            "fees",
            "size",
            "qty",
            "quantity",
        )
    ):
        definition.update(
            cellClass="qf-table-cell qf-table-cell-center qf-table-cell-number",
            headerClass=(
                "qf-table-header qf-table-header-wrap "
                "qf-table-header-center"
            ),
        )
    else:
        definition.update(
            cellClass="qf-table-cell qf-table-cell-center",
            headerClass=(
                "qf-table-header qf-table-header-wrap "
                "qf-table-header-center"
            ),
        )
    return definition


def _artifact_grid(
    rows: tuple[dict[str, Any], ...],
    *,
    empty: str,
    profile: str | None = None,
) -> Any:
    if not rows:
        return html.P(empty, className="empty-state-copy")
    columns = [
        _artifact_column_definition(key, profile=profile)
        for key in rows[0]
    ]
    return dag.AgGrid(
        columnDefs=columns,
        rowData=list(rows),
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
            "paginationPageSize": 10,
            "suppressColumnVirtualisation": False,
        },
        columnSize="responsiveSizeToFit" if profile != "trades" else "autoSize",
        className=(
            "ag-theme-alpine qf-data-grid qf-trades-grid"
            if profile == "trades"
            else "ag-theme-alpine qf-data-grid"
        ),
        style={"height": "320px", "width": "100%"},
    )


def _artifact_table(title: str, rows: tuple[dict[str, Any], ...], *, empty: str) -> Any:
    return _detail_subsection(
        title,
        _artifact_grid(rows, empty=empty),
        "run-detail-nested",
    )


def _curve_figure(
    rows: tuple[dict[str, Any], ...],
    *,
    y_field: str,
    title: str,
    color: str,
    percent: bool = False,
    markers: bool = False,
    emphasize_min: bool = False,
) -> go.Figure:
    series = pd.Series(
        [row.get(y_field) for row in rows],
        index=[row.get("timestamp") for row in rows],
        name=title,
    )
    return _figure(
        series,
        title,
        color,
        percent=percent,
        markers=markers,
        emphasize_min=emphasize_min,
    )


def _curve_graph(
    rows: tuple[dict[str, Any], ...],
    *,
    y_field: str,
    title: str,
    color: str,
    empty: str,
    percent: bool = False,
    markers: bool = False,
    emphasize_min: bool = False,
) -> Any:
    if not rows:
        return html.P(
            empty,
            className="empty-state-copy",
        )
    return dcc.Graph(
        figure=_curve_figure(
            rows,
            y_field=y_field,
            title=title,
            color=color,
            percent=percent,
            markers=markers,
            emphasize_min=emphasize_min,
        ),
        responsive=True,
        style={"width": "100%", "minWidth": 0},
    )


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number) or not math.isfinite(number):
        return None
    return number


def _money(value: Any) -> str:
    number = _numeric_value(value)
    return "Not recorded" if number is None else f"${number:,.2f}"


def _percentage(value: Any) -> str:
    number = _numeric_value(value)
    return "Not recorded" if number is None else f"{number:.3%}"


def _benchmark_summary_fields(detail: SelectedRunDetailView) -> tuple[DetailField, ...]:
    benchmark = detail.evidence.benchmark or {}
    if not benchmark:
        return ()
    return (
        DetailField("Benchmark", str(benchmark.get("label") or "Not recorded")),
        DetailField("Starting capital", _money(benchmark.get("starting_capital"))),
        DetailField("Benchmark timing", str(benchmark.get("timing") or "Not recorded")),
        DetailField("Strategy timing", str(benchmark.get("strategy_timing") or "Not recorded")),
        DetailField(
            "Strategy sizing",
            str(benchmark.get("strategy_position_sizing") or "Not recorded"),
        ),
        DetailField(
            "Benchmark sizing",
            str(benchmark.get("benchmark_position_sizing") or "Not recorded"),
        ),
        DetailField("Fees", _percentage(benchmark.get("fees"))),
        DetailField("Slippage", _percentage(benchmark.get("slippage"))),
        DetailField("Fixed fee per order", _money(benchmark.get("fixed_fee_per_order"))),
        DetailField("Series handling", str(benchmark.get("resampling") or "Not recorded")),
        DetailField(
            "Strategy minus benchmark",
            _money(benchmark.get("strategy_minus_benchmark")),
        ),
        DetailField("Limitations", str(benchmark.get("limitations") or "Not recorded")),
    )


def _portfolio_value_panel(detail: SelectedRunDetailView) -> Any:
    if not detail.evidence.equity_curve:
        return html.P(
            "No persisted equity curve artifact is available for this run.",
            className="empty-state-copy",
        )
    figure = _curve_figure(
        detail.evidence.equity_curve,
        y_field="value",
        title=(
            "Portfolio value vs same-instrument buy-and-hold"
            if detail.evidence.benchmark_curve
            else "Portfolio value over time"
        ),
        color="#2563eb",
    )
    if detail.evidence.benchmark_curve:
        benchmark_label = (
            (detail.evidence.benchmark or {}).get("label")
            or "Same-instrument buy-and-hold"
        )
        benchmark_series = pd.Series(
            [row.get("value") for row in detail.evidence.benchmark_curve],
            index=[row.get("timestamp") for row in detail.evidence.benchmark_curve],
            name=benchmark_label,
        )
        figure.add_trace(
            go.Scattergl(
                x=benchmark_series.index,
                y=list(benchmark_series.values),
                mode="lines",
                line={"color": "#0f766e", "width": 2, "dash": "dash"},
                name=str(benchmark_label),
                hovertemplate="%{x}<br>%{y:$,.2f}<extra></extra>",
            )
        )
    figure.update_layout(legend={"orientation": "h", "y": -0.2})
    return html.Div(
        [
            dcc.Graph(
                id="portfolio-benchmark-chart",
                figure=figure,
                responsive=True,
                style={"width": "100%", "minWidth": 0},
            ),
            _detail_fields(
                _benchmark_summary_fields(detail),
                empty=(
                    "No persisted buy-and-hold benchmark is available. "
                    "Rerun the approved fixture to capture the missing comparison series."
                ),
            ),
        ],
        className="run-benchmark-panel",
    )


def _evidence_instrument(detail: SelectedRunDetailView) -> str:
    benchmark = detail.evidence.benchmark or {}
    instrument = benchmark.get("instrument")
    if isinstance(instrument, str) and instrument.strip():
        return instrument.strip()
    symbol = _detail_field_value(detail.market_data, "Symbol")
    return symbol or "Underlying"


def _evidence_timeframe(detail: SelectedRunDetailView) -> str:
    timeframe = _detail_field_value(detail.market_data, "Timeframe", "Interval")
    return timeframe or "recorded"


def _trade_marker_rows(
    trades: tuple[dict[str, Any], ...],
    *,
    event: str,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    if event == "entry":
        timestamp_keys = ("Entry Index", "Entry Time", "Entry Timestamp", "entry_time")
        price_keys = ("Avg Entry Price", "Entry Price", "entry_price")
    elif event == "exit":
        timestamp_keys = ("Exit Index", "Exit Time", "Exit Timestamp", "exit_time")
        price_keys = ("Avg Exit Price", "Exit Price", "exit_price")
    else:
        return ()
    for trade in trades:
        if event == "exit" and str(trade.get("Status", "")).lower() == "open":
            continue
        timestamp = next(
            (trade.get(key) for key in timestamp_keys if trade.get(key) not in (None, "")),
            None,
        )
        price = next(
            (
                _numeric_value(trade.get(key))
                for key in price_keys
                if _numeric_value(trade.get(key)) is not None
            ),
            None,
        )
        if timestamp in (None, "") or price is None:
            continue
        direction = str(trade.get("Direction", trade.get("direction", ""))).strip()
        rows.append(
            {
                "timestamp": str(timestamp),
                "price": price,
                "size": trade.get("Size", trade.get("size", "Not recorded")),
                "fees": (
                    trade.get("Entry Fees", trade.get("entry_fees", "Not recorded"))
                    if event == "entry"
                    else trade.get("Exit Fees", trade.get("exit_fees", "Not recorded"))
                ),
                "direction": direction or "Not recorded",
            }
        )
    return tuple(rows)


def _marker_trace_name(rows: tuple[dict[str, Any], ...], event: str) -> str:
    directions = {str(row.get("direction", "")).lower() for row in rows}
    if directions == {"long"}:
        return f"Long {event} markers"
    if directions == {"short"}:
        return f"Short {event} markers"
    return f"Trade {event} markers"


def _price_marker_panel(detail: SelectedRunDetailView) -> Any:
    prices = detail.evidence.price_series
    if not prices:
        return html.Div(
            [
                html.Span("Evidence not recorded", className="pending-state-badge"),
                html.P(
                    (
                        "This run does not include a persisted underlying price "
                        "series or buy-and-hold benchmark."
                    ),
                    className="empty-state-copy",
                ),
                html.Small(
                    (
                        "Older runs remain readable, but the approved fixture must "
                        "be rerun to capture price, entry/exit marker, and benchmark evidence."
                    ),
                    className="empty-state-note",
                ),
            ],
            className="run-price-marker-empty compact-empty-state",
        )
    instrument = _evidence_instrument(detail)
    timeframe = _evidence_timeframe(detail)
    entry_rows = _trade_marker_rows(detail.evidence.trades, event="entry")
    exit_rows = _trade_marker_rows(detail.evidence.trades, event="exit")
    figure = go.Figure(
        go.Scattergl(
            x=[row.get("timestamp") for row in prices],
            y=[row.get("close") for row in prices],
            customdata=[
                [row.get("open"), row.get("high"), row.get("low"), row.get("close")]
                for row in prices
            ],
            mode="lines",
            line={"color": "#172033", "width": 1.5},
            name=f"{instrument} close",
            hovertemplate=(
                "%{x}<br>"
                "Open %{customdata[0]:$,.2f}<br>"
                "High %{customdata[1]:$,.2f}<br>"
                "Low %{customdata[2]:$,.2f}<br>"
                "Close %{customdata[3]:$,.2f}<extra></extra>"
            ),
        )
    )
    if entry_rows:
        figure.add_trace(
            go.Scatter(
                x=[row["timestamp"] for row in entry_rows],
                y=[row["price"] for row in entry_rows],
                mode="markers",
                marker={
                    "symbol": "triangle-up",
                    "size": 9,
                    "color": "#16a34a",
                    "line": {"color": "#064e3b", "width": 1},
                },
                customdata=[
                    [row["size"], row["fees"], row["direction"]]
                    for row in entry_rows
                ],
                name=_marker_trace_name(entry_rows, "entry"),
                hovertemplate=(
                    "Entry %{x}<br>Price %{y:$,.2f}<br>"
                    "Size %{customdata[0]}<br>Fees %{customdata[1]}<br>"
                    "Direction %{customdata[2]}<extra></extra>"
                ),
            )
        )
    if exit_rows:
        figure.add_trace(
            go.Scatter(
                x=[row["timestamp"] for row in exit_rows],
                y=[row["price"] for row in exit_rows],
                mode="markers",
                marker={
                    "symbol": "triangle-down",
                    "size": 9,
                    "color": "#dc2626",
                    "line": {"color": "#7f1d1d", "width": 1},
                },
                customdata=[
                    [row["size"], row["fees"], row["direction"]]
                    for row in exit_rows
                ],
                name=_marker_trace_name(exit_rows, "exit"),
                hovertemplate=(
                    "Exit %{x}<br>Price %{y:$,.2f}<br>"
                    "Size %{customdata[0]}<br>Fees %{customdata[1]}<br>"
                    "Direction %{customdata[2]}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        title=f"{instrument} observed {timeframe} price with trade entries and exits",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 45, "r": 20, "t": 55, "b": 62},
        hovermode="x unified",
        yaxis={"tickformat": "$,.2f", "title": f"{instrument} price"},
        xaxis={"rangeslider": {"visible": False}},
        legend={"orientation": "h", "y": -0.2},
    )
    return html.Div(
        [
            dcc.Graph(
                id="price-marker-chart",
                figure=figure,
                responsive=True,
                style={"width": "100%", "minWidth": 0},
            ),
            html.Small(
                (
                    f"Full observed {instrument} {timeframe} series: {len(prices):,} bars. "
                    "No synthetic bars and no chart resampling are applied."
                ),
                className="empty-state-note",
            ),
        ],
        className="run-price-marker-panel",
    )


def _trade_pnl_chart(trades: tuple[dict[str, Any], ...], *, mode: str) -> Any:
    closed_trades = _closed_trade_rows(trades)
    pnl_values = [row["pnl"] for row in closed_trades]
    if not pnl_values:
        return html.P(
            "This chart appears when closed trades include persisted P&L values.",
            className="empty-state-copy",
        )
    if mode == "distribution":
        figure = go.Figure(
            go.Histogram(
                x=pnl_values,
                marker={
                    "color": "#22c55e",
                    "line": {"color": "#16a34a", "width": 1},
                },
                name="Trade P&L",
            )
        )
        figure.update_layout(
            title="Trade P&L distribution",
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin={"l": 45, "r": 20, "t": 55, "b": 40},
            yaxis_title="Trades",
            xaxis_tickformat="$,.2f",
        )
    else:
        cumulative = pd.Series(pnl_values).cumsum()
        point_colors = [
            "#16a34a" if pnl > 0 else "#ef4444" if pnl < 0 else "#64748b"
            for pnl in pnl_values
        ]
        hover_data = [
            [
                index,
                row["close_time"],
                row["pnl"],
                cumulative_value,
                (
                    row["return"]
                    if isinstance(row["return"], float)
                    else float("nan")
                ),
            ]
            for index, (row, cumulative_value) in enumerate(
                zip(closed_trades, cumulative.values, strict=True),
                start=1,
            )
        ]
        figure = go.Figure(
            go.Scatter(
                x=list(range(1, len(cumulative) + 1)),
                y=cumulative.values,
                mode="lines+markers",
                fill="tozeroy",
                line={"color": "#16a34a", "width": 3},
                marker={
                    "size": 7,
                    "color": point_colors,
                    "line": {"color": "#ffffff", "width": 1},
                },
                customdata=hover_data,
                name="Cumulative P&L",
                hovertemplate=(
                    "Trade %{customdata[0]}<br>"
                    "Close %{customdata[1]}<br>"
                    "Trade P&L %{customdata[2]:$,.2f}<br>"
                    "Cumulative P&L %{customdata[3]:$,.2f}<br>"
                    "Return %{customdata[4]:.2%}<extra></extra>"
                ),
            )
        )
        figure.update_layout(
            title="Cumulative trade P&L",
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin={"l": 45, "r": 20, "t": 55, "b": 62},
            hovermode="x unified",
            yaxis_tickformat="$,.2f",
            xaxis={
                "title": "Completed trade number",
                "tickmode": "linear",
                "tick0": 1,
                "dtick": max(1, round(len(cumulative) / 8)),
                "tickformat": "d",
            },
        )
    return dcc.Graph(
        figure=figure,
        responsive=True,
        style={"width": "100%", "minWidth": 0},
    )


def _run_chart_and_trade_focus(detail: SelectedRunDetailView | None) -> Any:
    if detail is None:
        return html.P(
            "Charts and completed trades appear after selecting a persisted run.",
            className="empty-state-copy",
        )
    return html.Div(
        [
            _detail_subsection(
                "Portfolio value and buy-and-hold comparison",
                _portfolio_value_panel(detail),
                "run-visual-card run-chart-focus run-card-span-2",
            ),
            _detail_subsection(
                "Underlying price, entries, and exits",
                _price_marker_panel(detail),
                "run-visual-card run-price-focus run-card-span-2",
            ),
            _detail_subsection(
                "Drawdown over time",
                _curve_graph(
                    detail.evidence.drawdown_curve,
                    y_field="drawdown",
                    title="Drawdown over time",
                    color="#ef4444",
                    empty="No persisted drawdown artifact is available for this run.",
                    percent=True,
                    markers=True,
                    emphasize_min=True,
                ),
                "run-visual-card run-drawdown-focus",
            ),
            _detail_subsection(
                "Cumulative trade P&L",
                _trade_pnl_chart(detail.evidence.trades, mode="cumulative"),
                "run-visual-card run-pnl-focus",
            ),
            _detail_subsection(
                "Trade return distribution",
                _trade_pnl_chart(detail.evidence.trades, mode="distribution"),
                "run-visual-card run-distribution-focus",
            ),
            _detail_subsection(
                "Trade summary",
                _trade_review_summary(detail.evidence.trades),
                "run-visual-card run-trade-summary-focus",
            ),
            _detail_subsection(
                "Recent trades",
                _artifact_grid(
                    detail.evidence.trades,
                    empty="No persisted trades artifact is available.",
                    profile="trades",
                ),
                "run-visual-card run-trade-focus",
            ),
        ],
        className="run-chart-trade-focus",
    )


def _run_evidence(detail: SelectedRunDetailView) -> Any:
    notice = (
        html.Div(
            [html.P(message) for message in detail.evidence.notices],
            className="fixture-disclaimer fixture-disclaimer-evidence",
        )
        if detail.evidence.notices
        else None
    )
    return html.Div(
        [
            notice,
            _detail_subsection(
                "Result metrics",
                _detail_fields(detail.evidence.metrics, empty="No persisted metrics artifact is available."),
                "run-detail-nested",
            ),
            _detail_subsection(
                "Validation outcome",
                _detail_fields(
                    detail.evidence.validation_outcome,
                    empty="No normalized validation outcome is available.",
                ),
                "run-detail-nested",
            ),
            _detail_subsection(
                "Validation evidence",
                _detail_fields(detail.evidence.validation, empty="No validation evidence artifact is available."),
                "run-detail-nested",
            ),
            _detail_subsection(
                "Data provenance",
                _detail_fields(detail.evidence.provenance, empty="No data provenance is available."),
                "run-detail-nested",
            ),
        ]
    )


def _validation_evidence_summary(detail: SelectedRunDetailView | None) -> html.Div:
    status = _validation_outcome_value(detail)
    reason = (
        _detail_field_value(
            detail.evidence.validation_outcome if detail else (),
            "Reasons",
            "Reason",
            "Validation reason",
        )
        or "No concise validation reason is recorded."
    )
    status_key = status.strip().lower()
    if status_key in {"passed", "pass"}:
        next_action = "Review the supporting evidence before recording a decision."
    elif status_key in {"failed", "fail"}:
        next_action = "Inspect the technical details before deciding how to proceed."
    else:
        next_action = "Inspect the technical details to determine the available next step."

    return html.Div(
        [
            html.H3("Validation summary"),
            html.Div(
                [
                    html.Span("Validation result", className="metric-label"),
                    html.Strong(status),
                ],
                className="metric-card",
            ),
            html.P(reason, className="run-status-summary"),
            html.P(f"Next action: {next_action}", className="field-help"),
        ],
        className="run-validation-summary",
    )


def _validation_evidence_tab(detail: SelectedRunDetailView | None) -> html.Div:
    if detail is None:
        technical_details = [
            _detail_subsection(
                "Artifacts and validation",
                html.P(
                    "Artifact validation details are not available for this run.",
                    className="empty-state-copy",
                ),
            ),
            _detail_subsection(
                "Result summary",
                html.P(
                    "No persisted result summary is available for this run.",
                    className="empty-state-copy",
                ),
            ),
        ]
    else:
        warnings = (
            html.Div(
                [html.P(warning) for warning in detail.warnings],
                className="run-detail-warning",
            )
            if detail.warnings
            else None
        )
        technical_details = [
            warnings,
            _detail_subsection("Validation and evidence", _run_evidence(detail)),
            _detail_subsection(
                "Artifacts and validation",
                _artifact_inventory(detail.artifacts),
            ),
            _detail_subsection(
                "Result summary",
                _result_summary(detail.result_summary),
            ),
        ]

    return html.Div(
        [
            _validation_evidence_summary(detail),
            html.Details(
                [
                    html.Summary("Show technical details"),
                    html.Div(technical_details, className="run-validation-technical-details"),
                ],
                className="operator-details run-validation-details",
            ),
        ],
        className="run-tab-panel",
    )


def _run_detail_analysis_tab(
    *,
    label: str,
    value: str,
    children: Any,
) -> dcc.Tab:
    return dcc.Tab(
        label=label,
        value=value,
        children=children,
        className="run-analysis-tab",
        selected_className="run-analysis-tab-selected",
        style={
            "alignItems": "center",
            "backgroundColor": "#f8fafc",
            "border": "1px solid #cbd7e6",
            "borderRadius": "6px 6px 0 0",
            "color": "#334155",
            "display": "flex",
            "fontWeight": 700,
            "justifyContent": "center",
            "minHeight": "44px",
            "padding": "10px 16px",
        },
        selected_style={
            "backgroundColor": "#2357d9",
            "border": "1px solid #2357d9",
            "color": "#ffffff",
            "fontWeight": 800,
        },
    )


def _run_detail_analysis_tabs(detail: SelectedRunDetailView | None) -> Any:
    if detail is None:
        return dcc.Tabs(
            [
                _run_detail_analysis_tab(
                    label="Strategy Checks",
                    value="evidence",
                    children=_validation_evidence_tab(None),
                ),
                _run_detail_analysis_tab(
                    label="Trading Assumptions",
                    value="assumptions",
                    children=html.Div(
                        _detail_subsection(
                            "Trading assumptions",
                            html.P(
                                "Execution assumptions are not available for this run.",
                                className="empty-state-copy",
                            ),
                        ),
                        className="run-tab-panel",
                    ),
                ),
                _run_detail_analysis_tab(
                    label="Research History",
                    value="lineage",
                    children=html.Div(
                        _detail_subsection(
                            "Research history",
                            html.P(
                                "Research history details are not available for this run.",
                                className="empty-state-copy",
                            ),
                        ),
                        className="run-tab-panel",
                    ),
                ),
                _run_detail_analysis_tab(
                    label="Strategy Settings",
                    value="configuration",
                    children=html.Div(
                        _detail_subsection(
                            "Strategy settings",
                            html.P(
                                "Strategy settings are not available for this run.",
                                className="empty-state-copy",
                            ),
                        ),
                        className="run-tab-panel",
                    ),
                ),
                _run_detail_analysis_tab(
                    label="Technical Details",
                    value="diagnostics",
                    children=html.Div(
                        _detail_subsection(
                            "Technical Details",
                            html.P(
                                "Technical details are not available for this run.",
                                className="empty-state-copy",
                            ),
                        ),
                        className="run-tab-panel",
                    ),
                ),
            ],
            id="run-detail-analysis-tabs",
            value="evidence",
            className="run-analysis-tabs",
            parent_style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "8px",
            },
        )
    return dcc.Tabs(
        [
            _run_detail_analysis_tab(
                label="Strategy Checks",
                value="evidence",
                children=_validation_evidence_tab(detail),
            ),
            _run_detail_analysis_tab(
                label="Trading Assumptions",
                value="assumptions",
                children=html.Div(
                    _detail_subsection(
                        "Trading assumptions",
                        [
                            _detail_subsection(
                                "Market data",
                                _detail_fields(
                                    detail.market_data,
                                    empty="No market-data specification recorded.",
                                ),
                                "run-detail-nested",
                            ),
                            _detail_subsection(
                                "Trading assumptions",
                                _detail_fields(
                                    detail.execution,
                                    empty="No execution assumptions recorded.",
                                ),
                                "run-detail-nested",
                            ),
                            _detail_subsection(
                                "Ranking",
                                _detail_fields(
                                    detail.ranking,
                                    empty="No ranking specification recorded.",
                                ),
                                "run-detail-nested",
                            ),
                            _detail_subsection(
                                "Screening",
                                _detail_fields(
                                    detail.screening,
                                    empty="No screening specification recorded.",
                                ),
                                "run-detail-nested",
                            ),
                        ],
                    ),
                    className="run-tab-panel",
                ),
            ),
            _run_detail_analysis_tab(
                label="Research History",
                value="lineage",
                children=html.Div(
                    _detail_subsection(
                        "Research history",
                        [
                            _detail_fields(
                                detail.manifest_fields,
                                empty="Manifest status is unavailable.",
                            ),
                            _detail_fields(
                                detail.lineage_fields,
                                empty="Research history is not recorded.",
                            ),
                        ],
                    ),
                    className="run-tab-panel",
                ),
            ),
            _run_detail_analysis_tab(
                label="Strategy Settings",
                value="configuration",
                children=html.Div(
                    _detail_subsection(
                        "Strategy settings",
                        [
                            _detail_fields(
                                detail.configuration_fields,
                                empty="Strategy settings are unavailable.",
                            ),
                            _detail_subsection(
                                "Parameters",
                                _detail_fields(
                                    detail.parameters,
                                    empty="No parameters recorded.",
                                ),
                                "run-detail-nested",
                            ),
                            _detail_subsection(
                                "Ranking",
                                _detail_fields(
                                    detail.ranking,
                                    empty="No ranking specification recorded.",
                                ),
                                "run-detail-nested",
                            ),
                            _detail_subsection(
                                "Screening",
                                _detail_fields(
                                    detail.screening,
                                    empty="No screening specification recorded.",
                                ),
                                "run-detail-nested",
                            ),
                        ],
                    ),
                    className="run-tab-panel",
                ),
            ),
            _run_detail_analysis_tab(
                label="Technical Details",
                value="diagnostics",
                children=html.Div(
                    [
                        (
                            html.Div(
                                [html.P(warning) for warning in detail.warnings],
                                className="run-detail-warning",
                            )
                            if detail.warnings
                            else None
                        ),
                        _detail_subsection(
                            "Artifacts and validation",
                            _artifact_inventory(detail.artifacts),
                        ),
                        _detail_subsection(
                            "Result summary",
                            _result_summary(detail.result_summary),
                        ),
                    ],
                    className="run-tab-panel",
                ),
            ),
        ],
        id="run-detail-analysis-tabs",
        value="evidence",
        className="run-analysis-tabs",
        parent_style={
            "display": "flex",
            "flexWrap": "wrap",
            "gap": "8px",
        },
    )


def _run_event_content(events: tuple[RunEvent, ...]) -> Any:
    if not events:
        return html.P(
            "No operator events are recorded for this run.",
            className="empty-state-copy",
        )
    return html.Ol(
        [
            html.Li(
                [
                    html.Div(
                        [
                            html.Strong(event.event_type.replace("_", " ")),
                            html.Span(event.severity),
                        ],
                        className="run-event-heading",
                    ),
                    html.P(event.message),
                    html.Small(f"{event.timestamp} · {event.source}"),
                ],
                className=f"run-event run-event-{event.severity}",
            )
            for event in events
        ],
        className="run-event-list",
    )


def _run_action_controls(
    run: RunSummary | None,
    *,
    launchable_configuration: bool,
) -> html.Div:
    (
        launch_disabled,
        launch_title,
        reproduction_disabled,
        reproduction_title,
        cancellation_disabled,
        cancellation_title,
    ) = _run_action_availability(run, launchable_configuration)
    run_succeeded = not reproduction_disabled
    run_running = not cancellation_disabled
    return html.Div(
        [
            html.Div(
                [
                    html.Button(
                        "Launch new run from this configuration",
                        id="launch-selected-run-configuration",
                        n_clicks=0,
                        disabled=launch_disabled,
                        className="secondary-action",
                        title=launch_title,
                    ),
                    html.Div(
                        (
                            "This creates a new run identity from the selected run's configuration."
                            if run is not None and launchable_configuration
                            else "Select a persisted run to inspect its launch controls."
                            if run is None
                            else "A new run cannot be launched from this configuration."
                        ),
                        id="historical-launch-message",
                        className="historical-launch-message",
                    ),
                ],
                className="run-history-launch-controls",
            ),
            html.Div(
                [
                    html.Button(
                        "Reproduce selected run",
                        id="reproduce-selected-run",
                        n_clicks=0,
                        disabled=reproduction_disabled,
                        className="secondary-action",
                        title=reproduction_title,
                    ),
                    html.Div(
                        (
                            "Reproduction creates a new run and compares it with the original."
                            if run_succeeded
                            else "Select a persisted run to inspect its reproduction controls."
                            if run is None
                            else "Reproduction is unavailable for this run state."
                        ),
                        id="reproduction-message",
                        className="reproduction-message",
                    ),
                ],
                className="run-reproduction-controls",
            ),
            html.Button(
                "Request cancellation",
                id="cancel-selected-run",
                n_clicks=0,
                disabled=cancellation_disabled,
                className="danger-action",
                title=cancellation_title,
            ),
            html.Div(
                (
                    "Cancellation is cooperative. The run remains active "
                    "until the fixture acknowledges the request."
                    if run_running
                    else "Select a persisted run to inspect its cancellation controls."
                    if run is None
                    else "Cancellation is unavailable for this run state."
                ),
                id="cancellation-message",
                className="cancellation-message",
            ),
        ],
        className="run-cancellation-controls",
    )


def _run_action_availability(
    run: RunSummary | None,
    launchable_configuration: bool,
) -> tuple[bool, str, bool, str, bool, str]:
    if run is None:
        return (
            True,
            "Select a persisted run before launching its configuration.",
            True,
            "Select a persisted run before requesting reproduction.",
            True,
            "Select a persisted run before requesting cancellation.",
        )
    return (
        not launchable_configuration,
        (
            "Launch a new run from this historical run's immutable configuration."
            if launchable_configuration
            else "This run's saved configuration is unavailable or not launchable."
        ),
        run.status != "succeeded",
        (
            "Create a new run from this persisted run after validating its manifest and artifacts."
            if run.status == "succeeded"
            else "Only a succeeded persisted run can be reproduced."
        ),
        run.status != "running",
        (
            "Request cooperative cancellation for this active run."
            if run.status == "running"
            else "Only an active running fixture can be cancelled."
        ),
    )


def _run_detail_panel(
    run: RunSummary | None,
    events: tuple[RunEvent, ...] = (),
    *,
    detail: SelectedRunDetailView | None = None,
) -> html.Section:
    if run is None:
        return html.Section(
            [
                html.H2("Run details"),
                html.P(
                    "Select a recent run to inspect its authoritative state and events.",
                    className="empty-state-copy",
                ),
            ],
                className="panel run-detail-panel",
        )

    identity_fields = [
        ("Run ID", run.run_id),
        ("Configuration", run.configuration_id),
        ("Strategy", f"{run.strategy_id}@{run.strategy_version}"),
        ("Stage", run.stage),
        ("Attempt count", str(run.attempt_count)),
    ]
    timing_fields = [
        ("Created", run.created_at),
        ("Started", run.started_at or "Not started"),
        ("Completed", run.completed_at or "Not completed"),
        ("Prefect flow run", run.prefect_flow_run_id or "Not available"),
        ("Prefect API", run.prefect_api_url or "Not available"),
    ]
    terminal_summary = (
        run.error_summary
        if run.error_summary
        else "Infrastructure fixture evidence verifies the factory path; it does not imply profitability."
    )

    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.P("Selected backtest", className="section-eyebrow"),
                            html.H2(_strategy_display_name(run.strategy_id)),
                            html.P(terminal_summary, className="run-status-summary"),
                        ],
                        className="run-status-copy",
                    ),
                    html.Div(
                        [
                            _outcome_badge(
                                _validation_outcome_value(detail),
                                run.status,
                            ),
                            html.Span(
                                run.status,
                                className=f"run-status run-status-{run.status}",
                            ),
                            html.Strong("Validation result"),
                            html.Small("Traceability retained below"),
                        ],
                        className="run-status-badge-stack",
                    ),
                ],
                className="run-detail-hero",
            ),
            _run_identity_strip(run, detail),
            (
                html.Div(
                    [
                        html.H3("Error summary"),
                        html.P(run.error_summary),
                    ],
                    className="run-detail-error",
                )
                if run.error_summary
                else None
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.H3("Primary metrics"),
                            html.P(
                                "Only metrics present in persisted evidence are shown.",
                                className="field-help",
                            ),
                        ],
                        className="run-section-heading",
                    ),
                    html.Div(
                        _primary_metric_cards(detail),
                        className="run-primary-results-grid",
                    ),
                ],
                className="run-primary-results",
            ),
            _run_chart_and_trade_focus(detail),
            html.Div(
                "Infrastructure fixture evidence verifies the factory path; it does not imply profitability.",
                className="fixture-disclaimer",
            ),
            _run_detail_analysis_tabs(detail),
            html.Details(
                [
                    html.Summary("Operations and diagnostics"),
                    html.Div(
                        [
                            _detail_subsection(
                                "Run identity and timing",
                                [
                                    html.Dl(
                                        [
                                            html.Div([html.Dt(label), html.Dd(value)])
                                            for label, value in identity_fields
                                        ],
                                        className="run-detail-fields",
                                    ),
                                    html.Dl(
                                        [
                                            html.Div([html.Dt(label), html.Dd(value)])
                                            for label, value in timing_fields
                                        ],
                                        className="run-detail-fields",
                                    ),
                                ],
                                "run-detail-nested",
                            ),
                            _detail_subsection(
                                "Run events",
                                _run_event_content(events),
                                "run-detail-nested",
                            ),
                        ],
                        className="run-operations-panel",
                    ),
                ],
                open=False,
                className="operator-details run-operations-details",
            ),
        ],
        className="panel run-detail-panel",
    )


def _runs_page(
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    recent_runs: tuple[RunSummary, ...] = (),
    recent_events: tuple[RunEvent, ...] = (),
    selected_run_panel: Any | None = None,
    selected_run_id: str | None = None,
    all_runs: tuple[RunSummary, ...] = (),
    history_rows: tuple[dict[str, object], ...] = (),
) -> html.Div:
    configurations = (
        list_saved_configurations()
        if configurations is None
        else configurations
    )
    ordered_runs = _ordered_backtests(recent_runs)
    initial_selected_run_id = (
        selected_run_id
        if selected_run_id is not None
        else ordered_runs[0].run_id
        if ordered_runs
        else None
    )
    initial_selected_run = next(
        (
            run
            for run in recent_runs
            if run.run_id == initial_selected_run_id
        ),
        None,
    )

    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P(
                                "RESEARCH / RESULTS",
                                className="page-eyebrow",
                            ),
                            html.H1(
                                "Results",
                                className="page-title",
                            ),
                            html.P(
                                "Understand what happened, whether the evidence is usable, and what decision is required.",
                                className="page-description",
                            ),
                        ],
                    ),
                    html.Div(
                        [
                            dcc.Link(
                                "Compare",
                                href="/research/compare-backtests",
                                className="secondary-action page-action",
                                title="Use Compare Backtests to compare persisted backtests.",
                            ),
                            html.Button(
                                "Export",
                                className="secondary-action page-action",
                                disabled=True,
                                title="Export is unavailable until a persisted export path is implemented.",
                            ),
                            html.Button(
                                "Refresh",
                                id="refresh-runs",
                                n_clicks=0,
                                className="primary-action page-action",
                                title="Refresh persisted runs, events, and selected-run evidence.",
                            ),
                        ],
                        className="page-actions",
                    ),
                ],
                className="page-heading page-heading-with-actions",
            ),
            _strategy_research_path("/research/backtest-results"),
            _results_operator_context(initial_selected_run),
            dcc.Store(
                id="selected-run-state",
                data=initial_selected_run_id,
                storage_type="session",
            ),
            html.Section(
                [
                    html.H2("Run history"),
                    html.P("Search and sort every persisted run. Selecting a row opens the backtest details.", className="field-help"),
                    dag.AgGrid(
                        id="run-history-grid",
                        rowData=list(history_rows) if history_rows else [_history_row(run) for run in all_runs],
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
                            {
                                "field": "total_return",
                                "headerName": "Total Return",
                                "type": "numericColumn",
                                "filter": "agNumberColumnFilter",
                                "valueFormatter": {
                                    "function": "params.value == null ? '' : (params.value * 100).toFixed(2) + '%'"
                                },
                            },
                            {
                                "field": "annualized_return",
                                "headerName": "Annualized Return",
                                "type": "numericColumn",
                                "filter": "agNumberColumnFilter",
                                "valueFormatter": {
                                    "function": "params.value == null ? '' : (params.value * 100).toFixed(2) + '%'"
                                },
                            },
                            {
                                "field": "sharpe_ratio",
                                "headerName": "Sharpe Ratio",
                                "type": "numericColumn",
                                "filter": "agNumberColumnFilter",
                                "valueFormatter": {
                                    "function": "params.value == null ? '' : Number(params.value).toFixed(2)"
                                },
                            },
                            {
                                "field": "number_of_trades",
                                "headerName": "Number of Trades",
                                "type": "numericColumn",
                                "filter": "agNumberColumnFilter",
                                "valueFormatter": {
                                    "function": "params.value == null ? '' : Math.round(params.value).toLocaleString()"
                                },
                            },
                            {"field": "artifact_status", "headerName": "Artifacts"},
                            {"field": "reproducibility", "headerName": "Reproducibility"},
                        ],
                        defaultColDef={"sortable": True, "filter": True, "resizable": True},
                        dashGridOptions={"rowSelection": "single"},
                        getRowId="params.data.run_id",
                        selectedRows=[],
                        style={"height": "360px"},
                    ),
                ],
                className="panel run-history-panel",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Section(
                                [
                                    html.Label(
                                        "Selected backtest",
                                        htmlFor="selected-run-selector",
                                        className="field-label",
                                    ),
                                    dcc.Dropdown(
                                        id="selected-run-selector",
                                        options=_selector_options(recent_runs),
                                        value=initial_selected_run_id,
                                        clearable=False,
                                        placeholder="No recent backtests",
                                    ),
                                    html.P(
                                        "Raw run identity remains available in the selected backtest metadata.",
                                        className="field-help compact-field-help",
                                    ),
                                ],
                                className="panel run-selector-panel compact-run-selector-panel",
                            ),
                        ],
                        className="run-results-toolbar",
                    ),
                    html.Div(
                        selected_run_panel
                        if selected_run_panel is not None
                        else _run_detail_panel(None),
                        id="selected-run-detail",
                    ),
                    _trade_explorer_layout(),
                ],
                className="backtest-detail-workspace workflow-group-results",
            ),
            html.Section(
                [
                    html.Details(
                        [
                            html.Summary("Comparison and selected-backtest actions"),
                            html.Div(
                                _recent_runs_panel(recent_runs),
                                id="recent-runs-monitor",
                                className="secondary-run-monitor",
                            ),
                            html.Section(
                                [
                                    html.H3("Selected backtest actions"),
                                    _run_action_controls(
                                        initial_selected_run,
                                        launchable_configuration=(
                                            initial_selected_run is not None
                                            and _configuration_is_launchable(
                                                initial_selected_run.configuration_id,
                                                configurations,
                                            )
                                        ),
                                    ),
                                ],
                                className="panel selected-run-actions-panel",
                            ),
                        ],
                        open=False,
                        className="operator-details mockup-secondary-details",
                    ),
                ],
                className="workflow-group workflow-group-analysis",
            ),
            html.Section(
                [
                    html.H2("Operations and diagnostics"),
                    html.Details(
                        [
                            html.Summary("Recovery and operator events"),
                            html.Div(
                                [
                                    html.Section(
                                        [
                                            html.H3("Stale-run recovery"),
                                            html.P(
                                                (
                                                    "Fail fixture runs that remained created or running "
                                                    "before an explicit UTC cutoff."
                                                ),
                                                className="field-help",
                                            ),
                                            html.Label(
                                                "Stale before (UTC)",
                                                htmlFor="stale-before-input",
                                                className="field-label",
                                            ),
                                            dcc.Input(
                                                id="stale-before-input",
                                                type="text",
                                                placeholder="2026-07-13T12:00:00Z",
                                                debounce=True,
                                                className="stale-before-input",
                                            ),
                                            html.Button(
                                                "Recover stale fixture runs",
                                                id="recover-stale-runs",
                                                n_clicks=0,
                                                className="secondary-action",
                                                title=(
                                                    "Fail created or running fixture runs older than "
                                                    "the explicit UTC cutoff."
                                                ),
                                            ),
                                            html.Div(
                                                (
                                                    "No recovery has been requested. The cutoff must be "
                                                    "an explicit UTC timestamp."
                                                ),
                                                id="stale-recovery-message",
                                                className="stale-recovery-message",
                                            ),
                                        ],
                                        className="panel stale-recovery-panel",
                                    ),
                                    html.Div(
                                        _recent_events_panel(recent_events),
                                        id="recent-events-monitor",
                                    ),
                                ],
                                className="operations-diagnostics-grid",
                            ),
                        ],
                        open=False,
                        className="operator-details operations-diagnostics-details",
                    ),
                ],
                className="workflow-group workflow-group-operations",
            ),
        ],
        className="page-container",
    )


def _history_row(run: RunSummary) -> dict[str, object]:
    return {
        "run_id": run.run_id,
        "created_at": run.created_at,
        "instrument": "Not recorded",
        "strategy": _strategy_display_name(run.strategy_id),
        "stage": {
            "fixture": "Fixture backtest",
            "walk_forward": "Walk-forward validation",
            "monte_carlo": "Monte Carlo validation",
            "robustness": "Robustness validation",
            "oos": "Out-of-sample evidence",
            "screening": "Screening",
        }.get(run.stage, run.stage.replace("_", " ").title()),
        "status": run.status.replace("_", " ").title(),
        "review": "Not checked",
        "evidence": "Unverified",
        "total_return": None,
        "annualized_return": None,
        "sharpe_ratio": None,
        "number_of_trades": None,
        "metric_basis": "No persisted ranked result",
        "artifact_status": "Unverified",
        "reproducibility": "Unverified",
    }


def _comparison_value_text(value: object) -> str:
    if value in (None, {}, ()):
        return "Missing or unavailable"
    if isinstance(value, dict):
        if not value:
            return "Missing or unavailable"
        return "; ".join(
            f"{_operator_label(key)}: {_comparison_value_text(value[key])}"
            for key in sorted(value)
        )
    if isinstance(value, (list, tuple)):
        if not value:
            return "Missing or unavailable"
        return ", ".join(_comparison_value_text(item) for item in value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str) and (
        value in OPERATOR_VALUE_LABELS
        or (value.islower() and "_" in value and len(value) <= 40)
    ):
        friendly = OPERATOR_VALUE_LABELS.get(
            value,
            value.replace("_", " ").replace("-", " ").title(),
        )
        return f"{friendly} ({value})" if friendly != value else value
    return str(value)


def _run_comparison_panel(comparison: tuple[dict[str, object], ...]) -> html.Section:
    run_ids = [str(item["run_id"]) for item in comparison]
    field_groups = zip(
        *[item.get("fields", ()) for item in comparison],
        strict=True,
    )
    rows = []
    state_counts = {"equal": 0, "changed": 0, "missing": 0}
    for fields in field_groups:
        first = fields[0]
        state = str(first["state"])
        state_counts[state] = state_counts.get(state, 0) + 1
        rows.append(
            html.Tr(
                [
                    html.Th(str(first["label"]), scope="row"),
                    html.Td(
                        state,
                        className=f"comparison-state comparison-state-{state}",
                    ),
                    *[
                        html.Td(_comparison_value_text(field["value"]))
                        for field in fields
                    ],
                ],
                className=f"comparison-row comparison-row-{state}",
            )
        )

    return html.Section(
        [
            html.H3("Backtest comparison"),
            html.Div(
                [
                    html.Article(
                        [
                            html.Span("Backtests", className="metric-label"),
                            html.Strong(str(len(run_ids))),
                        ],
                        className="comparison-summary-card",
                    ),
                    html.Article(
                        [
                            html.Span("Equal", className="metric-label"),
                            html.Strong(str(state_counts.get("equal", 0))),
                        ],
                        className="comparison-summary-card comparison-summary-equal",
                    ),
                    html.Article(
                        [
                            html.Span("Changed", className="metric-label"),
                            html.Strong(str(state_counts.get("changed", 0))),
                        ],
                        className="comparison-summary-card comparison-summary-changed",
                    ),
                    html.Article(
                        [
                            html.Span("Missing", className="metric-label"),
                            html.Strong(str(state_counts.get("missing", 0))),
                        ],
                        className="comparison-summary-card comparison-summary-missing",
                    ),
                ],
                className="comparison-summary-grid",
            ),
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("Field"),
                                html.Th("State"),
                                *[
                                    html.Th(
                                        [
                                            html.Span(f"Backtest {index}"),
                                            html.Small(
                                                run_id,
                                                className="comparison-trace-id",
                                            ),
                                        ]
                                    )
                                    for index, run_id in enumerate(run_ids, start=1)
                                ],
                            ]
                        )
                    ),
                    html.Tbody(rows),
                ],
                className="run-comparison-table",
            ),
        ],
        className="run-comparison-result",
    )


def _comparisons_page(recent_runs: tuple[RunSummary, ...] = ()) -> html.Div:
    selected_values = _default_comparison_values(recent_runs)
    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P(
                                "RESEARCH / COMPARE",
                                className="page-eyebrow",
                            ),
                            html.H1(
                                "Compare results",
                                className="page-title",
                            ),
                            html.P(
                                "Compare persisted tests without hiding evidence or assumption differences.",
                                className="page-description",
                            ),
                        ],
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Export",
                                className="secondary-action page-action",
                                disabled=True,
                                title=(
                                    "Export is unavailable until a persisted export path "
                                    "is implemented."
                                ),
                            ),
                            html.Button(
                                "Refresh",
                                id="refresh-comparisons",
                                n_clicks=0,
                                className="secondary-action page-action",
                                title="Refresh persisted backtest choices.",
                            ),
                        ],
                        className="page-actions",
                    ),
                ],
                className="page-heading page-heading-with-actions",
            ),
            _strategy_research_path("/research/compare-backtests"),
            operator_context(component_id="compare-operator-context"),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Selection", className="section-kicker"),
                            html.H2("Selected backtests"),
                            html.P(
                                (
                                    "Choose two or more saved backtests to compare their "
                                    "results and research checks."
                                ),
                                className="section-description",
                            ),
                        ],
                        className="section-heading-row",
                    ),
                    html.Div(
                        [
                            html.Label(
                                "Selected backtests",
                                htmlFor="comparison-run-selector",
                                className="field-label",
                            ),
                            dcc.Dropdown(
                                id="comparison-run-selector",
                                options=_selector_options(recent_runs),
                                value=selected_values,
                                multi=True,
                                placeholder="Select at least two persisted backtests",
                            ),
                            html.P(
                                "Choose saved backtests by their readable labels.",
                                className="field-help compact-field-help",
                            ),
                        ],
                        className="comparison-selector-control",
                    ),
                    html.Div(
                        _comparison_backtest_cards(recent_runs, selected_values),
                        id="comparison-selected-cards",
                        className="comparison-selected-grid",
                    ),
                    html.Div(
                        [
                            html.Button(
                                "Compare selected backtests",
                                id="compare-selected-runs",
                                n_clicks=0,
                                className="primary-action page-action",
                                title=(
                                    "Compare immutable persisted backtest metadata and "
                                    "available evidence."
                                ),
                            ),
                        ],
                        className="comparison-action-row",
                    ),
                ],
                className="comparison-setup-panel",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Evidence", className="section-kicker"),
                            html.H2("Comparison summary"),
                            html.P(
                                (
                                    "Equal, changed and missing states are grouped across "
                                    "performance metrics, strategy settings, trading assumptions, "
                                    "strategy checks and research history."
                                ),
                                className="section-description",
                            ),
                        ],
                        className="section-heading-row",
                    ),
                    html.Div(
                        "Select at least two persisted backtests, then compare them.",
                        id="run-comparison-output",
                        className="run-comparison-output comparison-empty-state",
                    ),
                ],
                className="comparison-results-panel",
            ),
        ],
        className="page-container comparison-page",
    )


def _run_launch_summary(run: RunSummary) -> html.Div:
    """Render one service-owned launch result without duplicating orchestration."""

    prefect_reference = (
        run.prefect_flow_run_id
        if run.prefect_flow_run_id
        else "Not available"
    )
    timing = run.completed_at or run.started_at or run.created_at
    status_class = (
        "run-launch-status run-launch-status-success"
        if run.status == "succeeded"
        else "run-launch-status run-launch-status-error"
        if run.status in {"failed", "cancelled"}
        else "run-launch-status"
    )

    details = [
        html.Li(f"Quant Factory run: {run.run_id}"),
        html.Li(f"Status: {run.status}"),
        html.Li(f"Attempt count: {run.attempt_count}"),
        html.Li(f"Recorded: {timing}"),
        html.Li(f"Prefect flow run: {prefect_reference}"),
    ]
    if run.error_summary:
        details.append(html.Li(f"Error: {run.error_summary}"))

    return html.Section(
        [
            html.H3("Run launched"),
            html.Ul(details),
        ],
        className=status_class,
        **{"data-run-id": run.run_id},
    )


def _configuration_is_launchable(
    configuration_id: str,
    configurations: tuple[SavedConfigurationView, ...],
) -> bool:
    return any(
        configuration.configuration_id == configuration_id
        and configuration.launchable
        for configuration in configurations
    )


REVIEW_CONTEXT_UNAVAILABLE_MESSAGE = (
    "Durable decision unavailable: this backtest has no persisted review context "
    "linking out-of-sample, walk-forward, Monte Carlo and robustness evidence."
)


def _review_context_unavailable_notice() -> html.Div:
    return _operator_message(
        REVIEW_CONTEXT_UNAVAILABLE_MESSAGE,
        tone="warning",
    )


def _review_context_failure_message(exc: BaseException) -> str:
    message = str(exc) or REVIEW_CONTEXT_UNAVAILABLE_MESSAGE
    if "review context artifact is missing" in message:
        return REVIEW_CONTEXT_UNAVAILABLE_MESSAGE
    return message


def _decision_summary(decision: Any) -> html.Div:
    review = decision.document["decision"]["review"]
    gate = decision.document["decision"]["lockbox_gate"]
    references = gate.get("referenced_artifacts", ())
    return html.Div(
        [
            html.Strong("Evidence decision artifact validated."),
            html.Dl(
                [
                    html.Div([html.Dt("Status"), html.Dd(review.get("state", "—"))]),
                    html.Div([html.Dt("Reviewer"), html.Dd(review.get("reviewer", "—"))]),
                    html.Div([html.Dt("Reason"), html.Dd(review.get("reason", "—"))]),
                    html.Div([html.Dt("Gate"), html.Dd(gate.get("status", "—"))]),
                    html.Div([html.Dt("Decision identity"), html.Dd(decision.decision_identity)]),
                    html.Div([html.Dt("Referenced evidence"), html.Dd(str(len(references)))]),
                ],
                className="run-detail-fields",
            ),
        ],
        className="operator-message operator-message-success",
    )


def _system_page() -> html.Div:
    health = spym_dashboard_health(load_spym_manifest())
    return html.Div(
        [
            _page_heading(
                "SYSTEM",
                "System Status",
                "Review service availability, storage and integrity status.",
            ),
            html.Section(
                [
                    html.H2("SPYM equity data contract"),
                    html.P(
                        (
                            "The provider is selected; the dataset is usable "
                            "only when the committed manifest validates."
                        )
                    ),
                    html.Dl(
                        [
                            html.Div(
                                [
                                    html.Dt(key.replace("_", " ").title()),
                                    html.Dd(value),
                                ]
                            )
                            for key, value in health.items()
                        ],
                        id="spym-data-health",
                        className="run-monitor-details",
                    ),
                ],
                className="panel system-health-panel",
            ),
        ],
        className="page-container",
    )


def page_for_path(
    pathname: str | None,
    context: DashboardContext | None,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    recent_runs: tuple[RunSummary, ...] = (),
    recent_events: tuple[RunEvent, ...] = (),
    selected_run_panel: Any | None = None,
    selected_run_id: str | None = None,
    dashboard_database: Path | None = None,
    artifact_root: Path | None = None,
    catalog_snapshot: tuple | None = None,
    all_runs: tuple[RunSummary, ...] = (),
    history_rows: tuple[dict[str, object], ...] = (),
) -> html.Div:
    route = pathname or "/"
    if route == "/":
        return _overview_page(
            recent_runs=recent_runs,
            recent_events=recent_events,
        )
    if route == "/research/ideas":
        from dashboard.pages.ideas import layout as ideas_layout

        return ideas_layout()
    if route == "/research/setup":
        from dashboard.pages.setup import layout as setup_layout

        return setup_layout(configurations=configurations)
    if route == "/research/run-test":
        from dashboard.pages.run_test import layout as run_test_layout

        return run_test_layout(configurations=configurations)
    if route == "/research/market-data":
        from dashboard.pages.market_data import layout as market_data_layout

        return market_data_layout(catalog_snapshot=catalog_snapshot)
    if route == "/research/backtest-results":
        from dashboard.pages.backtest_results import layout as backtest_results_layout

        return backtest_results_layout(
            configurations=configurations,
            recent_runs=recent_runs,
            recent_events=recent_events,
            selected_run_panel=selected_run_panel,
            selected_run_id=selected_run_id,
            all_runs=all_runs,
            history_rows=history_rows,
        )
    if route == "/research/strategy-review":
        from dashboard.pages.strategy_review import layout as strategy_review_layout

        return strategy_review_layout(context, recent_runs=recent_runs)
    if route == "/research/compare-backtests":
        from dashboard.pages.compare_backtests import layout as compare_backtests_layout

        return compare_backtests_layout(recent_runs=recent_runs)
    if route == "/paper/fleet":
        return _pending_page(
            "PAPER TRADING",
            "Paper Trading Overview",
            "Forward performance across approved strategies, kept separate and individually traceable.",
            scope_note=(
                "Paper-trading execution is intentionally not implemented in this milestone pass."
            ),
        )
    if route == "/paper/strategy":
        return _pending_page(
            "PAPER TRADING",
            "Strategy Monitor",
            "Actual forward activity, strategy-specific P&L, positions, orders, fills and health.",
            scope_note=(
                "Paper-account and broker data are unavailable in this research-dashboard pass."
            ),
        )
    if route == "/system":
        from dashboard.pages.system_health import layout as system_health_layout

        return system_health_layout(
            dashboard_database if dashboard_database is not None else database_path(),
            artifact_root if artifact_root is not None else PROJECT_ROOT,
            catalog_snapshot=catalog_snapshot,
        )
    if route == "/system/providers":
        from dashboard.pages.system_health import provider_layout

        return provider_layout(catalog_snapshot=catalog_snapshot)
    if route == "/settings":
        return _pending_page(
            "GLOBAL / SETTINGS",
            "Settings",
            "Operator preferences and dashboard configuration.",
        )
    return _not_found_page(route)


def route_content_for_path(
    pathname: str | None,
    context: DashboardContext | None,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    recent_runs: tuple[RunSummary, ...] = (),
    recent_events: tuple[RunEvent, ...] = (),
    selected_run_panel: Any | None = None,
    selected_run_id: str | None = None,
    all_runs: tuple[RunSummary, ...] = (),
) -> html.Div:
    route = pathname or "/"
    return page_for_path(
        route,
        context,
        configurations,
        recent_runs=recent_runs,
        recent_events=recent_events,
        selected_run_panel=selected_run_panel,
        selected_run_id=selected_run_id,
        all_runs=all_runs,
    )


def create_layout(
    context: DashboardContext | None,
    configurations: tuple[SavedConfigurationView, ...] | None = None,
    *,
    initial_pathname: str = "/",
    recent_runs: tuple[RunSummary, ...] = (),
    recent_events: tuple[RunEvent, ...] = (),
    selected_run_panel: Any | None = None,
    selected_run_id: str | None = None,
    dashboard_database: Path | None = None,
    artifact_root: Path | None = None,
    all_runs: tuple[RunSummary, ...] = (),
    history_rows: tuple[dict[str, object], ...] = (),
) -> html.Div:
    return create_dashboard_layout(
        context,
        configurations,
        page_factory=partial(
            page_for_path,
            dashboard_database=dashboard_database,
            artifact_root=artifact_root,
            catalog_snapshot=inspect_catalog(),
        ),
        initial_pathname=initial_pathname,
        recent_runs=recent_runs,
        recent_events=recent_events,
        selected_run_panel=selected_run_panel,
        selected_run_id=selected_run_id,
        all_runs=all_runs,
        history_rows=history_rows,
    )


def create_app(
    context: DashboardContext | None = None,
    review_database: str | Path | None = None,
    run_service: FixtureRunService | None = None,
    run_detail_adapter: RunDetailDashboardAdapter | None = None,
) -> Dash:
    # Mounted pages read persisted runs. Opening the dashboard must never
    # download prices or run the legacy RSI parameter grid as a side effect.
    dashboard_database = database_path(review_database)
    configurations = list_saved_configurations(dashboard_database)
    runs = run_service or FixtureRunService(database=dashboard_database)
    detail_adapter = run_detail_adapter or RunDetailDashboardAdapter(
        database=dashboard_database
    )
    artifact_root = getattr(detail_adapter, "artifact_root", Path.cwd())
    recent_run_records = runs.recent_runs(limit=20)
    all_run_records = (
        runs.all_runs() if hasattr(runs, "all_runs") else recent_run_records
    )
    history_records = (
        runs.all_history(artifact_root=artifact_root)
        if hasattr(runs, "all_history")
        else tuple(_history_row(run) for run in all_run_records)
    )
    recent_event_records = runs.recent_events(limit=20)
    selected_run_panel: Any | None = None
    selected_run_id: str | None = None
    if recent_run_records:
        selected_run, selected_detail = _select_initial_backtest(
            recent_run_records,
            detail_adapter,
        )
    else:
        selected_run, selected_detail = None, None
    if selected_run is not None:
        selected_run_id = selected_run.run_id
        if selected_detail is None:
            try:
                selected_detail = detail_adapter.selected_run_detail(
                    selected_run.run_id
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                selected_detail = SelectedRunDetailView(
                    configuration_fields=(),
                    parameters=(),
                    market_data=(),
                    execution=(),
                    ranking=(),
                    screening=(),
                    lineage_fields=(),
                    manifest_fields=(),
                    artifacts=(),
                    result_summary=ResultSummaryView(
                        status="empty",
                        message="No persisted result summary is available for this run.",
                        rows=(),
                    ),
                    evidence=RunEvidenceView(
                        notices=(),
                        metrics=(),
                        trades=(),
                        orders=(),
                        equity_curve=(),
                        drawdown_curve=(),
                        validation=(),
                        provenance=(),
                        warnings=(),
                    ),
                    warnings=(f"Run detail retrieval failed: {exc}",),
                )
        selected_run_panel = _run_detail_panel(
            selected_run,
            runs.events_for_run(selected_run.run_id),
            detail=selected_detail,
        )
    elif recent_run_records:
        selected_run = recent_run_records[0]
        selected_run_id = selected_run.run_id
        try:
            selected_detail = detail_adapter.selected_run_detail(selected_run.run_id)
        except (KeyError, RuntimeError, ValueError) as exc:
            selected_detail = SelectedRunDetailView(
                configuration_fields=(),
                parameters=(),
                market_data=(),
                execution=(),
                ranking=(),
                screening=(),
                lineage_fields=(),
                manifest_fields=(),
                artifacts=(),
                result_summary=ResultSummaryView(
                    status="empty",
                    message="No persisted result summary is available for this run.",
                    rows=(),
                ),
                evidence=RunEvidenceView(
                    notices=(),
                    metrics=(),
                    trades=(),
                    orders=(),
                    equity_curve=(),
                    drawdown_curve=(),
                    validation=(),
                    provenance=(),
                    warnings=(),
                ),
                warnings=(f"Run detail retrieval failed: {exc}",),
            )
        selected_run_panel = _run_detail_panel(
            selected_run,
            runs.events_for_run(selected_run.run_id),
            detail=selected_detail,
        )
    app = Dash(
        __name__,
        suppress_callback_exceptions=True,
        meta_tags=[
            {
                "name": "viewport",
                "content": (
                    "width=device-width, initial-scale=1, "
                    "maximum-scale=5, user-scalable=yes"
                ),
            }
        ],
    )
    _register_initial_path_cookie(app)
    app.title = "Quant Factory"
    layout_kwargs = {
        "dashboard_database": dashboard_database,
        "artifact_root": artifact_root,
        "recent_runs": recent_run_records,
        "recent_events": recent_event_records,
        "selected_run_panel": selected_run_panel,
        "selected_run_id": selected_run_id,
        "all_runs": all_run_records,
        "history_rows": history_records,
    }

    def serve_layout() -> html.Div:
        # A new tab or refresh must reflect runs created since server startup.
        # Initial callback hydration deliberately preserves mounted selector
        # options, so a startup-only snapshot would hide later runs.
        current_layout_kwargs = {
            **layout_kwargs,
            "recent_runs": runs.recent_runs(limit=20),
            "recent_events": runs.recent_events(limit=20),
            "all_runs": (
                runs.all_runs() if hasattr(runs, "all_runs") else runs.recent_runs(limit=20)
            ),
            "history_rows": (
                runs.all_history(artifact_root=artifact_root)
                if hasattr(runs, "all_history")
                else tuple(_history_row(run) for run in runs.recent_runs(limit=20))
            ),
        }
        return create_layout(
            context,
            configurations,
            initial_pathname=_request_pathname_for_initial_layout(),
            **current_layout_kwargs,
        )

    app.layout = serve_layout
    app.validation_layout = create_layout(
        context,
        configurations,
        **layout_kwargs,
    )

    from dashboard.callbacks.backtest_results import (
        register_backtest_results_callbacks,
    )
    from dashboard.callbacks.compare_backtests import (
        register_compare_backtests_callbacks,
    )
    from dashboard.callbacks.ideas import register_ideas_callbacks
    from dashboard.callbacks.routing import register_routing_callbacks
    from dashboard.callbacks.strategy_review import (
        register_strategy_review_callbacks,
    )
    from dashboard.callbacks.trade_explorer import register_trade_explorer_callbacks

    register_routing_callbacks(app)
    register_ideas_callbacks(app)
    register_backtest_results_callbacks(
        app,
        runs=runs,
        detail_adapter=detail_adapter,
        configurations=configurations,
    )
    register_trade_explorer_callbacks(app, detail_adapter=detail_adapter)
    register_compare_backtests_callbacks(
        app,
        runs=runs,
        dashboard_database=dashboard_database,
        artifact_root=artifact_root,
    )
    register_strategy_review_callbacks(
        app,
        runs=runs,
        detail_adapter=detail_adapter,
        dashboard_database=dashboard_database,
        artifact_root=artifact_root,
    )

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8050, debug=False)
