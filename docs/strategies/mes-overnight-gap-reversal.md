# MES overnight-gap reversal development screen

> Current phase, status, blockers, and next action are authoritative only in
> [`docs/MILESTONES.md`](../MILESTONES.md).

## Proposal and evidence boundary

This is one fixed, source-inspired development-screen proposal for R11. It is
not another opening-range breakout, late-day momentum transfer, RSI/Donchian
variant, or calendar hold. The repository prior-work audit found no earlier
Quant Factory overnight-gap reversal proposal, implementation, or result.

Decision 310 records the owner's acceptance of this exact single development
screen. The experiment has not run and has no result. A development pass would
only retain the candidate for separately predeclared chronological validation;
it would not establish an edge, spend protected evidence, qualify an options
implementation, or authorize deployment, paper/live orders, or capital.

## Named rationale and transfer limitation

- Liu and Tse, [“Overnight returns of stock indexes: Evidence from ETFs and
  futures”](https://www.sciencedirect.com/science/article/pii/S1059056016301563),
  report that overnight returns negatively predict first-half-hour returns in
  US ETF and S&P index-futures data, including out-of-sample predictability in
  their 1999–2014 sample.
- Iwanaga and Sakemoto, [“Does overnight return predict the first half-hour
  return for U.S. market indices?”](https://www.sciencedirect.com/science/article/pii/S1062940826001294),
  report the negative SPY relation in a modern study and that it weakened after
  the 2010s.
- Grant, Wolf, and Yu, [“Intraday price reversals in the US stock index futures
  market”](https://www.sciencedirect.com/science/article/pii/S0378426604000949),
  provide older contextual evidence that opening reversals in S&P futures can
  be materially reduced by transaction costs. Their thresholded rule is not
  this proposal's rule.

The proposed trade is a Quant Factory MES transfer, not a paper replication.
It tests only the 25 minutes from 09:35 through 10:00, not the papers' complete
09:30–10:00 interval. MES trades overnight and lacks SPY's cash-opening auction
and investor-clientele structure, so transfer failure is a primary
falsification risk rather than an implementation defect.

## Fixed data boundary and provenance

- Instrument/dataset: one MES contract using only the checksum-matching
  `futures_MES_5m_databento` Parquet and its committed manifest.
- Series: Databento `MES.c.0`, calendar/front-expiry rank zero, original
  unadjusted prices, UTC left-labeled five-minute bars.
- Development session dates: 2019-05-06 through 2023-12-29, inclusive.
- The candidate-local loader must predicate-push this exact timestamp range:
  `2019-05-06T00:00:00Z <= ts_event < 2023-12-30T00:00:00Z`. It must assert
  that the loaded maximum is below the upper bound before signal construction.
- Candidate logic must not load or inspect rows from 2024 onward. The source
  file's full extent was used by prior strategy work, so this development slice
  is not historically unseen; 2024+ is only prospectively withheld from this
  rule and must not be described as pristine independent evidence.
- No new price data or feed substitution is allowed for the development screen.
  Missing owned-data configuration fails closed.

Before execution, resolve `MES.c.0` to instrument IDs for the complete
development range through Databento's historical symbology endpoint. Require a
complete `OK` response with no partial or not-found intervals, normalize and
checksum the mapping intervals, and persist that provenance. Exclude a session
if its prior-close-to-current-open signal interval crosses any mapping boundary.
If complete mapping metadata is unavailable, stop; do not infer a return from a
roll gap or substitute sampled switch dates or a hand-built quarterly calendar.

## Exact session rule and event ordering

Use the NYSE calendar and interpret boundaries in `America/New_York`. Bars stay
UTC in storage.

For current NYSE session `t`:

1. `prior_close` is the close of the prior actual NYSE session's 15:55
   left-labeled MES bar, corresponding to the 16:00 boundary.
2. `current_open` is the open of session `t`'s 09:30 left-labeled bar.
3. At 09:30, after `current_open` is observed, compute
   `gap = current_open / prior_close - 1`. Do not use the 09:30 bar's high,
   low, close, or volume in the decision.
4. Stage the fixed order during the 09:30–09:35 interval and fill at the raw
   open of the 09:35 bar. A positive gap enters short; a negative gap enters
   long; an exactly zero gap produces no trade.
5. Exit the position at the raw open of the 10:00 bar.

This ordering makes the 09:35 fill later than every signal input. There is at
most one trade per session and no threshold, parameter grid, volatility or
volume filter, stop, target, accumulation, alternate exit, or overnight carry.

Require the prior 15:55 boundary and a contiguous sequence of current-session
bars labeled 09:30, 09:35, 09:40, 09:45, 09:50, 09:55, and 10:00, all with
finite positive OHLC prices and finite nonnegative volume. Otherwise exclude
and report the session. A session following an NYSE early close normally lacks
the prior 15:55 boundary and is therefore explicitly excluded; do not replace
it with the early-close print.

## Execution and deterministic accounting

- Initial normalization cash: USD 100,000.
- Position: exactly one MES contract; USD 5.00 per index point; no leverage or
  position-size grid.
- Fee: USD 0.62 per contract per side, charged separately on entry and exit.
- Slippage: exactly one adverse MES tick (0.25 index points) per side, applied
  once to the raw 09:35 and 10:00 prices.
- For direction `d` (`+1` long, `-1` short),
  `entry_fill = entry_raw + d * 0.25` and
  `exit_fill = exit_raw - d * 0.25`.
- Net trade P&L in dollars is
  `d * (exit_fill - entry_fill) * 5.00 - 1.24`.
- Margin, financing, queue position, fill probability, and spread beyond the
  modeled adverse tick are not modeled and must be reported as limitations.

Build one schedule-complete daily equity series across every NYSE session in
the development boundary. Start at USD 100,000; add that session's net trade
P&L at 10:00, or zero for a zero-gap, roll-crossing, early-close-following, or
otherwise excluded session. Do not use VectorBT's five-minute frequency to
annualize the result.

Compute exactly:

- `total_return = final_equity / 100000 - 1`;
- `annualized_return = (final_equity / 100000) ** (252 / session_count) - 1`;
- one daily return per scheduled session as
  `equity_t / equity_(t-1) - 1`, including zero-return flat/excluded sessions;
- `sharpe_ratio = sqrt(252) * mean(daily_returns) /
  sample_std(daily_returns, ddof=1)` with zero risk-free rate;
- maximum drawdown from the schedule-complete end-of-session equity curve only;
- `win_rate = count(net_trade_pnl > 0) / completed_trades`, with zero-P&L
  trades not wins;
- completed-trade count plus every exclusion count and reason.

Nonpositive equity, fewer than two daily returns, zero daily-return standard
deviation, missing metrics, or non-finite values fail closed.

## Conjunctive development decision

One row is evaluated against the existing screening contract. It survives only
if every condition passes:

1. all required metrics are present and finite;
2. at least 750 trades complete—the predeclared multiyear coverage floor, not
   an economic-performance claim;
3. net total return is strictly positive;
4. net annualized return is strictly positive;
5. daily Sharpe is at least 0.5;
6. daily-equity maximum drawdown magnitude is no more than 35%.

The positive total and annualized gates and 35% drawdown ceiling deliberately
reuse the generic provisional screening vocabulary; Sharpe is the primary
risk-adjusted economic gate, while the trade floor detects inadequate usable
coverage. No win-rate threshold applies. Any failure rejects the candidate and
stops. A pass does not automatically start OOS, walk-forward, robustness,
Monte Carlo, protected testing, execution-vehicle work, or trading.

## Reuse boundary under owner approval

Decision 310 authorizes implementation to reuse the verified
licensed VectorBT Pro 2026.4.7 environment, manifest validation, NYSE calendar,
screening, durable persistence, and generic candidate runtime. Custom work is
limited to a candidate-local predicate-bounded loader, signal/price adapter,
and exact accounting above. Do not change the generic execution schema or
install another VectorBT Pro copy.
