"""Comparison helpers for explicit experiment execution models."""

from typing import Any

import pandas as pd

from backtesting.experiments import ExperimentResult

COMPARISON_METRICS = (
    "total_return",
    "annualized_return",
    "sharpe_ratio",
    "max_drawdown",
    "number_of_trades",
)


def build_execution_comparison(
    same_bar: ExperimentResult,
    next_bar: ExperimentResult,
) -> pd.DataFrame:
    """Compare top results and the top-five parameter ordering."""
    parameter_columns = [
        column
        for column in same_bar.ranked_results.columns
        if column not in {
            *COMPARISON_METRICS,
            "win_rate",
            "data_source",
            "prices_adjusted",
            "data_start_date",
            "data_end_date",
            "row_count",
            "execution_mode",
            "signal_timing",
            "execution_timing",
            "execution_price",
            "initial_cash",
            "fees",
            "slippage",
            "position_sizing",
            "direction",
            "leverage",
            "accumulate",
            "validation_status",
            "validation_gate_count",
            "parameter_row_id",
            "screening_status",
            "screening_passed_rule_count",
            "screening_failed_rule_count",
            "screening_rejection_reasons",
        }
    ]
    old_top = same_bar.ranked_results.iloc[0]
    new_top = next_bar.ranked_results.iloc[0]
    values: dict[str, Any] = {
        "old_mode": same_bar.execution_assumptions["execution_mode"],
        "new_mode": next_bar.execution_assumptions["execution_mode"],
    }
    for column in parameter_columns:
        values[f"old_{column}"] = old_top[column]
        values[f"new_{column}"] = new_top[column]
    for metric in COMPARISON_METRICS:
        values[f"old_{metric}"] = old_top[metric]
        values[f"new_{metric}"] = new_top[metric]
        values[f"change_{metric}"] = new_top[metric] - old_top[metric]

    old_order = same_bar.ranked_results.loc[:, parameter_columns].head(5)
    new_order = next_bar.ranked_results.loc[:, parameter_columns].head(5)
    values["top_five_ranking_changed"] = not old_order.equals(new_order)
    return pd.DataFrame([values])


def format_execution_comparison(comparison: pd.DataFrame) -> str:
    row = comparison.iloc[0]
    return "\n".join(
        [
            "\nExecution model comparison:",
            (
                f"  Same-bar close top: window={int(row['old_rsi_window'])}, "
                f"entry={int(row['old_entry_threshold'])}, "
                f"exit={int(row['old_exit_threshold'])}"
            ),
            (
                f"  Next-bar open top: window={int(row['new_rsi_window'])}, "
                f"entry={int(row['new_entry_threshold'])}, "
                f"exit={int(row['new_exit_threshold'])}"
            ),
            f"  Total return change: {row['change_total_return']:.2%}",
            f"  Annualized return change: {row['change_annualized_return']:.2%}",
            f"  Sharpe ratio change: {row['change_sharpe_ratio']:.3f}",
            f"  Maximum drawdown change: {row['change_max_drawdown']:.2%}",
            f"  Trade count change: {int(row['change_number_of_trades'])}",
            (
                "  Top-five ranking changed: "
                + ("Yes" if row["top_five_ranking_changed"] else "No")
            ),
        ]
    )
