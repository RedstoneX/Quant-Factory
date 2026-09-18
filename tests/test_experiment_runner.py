"""Deterministic tests for the reusable experiment runner."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import backtesting.experiments.runner as runner_module
import backtesting.run_rsi_demo as demo
from backtesting.experiments import (
    ExecutionConfig,
    ExperimentConfig,
    METRIC_COLUMNS,
    build_portfolio,
    execute_experiment,
    extract_metrics,
)
from market_data import DataAudit, MarketDataConfig
from strategies import get_strategy
from strategies.rsi_mean_reversion import RSI_MEAN_REVERSION_SPEC


def _data() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=80, freq="D")
    return pd.DataFrame(
        {
            "Open": [99 + ((i % 12) - 6) * 2 for i in range(len(index))],
            "Close": [100 + ((i % 12) - 6) * 2 for i in range(len(index))],
        },
        index=index,
        dtype=float,
    )


def _audit(data: pd.DataFrame) -> DataAudit:
    return DataAudit(
        cache_schema_version=2,
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="vectorbtpro.YFData.pull",
        interval="1 day",
        requested_start="2016-01-01",
        requested_dynamic_end_policy="test",
        latest_completed_exchange_session="2024-03-20",
        prices_adjusted=True,
        adjustment_verification="test",
        download_time="2024-03-20T17:00:00-04:00",
        download_timezone="America/New_York",
        actual_first_row_date="2024-01-01",
        actual_last_row_date="2024-03-20",
        row_count=len(data),
        duplicate_timestamp_count=0,
        missing_open_count=0,
        missing_high_count=0,
        missing_low_count=0,
        missing_close_count=0,
        missing_volume_count=0,
        expected_session_gap_count=0,
    )


def _market_config(tmp_path: Path) -> MarketDataConfig:
    return MarketDataConfig(
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="vectorbtpro.YFData.pull",
        interval="1 day",
        requested_start="2016-01-01",
        end_date_policy="test",
        adjusted=True,
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        cache_path=tmp_path / "cache.csv",
    )


def _config(
    tmp_path: Path,
    combinations: tuple[dict[str, int], ...] | None = None,
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="test_rsi",
        strategy_id="rsi_mean_reversion",
        parameter_combinations=combinations
        or (
            {"window": 7, "entry_threshold": 25, "exit_threshold": 60},
            {"window": 14, "entry_threshold": 30, "exit_threshold": 50},
        ),
        market_data=_market_config(tmp_path),
        execution=ExecutionConfig.next_bar_open(
            initial_cash=10_000,
            fees=0.0005,
            slippage=0.0002,
            direction="longonly",
            accumulate=False,
            leverage=1.0,
        ),
        ranking_columns=("total_return", "sharpe_ratio"),
        ranking_ascending=(False, False),
        output_path=tmp_path / "results.csv",
        parameter_output_names=(("window", "rsi_window"),),
    )


def test_typed_experiment_configuration(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert config.experiment_id == "test_rsi"
    assert config.strategy_id == "rsi_mean_reversion"
    assert config.parameter_name_map == {"window": "rsi_window"}
    assert config.direction == "longonly"
    with pytest.raises(ValueError, match="equal lengths"):
        ExperimentConfig(
            **{
                **config.__dict__,
                "ranking_ascending": (False,),
            }
        )


def test_strategy_lookup_and_grid_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested: list[str] = []
    real_get_strategy = get_strategy

    def tracking_get_strategy(strategy_id: str):
        requested.append(strategy_id)
        return real_get_strategy(strategy_id)

    monkeypatch.setattr(runner_module, "get_strategy", tracking_get_strategy)
    result = execute_experiment(
        _config(tmp_path),
        _data(),
        _audit(_data()),
        run_timestamp="2024-03-20T21:00:00+00:00",
    )
    assert requested == ["rsi_mean_reversion"]
    assert result.evaluated_combinations == 2
    assert result.rejected_combinations == 0
    assert len(result.ranked_results) == 2
    assert result.run_timestamp == "2024-03-20T21:00:00+00:00"
    assert config_columns(result.ranked_results) == [
        "rsi_window",
        "entry_threshold",
        "exit_threshold",
        *METRIC_COLUMNS,
        "data_source",
        "prices_adjusted",
        "data_start_date",
        "data_end_date",
        "row_count",
        "execution_mode",
        "signal_timing",
        "execution_timing",
        "execution_price",
        "initial_cash",
        "fees",
        "slippage",
        "position_sizing",
        "direction",
        "leverage",
        "accumulate",
        "order_size",
        "price_multiplier",
        "fixed_fee_per_contract_per_side",
        "fixed_fee_per_order",
        "slippage_points",
        "slippage_ticks",
        "tick_size",
        "validation_status",
        "validation_gate_count",
        "parameter_row_id",
        "screening_status",
        "screening_passed_rule_count",
        "screening_failed_rule_count",
        "screening_rejection_reasons",
    ]
    assert (tmp_path / "results.csv").is_file()


def config_columns(frame: pd.DataFrame) -> list[str]:
    return list(frame.columns)


def test_invalid_parameters_are_recorded(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        (
            {"window": 7, "entry_threshold": 25, "exit_threshold": 60},
            {"window": 0, "entry_threshold": 25, "exit_threshold": 60},
        ),
    )
    data = _data()
    result = execute_experiment(config, data, _audit(data), write_output=False)
    assert result.evaluated_combinations == 1
    assert result.rejected_combinations == 1
    assert result.rejections[0].parameters["window"] == 0
    assert "window" in result.rejections[0].error


def test_unapproved_parameter_plan_fails_before_simulation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft_strategy = SimpleNamespace(
        spec=replace(RSI_MEAN_REVERSION_SPEC, approval_state="draft")
    )
    market_validation_called = False

    def unexpected_market_validation(*args: object, **kwargs: object) -> None:
        nonlocal market_validation_called
        market_validation_called = True

    monkeypatch.setattr(runner_module, "get_strategy", lambda _: draft_strategy)
    monkeypatch.setattr(
        runner_module, "validate_market_data", unexpected_market_validation
    )
    data = _data()
    with pytest.raises(ValueError, match="not approved for execution"):
        execute_experiment(_config(tmp_path), data, _audit(data), write_output=False)
    assert market_validation_called is False


def test_ranking_is_deterministic_on_ties(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(
        tmp_path,
        (
            {"window": 14, "entry_threshold": 30, "exit_threshold": 50},
            {"window": 7, "entry_threshold": 25, "exit_threshold": 60},
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "extract_metrics",
        lambda portfolio: {
            "total_return": 1.0,
            "annualized_return": 1.0,
            "sharpe_ratio": 1.0,
            "max_drawdown": -0.1,
            "number_of_trades": 1,
            "win_rate": 1.0,
        },
    )
    data = _data()
    first = execute_experiment(config, data, _audit(data), write_output=False)
    second = execute_experiment(config, data, _audit(data), write_output=False)
    pd.testing.assert_frame_equal(first.ranked_results, second.ranked_results)
    assert first.ranked_results["rsi_window"].tolist() == [7, 14]


def test_portfolio_metrics_and_result_provenance(tmp_path: Path) -> None:
    config = _config(tmp_path, ({"window": 7, "entry_threshold": 25, "exit_threshold": 60},))
    data = _data()
    strategy = get_strategy(config.strategy_id)
    signals = strategy.generate_signals(data, config.parameter_combinations[0])
    portfolio = build_portfolio(data, signals, config)
    metrics = extract_metrics(portfolio)
    assert tuple(metrics) == METRIC_COLUMNS
    assert isinstance(metrics["number_of_trades"], int)

    result = execute_experiment(config, data, _audit(data), write_output=False)
    assert result.strategy_id == "rsi_mean_reversion"
    assert result.strategy_version == "1.0.0"
    assert result.normalized_parameters == (
        {"window": 7, "entry_threshold": 25, "exit_threshold": 60},
    )
    assert result.market_data_audit.provider == "Yahoo Finance"
    assert result.execution_assumptions["initial_cash"] == 10_000
    assert result.execution_assumptions["direction"] == "longonly"
    assert result.execution_assumptions["execution_mode"] == "next_bar_open"
    assert result.execution_assumptions["execution_price"] == "Open"
    assert result.execution_assumptions["strategy"]["same_bar_limitation"]
    assert result.ranked_results.loc[0, "data_source"] == "Yahoo Finance"
    assert result.ranked_results.loc[0, "row_count"] == len(data)
    assert result.parameter_plan_summary.total_combinations == 27


def test_rsi_grid_count_and_wrapper_configuration() -> None:
    assert len(demo.EXPERIMENT_CONFIG.parameter_combinations) == 27
    assert demo.EXPERIMENT_CONFIG.output_path == demo.RESULT_PATH
    assert demo.EXPERIMENT_CONFIG.execution.mode == "next_bar_open"
    assert demo.SAME_BAR_COMPARISON_CONFIG.execution.mode == "same_bar_close"
