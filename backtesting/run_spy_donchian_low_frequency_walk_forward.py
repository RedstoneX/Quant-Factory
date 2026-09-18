"""Run bounded low-frequency walk-forward evidence for SPY Donchian 20/10."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.experiments import ExperimentConfig  # noqa: E402
from backtesting.run_spy_donchian import (  # noqa: E402
    DATA_CONFIG,
    RESULT_PATH as BASELINE_RESULT_PATH,
    _config as baseline_config,
)
from backtesting.walk_forward import WalkForwardConfig  # noqa: E402
from backtesting.walk_forward.low_frequency import (  # noqa: E402
    LowFrequencyEvidenceConfig,
    LowFrequencyEvidenceResult,
    execute_low_frequency_evidence,
)
from market_data import DataAudit  # noqa: E402
from market_data.calendars import get_exchange_calendar  # noqa: E402

OUTPUT_PATH = PROJECT_ROOT / "results" / "spy_donchian_low_frequency_walk_forward.json"
FORBIDDEN_START_DATE = "2024-05-28"
FIXED_PARAMETERS = {"entry_lookback": 20, "exit_lookback": 10}

EXPERIMENT_CONFIG = ExperimentConfig(
    experiment_id="spy_donchian_20_10_low_frequency_walk_forward",
    strategy_id="spy_donchian_trend_breakout_long",
    parameter_combinations=(FIXED_PARAMETERS,),
    market_data=DATA_CONFIG,
    execution=baseline_config("longonly").execution,
    ranking_columns=("total_return", "sharpe_ratio"),
    ranking_ascending=(False, False),
    output_path=BASELINE_RESULT_PATH,
    screening=baseline_config("longonly").screening,
)

WALK_FORWARD_CONFIG = WalkForwardConfig(
    experiment=EXPERIMENT_CONFIG,
    training_window_size=756,
    selection_window_size=None,
    test_window_size=252,
    step_size=252,
    training_mode="expanding",
    minimum_rows_per_window=30,
    shortlist_size=1,
    incomplete_final_window="drop",
    output_path=OUTPUT_PATH,
)

LOW_FREQUENCY_CONFIG = LowFrequencyEvidenceConfig(
    walk_forward=WALK_FORWARD_CONFIG,
    fixed_parameters=FIXED_PARAMETERS,
    output_path=OUTPUT_PATH,
    forbidden_start_date=FORBIDDEN_START_DATE,
)


def _audit_from_cache_metadata() -> DataAudit:
    metadata_path = DATA_CONFIG.metadata_path
    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"required cached SPY metadata is missing: {metadata_path}"
        )
    return DataAudit.from_dict(json.loads(metadata_path.read_text(encoding="utf-8")))


def load_pre_cutoff_cached_spy_data(
    *,
    cache_path: Path = DATA_CONFIG.cache_path,
    forbidden_start_date: str = FORBIDDEN_START_DATE,
) -> tuple[pd.DataFrame, DataAudit]:
    """Load exactly the cached NYSE sessions strictly before the forbidden date."""
    if not cache_path.is_file():
        raise FileNotFoundError(f"required cached SPY data is missing: {cache_path}")
    cutoff = pd.Timestamp(forbidden_start_date)
    calendar = get_exchange_calendar(DATA_CONFIG)
    pre_cutoff_sessions = calendar.schedule(
        start_date=DATA_CONFIG.requested_start,
        end_date=(cutoff - pd.Timedelta(days=1)).date(),
    )
    if pre_cutoff_sessions.empty:
        raise ValueError(f"cache contains no SPY rows before {forbidden_start_date}")

    frame = pd.read_csv(cache_path, nrows=len(pre_cutoff_sessions))
    frame["Date"] = pd.to_datetime(frame["Date"], utc=True).dt.tz_convert(
        DATA_CONFIG.market_timezone
    )
    frame = frame.set_index("Date")
    for column in ("Open", "High", "Low", "Close", "Volume"):
        frame[column] = pd.to_numeric(frame[column])
    frame = frame.loc[:, ["Open", "High", "Low", "Close", "Volume"]]
    if not frame.index.is_monotonic_increasing or not frame.index.is_unique:
        raise ValueError("pre-cutoff SPY cache slice is not strictly chronological")
    if bool((frame.index.tz_localize(None).normalize() >= cutoff).any()):
        raise ValueError("pre-cutoff SPY cache slice unexpectedly crossed cutoff")
    if len(frame) != len(pre_cutoff_sessions):
        raise ValueError("pre-cutoff SPY cache slice does not match NYSE sessions")

    cached_audit = _audit_from_cache_metadata()
    missing = frame.isna().sum()
    audit = replace(
        cached_audit,
        actual_first_row_date=frame.index[0].date().isoformat(),
        actual_last_row_date=frame.index[-1].date().isoformat(),
        row_count=len(frame),
        duplicate_timestamp_count=int(frame.index.duplicated().sum()),
        missing_open_count=int(missing["Open"]),
        missing_high_count=int(missing["High"]),
        missing_low_count=int(missing["Low"]),
        missing_close_count=int(missing["Close"]),
        missing_volume_count=int(missing["Volume"]),
        cache_action="streamed_pre_cutoff_slice",
        cache_decision_reason=(
            "bounded walk-forward evidence excludes all rows on or after "
            f"{forbidden_start_date}"
        ),
    )
    return frame, audit


def run_low_frequency_walk_forward(
    *, write_output: bool = True
) -> LowFrequencyEvidenceResult:
    data, audit = load_pre_cutoff_cached_spy_data()
    return execute_low_frequency_evidence(
        LOW_FREQUENCY_CONFIG,
        data,
        audit,
        write_output=write_output,
    )


def main() -> None:
    result = run_low_frequency_walk_forward()
    print("SPY Donchian 20/10 low-frequency walk-forward evidence")
    print(f"Evaluated range: {result.evaluated_start}..{result.evaluated_end}")
    print(
        "Aggregate: "
        f"{result.aggregate.status}, "
        f"{result.aggregate.sufficient_evidence_fold_count} sufficient folds, "
        f"{result.aggregate.passing_fold_count} passing "
        f"({result.aggregate.passing_percentage:.1%})"
    )
    for fold in result.folds:
        print(
            f"{fold.fold_id}: train {fold.train_start}..{fold.train_end}, "
            f"validation {fold.validation_start}..{fold.validation_end}, "
            f"trades={fold.trade_count}, total_return={fold.total_return:.6f}, "
            f"annualized_return={fold.annualized_return:.6f}, "
            f"sharpe={fold.sharpe_ratio:.6f}, "
            f"max_drawdown={fold.max_drawdown:.6f}, "
            f"evidence={fold.evidence_status}, "
            f"performance={fold.performance_status}, "
            f"combined={fold.combined_status}"
        )
    if result.aggregate.reasons:
        print("Reasons:")
        for reason in result.aggregate.reasons:
            print(f"  - {reason}")
    print(f"Saved low-frequency walk-forward report to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
