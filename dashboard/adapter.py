"""Selected-portfolio adapter for dashboard views."""

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pandas as pd

from backtesting.experiments import ExperimentConfig, build_portfolio, extract_metrics
from market_data import DataAudit
from strategies import get_strategy


@dataclass(frozen=True)
class SelectedPortfolioData:
    equity: pd.Series
    drawdown: pd.Series
    metrics: dict[str, float | int]
    strategy_identity: dict[str, str]
    provenance: dict[str, Any]
    execution_assumptions: dict[str, Any]
    normalized_parameters: dict[str, Any]


def _as_series(value: pd.Series | pd.DataFrame, name: str) -> pd.Series:
    if isinstance(value, pd.DataFrame):
        if value.shape[1] != 1:
            raise ValueError(f"Expected one {name} series; got {value.shape[1]}")
        value = value.iloc[:, 0]
    return value.rename(name)


def reconstruct_selected_portfolio(
    config: ExperimentConfig,
    data: pd.DataFrame,
    audit: DataAudit,
    parameters: Mapping[str, Any],
) -> SelectedPortfolioData:
    """Reconstruct one selected strategy portfolio without rerunning its grid."""
    strategy = get_strategy(config.strategy_id)
    normalized = strategy.validate_parameters(parameters)
    signals = strategy.generate_signals(data, normalized)
    portfolio = build_portfolio(data, signals, config)
    execution = config.execution

    return SelectedPortfolioData(
        equity=_as_series(portfolio.value, "Equity"),
        drawdown=_as_series(portfolio.drawdown, "Drawdown"),
        metrics=extract_metrics(portfolio),
        strategy_identity={
            "strategy_id": strategy.spec.identity.strategy_id,
            "name": strategy.spec.identity.name,
            "version": strategy.spec.identity.version,
            "family": strategy.spec.identity.family,
        },
        provenance={
            "provider": audit.provider,
            "start_date": audit.actual_first_row_date,
            "end_date": audit.actual_last_row_date,
            "prices_adjusted": audit.prices_adjusted,
            "row_count": audit.row_count,
        },
        execution_assumptions={
            "execution_mode": execution.mode,
            "signal_timing": execution.signal_timing,
            "signal_timing_label": execution.signal_timing_label,
            "execution_timing": execution.execution_timing,
            "execution_timing_label": execution.execution_timing_label,
            "execution_price": execution.execution_price_field,
            "initial_cash": execution.initial_cash,
            "fees": execution.fees,
            "slippage": execution.slippage,
            "position_sizing": execution.position_sizing,
            "direction": execution.direction,
            "leverage": execution.leverage,
            "accumulate": execution.accumulate,
            "strategy": asdict(strategy.spec.assumptions),
        },
        normalized_parameters=dict(normalized),
    )
