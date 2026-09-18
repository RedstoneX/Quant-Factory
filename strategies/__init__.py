"""Public strategy registry."""

from strategies.base import Strategy
from strategies.rsi_mean_reversion import RSI_MEAN_REVERSION_STRATEGY
from strategies.mes_opening_range_breakout import (
    MES_ORB_LONG_STRATEGY,
    MES_ORB_SHORT_STRATEGY,
)
from strategies.spy_donchian_trend_breakout import (
    SPY_DONCHIAN_LONG_STRATEGY,
    SPY_DONCHIAN_SHORT_STRATEGY,
)
from strategies.spym_rsi_mean_reversion_fixture import (
    SPYM_RSI_MEAN_REVERSION_FIXTURE_STRATEGY,
)
from strategies.parameter_governance import (
    PROVISIONAL_GRID_WARNING_THRESHOLD,
    ParameterGridContribution,
    ParameterPlanSummary,
    summarize_parameter_plan,
    validate_parameter_definition,
    validate_parameter_plan,
)


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        strategy_id = strategy.spec.identity.strategy_id
        if strategy_id in self._strategies:
            raise ValueError(f"Strategy ID already registered: {strategy_id}")
        self._strategies[strategy_id] = strategy

    def get(self, strategy_id: str) -> Strategy:
        try:
            return self._strategies[strategy_id]
        except KeyError as exc:
            raise KeyError(f"Unknown strategy ID: {strategy_id}") from exc


REGISTRY = StrategyRegistry()
REGISTRY.register(RSI_MEAN_REVERSION_STRATEGY)
REGISTRY.register(MES_ORB_LONG_STRATEGY)
REGISTRY.register(MES_ORB_SHORT_STRATEGY)
REGISTRY.register(SPY_DONCHIAN_LONG_STRATEGY)
REGISTRY.register(SPY_DONCHIAN_SHORT_STRATEGY)
REGISTRY.register(SPYM_RSI_MEAN_REVERSION_FIXTURE_STRATEGY)


def get_strategy(strategy_id: str) -> Strategy:
    """Return the strategy registered under a stable ID."""
    return REGISTRY.get(strategy_id)


__all__ = [
    "PROVISIONAL_GRID_WARNING_THRESHOLD",
    "ParameterGridContribution",
    "ParameterPlanSummary",
    "Strategy",
    "StrategyRegistry",
    "get_strategy",
    "summarize_parameter_plan",
    "validate_parameter_definition",
    "validate_parameter_plan",
]
