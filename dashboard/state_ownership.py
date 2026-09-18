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
    "navigation_drawer": {
        "source": "navigation-drawer-state.data",
        "owner": "dashboard.callbacks.routing",
        "rule": "An explicit menu-button click toggles the responsive drawer; every primary-navigation selection or pathname change closes it without rebuilding navigation or writing the URL.",
    },
    "idea_draft": {
        "source": "idea-draft-store.data",
        "owner": "dashboard.callbacks.ideas",
        "rule": "Ideas stores operator-authored text in the browser session only and never retrieves or executes it.",
    },
    "selected_configuration": {
        "source": "selected-configuration-state.data",
        "control": "configuration-selector.value",
        "owner": "dashboard.callbacks.setup",
        "rule": "Set up writes the operator choice to one session store; Run test reads that identity without mutation or an automatic launch.",
    },
    "run_test_launch": {
        "source": "run-test-launch-state.data",
        "owner": "dashboard.callbacks.backtest_results",
        "rule": "Run test owns one session launch key bound to its immutable configuration; submitted keys are never rebound and persisted submission state is authoritative.",
    },
    "selected_backtest": {
        "source": "selected-run-selector.value",
        "store": "selected-run-state.data",
        "owner": "dashboard.callbacks.backtest_results",
        "rule": "Explicit selector changes win over passive refresh and hydration callbacks.",
    },
    "historical_relaunch": {
        "source": "historical-launch-state.data",
        "owner": "dashboard.callbacks.backtest_results",
        "rule": "Results owns a distinct historical-relaunch key bound to the selected source run; it never shares reproduction or Run test state.",
    },
    "reproduction_launch": {
        "source": "reproduction-launch-state.data",
        "owner": "dashboard.callbacks.backtest_results",
        "rule": "Results owns a distinct reproduction key bound to the selected source run; submitted keys remain immutable across refresh and retry delivery.",
    },
    "review_selection": {
        "source": "selected-run-state.data",
        "owner": "dashboard.callbacks.results_review",
        "rule": "Results binds durable-review form state and messages to the shared selected persisted run; no separate review identity is written.",
    },
    "comparison_selection": {
        "source": "comparison-run-selector.value",
        "owner": "dashboard.callbacks.compare_backtests",
        "rule": "Compare owns comparison selector options, selected cards, and comparison output.",
    },
}
