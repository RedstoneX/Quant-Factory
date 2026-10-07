"""Focused evidence checks for Candidate screening artifacts."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from backtesting.experiments import ExecutionConfig, ExperimentConfig, MetricPolicy
from market_data import MarketDataConfig
from orchestration.candidate_screening_artifacts import _screening_artifacts


def test_metrics_artifact_persists_candidate_annualization() -> None:
    index = pd.date_range("2026-01-02 09:30", periods=3, freq="5min", tz="UTC")
    data = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
        },
        index=index,
    )
    row = {
        "parameter_row_id": "row-1",
        "total_return": 0.01,
        "annualized_return": 0.02,
        "sharpe_ratio": 0.5,
        "max_drawdown": -0.01,
        "number_of_trades": 1,
        "win_rate": 1.0,
    }
    config = ExperimentConfig(
        experiment_id="candidate",
        strategy_id="strategy",
        parameter_combinations=({},),
        market_data=MarketDataConfig(
            symbol="MES",
            provider="Databento",
            provider_implementation="verified_local_catalog:test",
            interval="5m",
            requested_start="2026-01-02",
            end_date_policy="fixed",
            adjusted=False,
            exchange_calendar="NYSE",
            market_timezone="America/New_York",
            cache_path=Path("unused.parquet"),
        ),
        execution=ExecutionConfig.next_bar_open(
            initial_cash=100_000,
            fees=0,
            slippage=0,
            direction="both",
            leverage=1,
            accumulate=False,
        ),
        ranking_columns=("total_return",),
        ranking_ascending=(False,),
        output_path=Path("unused.csv"),
        metric_policy=MetricPolicy(
            sampling="exchange_session_close",
            periods_per_year=252.0,
            risk_free_rate=0.0,
            basis="complete exchange-session-close portfolio equity and session returns",
            source="saved contract test",
        ),
    )
    records = pd.DataFrame(
        {"Entry Price": [100.5], "Exit Price": [102.5], "PnL": [2.0]}
    )
    portfolio = SimpleNamespace(
        trades=SimpleNamespace(records_readable=records),
        orders=SimpleNamespace(records_readable=pd.DataFrame({"Price": [100.5]})),
        value=pd.Series([100_000.0, 100_001.0, 100_002.0], index=index),
    )
    result = SimpleNamespace(
        ranked_results=pd.DataFrame([row]),
        strategy_id="strategy",
        strategy_version="1.0.0",
    )

    artifacts = _screening_artifacts(
        result=result,
        portfolio=portfolio,
        data=data,
        config=config,
        parameter_row_id="row-1",
    )
    metrics = next(document for _, name, document in artifacts if name == "metrics")

    assert metrics["annualization"] == {
        "sampling": "exchange_session_close",
        "sessions_per_year": 252,
        "risk_free_rate": 0.0,
        "basis": "complete exchange-session-close portfolio equity and session returns",
        "source": "saved contract test",
        "exchange_calendar": "NYSE",
    }
