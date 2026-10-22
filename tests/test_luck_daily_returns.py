"""The Luck test (deflated Sharpe, PBO) reads daily returns per setting, labelled in its record.

Daily-bar ideas score bit-identically to the bar-level method it replaced (resampling daily
data to days is the identity); intraday ideas score exactly as the same statistics computed by
hand from each day's closing value. Older records carry no label and show as the older method.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments.chunking import daily_values
from backtesting.experiments.runner import _record_luck
from backtesting.screening.deflated_sharpe import DeflatedSharpeResult, deflated_sharpe, grid_returns
from backtesting.screening.overfitting_pbo import OverfittingPBOResult, probability_of_backtest_overfitting
from backtesting.validation.walk_forward_artifacts.builder import _idea_overfitting_document
from backtesting.walk_forward.overfitting import IdeaOverfitting
from dashboard.score_projection import LUCK_OLDER, OLDER_LUCK_LINE, _grid_scores, luck_basis

CASH = 10_000.0
SETTINGS = 6


def _portfolio(index: pd.DatetimeIndex, seed: int = 3):
    """A real VectorBT PRO sweep: one column per setting, random entries and exits."""
    import vectorbtpro as vbt

    rng = np.random.default_rng(seed)
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.002, size=(len(index), SETTINGS)), axis=0)), index=index
    )
    entries = pd.DataFrame(rng.random(close.shape) < 0.05, index=index)
    exits = pd.DataFrame(rng.random(close.shape) < 0.05, index=index)
    return vbt.Portfolio.from_signals(close, entries, exits, init_cash=CASH, freq="1min")


def _bar_level_luck(values: np.ndarray, index: pd.DatetimeIndex):
    """The method before 20 Oct 2026: deflated Sharpe on every bar; PBO on dates' last values."""
    daily = pd.DataFrame(values, index=index).groupby(index.date).last()
    returns = grid_returns(daily.to_numpy(), CASH, pd.DatetimeIndex(daily.index))
    return deflated_sharpe(values, CASH), probability_of_backtest_overfitting(returns)


@pytest.mark.licensed_vectorbt
def test_daily_bars_score_bit_identically_to_the_bar_level_method() -> None:
    index = pd.bdate_range("2020-01-02 16:00", periods=400, tz="America/New_York")
    portfolio = _portfolio(index)
    before_dsr, before_pbo = _bar_level_luck(portfolio.value.to_numpy(), index)
    after_dsr, after_pbo = _record_luck(daily_values(portfolio, SETTINGS), CASH)
    assert after_dsr.trial_probabilities == before_dsr.trial_probabilities
    assert (after_dsr.probability, after_dsr.best_sharpe, after_dsr.observations) == (
        before_dsr.probability, before_dsr.best_sharpe, before_dsr.observations
    )
    assert (after_pbo.probability, after_pbo.splits) == (before_pbo.probability, before_pbo.splits)
    assert after_dsr.returns_basis == after_pbo.returns_basis == "daily"


@pytest.mark.licensed_vectorbt
def test_minute_bars_score_on_each_days_closing_value() -> None:
    days = pd.bdate_range("2024-01-02", periods=40)
    index = pd.DatetimeIndex(
        [day + pd.Timedelta(hours=9, minutes=30 + m) for day in days for m in range(390)]
    ).tz_localize("America/New_York")
    portfolio = _portfolio(index)
    kept = daily_values(portfolio, SETTINGS)
    assert all(len(series) == len(days) for series in kept)  # nothing bar-level outlives the chunk
    by_hand = portfolio.value.groupby(index.date).last().to_numpy()  # each day's closing value
    luck, pbo = _record_luck(kept, CASH)
    expected = deflated_sharpe(by_hand, CASH)
    assert luck.trial_probabilities == expected.trial_probabilities and luck.observations == len(days)
    hand_returns = grid_returns(by_hand, CASH, pd.DatetimeIndex(days))
    assert pbo.probability == probability_of_backtest_overfitting(hand_returns).probability


def _dsr(basis: str | None) -> DeflatedSharpeResult:
    return DeflatedSharpeResult(
        trials=6, effective_trials=6.0, best_trial_index=0, best_sharpe=0.1, observations=300,
        probability=0.7, trial_probabilities=(0.7,) * 6, returns_basis=basis,
    )


def test_the_method_label_is_stored_in_the_evidence_record() -> None:
    pbo = OverfittingPBOResult(probability=0.3, splits=70, trials=6, observations=300, returns_basis="daily")
    labelled = _idea_overfitting_document(IdeaOverfitting(6, _dsr("daily"), pbo))
    assert labelled["returns_basis"] == "daily" and luck_basis(labelled) == "daily"
    older = _idea_overfitting_document(IdeaOverfitting(6, _dsr(None), None))
    assert "returns_basis" not in older and luck_basis(older) == LUCK_OLDER
    assert luck_basis(_idea_overfitting_document(None)) is None


def test_older_method_score_shows_grey_with_its_line_and_is_blank_in_the_grid() -> None:
    scores_ui = pytest.importorskip("dashboard.ui.scores")  # needs the dashboard's UI packages
    older = {"luck": 0.91, "luck_basis": LUCK_OLDER}
    card = scores_ui.score_cards(older)[3].children.children
    assert card[1].children == "91%" and card[1].c == "dimmed" and card[2].children == OLDER_LUCK_LINE
    assert _grid_scores(older)["luck"] is None
    assert _grid_scores({"luck": 0.4, "luck_basis": "daily"})["luck"] == 0.4
    assert "isDescending" in scores_ui._LUCK_ORDER  # older rows sort last in either direction
