"""Authoritative dashboard UI state ownership.

ADR 0008 requires one owner for each browser-visible state value so delayed
hydration callbacks cannot compete with explicit operator choices.
"""

from __future__ import annotations


STATE_OWNERS = {
    "active_route": {
        "source": "url.pathname",
        "owner": "dashboard.callbacks.routing",
        "rule": "Route callbacks only derive visibility and navigation classes; no callback writes the URL.",
    },
    "selected_backtest": {
        "source": "selected-run-selector.value",
        "store": "selected-run-state.data",
        "owner": "dashboard.callbacks.backtest_results",
        "rule": "Explicit selector changes win over passive refresh and hydration callbacks.",
    },
    "review_selection": {
        "source": "review-run-selector.value",
        "store": "selected-review-identity.data",
        "owner": "dashboard.callbacks.strategy_review",
        "rule": "Strategy Review owns durable-review identity, form state, and review messages.",
    },
    "comparison_selection": {
        "source": "comparison-run-selector.value",
        "owner": "dashboard.callbacks.compare_backtests",
        "rule": "Compare Backtests owns comparison selector options, selected cards, and comparison output.",
    },
}
