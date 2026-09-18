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
    "idea_draft": {
        "source": "idea-draft-store.data",
        "owner": "dashboard.callbacks.ideas",
        "rule": "Ideas stores operator-authored text in the browser session only and never retrieves or executes it.",
    },
    "selected_configuration": {
        "source": "selected-configuration-state.data",
        "control": "configuration-selector.value",
        "owner": "dashboard.callbacks.backtest_results",
        "rule": "Set up writes the operator choice to one session store; Run test reads that identity without mutation or an automatic launch.",
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
        "rule": "Compare owns comparison selector options, selected cards, and comparison output.",
    },
}
