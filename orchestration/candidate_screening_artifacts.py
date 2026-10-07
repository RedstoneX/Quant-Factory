"""Durable, same-portfolio evidence for one fixed Candidate screening run."""

from __future__ import annotations

import math
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.experiments import ExperimentConfig
from persistence import ArtifactType, PersistenceService, canonical_json

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
                         config: ExperimentConfig, parameter_row_id: str) -> tuple[tuple[ArtifactType, str, dict[str, Any]], ...]:
    """Serialize the screened portfolio itself, never a second simulation."""
    if len(result.ranked_results) != 1:
        raise RuntimeError("single-configuration screening must produce one ranked row")
    row = result.ranked_results.iloc[0]
    if row["parameter_row_id"] != parameter_row_id:
        raise RuntimeError("screening portfolio does not match the ranked parameter row")
    trades = portfolio.trades.records_readable
    orders = portfolio.orders.records_readable
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
    value = portfolio.value
    if isinstance(value, pd.DataFrame):
        if value.shape[1] != 1:
            raise RuntimeError("expected one-column portfolio equity series")
        value = value.iloc[:, 0]
    return (
        (ArtifactType.RUN_SUMMARY, "run_summary", {
            "strategy_id": result.strategy_id, "strategy_version": result.strategy_version,
            "selected_parameter_row_id": parameter_row_id, "selected_ranking_position": 1,
            "evidence_classification": "Development screening evidence only; not independent, protected, or edge proof",
            "promotion_eligible": False, "broker_orders": "disabled",
        }),
        (ArtifactType.METRICS, "metrics", {
            "parameter_row_id": parameter_row_id, "ranking_position": 1,
            "metrics": metrics, "annualization": annualization,
        }),
        (ArtifactType.TRADES_OR_ORDERS, "trades_and_orders", {
            "parameter_row_id": parameter_row_id, "ranking_position": 1,
            "instrument": config.market_data.symbol, "price_unit": price_unit,
            "pnl_unit": "USD", "price_multiplier": multiplier,
            "price_normalization": "Trade and order price fields are divided by the execution multiplier for display against source bars; monetary fields are unchanged.",
            "trades": _artifact_records(trades, price_multiplier=multiplier),
            "orders": _artifact_records(orders, price_multiplier=multiplier),
        }),
        (ArtifactType.EQUITY_CURVE, "equity_curve", {
            "parameter_row_id": parameter_row_id, "ranking_position": 1,
            "equity_curve": [{"timestamp": _artifact_value(index), "value": _artifact_value(item)} for index, item in value.items()],
            "price_series": [{"timestamp": _artifact_value(index),
                              **{key.lower(): _artifact_value(item[key]) for key in ("Open", "High", "Low", "Close")}}
                             for index, item in data[["Open", "High", "Low", "Close"]].iterrows()],
            "benchmark_omission": "No benchmark was declared for this bounded screening run.",
        }),
    )


def persist_screening_artifacts(*, persistence: PersistenceService, artifact_root: Path,
                                run_id: str, result: Any, portfolio: Any,
                                data: pd.DataFrame, config: ExperimentConfig,
                                parameter_row_id: str) -> None:
    for artifact_type, logical_name, document in _screening_artifacts(
        result=result, portfolio=portfolio, data=data, config=config,
        parameter_row_id=parameter_row_id,
    ):
        relative_path = f"state/artifacts/{run_id}/{logical_name}.json"
        destination = artifact_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = (canonical_json(document) + "\n").encode("utf-8")
        staging = destination.with_suffix(".json.tmp")
        staging.write_bytes(content)
        staging.replace(destination)
        persistence.register_artifact(
            run_id=run_id, artifact_type=artifact_type, logical_name=logical_name,
            media_type="application/json", format="json",
            location=relative_path, content=content,
        )
