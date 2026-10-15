"""Portable fake VectorBT used by pipeline tests; mirrors the attributes the evidence writers read."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd


def _FakeTrades(count: int) -> SimpleNamespace:
    pnl = pd.Series([1.0] * count, dtype=float)
    return SimpleNamespace(
        count=lambda: count, win_rate=0.60, records_readable=pd.DataFrame({"Trade Id": range(count)}),
        pnl=pnl, winning=SimpleNamespace(pnl=pnl), losing=SimpleNamespace(pnl=pnl.iloc[:0]),
        profit_factor=float("inf"), duration=pd.Series([2] * count, dtype=float),
    )

class _FakePortfolioResult:
    def __init__(self, index: pd.Index, trade_count: int) -> None:
        self.total_return = 0.05
        self.annualized_return = 0.10
        self.sharpe_ratio = 1.0
        self.max_drawdown = -0.02
        self.trades = _FakeTrades(max(1, trade_count))
        self.orders = SimpleNamespace(records_readable=pd.DataFrame({"Order Id": range(max(1, trade_count))}),
                                      fees=pd.Series([0.1] * max(1, trade_count)))
        self.long_view = self.short_view = self  # the summary reads VectorBT's direction views
        self.value = pd.Series(10_000.0, index=index, dtype=float)
        self.returns = pd.Series(0.001, index=index, dtype=float)

class _FakePortfolio:
    @staticmethod
    def from_signals(*, close, entries, short_entries=None, **_kwargs):
        counts = pd.DataFrame(entries).sum() + (0 if short_entries is None else pd.DataFrame(short_entries).sum())
        columns = [_FakePortfolioResult(close.index, int(count)) for count in counts]
        return _FakeSweep(columns) if isinstance(entries, pd.DataFrame) else columns[0]

class _FakeSweep:
    """One column per setting: each property holds one value per column, like VectorBT."""

    def __init__(self, columns: list[_FakePortfolioResult]) -> None:
        self.columns, self.iloc, self.value = columns, self, pd.concat([column.value for column in columns], axis=1)
        self.__dict__.update({name: pd.Series([getattr(c, name) for c in columns]) for name in ("total_return", "annualized_return", "sharpe_ratio", "max_drawdown")})
        self.trades = SimpleNamespace(count=lambda: pd.Series([c.trades.count() for c in columns]), win_rate=pd.Series([c.trades.win_rate for c in columns]))

    def __getitem__(self, key):
        return self.columns[key[1]]


class _FakeRSIResult:
    def __init__(self, index: pd.Index) -> None:
        self._index = index

    def rsi_crossed_below(self, _threshold: int) -> pd.Series:
        values = pd.Series(False, index=self._index, dtype=bool)
        values.iloc[2::8] = True
        return values

    def rsi_crossed_above(self, _threshold: int) -> pd.Series:
        values = pd.Series(False, index=self._index, dtype=bool)
        values.iloc[5::8] = True
        return values


class _FakeRSI:
    @staticmethod
    def run(close: pd.Series, *, window: int) -> _FakeRSIResult:
        _ = window
        return _FakeRSIResult(close.index)


FAKE_VECTORBT = SimpleNamespace(Portfolio=_FakePortfolio, RSI=_FakeRSI)
