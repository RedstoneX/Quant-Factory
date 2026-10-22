"""Fixed-rule stress is a real, fail-closed screen, not an informational label."""

import math
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

import backtesting.robustness.fixed_rule as fixed_rule
from backtesting.experiments import execute_experiment
from backtesting.experiments.models import ExecutionConfig, ExperimentConfig
from backtesting.robustness.models import FixedRuleCostStressPlan, FractionalCostStressPlan
from backtesting.screening import ScreeningConfig
from market_data import DataAudit, MarketDataConfig
from strategies.mes_vwap_orb_candidate import STRATEGY_ID

LENIENT = ScreeningConfig(
    minimum_trades=0, minimum_total_return=-1.0, minimum_annualized_return=-1.0,
    minimum_sharpe_ratio=None, maximum_drawdown=1.0,
)


def _session(day: str, *, breakout: bool) -> pd.DataFrame:
    index = pd.date_range(
        f"{day} 09:30", f"{day} 16:00", freq="5min", inclusive="left", tz="America/New_York"
    ).tz_convert("UTC")
    data = pd.DataFrame(
        {"Open": 100.0, "High": 100.5, "Low": 99.5, "Close": 100.0, "Volume": 10.0}, index=index
    )
    if breakout:
        signal_time = pd.Timestamp(f"{day} 10:00", tz="America/New_York").tz_convert("UTC")
        data.loc[signal_time, ["Open", "High", "Low", "Close"]] = [100.5, 101.6, 100.3, 101.5]
        data.loc[signal_time + pd.Timedelta(minutes=5), ["Open", "High"]] = [101.5, 101.5]
    return data


def _session_data() -> pd.DataFrame:
    """Two regular MES sessions: one long opening-range breakout at 10:00, then a flat day."""
    return pd.concat([_session("2025-01-15", breakout=True), _session("2025-01-16", breakout=False)])


def _audit(data: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=2, symbol="MES", provider="Databento", provider_implementation="fixture",
        interval="5m", requested_start=data.index[0].date().isoformat(), requested_dynamic_end_policy="fixed",
        latest_completed_exchange_session=data.index[-1].date().isoformat(), prices_adjusted=False,
        adjustment_verification="raw", download_time="2025-01-16T00:00:00+00:00", download_timezone="UTC",
        actual_first_row_date=data.index[0].isoformat(), actual_last_row_date=data.index[-1].isoformat(),
        row_count=len(data), duplicate_timestamp_count=0, missing_open_count=0, missing_high_count=0,
        missing_low_count=0, missing_close_count=0, missing_volume_count=0, expected_session_gap_count=0,
    )


def _experiment(tmp_path: Path, screening: ScreeningConfig | None = None) -> ExperimentConfig:
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
        output_path=tmp_path / "unused.csv",
        screening=screening or ScreeningConfig.provisional_defaults(),
    )


def _run(experiment: ExperimentConfig, data: pd.DataFrame, **costs):
    """The real engine's screen at the given costs, for cross-checking the stress gate."""
    result = execute_experiment(
        replace(experiment, execution=replace(experiment.execution, **costs)), data, _audit(data), write_output=False
    )
    row = result.ranked_results.iloc[0]
    finite = all(math.isfinite(float(row[key])) for key in ("total_return", "annualized_return", "sharpe_ratio", "max_drawdown"))
    return result.screening_results[0], row, finite


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize("screening", [ScreeningConfig.provisional_defaults(), LENIENT], ids=["provisional", "lenient"])
def test_fixed_rule_cost_stress_uses_higher_costs_as_gate(tmp_path, screening) -> None:
    data = _session_data()
    experiment = _experiment(tmp_path, screening)
    stressed_costs = {"fixed_fee_per_contract_per_side": 1.24, "slippage_ticks": 2}
    screen, row, finite = _run(experiment, data, **stressed_costs)
    _, baseline_row, _ = _run(experiment, data)

    result = fixed_rule.run_fixed_rule_cost_stress(
        experiment, FixedRuleCostStressPlan(1.24, 2), data, _audit(data)
    )

    assert result.stressed_costs == stressed_costs
    assert result.stressed_metrics["total_return"] == pytest.approx(float(row["total_return"]))
    assert result.stressed_metrics["total_return"] < float(baseline_row["total_return"])
    assert result.status == ("passed" if screen.passed and finite else "failed")
    assert [item.rule_id for item in result.threshold_results] == [
        f"stressed_{rule.rule_id}" for rule in screen.rule_results
    ]
    assert "stressed_return.total_minimum" in {item.rule_id for item in result.threshold_results}
    assert not (tmp_path / "unused.csv").exists()


def test_fixed_rule_cost_stress_rejects_non_stress(tmp_path) -> None:
    with pytest.raises(ValueError, match="exceed both baseline costs"):
        fixed_rule.run_fixed_rule_cost_stress(
            _experiment(tmp_path), FixedRuleCostStressPlan(0.62, 2), pd.DataFrame(), object()
        )


@pytest.mark.licensed_vectorbt
def test_mes_fixed_rule_stress_costs_are_unchanged(tmp_path) -> None:
    data = _session_data()
    result = fixed_rule.run_fixed_rule_cost_stress(
        _experiment(tmp_path), FixedRuleCostStressPlan(1.24, 2.0), data, _audit(data)
    )
    assert result.baseline_costs == {"fixed_fee_per_contract_per_side": 0.62, "slippage_ticks": 1}
    assert result.stressed_costs == {"fixed_fee_per_contract_per_side": 1.24, "slippage_ticks": 2.0}


def _stock_experiment(tmp_path: Path) -> ExperimentConfig:
    execution = ExecutionConfig.next_bar_open(
        initial_cash=10_000, fees=0.00002, slippage=0.0001, direction="both", leverage=1,
        accumulate=False, position_sizing="all_cash_whole_shares", order_size=1.0, tick_size=0.01,
    )
    return replace(_experiment(tmp_path, LENIENT), execution=execution)


@pytest.mark.licensed_vectorbt
def test_whole_share_stress_doubles_slippage_and_keeps_fees(tmp_path) -> None:
    data = _session_data()
    experiment = _stock_experiment(tmp_path)
    screen, row, finite = _run(experiment, data, fees=0.00002, slippage=0.0002)
    result = fixed_rule.run_fixed_rule_cost_stress(
        experiment, FractionalCostStressPlan(fees=0.00002, slippage=0.0002), data, _audit(data)
    )
    assert result.stressed_costs == {"fees": 0.00002, "slippage": 0.0002}
    assert result.stressed_metrics["total_return"] == pytest.approx(float(row["total_return"]))
    assert result.status == ("passed" if screen.passed and finite else "failed")
    with pytest.raises(ValueError, match="must raise slippage"):
        fixed_rule.run_fixed_rule_cost_stress(
            experiment, FractionalCostStressPlan(fees=0.00002, slippage=0.0001), data, _audit(data)
        )
    with pytest.raises(ValueError, match="requires whole-share sizing"):
        fixed_rule.run_fixed_rule_cost_stress(
            _experiment(tmp_path), FractionalCostStressPlan(fees=0.0, slippage=0.0002), data, _audit(data)
        )
