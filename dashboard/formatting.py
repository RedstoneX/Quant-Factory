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


def format_percent(value: Any) -> str:
    """A fraction as a percent without trailing zeros, e.g. 0.0173 -> 1.73%, 0.35 -> 35%, 1 -> 100%."""
    if value is None:
        return "—"
    text = f"{float(value) * 100:.2f}".rstrip("0").rstrip(".")
    return f"{'0' if text in {'-0', ''} else text}%"


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


def format_money(value: Any) -> str:
    """Dollars with two decimals and a sign on losses, e.g. $64.44 or -$18.98."""
    if value is None:
        return "—"
    amount = round(float(value), 2) + 0.0
    return f"-${abs(amount):,.2f}" if amount < 0 else f"${amount:,.2f}"


def profit_factor(profits: Any) -> float | None:
    """Gross profit divided by gross loss; None when there is no loss to divide by."""
    numbers = [float(item) for item in profits if item is not None]
    loss = -sum(item for item in numbers if item < 0)
    return sum(item for item in numbers if item > 0) / loss if loss > 0 else None
