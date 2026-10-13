from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dashboard.run_adapter import IdeaDraftView
from research_intake import validate_candidate_packet
from strategies.mes_opening_range_breakout import MES_ORB_GRID_STRATEGY
from tools.run_mes_orb_grid_candidate import (
    CANDIDATE_ID, CANDIDATE_VERSION, PARAMETER_COMBINATIONS,
    admit_candidate, admit_candidate_identity,
)


def test_exact_owner_packet_maps_to_42_configuration_study() -> None:
    packet = json.loads(Path("research_intake/mes_orb_parameter_grid_candidate.json").read_text())
    packet["candidate"]["status"] = "owner_approved"
    approved = validate_candidate_packet(packet)
    assert approved.valid
    draft = IdeaDraftView(
        draft_id=CANDIDATE_ID, title="MES opening-range breakout parameter grid",
        description="", source_url="", attribution="owner", notes="",
        configuration_id=None, created_at="2026-10-13T00:00:00Z",
        updated_at="2026-10-13T00:00:00Z", candidate_json=approved.canonical_json,
    )
    definition = admit_candidate(draft)
    assert len(definition.experiment.parameter_combinations) == 42
    assert definition.experiment.parameter_combinations == PARAMETER_COMBINATIONS


def test_nearby_orb_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside the exact MES ORB"):
        admit_candidate_identity("qfc_nearby", CANDIDATE_VERSION)


def test_grid_strategy_accepts_owner_windows_and_separate_directions() -> None:
    index = pd.date_range("2025-01-15 14:30", periods=8, freq="5min", tz="UTC")
    frame = pd.DataFrame(
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 10.0},
        index=index,
    )
    assert MES_ORB_GRID_STRATEGY.validate_parameters(
        {"range_minutes": 10, "breakout_offset_ticks": 1, "direction_variant": "short"}
    )["direction_variant"] == "short"
    with pytest.raises(ValueError, match="range_minutes must be one of"):
        MES_ORB_GRID_STRATEGY.validate_parameters(
            {"range_minutes": 25, "breakout_offset_ticks": 1, "direction_variant": "long"}
        )
