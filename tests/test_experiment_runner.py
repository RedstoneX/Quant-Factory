"""Deterministic tests for the reusable experiment runner."""

from dataclasses import replace
import math
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import backtesting.experiments.chunking as chunking_module
import backtesting.experiments.runner as runner_module
import backtesting.experiments.metrics as metrics_module
import backtesting.run_rsi_demo as demo
from backtesting.experiments import (
    ExecutionConfig,
    ExperimentConfig,
    METRIC_COLUMNS,
    MetricPolicy,
    SignalResult,
    build_portfolio,
    execute_experiment,
    extract_metrics,
)
from backtesting.experiments.metrics import session_close_metrics_frame
from backtesting.screening import screen_metrics
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


def _install_portable_runner_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy = get_strategy("rsi_mean_reversion")

    def deterministic_signals(
        data: pd.DataFrame | pd.Series, parameters: dict[str, int]
    ) -> SignalResult:
        normalized = strategy.validate_parameters(parameters)
        index = data.index
        entries = pd.Series(False, index=index, dtype=bool)
        exits = pd.Series(False, index=index, dtype=bool)
        entries.iloc[5::12] = True
        exits.iloc[8::12] = True
        return SignalResult(entries=entries, exits=exits, parameters=normalized)

    monkeypatch.setattr(strategy, "generate_signals", deterministic_signals)
    monkeypatch.setattr(
        runner_module,
        "_construct_portfolio",
        lambda data, aligned, config: object(),
    )
    monkeypatch.setattr(
        chunking_module,
        "extract_sweep_metrics",
        lambda portfolio, count, **kwargs: count * [{
            "total_return": 0.10,
            "annualized_return": 0.10,
            "sharpe_ratio": 1.0,
            "max_drawdown": -0.10,
            "number_of_trades": 20,
            "win_rate": 0.50,
        }],
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


@pytest.mark.licensed_vectorbt
@pytest.mark.parametrize("risk_free", [0.0, 0.04])
def test_session_metrics_use_completed_exchange_sessions_not_overnight_bars(
    tmp_path: Path, risk_free: float
) -> None:
    index = pd.DatetimeIndex(
        [
            "2024-01-02T00:00:00Z",
            "2024-01-02T14:30:00Z",
            "2024-01-02T20:55:00Z",
            "2024-01-02T22:00:00Z",
            "2024-01-03T14:30:00Z",
            "2024-01-03T20:55:00Z",
            "2024-01-03T22:00:00Z",
        ]
    )
    values = pd.Series(
        [
            100_000.0,
            100_000.0,
            101_000.0,
            101_000.0,
            101_000.0,
            100_500.0,
            100_500.0,
        ],
        index=index,
    )
    config = replace(
        _config(tmp_path),
        market_data=replace(_market_config(tmp_path), interval="5m"),
        execution=replace(_config(tmp_path).execution, initial_cash=100_000.0),
        metric_policy=MetricPolicy(
            sampling="exchange_session_close",
            periods_per_year=252.0,
            risk_free_rate=risk_free,
            basis="complete exchange-session-close portfolio equity and session returns",
            source="test contract",
        ),
    )
    data = pd.DataFrame({"Close": 100.0}, index=index)
    total, annualized, sharpe = session_close_metrics_frame(
        values.to_frame(), None, data, config
    )[0]
    # Published definitions VectorBT PRO's ReturnsAccessor implements: first
    # return is against initial cash, the annual risk-free rate is compounded
    # down to one session, sample std (ddof=1), annualised by sqrt(252).
    excess = pd.Series([0.01, 100_500.0 / 101_000.0 - 1.0]) - (
        (1.0 + risk_free) ** (1.0 / 252.0) - 1.0
    )

    assert total == pytest.approx(0.005)
    assert annualized == pytest.approx(1.005**126 - 1.0)
    assert sharpe == pytest.approx(excess.mean() / excess.std(ddof=1) * 252**0.5)


def test_session_metrics_fail_closed_without_exact_closing_bar(tmp_path: Path) -> None:
    index = pd.DatetimeIndex(
        [
            "2024-01-02T14:30:00Z",
            "2024-01-02T20:50:00Z",
            "2024-01-03T14:30:00Z",
            "2024-01-03T20:55:00Z",
            "2024-01-03T22:00:00Z",
        ]
    )
    portfolio = SimpleNamespace(value=pd.Series(100_000.0, index=index))
    config = replace(
        _config(tmp_path),
        market_data=replace(_market_config(tmp_path), interval="5m"),
        metric_policy=MetricPolicy(
            sampling="exchange_session_close",
            periods_per_year=252.0,
            risk_free_rate=0.0,
            basis="complete exchange-session-close portfolio equity and session returns",
            source="test contract",
        ),
    )

    with pytest.raises(RuntimeError, match="missing the closing bar"):
        metrics_module.session_close_metrics(
            portfolio,
            pd.DataFrame({"Close": 100.0}, index=index),
            config,
        )


@pytest.mark.licensed_vectorbt
def test_session_metrics_use_last_observation_only_when_portfolio_is_flat(
    tmp_path: Path,
) -> None:
    index = pd.DatetimeIndex(
        [
            "2024-01-02T14:30:00Z",
            "2024-01-02T20:50:00Z",
            "2024-01-03T14:30:00Z",
            "2024-01-03T20:55:00Z",
            "2024-01-03T22:00:00Z",
        ]
    )
    value = pd.DataFrame(
        {"v": [100_000.0, 101_000.0, 101_000.0, 102_000.0, 102_000.0]}, index=index
    )
    assets = pd.DataFrame({"v": 0.0}, index=index)
    config = replace(
        _config(tmp_path),
        market_data=replace(_market_config(tmp_path), interval="5m"),
        execution=replace(_config(tmp_path).execution, initial_cash=100_000.0),
        metric_policy=MetricPolicy(
            sampling="exchange_session_close",
            periods_per_year=252.0,
            risk_free_rate=0.0,
            basis="flat fallback proof",
            source="test contract",
        ),
    )
    total_return, annualized_return, sharpe = metrics_module.session_close_metrics_frame(
        value, assets, pd.DataFrame({"Close": 100.0}, index=index), config
    )[0]
    assert total_return == pytest.approx(0.02)
    returns = pd.Series([0.01, 102_000.0 / 101_000.0 - 1.0])
    assert annualized_return == pytest.approx(1.02 ** (252 / 2) - 1.0)
    assert sharpe == pytest.approx(returns.mean() / returns.std(ddof=1) * 252**0.5)


@pytest.mark.licensed_vectorbt
def test_session_metrics_exclude_wholly_absent_exchange_session(tmp_path: Path) -> None:
    index = pd.DatetimeIndex(
        [
            "2024-01-02T20:55:00Z",
            "2024-01-02T22:00:00Z",
            "2024-01-04T20:55:00Z",
            "2024-01-04T22:00:00Z",
        ]
    )
    value = pd.DataFrame({"v": [101_000.0, 101_000.0, 102_000.0, 102_000.0]}, index=index)
    assets = pd.DataFrame({"v": 0.0}, index=index)
    config = replace(
        _config(tmp_path),
        market_data=replace(_market_config(tmp_path), interval="5m"),
        execution=replace(_config(tmp_path).execution, initial_cash=100_000.0),
        metric_policy=MetricPolicy(
            sampling="exchange_session_close", periods_per_year=252.0,
            risk_free_rate=0.0, basis="absent-session proof", source="test contract",
        ),
    )
    total_return, annualized_return, sharpe = metrics_module.session_close_metrics_frame(
        value, assets, pd.DataFrame({"Close": 100.0}, index=index), config
    )[0]
    assert total_return == pytest.approx(0.02)
    returns = pd.Series([0.01, 0.0, 102_000.0 / 101_000.0 - 1.0])
    assert annualized_return == pytest.approx(1.02 ** (252 / 3) - 1.0)
    assert sharpe == pytest.approx(returns.mean() / returns.std(ddof=1) * 252**0.5)


@pytest.mark.licensed_vectorbt
def test_session_metrics_count_a_final_bar_ending_at_the_close_as_complete(tmp_path: Path) -> None:
    # One-minute regular-session bars are labelled by their open: 15:59 New York ends at the close.
    index = pd.DatetimeIndex(["2024-01-02T20:59:00Z", "2024-01-03T20:59:00Z", "2024-01-04T20:59:00Z"])
    value = pd.DataFrame({"v": 100_000.0}, index=index)
    config = replace(
        _config(tmp_path),
        market_data=replace(_market_config(tmp_path), interval="1m"),
        metric_policy=MetricPolicy(
            sampling="exchange_session_close",
            periods_per_year=252.0,
            risk_free_rate=0.0,
            basis="complete exchange-session-close portfolio equity and session returns",
            source="test contract",
        ),
    )

    result = metrics_module.session_close_metrics_frame(
        value, None, pd.DataFrame({"Close": 100.0}, index=index), config
    )[0]
    assert len(result) == 3  # computed, not refused as a partial session


def test_session_metrics_fail_closed_on_partial_final_session(tmp_path: Path) -> None:
    index = pd.DatetimeIndex(
        [
            "2024-01-02T20:55:00Z",
            "2024-01-03T20:55:00Z",
            "2024-01-04T18:00:00Z",
        ]
    )
    portfolio = SimpleNamespace(value=pd.Series(100_000.0, index=index))
    config = replace(
        _config(tmp_path),
        market_data=replace(_market_config(tmp_path), interval="5m"),
        metric_policy=MetricPolicy(
            sampling="exchange_session_close",
            periods_per_year=252.0,
            risk_free_rate=0.0,
            basis="complete exchange-session-close portfolio equity and session returns",
            source="test contract",
        ),
    )

    with pytest.raises(RuntimeError, match="partially observed final session"):
        metrics_module.session_close_metrics(
            portfolio,
            pd.DataFrame({"Close": 100.0}, index=index),
            config,
        )


@pytest.mark.licensed_vectorbt
def test_flat_session_metrics_are_truthfully_screened_out(tmp_path: Path) -> None:
    index = pd.DatetimeIndex(
        [
            "2024-01-02T20:55:00Z",
            "2024-01-02T22:00:00Z",
            "2024-01-03T20:55:00Z",
            "2024-01-03T22:00:00Z",
        ]
    )
    value = pd.DataFrame({"v": 100_000.0}, index=index)
    config = replace(
        _config(tmp_path),
        market_data=replace(_market_config(tmp_path), interval="5m"),
        execution=replace(_config(tmp_path).execution, initial_cash=100_000.0),
        metric_policy=MetricPolicy(
            sampling="exchange_session_close",
            periods_per_year=252.0,
            risk_free_rate=0.0,
            basis="complete exchange-session-close portfolio equity and session returns",
            source="test contract",
        ),
    )
    total_return, annualized_return, sharpe = metrics_module.session_close_metrics_frame(
        value, None, pd.DataFrame({"Close": 100.0}, index=index), config
    )[0]
    metrics = {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": 0.0,
        "number_of_trades": 0,
        "win_rate": float("nan"),
    }
    screening = screen_metrics(
        experiment_id=config.experiment_id,
        strategy_id=config.strategy_id,
        strategy_version="test",
        parameters={},
        execution_assumptions={},
        metrics=metrics,
        config=config.screening,
    )

    assert math.isnan(float(metrics["sharpe_ratio"]))
    assert screening.passed is False
    assert "sharpe_ratio" in screening.rule_results[1].details["non_finite"]


def test_strategy_lookup_and_grid_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_portable_runner_boundaries(monkeypatch)
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


def test_invalid_parameters_are_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_portable_runner_boundaries(monkeypatch)
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
    _install_portable_runner_boundaries(monkeypatch)
    config = _config(
        tmp_path,
        (
            {"window": 14, "entry_threshold": 30, "exit_threshold": 50},
            {"window": 7, "entry_threshold": 25, "exit_threshold": 60},
        ),
    )
    monkeypatch.setattr(
        chunking_module,
        "extract_sweep_metrics",
        lambda portfolio, count, **kwargs: count * [{
            "total_return": 1.0,
            "annualized_return": 1.0,
            "sharpe_ratio": 1.0,
            "max_drawdown": -0.1,
            "number_of_trades": 1,
            "win_rate": 1.0,
        }],
    )
    data = _data()
    first = execute_experiment(config, data, _audit(data), write_output=False)
    second = execute_experiment(config, data, _audit(data), write_output=False)
    pd.testing.assert_frame_equal(first.ranked_results, second.ranked_results)
    assert first.ranked_results["rsi_window"].tolist() == [7, 14]


@pytest.mark.licensed_vectorbt
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
