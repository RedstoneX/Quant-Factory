"""Run chronological OOS evaluation for approved SPY Donchian survivors."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.experiments import ExperimentConfig  # noqa: E402
from backtesting.out_of_sample import (  # noqa: E402
    ChronologicalSplitConfig,
    OutOfSampleConfig,
    OutOfSampleProgressionError,
    execute_out_of_sample,
)
from backtesting.run_spy_donchian import (  # noqa: E402
    DATA_CONFIG,
    RESULT_PATH as BASELINE_RESULT_PATH,
    _config as baseline_config,
)
from market_data import load_market_data  # noqa: E402

OUTPUT_PATH = PROJECT_ROOT / "results" / "spy_donchian_oos.json"
APPROVED_SURVIVOR_PARAMETERS = (
    {"entry_lookback": 20, "exit_lookback": 10},
    {"entry_lookback": 55, "exit_lookback": 20},
    {"entry_lookback": 55, "exit_lookback": 10},
)

EXPERIMENT_CONFIG = ExperimentConfig(
    experiment_id="spy_donchian_daily_long_oos",
    strategy_id="spy_donchian_trend_breakout_long",
    parameter_combinations=APPROVED_SURVIVOR_PARAMETERS,
    market_data=DATA_CONFIG,
    execution=baseline_config("longonly").execution,
    ranking_columns=("total_return", "sharpe_ratio"),
    ranking_ascending=(False, False),
    output_path=BASELINE_RESULT_PATH,
    screening=baseline_config("longonly").screening,
)

OOS_CONFIG = OutOfSampleConfig(
    experiment=EXPERIMENT_CONFIG,
    split=ChronologicalSplitConfig(
        train_fraction=0.60,
        selection_fraction=0.20,
        test_fraction=0.20,
        minimum_rows_per_partition=30,
    ),
    output_path=OUTPUT_PATH,
    shortlist_size=3,
)


def main() -> None:
    market_data = load_market_data(EXPERIMENT_CONFIG.market_data)
    try:
        result = execute_out_of_sample(OOS_CONFIG, market_data.data, market_data.audit)
    except OutOfSampleProgressionError as exc:
        print(f"Out-of-sample progression stopped: {exc}")
        print(f"Saved out-of-sample failure report to {OUTPUT_PATH}")
        return
    split = result.split
    print(
        "Chronological split: "
        f"train {split.train.start}..{split.train.end} ({split.train.row_count}), "
        f"selection {split.selection.start}..{split.selection.end} "
        f"({split.selection.row_count}), test {split.test.start}..{split.test.end} "
        f"({split.test.row_count})"
    )
    print(f"Starting candidates: {len(APPROVED_SURVIVOR_PARAMETERS)}")
    print(f"Training shortlist: {result.shortlist_parameters}")
    print(f"Locked parameters: {result.selected_parameters}")
    print(f"Parameter lock: {result.parameter_lock.lock_id}")
    print("Held-out test metrics:")
    print(result.test_result.ranked_results.to_string(index=False))
    print(f"Saved out-of-sample report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
