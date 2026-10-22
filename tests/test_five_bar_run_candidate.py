from __future__ import annotations

import pandas as pd
import pytest
from pathlib import Path

from backtesting.experiments.runner import align_signals_for_execution
from dashboard.run_adapter import IdeaDraftView
from tools.run_five_bar_candidate import (
    CANDIDATE_ID,
    CANDIDATE_VERSION,
    PARAMETER_COMBINATIONS,
    admit_candidate,
    admit_candidate_identity,
)
from strategies.mes_five_bar_run_exhaustion import STRATEGY_ID
from strategies.mes_five_bar_run_exhaustion import generate_signals


def _session() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range(
        "2025-01-15 09:30", "2025-01-15 16:00", freq="5min",
        inclusive="left", tz="America/New_York",
    ).tz_convert("UTC")
    frame = pd.DataFrame(
        {"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0, "Volume": 10.0},
        index=index,
    )
    schedule = pd.DataFrame(
        {
            "market_open": [pd.Timestamp("2025-01-15 09:30", tz="America/New_York").tz_convert("UTC")],
            "market_close": [pd.Timestamp("2025-01-15 16:00", tz="America/New_York").tz_convert("UTC")],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2025-01-15")]),
    )
    return frame, schedule


def test_exact_retained_candidate_admits_to_immutable_study_plan() -> None:
    packet = Path("tests/fixtures/qfc_d21077c94c96d40b205628d2ef90fee3.json").read_text()
    draft = IdeaDraftView(
        draft_id=CANDIDATE_ID, title="Five-bar run exhaustion", description="",
        source_url="", attribution="retained R15 packet", notes="", configuration_id=None,
        created_at="2026-10-12T17:10:00Z", updated_at="2026-10-12T17:10:00Z",
        candidate_json=packet,
    )
    definition = admit_candidate(draft)

    assert definition.experiment.strategy_id == STRATEGY_ID
    assert definition.experiment.parameter_combinations == PARAMETER_COMBINATIONS
    assert definition.experiment.market_data.symbol == "MES"


def test_admission_rejects_nearby_candidate_identity() -> None:
    with pytest.raises(ValueError, match="outside the one-Candidate"):
        admit_candidate_identity("qfc_nearby_but_not_exact", CANDIDATE_VERSION)
    with pytest.raises(ValueError, match="outside the one-Candidate"):
        admit_candidate_identity(CANDIDATE_ID, "0" * 64)


def test_adapter_reverses_qualifying_run_and_holds_two_completed_bars() -> None:
    frame, schedule = _session()
    run = pd.date_range("2025-01-15 10:00", periods=5, freq="5min", tz="America/New_York").tz_convert("UTC")
    frame.loc[run, "Close"] = 100.5
    frame.loc[run, "High"] = 100.75

    raw = generate_signals(
        frame, {"run_length": 5, "minimum_ticks_per_bar": 2}, schedule=schedule
    )
    from tools.run_five_bar_candidate import study_plan_definition
    aligned = align_signals_for_execution(raw, study_plan_definition().experiment.execution)

    entry = pd.Timestamp("2025-01-15 10:25", tz="America/New_York").tz_convert("UTC")
    exit_ = pd.Timestamp("2025-01-15 10:35", tz="America/New_York").tz_convert("UTC")
    assert aligned.short_entries.at[entry]
    assert aligned.short_exits.at[exit_]
    assert not aligned.entries.any()


def test_adapter_rejects_unapproved_parameter_value() -> None:
    frame, schedule = _session()
    with pytest.raises(ValueError, match="must be one of"):
        generate_signals(
            frame, {"run_length": 7, "minimum_ticks_per_bar": 1}, schedule=schedule
        )
