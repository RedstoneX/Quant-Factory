"""Walk-forward evidence normalization over windows built by the real splitter."""

from dataclasses import replace

import pandas as pd

from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.validation import normalize_walk_forward_evidence
from backtesting.walk_forward.models import (
    WalkForwardConfig,
    WalkForwardFoldResult,
    WalkForwardResult,
    WalkForwardWindow,
)
from backtesting.walk_forward.splitter import build_walk_forward_windows
from tests.test_validation_evidence_contract import _parameter_lock, _wf_result, _wf_rules


def _wf_frame(rows: int = 60) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame({"Close": range(rows)}, index=index)


def _wf_config(
    tmp_path,
    *,
    mode: str = "rolling",
    selection_size: int | None = 5,
    step_size: int = 5,
) -> WalkForwardConfig:
    return WalkForwardConfig(
        experiment=replace(EXPERIMENT_CONFIG, output_path=tmp_path / "base.csv"),
        training_window_size=10,
        selection_window_size=selection_size,
        test_window_size=5,
        step_size=step_size,
        training_mode=mode,
        minimum_rows_per_window=2,
        shortlist_size=1,
        incomplete_final_window="drop",
        output_path=tmp_path / "walk_forward.json",
    )


def _wf_result_from_windows(windows: tuple[WalkForwardWindow, ...]) -> WalkForwardResult:
    return _wf_result(
        tuple(
            WalkForwardFoldResult(
                fold_id=window.fold_id,
                status="successful",
                window=window,
                training_result=None,
                selection_result=None,
                test_result=None,
                shortlist_parameters=(),
                parameter_lock=_parameter_lock(window.fold_id),
                selected_parameters={"window": 14},
                test_metrics={},
                failure_reason=None,
            )
            for window in windows
        )
    )


def test_walk_forward_integration_accepts_real_rolling_windows(tmp_path):
    config = _wf_config(tmp_path)
    result = _wf_result_from_windows(build_walk_forward_windows(_wf_frame(), config))

    record = normalize_walk_forward_evidence(result, window_rules=_wf_rules())

    assert record.status == "insufficient_evidence"


def test_walk_forward_integration_accepts_real_expanding_windows(tmp_path):
    config = _wf_config(tmp_path, mode="expanding")
    result = _wf_result_from_windows(build_walk_forward_windows(_wf_frame(), config))

    record = normalize_walk_forward_evidence(
        result, window_rules=_wf_rules(mode="expanding")
    )

    assert record.status == "insufficient_evidence"


def test_walk_forward_integration_accepts_real_rolling_step_equal_to_train(tmp_path):
    config = _wf_config(tmp_path, step_size=10)
    result = _wf_result_from_windows(build_walk_forward_windows(_wf_frame(), config))

    record = normalize_walk_forward_evidence(
        result, window_rules=_wf_rules(step_size=10)
    )

    assert record.status == "insufficient_evidence"


def test_walk_forward_integration_accepts_real_rolling_step_larger_than_train(tmp_path):
    config = _wf_config(tmp_path, step_size=15)
    result = _wf_result_from_windows(build_walk_forward_windows(_wf_frame(), config))

    record = normalize_walk_forward_evidence(
        result, window_rules=_wf_rules(step_size=15)
    )

    assert record.status == "insufficient_evidence"


def test_walk_forward_integration_rejects_real_windows_with_declared_step_mismatch(
    tmp_path,
):
    config = _wf_config(tmp_path, step_size=5)
    result = _wf_result_from_windows(build_walk_forward_windows(_wf_frame(), config))

    record = normalize_walk_forward_evidence(
        result, window_rules=_wf_rules(step_size=6)
    )

    assert record.status == "invalid"
    assert record.reasons == (
        "malformed walk_forward result: fold_002: rolling train window advanced by a different step",
    )
