"""Deterministic tests for the Milestone 22A normalized evidence contract."""

from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.monte_carlo.models import (
    MonteCarloConfig,
    MonteCarloResult,
    SourceSeries,
    ThresholdResult as MonteCarloThresholdResult,
)
from backtesting.out_of_sample.models import OutOfSampleResult
from backtesting.out_of_sample.models import DataPartition, ParameterLock
from backtesting.robustness.models import RobustnessResult
from backtesting.screening.models import ScreeningResult, ScreeningRuleResult
from backtesting.validation import (
    ExecutionCostAssumptions,
    NormalizedEvidenceRecord,
    StageAcceptanceThreshold,
    ValidationPeriod,
    ValidationSpecification,
    WalkForwardWindowRules,
    map_native_status,
    normalize_evidence,
    normalize_low_frequency_walk_forward_evidence,
    normalize_monte_carlo_evidence,
    normalize_out_of_sample_evidence,
    normalize_robustness_evidence,
    normalize_walk_forward_evidence,
)
from backtesting.walk_forward.low_frequency import (
    LowFrequencyAggregateEvidence,
    LowFrequencyEvidenceResult,
)
from backtesting.walk_forward.models import (
    WalkForwardConfig,
    WalkForwardFoldResult,
    WalkForwardResult,
    WalkForwardWindow,
)
from backtesting.walk_forward.splitter import build_walk_forward_windows


def _monte_carlo(status: str, reasons: tuple[str, ...] = ()) -> MonteCarloResult:
    source = SourceSeries(
        source_id="source-1",
        source_kind="trade_returns",
        experiment_id="experiment-1",
        strategy_id="fixture",
        strategy_version="1",
        values=(0.01, 0.02),
        provenance={},
        execution_assumptions={},
    )
    return MonteCarloResult(
        schema_version=1,
        status=status,
        source=source,
        config=MonteCarloConfig(minimum_observations=2),
        observation_count=2,
        original_metrics={},
        distributions={},
        loss_probability=None,
        drawdown_breach_probability=None,
        threshold_results=(
            MonteCarloThresholdResult("loss_probability", True, 0.1, 0.25, "ok"),
        ),
        execution_stress=(),
        reasons=reasons,
        warnings=(),
        timestamp="2026-07-14T00:00:00+00:00",
    )


def _out_of_sample(passed: bool) -> OutOfSampleResult:
    rule = ScreeningRuleResult(
        rule_id="minimum_trades",
        metric="number_of_trades",
        observed_value=3,
        threshold=5,
        status="passed" if passed else "failed",
        message="minimum trades met" if passed else "minimum trades not met",
    )
    screening = ScreeningResult(
        parameter_row_id="row-1",
        passed=passed,
        rule_results=(rule,),
        passed_rule_count=1 if passed else 0,
        failed_rule_count=0 if passed else 1,
        strategy_id="fixture",
        strategy_version="1",
        normalized_parameters={"window": 14},
        execution_assumptions={},
        rejection_reasons=() if passed else ("screening rejected selected parameters",),
    )
    return OutOfSampleResult(
        split=None,  # The adapter needs only locked test evidence.
        training_result=None,
        selection_result=None,
        test_result=SimpleNamespace(screening_results=(screening,)),
        parameter_lock=SimpleNamespace(lock_id="lock-1"),
        shortlist_parameters=(),
        selected_parameters={"window": 14},
    )


def _walk_forward(status: str, reason: str | None = None) -> WalkForwardResult:
    fold = WalkForwardFoldResult(
        fold_id="fold_001",
        status=status,
        window=None,
        training_result=None,
        selection_result=None,
        test_result=None,
        shortlist_parameters=(),
        parameter_lock=None,
        selected_parameters=None,
        test_metrics={},
        failure_reason=reason,
    )
    return WalkForwardResult(
        folds=(fold,),
        total_fold_count=1,
        successful_fold_count=1 if status == "successful" else 0,
        failed_fold_count=1 if status == "failed" else 0,
        selected_parameters_by_fold=(),
        unique_parameter_set_count=0,
        parameter_frequencies=(),
        parameter_change_percentage=0.0,
        maximum_consecutive_persistence=0,
        failed_fold_ids=(),
        failure_reasons=(),
        fold_test_metrics=None,
        average_fold_metrics={},
        median_fold_metrics={},
        out_of_sample_returns=None,
        out_of_sample_equity=None,
        compounded_return=None,
        endpoint_max_drawdown=None,
        fold_return_sharpe=None,
        total_trades=0,
    )


