"""Reusable dashboard read models with lazy analytical imports.

Importing the lightweight operator UI must not initialize the backtesting and
market-data stack. Historical public exports remain available on first use.
"""

from typing import Any


__all__ = ["SelectedPortfolioData", "reconstruct_selected_portfolio"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from dashboard.adapter import SelectedPortfolioData, reconstruct_selected_portfolio

        return {
            "SelectedPortfolioData": SelectedPortfolioData,
            "reconstruct_selected_portfolio": reconstruct_selected_portfolio,
        }[name]
    raise AttributeError(name)
