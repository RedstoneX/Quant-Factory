# SPYM intraday-momentum transfer test

## Status and hypothesis

Decision 296 (accepted 2026-09-20) approves this as a bounded development/reference
screen. It is a SPYM transfer test—not a SPY reproduction—of Gao, Han, Li &
Zhou, “Market Intraday Momentum,” *Journal of Financial Economics* (2018), DOI
[`10.1016/j.jfineco.2018.05.009`](https://doi.org/10.1016/j.jfineco.2018.05.009).
The bounded development/reference screen has completed from clean source at
source revision `3ae6912937501b46f67666dea269ec76e92caad5` using licensed
VectorBT Pro 2026.4.7.
It screened out at the initial screen; final evidence review is in progress.
This is not independent/protected evidence and does not claim a tested,
merged, deployed, accepted, promoted, or edge result.

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
risk-free basis. When the screen runs, persisted fill prices must include the
stated 0.02% adverse slippage applied directionally to the observed 15:30 Open
and 15:59 Close base prices.

Any reported maximum drawdown is calculated only from end-of-eligible-session
equity values. Missing intraday bars limit the available path and drawdown
evidence.

## Evidence boundary and limitations

This is development/reference evidence only; the full available extent was
already inspected, so it is not independent or protected evidence. The history
is short; raw prices can let dividends affect the signal; `EQUS.MINI` is not the
official closing auction; bars are missing; the source excluded days with fewer
than 500 trades while this feed has no comparable trade-count field; and Alpaca
shortability and account eligibility are unknown. Do not promote, place paper
orders, deploy, or claim an edge from this screen.

## Initial screen result

The screen produced 133 closed trades and 266 orders across 70 long, 63 short,
and 0 zero signals; 40 sessions were excluded. Total return was
`-0.1686805974716311` (`-16.87%`), annualized return
`-0.29533724723539356` (`-29.53%`), Sharpe
`-12.968788931253316`, maximum end-of-eligible-session drawdown
`-0.1686805974716311` (`-16.87%`), and win rate `0.15789473684210525`
(`15.79%`). The screen passed 0 variants and screened out 1 variant because it
failed the total-return, annualized-return, and Sharpe rules.

The 7/7 persisted artifacts were valid; database, artifact, and dashboard
metrics agreed; the dataset checksum matched; no warnings were emitted; and no
orders occurred outside simulation. These are measured development/reference
results over the already-inspected extent, not independent or protected
evidence, an edge, or promotion evidence.

## Progression and reuse

Finish final evidence review of the completed bounded screen; do not rerun or
extend this rejected candidate. Any new screen requires owner selection and
approval of another source-attributed candidate with fixed boundaries. Do not
progress automatically; no next candidate is currently selected or approved,
and no paper, deployment, or live work is authorized. The existing VectorBT Pro engine, manifest
verification, screening, durable persistence/artifacts, filters, and dashboard
remain the reusable path; do not change the common engine or schema. Under
Decision 287's verified-operational-blocker
exception, the screen may receive only two narrow candidate-display truth
corrections: suppress the generic annualization notice when persisted `252`
sessions/year and zero risk-free basis are present, and suppress the blanket
SPYM fixture-only notice for this approved candidate while retaining historical
fixture wording for actual fixtures. These are not redesign, polish, or new
features. Preserve excluded sessions and all screen outputs. A screen result
only determines whether a separately approved next evidence stage is
considered; it does not authorize one automatically.