def _wf_rules(
    *,
    mode: str = "rolling",
    selection_size: int | None = 5,
    test_size: int = 5,
    step_size: int = 5,
) -> WalkForwardWindowRules:
    return WalkForwardWindowRules(
        training_window_size=10,
        selection_window_size=selection_size,
        test_window_size=test_size,
        step_size=step_size,
        training_mode=mode,
        minimum_rows_per_window=2,
        incomplete_final_window="drop",
    )


def _partition(name: str, start_offset: int, rows: int, *, freq: str = "D") -> DataPartition:
    start = pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=start_offset)
    index = pd.date_range(start, periods=rows, freq=freq, tz="UTC")
    data = pd.DataFrame({"Close": range(rows)}, index=index)
    return DataPartition(
        name=name,
        data=data,
        start=str(index[0].date()),
        end=str(index[-1].date()),
        row_count=rows,
    )


def _parameter_lock(fold_id: str = "fold_001") -> ParameterLock:
    return ParameterLock(
        lock_id=f"{fold_id}:lock",
        experiment_id="experiment-1",
        strategy_id="fixture",
        strategy_version="1",
        normalized_parameters=(("window", 14),),
        selection_parameter_row_id="row-1",
        selection_start="2020-01-01",
        selection_end="2020-01-10",
        ranking_columns=("score",),
        ranking_ascending=(False,),
    )


def _wf_fold(
    fold_id: str,
    *,
    train_start: int,
    train_rows: int = 10,
    selection_start: int | None = 10,
    selection_rows: int = 5,
    test_start: int = 15,
    test_rows: int = 5,
    test_freq: str = "D",
    status: str = "successful",
    failure_reason: str | None = None,
    selected: bool = True,
    locked: bool = True,
) -> WalkForwardFoldResult:
    selection = (
        _partition(f"{fold_id}:selection", selection_start, selection_rows)
        if selection_start is not None
        else None
    )
    return WalkForwardFoldResult(
        fold_id=fold_id,
        status=status,
        window=WalkForwardWindow(
            fold_id=fold_id,
            train=_partition(f"{fold_id}:train", train_start, train_rows),
            selection=selection,
            test=_partition(f"{fold_id}:test", test_start, test_rows, freq=test_freq),
        ),
        training_result=None,
        selection_result=None,
        test_result=None,
        shortlist_parameters=(),
        parameter_lock=_parameter_lock(fold_id) if locked else None,
        selected_parameters={"window": 14} if selected else None,
        test_metrics={},
        failure_reason=failure_reason,
    )


def _wf_result(folds: tuple[WalkForwardFoldResult, ...]) -> WalkForwardResult:
    failed = tuple(fold for fold in folds if fold.status == "failed")
    successful = tuple(fold for fold in folds if fold.status == "successful")
    return WalkForwardResult(
        folds=folds,
        total_fold_count=len(folds),
        successful_fold_count=len(successful),
        failed_fold_count=len(failed),
        selected_parameters_by_fold=(),
        unique_parameter_set_count=0,
        parameter_frequencies=(),
        parameter_change_percentage=0.0,
        maximum_consecutive_persistence=0,
        failed_fold_ids=tuple(fold.fold_id for fold in failed),
        failure_reasons=tuple(
            (fold.fold_id, fold.failure_reason or "unknown") for fold in failed
        ),
        fold_test_metrics=pd.DataFrame(),
        average_fold_metrics={},
        median_fold_metrics={},
        out_of_sample_returns=pd.Series(dtype=float),
        out_of_sample_equity=pd.Series(dtype=float),
        compounded_return=None,
        endpoint_max_drawdown=None,
        fold_return_sharpe=None,
        total_trades=0,
    )


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


