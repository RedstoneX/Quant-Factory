import json
from pathlib import Path
import numpy as np
import pytest
from dataclasses import replace
from backtesting.monte_carlo import *
from backtesting.monte_carlo.sources import load_rsi_walk_forward_source

def source(values=(.01,-.02,.03,.01,-.01,.02)):
    return SourceSeries("s","period_returns","e","strategy","1",tuple(values),{"provider":"fixture"},{"fees":.001},"daily")
def config(**kw): return replace(MonteCarloConfig(simulation_count=20, minimum_observations=3, percentiles=(5,25,50,75,95)), **kw)

def test_seed_reproducibility_and_variation():
    a=resample_paths(source().values,config()); b=resample_paths(source().values,config()); c=resample_paths(source().values,config(seed=43))
    assert np.array_equal(a,b); assert not np.array_equal(a,c)
def test_iid_permutation_and_block():
    vals=source().values
    assert resample_paths(vals,config()).shape==(20,6)
    p=resample_paths(vals,config(method="path_permutation")); assert sorted(p[0])==sorted(vals)
    b=resample_paths(vals,config(method="moving_block_bootstrap",block_length=2)); assert b.shape==(20,6)
def test_config_validation():
    with pytest.raises(ValueError): config(simulation_count=0)
    with pytest.raises(TypeError): config(seed=True)
    with pytest.raises(ValueError): config(percentiles=(5,5,50,75,95))
    with pytest.raises(ValueError): config(percentiles=(-1,25,50,75,95))
    with pytest.raises(ValueError): config(method="moving_block_bootstrap",block_length=0)
def test_input_statuses():
    assert run_monte_carlo(source(()),config()).status=="insufficient_evidence"
    assert run_monte_carlo(source((.1,)),config()).status=="insufficient_evidence"
    assert run_monte_carlo(source((.1,np.nan,.2)),config()).status=="invalid_input"
    assert run_monte_carlo(source((.1,np.inf,.2)),config()).status=="invalid_input"
    assert run_monte_carlo(source((.1,-1,.2)),config()).status=="invalid_input"
def test_metrics():
    vals=(.1,-.2,.1)
    assert cumulative_return(vals)==pytest.approx(1.1*.8*1.1-1)
    assert equity_path(vals).tolist()==pytest.approx([1.1,.88,.968])
    assert maximum_drawdown(vals)==pytest.approx(-.2)
def test_summaries_probabilities_and_thresholds():
    r=run_monte_carlo(source(),config())
    assert "p5" in r.distributions["terminal_return"]
    assert 0<=r.loss_probability<=1 and 0<=r.drawdown_breach_probability<=1
    passed=run_monte_carlo(source((.1,.1,.1)),config(maximum_loss_probability=1,maximum_drawdown_breach_probability=1,minimum_lower_percentile_return=-1))
    assert passed.status=="passed"
    failed=run_monte_carlo(source((-.2,-.1,-.05)),config(maximum_loss_probability=0,maximum_drawdown_breach_probability=0,minimum_lower_percentile_return=0))
    assert failed.status=="failed" and len(failed.reasons)>=2
def test_immutability_cost_stress_and_serialization():
    vals=[.02,.01,-.01]; original=vals.copy()
    trade_source = replace(source(vals), source_kind="trade_returns")
    r=run_monte_carlo(trade_source,config(execution_cost_scenarios=(ExecutionCostScenario("bad",fee_increase=.001),)))
    assert vals==original
    assert r.execution_stress[0].stressed_cumulative_return<=r.execution_stress[0].original_cumulative_return
    json.dumps(r.to_dict(),default=str)
def test_block_too_large_and_zero_variance():
    assert run_monte_carlo(source(),config(method="moving_block_bootstrap",block_length=9)).status=="invalid_input"
    assert "zero variance" in " ".join(run_monte_carlo(source((.01,.01,.01)),config()).warnings)

def test_period_execution_stress_is_insufficient():
    result = run_monte_carlo(source(), config(execution_cost_scenarios=(ExecutionCostScenario("stress", fee_increase=.001),)))
    assert result.execution_stress[0].status == "insufficient_evidence"

def test_permutation_terminal_invariance_and_drawdown_variation():
    values = (.4, -.3, .2, -.1, .05)
    paths = resample_paths(values, config(method="path_permutation", simulation_count=50))
    terminals = [cumulative_return(path) for path in paths]
    drawdowns = [maximum_drawdown(path) for path in paths]
    assert terminals == pytest.approx([cumulative_return(values)] * len(paths))
    assert len(set(round(value, 10) for value in drawdowns)) > 1

@pytest.mark.parametrize("kwargs", [
    {"percentiles": (5, 25, float("nan"), 75, 95)},
    {"drawdown_threshold": float("inf")},
    {"annualization_factor": 0},
    {"annualization_factor": float("nan")},
    {"simulation_count": True},
])
def test_hardened_config_validation(kwargs):
    with pytest.raises((TypeError, ValueError)):
        config(**kwargs)

def test_source_and_scenario_validation():
    with pytest.raises(ValueError): replace(source(), source_kind="unknown")
    with pytest.raises(ValueError): replace(source(), source_id=" ")
    with pytest.raises(TypeError): replace(source(), provenance=[])
    with pytest.raises(ValueError): ExecutionCostScenario(" ")
    with pytest.raises(ValueError): ExecutionCostScenario("x", fee_increase=float("nan"))

def test_strict_report_round_trip(tmp_path):
    result = run_monte_carlo(source(), config())
    path = tmp_path / "report.json"
    write_report(path, result.to_dict())
    payload = read_report(path)
    assert payload["schema_version"] == 1
    assert "NaN" not in path.read_text() and "Infinity" not in path.read_text()
    path.write_text('{"schema_version": 1}')
    with pytest.raises(ValueError): read_report(path)

def _artifact(folds, **overrides):
    payload = {"schema_version": 1, "experiment_id": "rsi_spy_daily_demo", "strategy_id": "rsi_mean_reversion", "strategy_version": "1.0.0", "execution_assumptions": {"execution_mode": "next_bar_open"}, "folds": folds}
    payload.update(overrides)
    return payload

def test_artifact_missing_malformed_and_identity(tmp_path):
    path = tmp_path / "wf.json"
    assert load_rsi_walk_forward_source(path).input_status == "insufficient_evidence"
    path.write_text("{")
    assert load_rsi_walk_forward_source(path).input_status == "invalid_input"
    path.write_text(json.dumps(_artifact([], experiment_id="wrong")))
    assert load_rsi_walk_forward_source(path).input_status == "invalid_input"

def test_artifact_failed_invalid_and_valid_success(tmp_path):
    path = tmp_path / "wf.json"
    failed = {"fold_id": "fold_001", "status": "failed", "test_metrics": {}, "test": {"start": "a", "end": "b", "row_count": 2}}
    path.write_text(json.dumps(_artifact([failed])))
    assert load_rsi_walk_forward_source(path).input_status == "insufficient_evidence"
    success = {"fold_id": "fold_001", "status": "successful", "test_metrics": {"total_return": float("nan")}, "test": {"start": "a", "end": "b", "row_count": 2}}
    path.write_text(json.dumps(_artifact([success])))
    assert load_rsi_walk_forward_source(path).input_status == "invalid_input"
    success["test_metrics"]["total_return"] = .1
    path.write_text(json.dumps(_artifact([success])))
    loaded = load_rsi_walk_forward_source(path)
    assert loaded.input_status is None and loaded.values == (.1,)
    path.write_text(json.dumps(_artifact([success], strategy_id="wrong")))
    assert load_rsi_walk_forward_source(path).input_status == "invalid_input"
