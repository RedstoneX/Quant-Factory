"""Run the RSI experiment through chronological out-of-sample evaluation."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.out_of_sample import (  # noqa: E402
    ChronologicalSplitConfig,
    OutOfSampleConfig,
    execute_out_of_sample,
)
from backtesting.run_rsi_demo import EXPERIMENT_CONFIG  # noqa: E402
from market_data import load_market_data  # noqa: E402

OUTPUT_PATH = PROJECT_ROOT / "results" / "rsi_spy_oos.json"
OOS_CONFIG = OutOfSampleConfig(
    experiment=EXPERIMENT_CONFIG,
    split=ChronologicalSplitConfig(
        train_fraction=0.60,
        selection_fraction=0.20,
        test_fraction=0.20,
        minimum_rows_per_partition=30,
    ),
    output_path=OUTPUT_PATH,
    shortlist_size=5,
)


def main() -> None:
    market_data = load_market_data(EXPERIMENT_CONFIG.market_data)
    result = execute_out_of_sample(OOS_CONFIG, market_data.data, market_data.audit)
    split = result.split
    print(
        "Chronological split: "
        f"train {split.train.start}..{split.train.end} ({split.train.row_count}), "
        f"selection {split.selection.start}..{split.selection.end} "
        f"({split.selection.row_count}), test {split.test.start}..{split.test.end} "
        f"({split.test.row_count})"
    )
    print(f"Locked parameters: {result.selected_parameters}")
    print(f"Parameter lock: {result.parameter_lock.lock_id}")
    print("Held-out test metrics:")
    print(result.test_result.ranked_results.to_string(index=False))
    print(f"Saved out-of-sample report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