def _low_frequency(status: str, reasons: tuple[str, ...]) -> LowFrequencyEvidenceResult:
    aggregate = LowFrequencyAggregateEvidence(
        status=status,
        sufficient_evidence_fold_count=3,
        passing_fold_count=3 if status == "passed" else 0,
        passing_percentage=1.0 if status == "passed" else 0.0,
        required_sufficient_folds=3,
        required_passing_percentage=0.6,
        maximum_allowed_drawdown=0.35,
        worst_drawdown=-0.1,
        reasons=reasons,
    )
    return LowFrequencyEvidenceResult(
        strategy_id="fixture",
        strategy_version="1",
        experiment_id="experiment-1",
        strategy_frequency="low_frequency",
        fixed_parameters={},
        forbidden_start_date="2024-05-28",
        evaluated_start="2020-01-01",
        evaluated_end="2020-12-31",
        folds=(),
        aggregate=aggregate,
    )


def _robustness(status: str, reasons: tuple[str, ...]) -> RobustnessResult:
    return RobustnessResult(
        schema_version=1,
        status=status,
        strategy_id="fixture",
        strategy_version="1",
        experiment_id="experiment-1",
        source_artifact_id="artifact-1",
        locked_parameters={},
        data_provenance={},
        execution_assumptions={},
        neighborhood_construction=None,
        parameter_points=(),
        neighborhood_summary=None,
        regime_metadata=None,
        regime_results=(),
        component_statuses={},
        reasons=reasons,
        warnings=(),
        timestamp="2026-07-14T00:00:00+00:00",
    )


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        ("passed", "passed"),
        ("failed", "failed"),
        ("insufficient_evidence", "insufficient_evidence"),
        ("invalid_input", "invalid"),
        ("unexpected", "invalid"),
    ],
)
def test_native_status_vocabulary_maps_without_promotion(native, expected):
    assert map_native_status(native) == expected


def test_out_of_sample_maps_selected_test_screening_and_preserves_reasons():
    record = normalize_out_of_sample_evidence(_out_of_sample(False))

    assert record.status == "failed"
    assert record.source_identity == "lock-1"
    assert record.protected_data_state == "spent"
    assert record.eligible_to_progress is False
    assert record.reasons == (
        "screening rejected selected parameters",
        "minimum trades not met",
    )
    assert record.threshold_results[0].status == "failed"


def test_out_of_sample_passing_lockbox_evidence_can_progress():
    record = normalize_out_of_sample_evidence(_out_of_sample(True))

    assert record.status == "passed"
    assert record.eligible_to_progress is True


def test_generic_out_of_sample_dispatch_preserves_lockbox_default_and_overrides():
    result = _out_of_sample(True)

    default = normalize_evidence(result)
    gated = normalize_evidence(result, protected_data_state="gated")
    unspent = normalize_evidence(result, protected_data_state="unspent")

    assert default.protected_data_state == "spent"
    assert default.eligible_to_progress is True
    assert gated.protected_data_state == "gated"
    assert gated.eligible_to_progress is False
    assert unspent.protected_data_state == "unspent"
    assert unspent.eligible_to_progress is False


def test_successful_walk_forward_folds_are_not_an_accepted_evidence_decision():
    record = normalize_walk_forward_evidence(_walk_forward("successful"))

    assert record.status == "insufficient_evidence"
    assert record.eligible_to_progress is False
    assert record.reasons == (
        "successful walk-forward folds do not define an overall acceptance decision",
    )


def test_failed_walk_forward_fold_maps_to_failed_with_its_reason():
    record = normalize_walk_forward_evidence(_walk_forward("failed", "selection failed"))

    assert record.status == "failed"
    assert record.reasons == ("fold_001: selection failed",)


