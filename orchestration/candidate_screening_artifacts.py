"""Durable, same-portfolio evidence for one fixed Candidate screening run."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.experiments import ExperimentConfig
from persistence import ArtifactType, PersistenceService, canonical_json


@dataclass(frozen=True)
class ScreeningPortfolioSnapshot:
    """Bounded evidence extracted while one screening portfolio is alive."""

    trades: pd.DataFrame
    orders: pd.DataFrame
    value: pd.Series | pd.DataFrame


def snapshot_screening_portfolio(portfolio: Any) -> ScreeningPortfolioSnapshot:
    """Detach the evidence we retain without holding every VectorBT portfolio."""
    value = portfolio.value
    return ScreeningPortfolioSnapshot(
        trades=portfolio.trades.records_readable.copy(),
        orders=portfolio.orders.records_readable.copy(),
        value=value.copy(),
    )

def _artifact_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def _artifact_records(frame: pd.DataFrame, *, price_multiplier: float = 1.0) -> list[dict[str, Any]]:
    rows = [{str(key): _artifact_value(value) for key, value in row.items()}
            for row in frame.to_dict(orient="records")]
    if price_multiplier != 1.0:
        for row in rows:
            for key, value in row.items():
                if "price" in key.lower() and isinstance(value, Real) and not isinstance(value, bool):
                    row[key] = float(value) / price_multiplier
    return rows


def _screening_artifacts(*, result: Any, portfolio: Any, data: pd.DataFrame,
                         config: ExperimentConfig, parameter_row_id: str,
                         include_price_series: bool = True) -> tuple[tuple[ArtifactType, str, dict[str, Any]], ...]:
    """Serialize the screened portfolio itself, never a second simulation."""
    matches = result.ranked_results.loc[
        result.ranked_results["parameter_row_id"] == parameter_row_id
    ]
    if len(matches) != 1:
        raise RuntimeError("screening portfolio must match one ranked parameter row")
    row = matches.iloc[0]
    ranking_position = int(matches.index[0]) + 1
    if isinstance(portfolio, ScreeningPortfolioSnapshot):
        trades, orders, value = portfolio.trades, portfolio.orders, portfolio.value
    else:
        trades, orders, value = portfolio.trades.records_readable, portfolio.orders.records_readable, portfolio.value
    recorded = row["number_of_trades"]
    if not isinstance(recorded, Real) or isinstance(recorded, bool) or not math.isfinite(float(recorded)) or float(recorded) != len(trades):
        raise RuntimeError("ranked trade count does not match the actual trade ledger")
    metrics = {key: _artifact_value(row[key]) for key in (
        "total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
        "number_of_trades", "win_rate")}
    policy = config.metric_policy
    annualization = None
    if policy is not None:
        annualization = {
            "sampling": policy.sampling,
            "sessions_per_year": int(policy.periods_per_year),
            "risk_free_rate": float(policy.risk_free_rate),
            "basis": policy.basis,
            "source": policy.source,
            "exchange_calendar": config.market_data.exchange_calendar,
        }
    multiplier = config.execution.price_multiplier
    price_unit = "index_points" if multiplier != 1.0 else "currency"
    if isinstance(value, pd.DataFrame):
        if value.shape[1] != 1:
            raise RuntimeError("expected one-column portfolio equity series")
        value = value.iloc[:, 0]
    return (
        (ArtifactType.RUN_SUMMARY, "run_summary", {
            "strategy_id": result.strategy_id, "strategy_version": result.strategy_version,
            "selected_parameter_row_id": parameter_row_id, "selected_ranking_position": ranking_position,
            "evidence_classification": "Development screening evidence only; not independent, protected, or edge proof",
            "promotion_eligible": False, "broker_orders": "disabled",
        }),
        (ArtifactType.METRICS, "metrics", {
            "parameter_row_id": parameter_row_id, "ranking_position": ranking_position,
            "metrics": metrics, "annualization": annualization,
        }),
        (ArtifactType.TRADES_OR_ORDERS, "trades_and_orders", {
            "parameter_row_id": parameter_row_id, "ranking_position": ranking_position,
            "instrument": config.market_data.symbol, "price_unit": price_unit,
            "pnl_unit": "USD", "price_multiplier": multiplier,
            "price_normalization": "Trade and order price fields are divided by the execution multiplier for display against source bars; monetary fields are unchanged.",
            "trades": _artifact_records(trades, price_multiplier=multiplier),
            "orders": _artifact_records(orders, price_multiplier=multiplier),
        }),
        (ArtifactType.EQUITY_CURVE, "equity_curve", {
            "parameter_row_id": parameter_row_id, "ranking_position": ranking_position,
            "equity_curve": [{"timestamp": _artifact_value(index), "value": _artifact_value(item)} for index, item in value.items()],
            "price_series": ([{"timestamp": _artifact_value(index),
                               **{key.lower(): _artifact_value(item[key]) for key in ("Open", "High", "Low", "Close")}}
                              for index, item in data[["Open", "High", "Low", "Close"]].iterrows()]
                             if include_price_series else []),
            "benchmark_omission": "No benchmark was declared for this bounded screening run.",
        }),
    )


def persist_screening_artifacts(*, persistence: PersistenceService, artifact_root: Path,
                                run_id: str, result: Any, portfolio: Any,
                                data: pd.DataFrame, config: ExperimentConfig,
                                parameter_row_id: str, namespace: str | None = None,
                                include_price_series: bool = True) -> None:
    for artifact_type, logical_name, document in _screening_artifacts(
        result=result, portfolio=portfolio, data=data, config=config,
        parameter_row_id=parameter_row_id, include_price_series=include_price_series,
    ):
        qualified_name = f"{namespace}/{logical_name}" if namespace else logical_name
        relative_path = f"state/artifacts/{run_id}/{qualified_name}.json"
        destination = artifact_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = (canonical_json(document) + "\n").encode("utf-8")
        staging = destination.with_suffix(".json.tmp")
        staging.write_bytes(content)
        staging.replace(destination)
        persistence.register_artifact(
            run_id=run_id, artifact_type=artifact_type, logical_name=qualified_name,
            media_type="application/json", format="json",
            location=relative_path, content=content,
        )


def persist_screening_price_series(*, persistence: PersistenceService,
                                   artifact_root: Path, run_id: str,
                                   data: pd.DataFrame, source_interval: str) -> None:
    """Persist one shared source-bar series for bounded configuration evidence."""
    logical_name = "screening_price_series"
    relative_path = f"state/artifacts/{run_id}/{logical_name}.json"
    document = {
        "source_interval": source_interval,
        "price_series": [
            {"timestamp": _artifact_value(index),
             **{key.lower(): _artifact_value(item[key]) for key in ("Open", "High", "Low", "Close")}}
            for index, item in data[["Open", "High", "Low", "Close"]].iterrows()
        ],
    }
    destination = artifact_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = (canonical_json(document) + "\n").encode("utf-8")
    staging = destination.with_suffix(".json.tmp")
    staging.write_bytes(content)
    staging.replace(destination)
    persistence.register_artifact(
        run_id=run_id, artifact_type=ArtifactType.EQUITY_CURVE,
        logical_name=logical_name, media_type="application/json", format="json",
        location=relative_path, content=content,
    )
