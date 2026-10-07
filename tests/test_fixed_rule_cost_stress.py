"""Fixed-rule stress is a real, fail-closed screen, not an informational label."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import backtesting.robustness.fixed_rule as fixed_rule
from backtesting.experiments.models import ExecutionConfig, ExperimentConfig
from backtesting.robustness.models import FixedRuleCostStressPlan
from backtesting.screening import ScreeningConfig
from market_data import MarketDataConfig
from strategies.mes_vwap_orb_candidate import STRATEGY_ID


def _experiment(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="fixed-mes-candidate",
        strategy_id=STRATEGY_ID,
        parameter_combinations=({},),
        market_data=MarketDataConfig(
            symbol="MES", provider="Databento",
            provider_implementation="verified_local_catalog:futures_MES_5m_databento",
            interval="5m", requested_start="2019-05-06", end_date_policy="fixed",
            adjusted=False, exchange_calendar="NYSE", market_timezone="America/New_York",
            cache_path=Path("futures/MES/5m/MES_5m_databento.parquet"),
        ),
        execution=ExecutionConfig.next_bar_open(
            initial_cash=100_000, fees=0, slippage=0, direction="both", leverage=1,
            accumulate=False, position_sizing="fixed_units", order_size=1,
            price_multiplier=5, fixed_fee_per_contract_per_side=0.62,
            slippage_ticks=1, tick_size=0.25,
        ),
        ranking_columns=("total_return",), ranking_ascending=(False,),
        output_path=tmp_path / "unused.csv", screening=ScreeningConfig.provisional_defaults(),
    )


@pytest.mark.parametrize("passed", [True, False])
def test_fixed_rule_cost_stress_uses_higher_costs_as_gate(tmp_path, monkeypatch, passed) -> None:
    observed = {}

    def fake_execute(experiment, data, audit, *, write_output):
        observed["execution"] = experiment.execution
        observed["write_output"] = write_output
        rule = SimpleNamespace(rule_id="minimum_total_return", status="passed" if passed else "failed", observed_value=0.01 if passed else -0.01, threshold=0.0, message="stressed total return")
        screen = SimpleNamespace(passed=passed, rule_results=(rule,))
        row = pd.DataFrame([{"number_of_trades": 30, "total_return": rule.observed_value, "annualized_return": 0.01, "sharpe_ratio": 0.6, "max_drawdown": -0.1}])
        return SimpleNamespace(screening_results=(screen,), ranked_results=row)

    monkeypatch.setattr(fixed_rule, "execute_experiment", fake_execute)
    result = fixed_rule.run_fixed_rule_cost_stress(
        _experiment(tmp_path), FixedRuleCostStressPlan(1.24, 2), pd.DataFrame(), object()
    )

    assert observed["execution"].fixed_fee_per_contract_per_side == 1.24
    assert observed["execution"].slippage_ticks == 2
    assert observed["write_output"] is False
    assert result.status == ("passed" if passed else "failed")
    assert result.threshold_results[0].rule_id == "stressed_minimum_total_return"


def test_fixed_rule_cost_stress_rejects_non_stress(tmp_path) -> None:
    with pytest.raises(ValueError, match="exceed both baseline costs"):
        fixed_rule.run_fixed_rule_cost_stress(
            _experiment(tmp_path), FixedRuleCostStressPlan(0.62, 2), pd.DataFrame(), object()
        )
