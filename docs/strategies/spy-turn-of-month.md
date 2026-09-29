# SPY modern turn-of-month development screen

> **Current status:** retained for possible future swing/calendar research, but
> rejected for the present R11 mission because the rule carries a position
> across multiple sessions. It is **not disproven**; it is simply out of scope
> for the current intraday/day-trading mandate and must not be backtested under
> R11.

> Current phase, status, blockers, and next action are authoritative only in
> [`docs/MILESTONES.md`](../MILESTONES.md).

## Proposal and evidence boundary

This is one fixed, source-inspired development-falsification proposal. The idea
was previously source-attributed and shortlisted under Decision 295, but never
selected, coded, acquired, or backtested. The prior-work audit therefore found
the proposal nonduplicative. Decision 306 retains the owner's explicit
candidate-approval gate; this specification does not satisfy or bypass it.

The experiment has not run and has no result. A future pass would be only
permission to consider independent validation; it would not be an edge,
protected evidence, an options claim, or paper/live authority.

## Named rationale

The evidence motivating a modern falsification is intentionally conflicting:

- Maberly and Waggoner, [“Closing the Question on the Continuation of
  Turn-of-The-Month Effects”](https://www.econstor.eu/bitstream/10419/100728/1/wp2000-11.pdf),
  found that the S&P 500 futures and spot effect disappeared after 1990.
- Thaler, [“Anomalies: Weekend, Holiday, Turn of the Month, and Intraday
  Effects”](https://www.aeaweb.org/articles?id=10.1257/jep.1.2.169), reviewed
  the original calendar anomaly and its uncertain explanation.
- Etula, Rinne, Suominen, and Vaittinen, [“Dash for Cash: Monthly Market Impact
  of Institutional Liquidity Needs”](https://academic.oup.com/rfs/article/33/1/75/5494694),
  documented modern month-end price pressure and nearby reversals associated
  with institutional liquidity needs.

The rule below is a fixed modern SPY test inspired by that literature, not an
exact replication of any paper. No other calendar effect, window, direction,
threshold, or instrument is in scope.

## Fixed data boundary

- Instrument: SPY.
- Provider: Yahoo Finance daily adjusted OHLCV through the existing licensed
  VectorBT Pro Yahoo boundary.
- Requested start: 2010-01-01.
- Hard end: the final completed NYSE session of 2023.
- Rows from 2024 onward must never be requested, loaded, or inspected for this
  development screen.
- Use a dedicated fixed-as-of cache and record its normalized checksum, row
  count, first/last dates, adjustment setting, and provider warnings.
- A complete event requires both its entry and exit inside the fixed boundary.
  December 2023 is excluded when its exit falls in 2024.
- Missing required sessions or non-finite/non-positive prices fail closed. No
  forward fill, synthetic bar, alternate date, or feed substitution is allowed.

## Exact rule and execution

Let `T` be the last NYSE trading session of a calendar month. Let `T+3` be the
third NYSE trading session of the following month.

- Submit a buy using adjusted `Open[T]` as the raw reference price.
- Submit a sell using adjusted `Close[T+3]` as the raw reference price.
- Long-only; one position; no accumulation, stop, target, filter, grid, or
  alternate exit.
- Initial cash: USD 10,000; all available cash; 1x leverage.
- Fee: 0.05% of traded notional on entry and exit.
- Slippage: pass `0.0002` to the engine exactly once for adverse execution on
  entry and exit; do not pre-adjust either raw reference price.
- Zero risk-free rate.
- Overnight financing, dividends beyond Yahoo’s adjusted-price treatment,
  taxes, opening/closing auction uncertainty, spread beyond modeled slippage,
  and fractional-share/account constraints are not modeled and must be
  reported as limitations.

The generic experiment runner cannot express different entry-open and
exit-close prices. If the owner accepts the proposal, implementation is limited
to a candidate-local mixed-price adapter following the established SPYM adapter
pattern: pass the raw adjusted open/close arrays plus the single engine
slippage argument above. Do not expand the generic execution schema for this
screen.

## Predeclared metrics and inference

Daily portfolio returns include every NYSE session in the fixed data interval;
out-of-market sessions have zero return. Mark open positions to the adjusted
daily close. Compute:

- total return from the full daily equity curve;
- annualized return as
  `(1 + total_return) ** (252 / session_count) - 1`;
- Sharpe as `sqrt(252) * mean(daily_returns) / sample_std(daily_returns)`;
- maximum drawdown from the daily adjusted-close-marked equity curve;
- arithmetic mean of net completed-event returns.

For the event-return mean, reuse the existing moving-block bootstrap with
exactly 10,000 resamples, a 12-event block, seed 42, and the fifth percentile
of bootstrapped arithmetic means as the one-sided 95% lower confidence bound.

## Conjunctive pass/fail decision

The candidate survives the development screen only if all conditions pass:

1. at least 120 completed events;
2. net total return is strictly positive;
3. net annualized return is strictly positive;
4. Sharpe ratio is at least 0.5;
5. maximum drawdown magnitude is no more than 35%;
6. the bootstrap fifth-percentile lower bound on mean net event return is
   strictly greater than zero.

Any failure rejects the candidate and stops. Passing retains only a development
candidate pending a separately authorized validation design. Do not inspect
2024+ data, alter a parameter, add another calendar effect, execute a protected
test, or progress automatically.