def test_walk_forward_integration_accepts_valid_rolling_folds_as_insufficient():
    result = _wf_result(
        (
            _wf_fold("fold_001", train_start=0, test_start=15),
            _wf_fold("fold_002", train_start=5, selection_start=15, test_start=20),
        )
    )

    record = normalize_walk_forward_evidence(result, window_rules=_wf_rules())

    assert record.status == "insufficient_evidence"
    assert record.reasons == (
        "successful walk-forward folds do not define an overall acceptance decision",
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


def test_walk_forward_integration_accepts_valid_expanding_folds():
    result = _wf_result(
        (
            _wf_fold("fold_001", train_start=0, train_rows=10, test_start=15),
            _wf_fold(
                "fold_002",
                train_start=0,
                train_rows=15,
                selection_start=15,
                test_start=20,
            ),
        )
    )

    record = normalize_walk_forward_evidence(
        result, window_rules=_wf_rules(mode="expanding")
    )

    assert record.status == "insufficient_evidence"


def test_walk_forward_integration_accepts_optional_selection_window():
    result = _wf_result(
        (
            _wf_fold(
                "fold_001",
                train_start=0,
                selection_start=None,
                test_start=10,
            ),
            _wf_fold(
                "fold_002",
                train_start=5,
                selection_start=None,
                test_start=15,
            ),
        )
    )

    record = normalize_walk_forward_evidence(
        result, window_rules=_wf_rules(selection_size=None)
    )

    assert record.status == "insufficient_evidence"


def test_walk_forward_integration_rejects_overlapping_tests():
    result = _wf_result(
        (
            _wf_fold("fold_001", train_start=0, test_start=15, test_freq="2D"),
            _wf_fold(
                "fold_002",
                train_start=5,
                selection_start=15,
                test_start=20,
            ),
        )
    )

    record = normalize_walk_forward_evidence(result, window_rules=_wf_rules())

    assert record.status == "invalid"
    assert record.reasons == (
        "malformed walk_forward result: fold_002: test window overlaps a prior test window",
    )


def test_walk_forward_integration_rejects_chronological_leakage():
    result = _wf_result(
        (
            _wf_fold(
                "fold_001",
                train_start=0,
                selection_start=8,
                test_start=15,
            ),
        )
    )

    record = normalize_walk_forward_evidence(result, window_rules=_wf_rules())

    assert record.status == "invalid"
    assert record.reasons == (
        "malformed walk_forward result: fold_001: selection overlaps train period",
    )


def test_walk_forward_integration_rejects_declared_rule_mismatch():
    result = _wf_result(
        (
            _wf_fold("fold_001", train_start=0, test_start=15),
            _wf_fold("fold_002", train_start=6, selection_start=16, test_start=21),
        )
    )

    record = normalize_walk_forward_evidence(result, window_rules=_wf_rules())

    assert record.status == "invalid"
    assert record.reasons == (
        "malformed walk_forward result: fold_002: rolling train window advanced by a different step",
    )


def test_walk_forward_integration_rejects_missing_parameter_lock():
    result = _wf_result(
        (_wf_fold("fold_001", train_start=0, test_start=15, locked=False),)
    )

    record = normalize_walk_forward_evidence(result, window_rules=_wf_rules())

    assert record.status == "invalid"
    assert record.reasons == (
        "malformed walk_forward result: fold_001: successful fold with selected parameters lacks a parameter lock",
    )


def test_walk_forward_integration_rejects_partition_row_count_metadata_mismatch():
    fold = _wf_fold("fold_001", train_start=0, test_start=15)
    object.__setattr__(fold.window.train, "row_count", 9)
    result = _wf_result((fold,))

    record = normalize_walk_forward_evidence(result, window_rules=_wf_rules())

    assert record.status == "invalid"
    assert record.reasons == (
        "malformed walk_forward result: fold_001:train partition row_count does not match data length",
    )


def test_walk_forward_integration_rejects_partition_date_metadata_mismatch():
    fold = _wf_fold("fold_001", train_start=0, test_start=15)
    object.__setattr__(fold.window.train, "start", "2020-01-02")
    result = _wf_result((fold,))

    record = normalize_walk_forward_evidence(result, window_rules=_wf_rules())

    assert record.status == "invalid"
    assert record.reasons == (
        "malformed walk_forward result: fold_001:train partition start does not match data",
    )


def test_walk_forward_integration_preserves_failed_fold_reason():
    result = _wf_result(
        (
            _wf_fold(
                "fold_001",
                train_start=0,
                test_start=15,
                status="failed",
                failure_reason="selection failed",
                selected=False,
                locked=False,
            ),
        )
    )

    record = normalize_walk_forward_evidence(result, window_rules=_wf_rules())

    assert record.status == "failed"
    assert record.reasons == ("fold_001: selection failed",)


def test_low_frequency_insufficient_evidence_remains_distinct_from_failed():
    insufficient = normalize_low_frequency_walk_forward_evidence(
        _low_frequency("insufficient_evidence", ("requires more folds",))
    )
    failed = normalize_low_frequency_walk_forward_evidence(
        _low_frequency("failed", ("pass rate below threshold",))
    )

    assert insufficient.status == "insufficient_evidence"
    assert failed.status == "failed"
    assert insufficient.reasons == ("requires more folds",)
    assert failed.reasons == ("pass rate below threshold",)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("passed", "passed"),
        ("failed", "failed"),
        ("insufficient_evidence", "insufficient_evidence"),
        ("invalid_input", "invalid"),
    ],
)
def test_monte_carlo_and_robustness_preserve_their_terminal_statuses(status, expected):
    monte = normalize_monte_carlo_evidence(_monte_carlo(status, ("native reason",)))
    robust = normalize_robustness_evidence(_robustness(status, ("native reason",)))

    assert monte.status == expected
    assert robust.status == expected
    assert monte.reasons == ("native reason",)
    assert robust.reasons == ("native reason",)


