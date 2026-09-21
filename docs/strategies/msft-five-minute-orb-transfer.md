# MSFT five-minute opening-range breakout transfer test

## Status

**Proposed; awaiting Terry's approval. Nothing in this document authorizes
implementation or execution.**

This is one bounded transfer test of the rules in Zarattini, Barbon and Aziz,
[*A Profitable Day Trading Strategy for the U.S. Equity
Market*](https://doi.org/10.2139/ssrn.4729284). The paper studies a diversified
long-and-short portfolio chosen from more than 7,000 U.S. stocks. Quant Factory
currently owns suitable history for only MSFT. This proposal therefore tests a
long-only MSFT subset; it does not reproduce the paper and does not imply that
MSFT has an edge.

The choice is economical: MSFT is an equity within the intended Alpaca asset
class, the project already owns validated five-minute data for it, Terry
prefers ORB as the next strategy family, and the alternatives in the existing
shortlist lack suitable unused data. Account eligibility would still require a
later check. SPYM momentum, SPY Donchian and MES ORB are already concluded and
must not be rerun or relabelled.

## One fixed rule

- Instrument: MSFT; no other symbol and no parameter grid.
- Session: NYSE regular hours only, 09:30 through 16:00 New York time.
- Daily eligibility, using only prior completed sessions: opening price above
  $5; 14-session average volume of at least 1,000,000 shares; 14-session ATR
  above $0.50; and first-five-minute volume at least equal to its prior
  14-session average.
- Direction: long only. A bullish first five-minute candle permits one buy;
  bearish or unchanged first candles produce no trade.
- Entry: after the first five-minute candle closes, buy when a later bar first
  reaches its high. Never enter from the opening candle itself.
- Risk exit: stop 10% of the prior 14-session ATR below the filled entry.
- Time exit: close any remaining position at the regular-session close. Never
  hold overnight and never add to a position.
- Sizing: risk at most 1% of current simulated capital at the stop, use whole
  shares, and cap exposure at available cash with no leverage.
- Bar ambiguity: when one five-minute bar can contain both entry and stop, use
  the loss-producing order; never assume the favorable path inside the bar.
- No target, trailing stop, alternate opening range, alternate direction,
  news filter, manual exception, local refinement or outcome-driven change.

The source uses both long and short trades, permits up to 4x leverage, and
selects the day's top 20 stocks by relative volume. Long-only MSFT and the 1x
cap are deliberate safety and data-availability adaptations. The paper's
reported portfolio results must not be attributed to this proposal.

## Data and costs

- Use only catalog entry `equities_MSFT_5m_databento`, checksum
  `9f94d54726580e35df187744b1734adb80c5d6043e8f2eb9211ecf52319828e1`.
- The catalog records 299,194 validated rows from 2019-05-01 through
  2026-02-13. Extended-hours bars must be removed; missing regular-session bars
  must remain missing and must never be filled or invented.
- A read-only timestamp-only check found 1,708 observed regular-session dates.
  It calculated the dates below without calculating signals, trades or profit.
- Adjusted-price and prior off-repository inspection status remain unknown.
  Corporate actions and five-minute bar ordering therefore remain explicit
  evidence limits.
- Simulated starting capital: $10,000; 1x maximum exposure; zero risk-free
  rate; 252 sessions per year.
- Apply the existing conservative equity assumptions on each transaction:
  0.05% fee plus 0.02% adverse slippage. Preserve both observed and simulated
  fill prices.

## Evidence boundary and stop rules

| Boundary | Dates | Rule |
|---|---|---|
| Build and initial screen | 2019-05-01 to 2023-05-23 | Stop unless the one fixed row has at least 20 trades, positive total and annualized return, Sharpe at least 0.5, and maximum drawdown no worse than 35%. |
| Selection confirmation | 2023-05-24 to 2024-10-01 | Recheck the unchanged rule and costs; stop on any failed screen and create no lock. |
| Final protected period | 2024-10-02 to 2026-02-13 | Keep closed until the unchanged rule is locked and the existing walk-forward, robustness and Monte Carlo gates allow the separate protected-test decision. |

All later filters must use only the first two periods until the protected gate
is reached. Any failed or invalid stage stops the chain. A pass only permits
the next recorded stage; it does not prove an edge, authorize another variant,
open the protected period automatically, deploy anything, or permit paper/live
trading.

Because the data came from a legacy archive, the final period can be protected
from this proposal forward but cannot honestly be called historically unseen.
Any result will therefore be candidate evidence with that limitation, not
independent proof of profitability.

## Reuse and implementation boundary if approved

Reuse the existing Databento manifest verification, NYSE session handling,
VectorBT Pro portfolio path, conservative equity costs, durable candidate-run
claim, persistence and artifacts, fixed filter coordinator, protected-test
gate, and dashboard. Add only the MSFT rule/data adapter and the smallest
stage adapters needed to feed existing services. Do not change the common
engine, schema, dashboard, data, framework or execution venues.

## Pre-proposal challenge resolved

- `CHANGED` — duplicate work is excluded: concluded SPYM momentum, SPY
  Donchian and MES ORB will not run again.
- `CHANGED` — the proposal is labelled a single-stock transfer; it does not
  copy MES parameters or claim the paper's cross-stock results.
- `CHANGED` — one long-only fixed rule replaces any grid and avoids assumed
  short availability or borrowing costs.
- `CHANGED` — extended-hours filtering, adjustment uncertainty, bar ambiguity
  and unknown prior inspection are explicit limits.
- `CHANGED` — the last 20% is locked from future inspection, while historical
  independence remains unclaimed.

## Documentation impact

- `AGENTS.md`: not applicable; no permanent operating rule changes.
- `docs/MILESTONES.md`: updated; the completed candidate investigation and
  owner checkpoint must survive compaction.
- `docs/DECISIONS.md`: not applicable until Terry approves, changes or declines
  the proposal.
- ADR, dashboard requirements, `README.md`, `docs/CHAT_HANDOFF.md`, data
  catalog, manifests and runbooks: not applicable; no architecture, public
  orientation, data, deployment or operating procedure changes.
