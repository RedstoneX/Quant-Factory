"""Run the approved exploratory MES five-minute opening-range experiment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.experiments import ExecutionConfig, ExperimentConfig, execute_experiment  # noqa: E402
from backtesting.screening import ScreeningConfig  # noqa: E402
from market_data import (  # noqa: E402
    DataAudit,
    MarketDataConfig,
    load_data_locations,
    load_dataset_manifest,
    verify_dataset_file,
)
from strategies.mes_opening_range_breakout import build_parameter_grid  # noqa: E402

DATASET_ID = "futures_MES_5m_databento"
RESULT_PATH = PROJECT_ROOT / "results" / "mes_orb_5m_exploratory.csv"
INITIAL_CASH = 100_000.0
IBKR_COMMISSION_PER_CONTRACT_PER_SIDE = 0.25
CME_EXCHANGE_FEE_PER_CONTRACT_PER_SIDE = 0.35
NFA_REGULATORY_FEE_PER_CONTRACT_PER_SIDE = 0.02
MANDATORY_CLEARING_FEE_PER_CONTRACT_PER_SIDE = 0.0
ALL_IN_FEE_PER_CONTRACT_PER_SIDE = 0.62
COST_STATUS = "confirmed_ibkr_nonmember_standard_routing"
ROLL_STATUS = "confirmed_mes_c_0_calendar_front_expiry_unadjusted"
PARAMETER_COMBINATIONS = build_parameter_grid()
SCENARIO_SLIPPAGE_TICKS = {
    "baseline": 1.0,
    "optimistic": 0.5,
    "stress": 2.0,
}


def result_path(scenario: str) -> Path:
    if scenario == "baseline":
        return RESULT_PATH
    return PROJECT_ROOT / "results" / f"mes_orb_5m_{scenario}.csv"


def load_mes_data() -> tuple[pd.DataFrame, DataAudit, dict[str, object]]:
    """Load and cryptographically verify the cataloged local MES dataset."""
    manifest = load_dataset_manifest(DATASET_ID)
    locations = load_data_locations()
    path = verify_dataset_file(manifest, locations)
    frame = pd.read_parquet(path)
    timestamp_field = str(manifest.metadata["timestamp_field"])
    if timestamp_field in frame.columns:
        frame = frame.set_index(timestamp_field)
    frame.index = pd.DatetimeIndex(frame.index).tz_convert("UTC")
    frame = frame.rename(columns={name: name.title() for name in ("open", "high", "low", "close", "volume")})
    frame = frame.loc[:, ["Open", "High", "Low", "Close", "Volume"]]
    warnings = [
        "Contract series is confirmed as unadjusted Databento MES.c.0; calendar-roll discontinuities remain and must not be treated as market returns.",
        "Costs assume standard non-member IBKR routing at no more than 1,000 E-micro contracts per month.",
    ]
    audit = DataAudit(
        cache_schema_version=1,
        symbol=manifest.symbol,
        provider=manifest.provider,
        provider_implementation="verified local catalog manifest",
        interval=manifest.timeframe,
        requested_start=str(manifest.metadata["earliest_timestamp"]),
        requested_dynamic_end_policy="Fixed extent of the cataloged legacy dataset",
        latest_completed_exchange_session=frame.index[-1].date().isoformat(),
        prices_adjusted=False,
        adjustment_verification=(
            "Confirmed Databento MES.c.0 calendar/front-expiry rank zero; "
            "prices are original and unadjusted"
        ),
        download_time=str(manifest.metadata["imported_at_utc"]),
        download_timezone="UTC",
        actual_first_row_date=frame.index[0].isoformat(),
        actual_last_row_date=frame.index[-1].isoformat(),
        row_count=len(frame),
        duplicate_timestamp_count=int(frame.index.duplicated().sum()),
        missing_open_count=int(frame["Open"].isna().sum()),
        missing_high_count=int(frame["High"].isna().sum()),
        missing_low_count=int(frame["Low"].isna().sum()),
        missing_close_count=int(frame["Close"].isna().sum()),
        missing_volume_count=int(frame["Volume"].isna().sum()),
        expected_session_gap_count=0,
        unexpected_session_gaps=[],
        provider_warnings=warnings,
        cache_path=str(manifest.canonical_relative_path),
        cache_action="verified and reused",
        cache_decision_reason=f"SHA-256 matched manifest {manifest.sha256}",
    )
    return frame, audit, manifest.metadata


def _config(direction: str, scenario: str = "baseline") -> ExperimentConfig:
    if scenario not in SCENARIO_SLIPPAGE_TICKS:
        raise ValueError(f"Unsupported MES execution scenario: {scenario}")
    strategy_direction = "long" if direction == "longonly" else "short"
    market = MarketDataConfig(
        symbol="MES",
        provider="Databento",
        provider_implementation="verified local catalog manifest",
        interval="5m",
        requested_start="catalog extent",
        end_date_policy="catalog extent",
        adjusted=False,
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        cache_path=Path("futures/MES/5m/MES_5m_databento.parquet"),
    )
    return ExperimentConfig(
        experiment_id=f"mes_5m_orb_{strategy_direction}_{scenario}",
        strategy_id=f"mes_opening_range_breakout_{strategy_direction}",
        parameter_combinations=PARAMETER_COMBINATIONS,
        market_data=market,
        execution=ExecutionConfig.next_bar_open(
            initial_cash=INITIAL_CASH,
            fees=0.0,
            slippage=0.0,
            direction=direction,
            accumulate=False,
            leverage=1.0,
            position_sizing="fixed_units",
            order_size=1.0,
            price_multiplier=5.0,
            fixed_fee_per_contract_per_side=ALL_IN_FEE_PER_CONTRACT_PER_SIDE,
            slippage_ticks=SCENARIO_SLIPPAGE_TICKS[scenario],
            tick_size=0.25,
        ),
        ranking_columns=("total_return", "sharpe_ratio"),
        ranking_ascending=(False, False),
        output_path=result_path(scenario),
        screening=ScreeningConfig.provisional_defaults(),
    )


def run_experiment(
    scenario: str = "baseline", *, write_output: bool = True
) -> pd.DataFrame:
    """Evaluate exactly 15 long and 15 short variants and rank them together."""
    data, audit, manifest = load_mes_data()
    timestamp = datetime.now(timezone.utc).isoformat()
    frames: list[pd.DataFrame] = []
    for direction in ("longonly", "shortonly"):
        result = execute_experiment(
            _config(direction, scenario),
            data,
            audit,
            run_timestamp=timestamp,
            write_output=False,
        )
        frame = result.ranked_results.copy()
        frame.insert(0, "direction_variant", direction)
        frames.append(frame)
    ranked = pd.concat(frames, ignore_index=True)
    ranked["dataset_id"] = DATASET_ID
    ranked["dataset_sha256"] = manifest["sha256"]
    ranked["cost_status"] = COST_STATUS
    ranked["execution_scenario"] = scenario
    ranked["ibkr_commission_per_contract_per_side"] = IBKR_COMMISSION_PER_CONTRACT_PER_SIDE
    ranked["cme_exchange_fee_per_contract_per_side"] = CME_EXCHANGE_FEE_PER_CONTRACT_PER_SIDE
    ranked["nfa_regulatory_fee_per_contract_per_side"] = NFA_REGULATORY_FEE_PER_CONTRACT_PER_SIDE
    ranked["mandatory_clearing_fee_per_contract_per_side"] = MANDATORY_CLEARING_FEE_PER_CONTRACT_PER_SIDE
    ranked["all_in_fee_per_contract_per_side"] = ALL_IN_FEE_PER_CONTRACT_PER_SIDE
    ranked["roll_method_status"] = ROLL_STATUS
    ranked["promotion_eligible"] = False
    ranked["promotion_status"] = (
        "blocked_no_unseen_evidence_and_unadjusted_roll_discontinuities"
    )
    ranked["_screening_order"] = ranked["screening_status"].map({"passed": 0, "screened_out": 1})
    ranked = ranked.sort_values(
        ["_screening_order", "total_return", "sharpe_ratio", "range_minutes", "breakout_offset_ticks", "direction_variant"],
        ascending=[True, False, False, True, True, True],
        kind="mergesort",
    ).drop(columns="_screening_order").reset_index(drop=True)
    if len(ranked) != 30:
        raise RuntimeError(f"Expected exactly 30 MES ORB variants, got {len(ranked)}")
    if write_output:
        output_path = result_path(scenario)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ranked.to_csv(output_path, index=False)
    return ranked


def _print_summary(scenario: str, ranked: pd.DataFrame) -> None:
    print(f"MES 5-minute ORB {scenario} cost screen")
    print(f"Evaluated: {len(ranked)} (15 long-only, 15 short-only)")
    print(f"Passed cheap screen: {(ranked['screening_status'] == 'passed').sum()}")
    print(ranked.loc[:, ["direction_variant", "range_minutes", "breakout_offset_ticks", "total_return", "sharpe_ratio", "max_drawdown", "number_of_trades", "screening_status"]].head(10).to_string(index=False))
    print(f"Saved {result_path(scenario)}")
    print(
        "Promotion blocked: the inspected extent is development/reference evidence "
        "and unadjusted calendar-roll discontinuities remain a limitation."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=(*SCENARIO_SLIPPAGE_TICKS, "all"),
        default="baseline",
    )
    args = parser.parse_args()
    scenarios = tuple(SCENARIO_SLIPPAGE_TICKS) if args.scenario == "all" else (args.scenario,)
    for scenario in scenarios:
        _print_summary(scenario, run_experiment(scenario))


if __name__ == "__main__":
    main()
