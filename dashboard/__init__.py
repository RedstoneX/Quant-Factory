"""Local visual decision dashboard."""

from typing import Any

from dashboard.adapter import SelectedPortfolioData, reconstruct_selected_portfolio

__all__ = ["SelectedPortfolioData", "create_app", "reconstruct_selected_portfolio"]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from dashboard.app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
