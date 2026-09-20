# SPYM intraday-momentum transfer test

## Status and hypothesis

Decision 296 (accepted 2026-09-20) approves this as a bounded development/reference
screen. It is a SPYM transfer test—not a SPY reproduction—of Gao, Han, Li &
Zhou, “Market Intraday Momentum,” *Journal of Financial Economics* (2018), DOI
[`10.1016/j.jfineco.2018.05.009`](https://doi.org/10.1016/j.jfineco.2018.05.009).
The implementation is in progress and the backtest has not run; no tested,
merged, deployed, accepted, promoted, or edge result is claimed.

## Exact fixed rule

- Instrument: SPYM, one position per eligible NYSE regular session.
- Signal: compare the previous session's 15:59 close with the current session's
  09:59 close. A positive return is long; zero or negative is short.
- Entry: current-session 15:30 open.
- Exit: current-session 15:59 close.
- Exclude a session if any required signal, entry, or exit boundary bar is
  missing. Do not fill, forward-fill, or synthesize bars.
- No tuning, grid, accumulation, additional filter, or alternate exit.

Readiness measured by a read-only actual-data check before execution: 173
sessions total; 133 eligible exact-boundary sessions (70 long, 63 short, 0
zero), covering 2025-11-03 through 2026-07-13. The check excludes 2025-12-01
and 2025-12-26 because their immediately prior scheduled NYSE sessions were
early closes with no required 15:59 bar. A stricter full-minute-continuity check
leaves 29 sessions, but the approved source rule requires boundary values and
realized daily returns rather than every intervening one-minute bar. Missing
intratrade bars remain an explicit drawdown/path limitation.

## Data and accounting

Use only the checksum-matching owned manifest
`equities_SPYM_1m_databento_equs_mini` and its SPYM `EQUS.MINI` raw 1-minute
dataset. No acquisition or feed substitution is allowed. Use $10,000 initial
cash, 1x leverage, all available cash, no accumulation, a 0.05% fee and 0.02%
adverse slippage on each transaction, 252 sessions per year, and a zero
risk-free basis.

## Evidence boundary and limitations

This is development/reference evidence only; the full available extent was
already inspected, so it is not independent or protected evidence. The history
is short; raw prices can let dividends affect the signal; `EQUS.MINI` is not the
official closing auction; bars are missing; the source excluded days with fewer
than 500 trades while this feed has no comparable trade-count field; and Alpaca
shortability and account eligibility are unknown. Do not promote, place paper
orders, deploy, or claim an edge from this screen.

## Progression and reuse

Finish and review the candidate-specific mixed-price adapter, then run one
bounded screen through the existing VectorBT Pro engine, manifest verification,
screening, durable persistence/artifacts, filters, and dashboard. Do not change
the common engine, schema, or dashboard. Preserve excluded sessions and all
screen outputs. A screen result only determines whether a separately approved
next evidence stage is considered; it does not authorize one automatically.
