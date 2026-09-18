"""Human-readable dashboard formatting helpers."""

from numbers import Real
from typing import Any


def format_metric(name: str, value: Any) -> str:
    if value is None:
        return "—"
    if name in {"total_return", "annualized_return", "max_drawdown", "win_rate"}:
        return f"{float(value):.2%}"
    if name == "sharpe_ratio":
        return f"{float(value):.2f}"
    if name == "number_of_trades":
        return f"{int(value):,}"
    if isinstance(value, Real):
        return f"{float(value):,.2f}"
    return str(value)


def format_assumption(name: str, value: Any) -> str:
    if value is None:
        return "None"
    if name == "initial_cash":
        return f"${float(value):,.0f}"
    if name in {"fees", "slippage"}:
        return f"{float(value):.3%}"
    if name == "leverage":
        return f"{float(value):g}×"
    return str(value)
