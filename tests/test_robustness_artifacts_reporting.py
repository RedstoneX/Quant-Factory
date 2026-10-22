import json
from pathlib import Path

import pytest

from backtesting.robustness import (
    find_valid_lock,
    insufficient_result,
    load_lock_artifact,
    read_robustness_report,
    validate_robustness_report,
    write_robustness_report,
)


EXPECTED = dict(
    expected_experiment_id="rsi_spy_daily_demo",
    expected_strategy_id="rsi_mean_reversion",
    expected_strategy_version="1.0.0",
    expected_execution={"execution_mode": "next_bar_open", "fees": 0.0005},
)


def valid_artifact(**overrides):
    payload = {
        "schema_version": 1,
        "artifact_kind": "out_of_sample",
        "artifact_id": "synthetic-lock",
        "experiment_id": "rsi_spy_daily_demo",
        "strategy_id": "rsi_mean_reversion",
        "strategy_version": "1.0.0",
        "source_start": "2020-01-01",
        "source_end": "2024-01-01",
        "data_provenance": {"provider": "fixture", "row_count": 1000},
        "execution_assumptions": {
            "execution_mode": "next_bar_open",
            "fees": 0.0005,
        },
        "parameter_lock": {
            "lock_id": "lock-1",
            "normalized_parameters": {
                "window": 14,
                "entry_threshold": 25,
                "exit_threshold": 55,
            },
        },
        "selection_status": "passed",
        "test_status": "passed",
        "metrics": {
            "total_return": 0.1,
            "max_drawdown": -0.1,
            "sharpe_ratio": 1.0,
            "number_of_trades": 25,
        },
    }
    payload.update(overrides)
    return payload


def write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_and_malformed_artifacts(tmp_path):
    missing = load_lock_artifact(tmp_path / "missing.json", **EXPECTED)
    assert missing.status == "insufficient_evidence"
    malformed_path = tmp_path / "bad.json"
    malformed_path.write_text("{")
    assert load_lock_artifact(malformed_path, **EXPECTED).status == "invalid_input"


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"schema_version": 2}, "schema"),
        ({"experiment_id": "wrong"}, "experiment_id"),
        ({"strategy_id": "wrong"}, "strategy_id"),
        ({"strategy_version": "wrong"}, "strategy_version"),
        ({"source_start": "2025-01-01", "source_end": "2024-01-01"}, "reversed"),
        ({"execution_assumptions": {"execution_mode": "same_bar_close", "fees": 0.0005}}, "execution"),
        ({"parameter_lock": None}, "lock"),
        ({"selection_status": "failed"}, "selection"),
        ({"metrics": {"total_return": float("nan"), "max_drawdown": -0.1, "number_of_trades": 2}}, "metrics"),
    ],
)
def test_invalid_artifact_variants(tmp_path, overrides, reason):
    path = tmp_path / "artifact.json"
    write(path, valid_artifact(**overrides))
    result = load_lock_artifact(path, **EXPECTED)
    assert result.status == "invalid_input"
    assert reason in " ".join(result.reasons)


def test_valid_oos_and_walk_forward_lock_artifacts(tmp_path):
    oos_path = tmp_path / "oos.json"
    write(oos_path, valid_artifact())
    oos = load_lock_artifact(oos_path, **EXPECTED)
    assert oos.status == "passed"
    assert oos.locked_parameters["window"] == 14
    walk_path = tmp_path / "walk.json"
    base = valid_artifact(artifact_kind="walk_forward", artifact_id="wf-lock")
    walk_lock = base.pop("parameter_lock")
    walk_metrics = base.pop("metrics")
    base.pop("selection_status")
    base.pop("test_status")
    base["selected_fold_id"] = "fold_001"
    base["folds"] = [
        {
            "fold_id": "fold_001",
            "status": "successful",
            "selection_status": "passed",
            "test_status": "passed",
            "parameter_lock": walk_lock,
            "test_metrics": walk_metrics,
            "test": {"start": "2020-01-01", "end": "2024-01-01"},
        }
    ]
    write(walk_path, base)
    walk = load_lock_artifact(walk_path, **EXPECTED)
    assert walk.status == "passed"
    valid, inspected = find_valid_lock((tmp_path / "missing.json", walk_path), **EXPECTED)
    assert valid == walk and len(inspected) == 2


def test_invalid_locked_parameters_are_rejected(tmp_path):
    payload = valid_artifact()
    payload["parameter_lock"]["normalized_parameters"]["window"] = 100
    path = tmp_path / "bad-lock.json"
    write(path, payload)
    result = load_lock_artifact(path, **EXPECTED)
    assert result.status == "invalid_input"
    assert "locked parameters are invalid" in " ".join(result.reasons)


def test_current_legacy_artifacts_have_no_valid_lock():
    project = Path(__file__).resolve().parents[1]
    valid, inspected = find_valid_lock(
        (
            project / "results" / "rsi_spy_oos.json",
            project / "results" / "rsi_spy_walk_forward.json",
        ),
        **EXPECTED,
    )
    assert valid is None
    assert inspected
    assert all(item.status != "passed" for item in inspected)


def test_strict_report_round_trip_and_validation(tmp_path):
    result = insufficient_result(
        strategy_id="rsi_mean_reversion",
        strategy_version="1.0.0",
        experiment_id="experiment",
        artifact_id="artifact",
        reasons=("fixture",),
    )
    path = tmp_path / "report.json"
    write_robustness_report(path, result.to_dict())
    payload = read_robustness_report(path)
    assert payload["schema_version"] == 1
    text = path.read_text()
    assert "NaN" not in text and "Infinity" not in text
    with pytest.raises(ValueError, match="missing"):
        validate_robustness_report({"schema_version": 1})
    nonfinite = result.to_dict()
    nonfinite["data_provenance"] = {"bad": float("nan")}
    with pytest.raises(ValueError, match="non-finite"):
        validate_robustness_report(nonfinite)
    payload["schema_version"] = 2
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="unsupported"):
        read_robustness_report(path)
