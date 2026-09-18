import numpy as np
import pandas as pd
import pytest

from backtesting.robustness import (
    RegimeConfig,
    RegimeLabels,
    attribute_returns_to_regimes,
    evaluate_regimes,
    label_regimes,
)
from backtesting.robustness.models import RegimeLabelMetadata


def prices() -> pd.Series:
    index = pd.date_range("2020-01-01", periods=12, freq="D", tz="UTC")
    return pd.Series([100, 101, 102, 103, 104, 90, 89, 88, 87, 95, 96, 97], index=index)


def config(**kwargs) -> RegimeConfig:
    values = dict(
        trend_window=3,
        trend_neutral_tolerance=0.005,
        volatility_window=3,
        volatility_threshold=0.20,
        annualization_factor=252.0,
        minimum_observations=2,
    )
    values.update(kwargs)
    return RegimeConfig(**values)


def test_labels_are_trailing_deterministic_and_record_warmup():
    close = prices()
    result = label_regimes(close, config())
    assert result.labels.index.equals(close.index)
    assert result.metadata.warmup_observation_count > 0
    assert result.labels.iloc[0] == "unknown|unknown"
    repeated = label_regimes(close, config())
    assert result.labels.equals(repeated.labels)
    assert result.realized_volatility.equals(repeated.realized_volatility)
    assert "trailing" in result.metadata.trend_rule
    assert result.metadata.annualization_factor == 252.0


def test_future_price_mutation_does_not_change_earlier_labels():
    close = prices()
    original = label_regimes(close, config()).labels
    changed = close.copy()
    changed.iloc[-1] = 10_000
    mutated = label_regimes(changed, config()).labels
    assert original.iloc[:-1].equals(mutated.iloc[:-1])


def test_unsorted_duplicate_or_nonfinite_prices_rejected():
    close = prices()
    with pytest.raises(ValueError, match="increasing"):
        label_regimes(close.iloc[::-1], config())
    duplicate = close.copy()
    duplicate.index = pd.DatetimeIndex([close.index[0]] * len(close))
    with pytest.raises(ValueError, match="unique"):
        label_regimes(duplicate, config())
    bad = close.copy()
    bad.iloc[3] = np.nan
    with pytest.raises(ValueError, match="finite"):
        label_regimes(bad, config())


def test_start_of_period_attribution_uses_previous_label():
    index = pd.date_range("2020-01-01", periods=4, freq="D", tz="UTC")
    returns = pd.Series([0.0, 0.1, -0.1, 0.2], index=index)
    labels = pd.Series(["a", "b", "c", "d"], index=index)
    attributed = attribute_returns_to_regimes(returns, labels)
    assert attributed["regime"].tolist() == ["unknown|unknown", "a", "b", "c"]


def test_attribution_requires_exact_index_alignment():
    close = prices()
    labels = label_regimes(close, config()).labels
    shifted = pd.Series(np.zeros(len(close)), index=close.index.shift(1, freq="D"))
    with pytest.raises(ValueError, match="identical"):
        attribute_returns_to_regimes(shifted, labels)


def manual_labels(index: pd.Index) -> RegimeLabels:
    labels = pd.Series(
        ["unknown|unknown", "bullish|low_volatility", "bullish|low_volatility", "bearish|high_volatility", "bearish|high_volatility"],
        index=index,
    )
    trend = labels.str.split("|").str[0]
    volatility = labels.str.split("|").str[1]
    metadata = RegimeLabelMetadata(
        first_usable_timestamp=index[1].isoformat(),
        warmup_observation_count=1,
        trend_rule="fixture trailing",
        volatility_rule="fixture trailing",
        annualization_factor=252.0,
        attribution_policy="start of period",
    )
    return RegimeLabels(labels, trend, volatility, pd.Series(np.nan, index=index), metadata)


def test_regime_evaluation_passes_with_adequate_evidence():
    index = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    returns = pd.Series([0.0, 0.01, 0.02, 0.01, 0.02], index=index)
    results = evaluate_regimes(
        returns,
        manual_labels(index),
        config(minimum_observations=1),
        minimum_return=0.0,
        maximum_drawdown_limit=0.35,
        minimum_sharpe=None,
    )
    assert results
    assert all(result.status == "passed" for result in results)
    assert all(result.first_timestamp and result.last_timestamp for result in results)


def test_regime_evidence_minimums_and_undefined_sharpe():
    index = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    returns = pd.Series([0.0, 0.01, 0.01, 0.01, 0.01], index=index)
    entries = pd.Series([False, False, False, False, False], index=index)
    insufficient = evaluate_regimes(
        returns,
        manual_labels(index),
        config(minimum_observations=3, minimum_trades=1),
        minimum_return=0.0,
        maximum_drawdown_limit=0.35,
        minimum_sharpe=None,
        trade_entries=entries,
    )
    assert all(result.status == "insufficient_evidence" for result in insufficient)
    undefined = evaluate_regimes(
        returns,
        manual_labels(index),
        config(minimum_observations=2),
        minimum_return=0.0,
        maximum_drawdown_limit=0.35,
        minimum_sharpe=0.5,
    )
    assert any("Sharpe is undefined" in result.warnings for result in undefined)


def test_failing_regime_is_failed_not_insufficient():
    index = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    returns = pd.Series([0.0, -0.2, -0.1, 0.01, 0.02], index=index)
    results = evaluate_regimes(
        returns,
        manual_labels(index),
        config(minimum_observations=2),
        minimum_return=0.0,
        maximum_drawdown_limit=0.15,
        minimum_sharpe=None,
    )
    assert any(result.status == "failed" for result in results)
