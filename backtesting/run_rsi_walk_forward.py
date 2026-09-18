"""Run the RSI grid through deterministic rolling walk-forward evaluation."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.run_rsi_demo import EXPERIMENT_CONFIG  # noqa: E402
from backtesting.walk_forward import (  # noqa: E402
    WalkForwardConfig,
    execute_walk_forward,
)
from market_data import load_market_data  # noqa: E402

OUTPUT_PATH = PROJECT_ROOT / "results" / "rsi_spy_walk_forward.json"
WALK_FORWARD_CONFIG = WalkForwardConfig.rolling_default(
    experiment=EXPERIMENT_CONFIG,
    output_path=OUTPUT_PATH,
)


def main() -> None:
    market_data = load_market_data(EXPERIMENT_CONFIG.market_data)
    result = execute_walk_forward(
        WALK_FORWARD_CONFIG,
        market_data.data,
        market_data.audit,
    )
    print(
        f"Walk-forward folds: {result.total_fold_count} total, "
        f"{result.successful_fold_count} successful, "
        f"{result.failed_fold_count} failed"
    )
    print(f"Compounded OOS return: {result.compounded_return}")
    print(f"Endpoint maximum drawdown: {result.endpoint_max_drawdown}")
    print(f"Selected parameter sets: {result.unique_parameter_set_count}")
    print(f"Parameter change percentage: {result.parameter_change_percentage}")
    if result.failure_reasons:
        print("Failed folds:")
        for fold_id, reason in result.failure_reasons:
            print(f"  {fold_id}: {reason}")
    print(f"Saved walk-forward report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
