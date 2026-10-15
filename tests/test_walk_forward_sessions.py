"""Intraday walk-forward windows are cut on exchange-session starts (CME session spans midnight UTC)."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pandas_market_calendars as mcal
import pytest

from backtesting.validation.evidence_models import WalkForwardWindowRules
from backtesting.validation.walk_forward_artifacts.builder import build_walk_forward_evidence_document
from backtesting.validation.walk_forward_artifacts.models import WALK_FORWARD_EVIDENCE_LOGICAL_NAME
from backtesting.validation.walk_forward_artifacts.validator import validate_walk_forward_evidence_document
from backtesting.walk_forward import build_walk_forward_windows
from backtesting.walk_forward.sessions import SessionGrid
from persistence import ArtifactType
from tests.test_walk_forward import _config
from tests.test_walk_forward_artifacts import _result_from_windows

CALENDAR = "CME_Equity"
SIZES = {"train": 900, "selection": 300, "test": 300}


def _cme_bars() -> pd.DataFrame:
    schedule = mcal.get_calendar(CALENDAR).schedule(start_date="2024-01-02", end_date="2024-03-28")
    index = pd.DatetimeIndex(
        [bar for open_, close in zip(schedule["market_open"], schedule["market_close"])
         for bar in pd.date_range(open_, close, freq="15min", inclusive="left")]
    )
    return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0}, index=index)


def _intraday_config(tmp_path: Path):
    config = _config(tmp_path)
    market_data = replace(config.experiment.market_data, interval="15min", exchange_calendar=CALENDAR)
    return replace(
        config,
        experiment=replace(config.experiment, market_data=market_data),
        training_window_size=SIZES["train"],
        selection_window_size=SIZES["selection"],
        test_window_size=SIZES["test"],
        step_size=SIZES["test"],
        minimum_rows_per_window=100,
    )


def _rules() -> WalkForwardWindowRules:
    return WalkForwardWindowRules(
        training_window_size=SIZES["train"], selection_window_size=SIZES["selection"],
        test_window_size=SIZES["test"], step_size=SIZES["test"], training_mode="rolling",
        minimum_rows_per_window=100, incomplete_final_window="drop",
    )


def _document(tmp_path: Path) -> dict:
    windows = build_walk_forward_windows(_cme_bars(), _intraday_config(tmp_path))
    return build_walk_forward_evidence_document(
        run_id="wf-run", source={"run_id": "wf-run"}, result=_result_from_windows(windows), rules=_rules()
    )


def _validate(document: dict) -> None:
    artifact = SimpleNamespace(
        logical_name=WALK_FORWARD_EVIDENCE_LOGICAL_NAME, artifact_type=ArtifactType.VALIDATION_EVIDENCE
    )
    validate_walk_forward_evidence_document(document=document, run_id="wf-run", artifact=artifact)


def test_intraday_cuts_land_on_session_starts_and_validate(tmp_path):
    data = _cme_bars()
    opens = set(mcal.get_calendar(CALENDAR).schedule("2024-01-02", "2024-03-28")["market_open"])
    windows = build_walk_forward_windows(data, _intraday_config(tmp_path))
    assert len(windows) >= 3
    alignment = {"exchange_calendar": CALENDAR, "interval": "15min"}
    session_rows = SessionGrid(alignment, data.index[0], data.index[-1]).max_session_rows
    assert session_rows == 4 * 24 * 4  # holiday weekend: Friday open to Monday-evening open, 15-min bars
    for fold in windows:
        assert fold.train.end < fold.selection.start < fold.test.start
        for kind in ("train", "selection", "test"):
            part = getattr(fold, kind)
            assert part.data.index[0] in opens
            assert SIZES[kind] <= part.row_count < SIZES[kind] + session_rows
    document = _document(tmp_path)
    assert document["evidence"]["session_alignment"] == {"exchange_calendar": CALENDAR, "interval": "15min"}
    _validate(document)


def test_validator_refuses_window_cut_mid_session(tmp_path):
    document = _document(tmp_path)
    fold = document["evidence"]["folds"][0]
    inside = pd.Timestamp(fold["selection"]["start"]) + pd.Timedelta(hours=2)
    fold["selection"]["start"] = inside.isoformat()
    fold["train"]["end"] = (inside - pd.Timedelta(minutes=15)).isoformat()
    with pytest.raises(ValueError, match="inconsistent") as refused:
        _validate(document)
    assert "splits an exchange session" in str(refused.value.__cause__)


def test_validator_refuses_window_a_session_larger_than_declared(tmp_path):
    document = _document(tmp_path)
    data = _cme_bars()
    alignment = {"exchange_calendar": CALENDAR, "interval": "15min"}
    oversized = SIZES["test"] + SessionGrid(alignment, data.index[0], data.index[-1]).max_session_rows
    document["evidence"]["folds"][0]["test"]["row_count"] = oversized
    with pytest.raises(ValueError, match="inconsistent") as refused:
        _validate(document)
    assert f"test window has {oversized} rows; expected 300" in str(refused.value.__cause__)