def test_malformed_and_unsupported_input_are_invalid_and_fail_closed():
    malformed = OutOfSampleResult(
        split=None,
        training_result=None,
        selection_result=None,
        test_result=SimpleNamespace(screening_results=()),
        parameter_lock=SimpleNamespace(lock_id="lock-1"),
        shortlist_parameters=(),
        selected_parameters={"window": 14},
    )

    malformed_monte = _monte_carlo("passed")
    object.__setattr__(malformed_monte.source, "source_id", "")
    malformed_lock = _out_of_sample(True)
    object.__setattr__(malformed_lock.parameter_lock, "lock_id", "")

    assert normalize_out_of_sample_evidence(malformed).status == "invalid"
    assert normalize_out_of_sample_evidence(malformed_lock).status == "invalid"
    assert normalize_monte_carlo_evidence(malformed_monte).status == "invalid"
    assert normalize_evidence(object()).status == "invalid"


def test_protected_data_state_is_explicit_and_blocks_unspent_or_gated_progression():
    specification = ValidationSpecification(
        train_period=ValidationPeriod("2020-01-01", "2020-06-30"),
        selection_period=ValidationPeriod("2020-07-01", "2020-09-30"),
        protected_lockbox_period=ValidationPeriod("2020-10-01", "2020-12-31"),
        walk_forward_rules=WalkForwardWindowRules(
            training_window_size=20,
            selection_window_size=10,
            test_window_size=10,
            step_size=10,
            training_mode="rolling",
            minimum_rows_per_window=10,
            incomplete_final_window="drop",
        ),
        execution_costs=ExecutionCostAssumptions(reference_id="saved-config:costs"),
        stage_acceptance_thresholds=(
            StageAcceptanceThreshold("monte_carlo", "loss_probability", "<=", 0.25),
        ),
    )
    passed = _monte_carlo("passed")
    unspent = normalize_monte_carlo_evidence(
        passed, protected_data_state=specification.protected_data_state
    )
    gated = normalize_monte_carlo_evidence(passed, protected_data_state="gated")
    spent = normalize_monte_carlo_evidence(passed, protected_data_state="spent")

    assert specification.protected_data_state == "unspent"
    assert unspent.eligible_to_progress is False
    assert gated.eligible_to_progress is False
    assert spent.eligible_to_progress is True


def test_execution_cost_assumptions_copy_caller_mapping_defensively():
    caller_assumptions = {"commission_per_share": 0.005}

    costs = ExecutionCostAssumptions(assumptions=caller_assumptions)
    caller_assumptions["commission_per_share"] = 99.0

    assert costs.assumptions["commission_per_share"] == 0.005
    with pytest.raises(TypeError):
        costs.assumptions["commission_per_share"] = 1.0


def test_unknown_protected_data_state_is_invalid():
    record = normalize_monte_carlo_evidence(
        _monte_carlo("passed"), protected_data_state="mystery"
    )

    assert record.status == "invalid"
    assert record.protected_data_state == "invalid"
    assert record.eligible_to_progress is False


def test_non_passing_normalized_record_requires_a_reason():
    with pytest.raises(ValueError, match="requires at least one reason"):
        NormalizedEvidenceRecord(
            stage_identity="monte_carlo",
            status="invalid",
            reasons=(),
        )
