"""Configure and run the Quant Factory RSI demonstration."""

from pathlib import Path
import sys
from dataclasses import replace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.execution_comparison import (  # noqa: E402
    build_execution_comparison,
    format_execution_comparison,
)
from backtesting.experiments import (  # noqa: E402
    ExecutionConfig,
    ExperimentConfig,
    execute_experiment,
)
from backtesting.experiments.runner import format_experiment_summary  # noqa: E402
from backtesting.screening import ScreeningConfig  # noqa: E402
from market_data import MarketDataConfig, load_market_data  # noqa: E402
from strategies.rsi_mean_reversion import build_parameter_grid  # noqa: E402

INITIAL_CASH = 10_000
FEES = 0.0005
SLIPPAGE = 0.0002
RESULT_PATH = PROJECT_ROOT / "results" / "rsi_spy_demo.csv"
COMPARISON_PATH = PROJECT_ROOT / "results" / "rsi_spy_execution_comparison.csv"
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

PARAMETER_COMBINATIONS = tuple(
    {
        "window": window,
        "entry_threshold": entry_threshold,
        "exit_threshold": exit_threshold,
    }
    for window, entry_threshold, exit_threshold in build_parameter_grid()
)

EXPERIMENT_CONFIG = ExperimentConfig(
    experiment_id="rsi_spy_daily_demo",
    strategy_id="rsi_mean_reversion",
    parameter_combinations=PARAMETER_COMBINATIONS,
    market_data=DATA_CONFIG,
    execution=ExecutionConfig.next_bar_open(
        initial_cash=INITIAL_CASH,
        fees=FEES,
        slippage=SLIPPAGE,
        direction="longonly",
        accumulate=False,
        leverage=1.0,
    ),
    ranking_columns=("total_return", "sharpe_ratio"),
    ranking_ascending=(False, False),
    output_path=RESULT_PATH,
    screening=ScreeningConfig.provisional_defaults(),
    parameter_output_names=(("window", "rsi_window"),),
)

SAME_BAR_COMPARISON_CONFIG = replace(
    EXPERIMENT_CONFIG,
    experiment_id="rsi_spy_daily_same_bar_close_comparison",
    execution=ExecutionConfig.same_bar_close(
        initial_cash=INITIAL_CASH,
        fees=FEES,
        slippage=SLIPPAGE,
        direction="longonly",
        accumulate=False,
        leverage=1.0,
    ),
)


def main() -> None:
    market_data = load_market_data(DATA_CONFIG)
    result = execute_experiment(
        EXPERIMENT_CONFIG,
        market_data.data,
        market_data.audit,
    )
    same_bar = execute_experiment(
        SAME_BAR_COMPARISON_CONFIG,
        market_data.data,
        market_data.audit,
        write_output=False,
    )
    comparison = build_execution_comparison(same_bar, result)
    COMPARISON_PATH.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(COMPARISON_PATH, index=False)
    print(format_experiment_summary(result, RESULT_PATH))
    print(format_execution_comparison(comparison))
    print(f"Saved execution comparison to {COMPARISON_PATH}")


if __name__ == "__main__":
    main()
