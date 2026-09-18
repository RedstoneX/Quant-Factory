"""Run the approved six-variant SPY daily Donchian baseline screen."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.experiments import ExecutionConfig, ExperimentConfig, execute_experiment  # noqa: E402
from backtesting.screening import ScreeningConfig  # noqa: E402
from market_data import MarketDataConfig, load_market_data  # noqa: E402
from strategies.spy_donchian_trend_breakout import build_parameter_grid  # noqa: E402

INITIAL_CASH = 10_000.0
FEES = 0.0005
SLIPPAGE = 0.0002
RESULT_PATH = PROJECT_ROOT / "results" / "spy_donchian_baseline.csv"
DATA_CONFIG = MarketDataConfig(
    symbol="SPY",
    provider="Yahoo Finance",
    provider_implementation="vectorbtpro.YFData.pull",
    interval="1 day",
    requested_start="2016-01-01",
    end_date_policy=(
        "Latest fully completed NYSE session that Yahoo Finance returned with "
        "complete daily OHLCV"
    ),
    adjusted=True,
    exchange_calendar="NYSE",
    market_timezone="America/New_York",
    cache_path=PROJECT_ROOT / "data" / "cache" / "spy_2016_dynamic_adjusted.csv",
    legacy_cache_paths=(
        PROJECT_ROOT
        / "data"
        / "cache"
        / "spy_2018-01-01_2025-12-31_adjusted.csv",
    ),
)
PARAMETER_COMBINATIONS = build_parameter_grid()


def _config(direction: str, output_path: Path = RESULT_PATH) -> ExperimentConfig:
    if direction not in {"longonly", "shortonly"}:
        raise ValueError(f"Unsupported Donchian direction: {direction}")
    strategy_direction = "long" if direction == "longonly" else "short"
    return ExperimentConfig(
        experiment_id=f"spy_donchian_daily_{strategy_direction}_baseline",
        strategy_id=f"spy_donchian_trend_breakout_{strategy_direction}",
        parameter_combinations=PARAMETER_COMBINATIONS,
        market_data=DATA_CONFIG,
        execution=ExecutionConfig.next_bar_open(
            initial_cash=INITIAL_CASH,
            fees=FEES,
            slippage=SLIPPAGE,
            direction=direction,
            accumulate=False,
            leverage=1.0,
        ),
        ranking_columns=("total_return", "sharpe_ratio"),
        ranking_ascending=(False, False),
        output_path=output_path,
        screening=ScreeningConfig.provisional_defaults(),
    )


def run_baseline_screen(*, write_output: bool = True) -> pd.DataFrame:
    """Evaluate exactly three long and three short approved Donchian variants."""
    market_data = load_market_data(DATA_CONFIG)
    timestamp = datetime.now(timezone.utc).isoformat()
    frames: list[pd.DataFrame] = []
    for direction in ("longonly", "shortonly"):
        result = execute_experiment(
            _config(direction),
            market_data.data,
            market_data.audit,
            run_timestamp=timestamp,
            write_output=False,
        )
        frame = result.ranked_results.copy()
        frame.insert(0, "direction_variant", direction)
        frames.append(frame)

    ranked = pd.concat(frames, ignore_index=True)
    ranked["_screening_order"] = ranked["screening_status"].map(
        {"passed": 0, "screened_out": 1}
    )
    ranked = ranked.sort_values(
        [
            "_screening_order",
            "total_return",
            "sharpe_ratio",
            "entry_lookback",
            "exit_lookback",
            "direction_variant",
        ],
        ascending=[True, False, False, True, True, True],
        kind="mergesort",
    ).drop(columns="_screening_order").reset_index(drop=True)
    ranked["promotion_status"] = ranked["screening_status"].map(
        {
            "passed": "baseline_survivor_pending_user_approval",
            "screened_out": "rejected_by_baseline_cheap_screen",
        }
    )
    if len(ranked) != 6:
        raise RuntimeError(f"Expected exactly 6 SPY Donchian variants, got {len(ranked)}")
    if write_output:
        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ranked.to_csv(RESULT_PATH, index=False)
    return ranked


def main() -> None:
    ranked = run_baseline_screen()
    passed = int((ranked["screening_status"] == "passed").sum())
    print("SPY daily Donchian baseline cheap screen")
    print(f"Evaluated: {len(ranked)} variants")
    print(f"Passed cheap screen: {passed}")
    print(
        ranked.loc[
            :,
            [
                "direction_variant",
                "entry_lookback",
                "exit_lookback",
                "total_return",
                "annualized_return",
                "sharpe_ratio",
                "max_drawdown",
                "number_of_trades",
                "win_rate",
                "screening_status",
            ],
        ].to_string(index=False)
    )
    print(f"Saved {RESULT_PATH}")
    if passed == 0:
        print("Decision: all six variants rejected by the baseline cheap screen.")
    else:
        print("Decision: survivor set recorded; stop for user approval.")


if __name__ == "__main__":
    main()
