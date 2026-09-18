# Execution Assumptions

## Why the old model was optimistic

The original RSI demonstration calculated a crossing from a daily closing price
and filled the resulting order at that same close. The completed close is not
known until the bar has finished, so that model assumes an order can use
information and receive a fill at effectively the same instant. It remains
available as `same_bar_close` only for explicit research comparison.

## Default daily model

The default is now `next_bar_open`:

1. The strategy receives data through a completed daily bar.
2. It calculates RSI and its crossing signal from that completed close.
3. The runner shifts the signal forward by one row.
4. The order fills at the next available session's adjusted `Open`, with the
   configured slippage applied by VectorBT Pro.

The first bar cannot contain a shifted execution. A signal on the final bar has
no future bar and therefore cannot execute. The alignment is strategy-agnostic;
the RSI calculation and threshold rules are unchanged.

## Typed configuration

`ExecutionConfig` records every behavior-driving assumption:

- signal timing: `completed_bar_close`;
- execution mode: `next_bar_open` or explicit comparison mode
  `same_bar_close`;
- execution price: `Open` or `Close`, validated against the mode;
- position sizing: `all_available_cash`;
- initial cash: $10,000;
- fees: 0.05% per transaction;
- slippage: 0.02%;
- direction: long-only;
- leverage: 1×;
- accumulation: disabled.

Unsupported modes, price/mode combinations, sizing methods, directions, or
invalid numeric assumptions fail before simulation. The hygiene layer also
validates data, signals, execution prices, and exact one-row alignment before
portfolio construction. The ranked CSV and `ExperimentResult` record the actual
configuration and concise validation status used.

## Verified comparison

Both modes were run over the same adjusted Yahoo Finance SPY dataset from
2016-01-04 through 2026-07-06 (2,640 rows). Both selected window 7, entry 25,
exit 60 as the top result.

| Metric | Same-bar close | Next-bar open | Change |
|---|---:|---:|---:|
| Total return | 99.45% | 105.95% | +6.49 pp |
| Annualized return | 10.02% | 10.51% | +0.49 pp |
| Sharpe ratio | 0.701 | 0.726 | +0.025 |
| Maximum drawdown | -30.49% | -30.99% | -0.49 pp |
| Trades | 35 | 35 | 0 |

The leading parameter set did not change, but the top-five order did. A more
realistic assumption need not reduce a particular historical result; its value
is that the timing is implementable and does not claim a fill at the signal's
already-completed close. The generated comparison is stored at
`results/rsi_spy_execution_comparison.csv` and remains ignored by Git.

## Remaining limitations

This model still assumes market-on-open fills with a fixed slippage rate. It
does not model spreads separately, volume impact, partial fills, opening
auctions, order rejection, taxes, financing, or intraday price paths. Those
limitations must not be interpreted as broker-ready execution realism.
