# ADR 0005: Execution adapters and initial venue sequence

- **Status:** Accepted, amended 2026-07-14 for Milestone 21E
- **Date:** 2026-07-13
- **Scope:** Research portability, order contracts, execution adapters, initial paper and micro-live venues
- **Supersedes:** The provisional SPYM language in the README, AGENTS.md, and ADR 0003 infrastructure-first dashboard product
- **Does not change:** Current milestone ordering or Milestone 20 implementation scope

## Context

Quant Factory must support research across equities, ETFs, futures, crypto,
options, and foreign exchange without allowing venue-specific APIs to leak into
strategy logic, validation, evidence, or research accounting.

The execution path also needs a deliberately simple first proof. The purpose of
the first connector is to validate the common execution lifecycle, accounting,
reconciliation, risk controls, persistence, and operator workflow. It is not a
declaration that the first connected market has the highest long-term research
priority or profitability potential.

SPY is already the primary liquid research benchmark. Its price makes it less
suitable for the first tightly bounded whole-share micro-live proof. SPYM remains
a valid low-cost Databento ingestion and infrastructure fixture, but it is not
the forward-test instrument. Milestone 21E selected SCHX for the future
broad-market whole-share paper and micro-live execution fixture after comparing
SCHX and SCHB liquidity, spreads, affordability, Databento coverage, symbology,
corporate actions and estimated data costs.

## Decision

### 1. Preserve a market-agnostic research core

Quant Factory remains market-agnostic at the research, validation, and evidence
layers.

Strategy, research, validation, evidence, and portfolio-analysis code must not
depend directly on Alpaca, Hyperliquid, Interactive Brokers, or another broker
or exchange API.

Market-specific facts such as session calendars, contract multipliers, tick
sizes, lot rules, and supported order types remain explicit typed inputs or
instrument metadata. They must not be inferred silently from a broker adapter.

### 2. Use a broker-independent execution contract

The common execution interface produces a broker-independent order model, such
as `OrderIntent`.

An order intent describes the requested economic action without containing a
venue SDK object or venue-specific request structure. At minimum, the future
contract is expected to identify:

- instrument;
- side;
- quantity and quantity unit;
- order type;
- limit or stop price when applicable;
- time in force;
- strategy and run identity;
- paper or live execution domain;
- risk and idempotency metadata.

Execution adapters translate the common intent into venue-specific API
requests, reconcile acknowledgements, fills, cancellations, rejections, and
positions, and return broker-neutral execution records.

No venue adapter becomes authoritative for research evidence or strategy
identity.

### 3. First connector: Alpaca Paper Trading

The first execution adapter will target Alpaca Paper Trading.

Its purpose is to prove:

- order-intent translation;
- paper-only credential isolation;
- submission and acknowledgement;
- fill and cancellation reconciliation;
- position and cash reconciliation;
- durable operator events;
- restart and duplicate-submission safety;
- risk controls and kill-switch behavior;
- dashboard operation.

This decision does not authorize implementation during Milestone 20 and does
not bypass the existing paper/live isolation ADR or later milestone gates.

### 4. Approved equity fixture structure

The first equity workflow uses whole shares and separates instruments by role:

- **Broad-market whole-share forward-test instrument:** SCHX. SCHB remains a
  close broad-market comparison symbol and portability reference, but Milestone
  21E evidence did not materially favor it over SCHX.
- **Growth/Nasdaq-like ETF portability fixture:** SCHG.
- **Small-cap ETF portability fixture:** SCHA.
- **Single-stock portability fixtures:** MSFT and AAPL. These are approved for
  historical and paper testing, but not presumed suitable for tightly bounded
  micro-live testing because one whole share may require materially more
  capital.
- **Current ingestion fixture:** SPYM remains approved for proving Databento
  acquisition, validation, checksum-gated reuse, lineage, and dashboard health.
  It is not presumed to be the final paper or micro-live instrument.

Whole shares are retained for the first proof because they simplify:

- quantity and cash accounting;
- order and fill reconciliation;
- deterministic tests;
- broker portability;
- comparison between paper and small-money execution;
- handling of partial fills and residual positions.

Fractional-share support may be added behind the same common interface, but it
is not required for the initial forward-test path.

### 5. Instrument evidence remains separate

SPY remains:

- the primary research benchmark;
- a highly liquid reference instrument;
- the likely first listed-options instrument later.

Research, validation, liquidity, and execution evidence for one instrument must
never be treated as evidence for another, even where holdings or price movement
appear similar.

Each ETF or stock used beyond deterministic infrastructure testing requires its
own:

- historical dataset identity and provider lineage;
- corporate-action and ticker-history review;
- liquidity and spread evidence;
- execution assumptions;
- paper reconciliation;
- explicit promotion record before micro-live use.

Similarity of mandate, holdings, or exposure is not evidence equivalence.

### 6. Final forward-test selection

Milestone 21E compared SCHX and SCHB using current evidence for:

- whole-share price and bounded capital requirement;
- historical data coverage and continuity;
- regular-session liquidity and volume;
- typical and stressed bid-ask spreads;
- broker availability and whole-share execution behavior;
- paper-versus-model reconciliation.

SCHX is selected because it preserves the documented preference, remains
affordable for one- or two-share testing, has the same 0.03% 30-day median
bid/ask spread evidence as SCHB, has higher current volume and assets under
management, resolves cleanly in Databento `EQUS.MINI`, and has low estimated
one-minute historical-data cost. SCHB has comparable affordability and broader
total-market exposure, but it did not present a material operational advantage.

This selection is not profitability approval and does not promote a strategy.
Before paper or live orders are submitted, the broker adapter and dashboard
workflow still require their own later milestone acceptance.

### 7. Second connector: Hyperliquid testnet

Hyperliquid testnet was the preferred second execution adapter in the
historical design. ADR 0007 and ADR 0009 now govern venue order; WEEX is the
conditional current preference subject to eligibility checks.

It is intended to validate that the common execution lifecycle also works for:

- cryptocurrency markets;
- continuous 24/7 operation;
- exchange-specific precision and minimum-order rules;
- different position, funding, and reconciliation behavior.

The adapter sequence does not establish crypto as the second research priority.

### 8. Interactive Brokers is deferred, not rejected

Interactive Brokers remains an important future connector for futures,
options, equities, and FX.

It is intentionally deferred because its operational and integration complexity
would add unnecessary risk to the first execution proof. Deferral is not a
rejection or a decision against future IBKR use.

### 9. Futures and FX

Futures, including MES, remain a target market. Futures execution integration
will follow proof of the common execution lifecycle.

FX remains a supported target asset class, but venue selection is intentionally
undecided.

No broker should be selected merely to make the architecture appear complete.

### 10. Connector sequence is not research priority

Execution connector order and research-market priority are separate decisions.

The connector sequence proves execution plumbing with controlled operational
complexity. It does not decide which asset class, market, instrument, or strategy
will ultimately produce the strongest validated opportunities.

## Consequences

- A venue SDK may appear only inside its adapter and venue-specific integration
  boundary.
- Common strategy and validation tests must run without broker credentials or
  broker SDK objects.
- Broker-neutral order, execution, position, and reconciliation models must be
  defined before the first production adapter.
- Alpaca paper and future live credentials remain isolated under ADR 0003.
- SPYM remains a valid ingestion fixture with its own Databento dataset identity,
  but it is no longer locked as the first micro-live instrument.
- SCHX is the selected broad-market whole-share paper and micro-live execution
  fixture for later milestones. SCHB remains a comparison and portability
  reference.
- SCHG and SCHA are retained as ETF portability fixtures.
- MSFT and AAPL remain historical and paper portability fixtures unless a later
  explicit capital decision approves whole-share micro-live use.
- Existing SPY, MES, and other historical work retains its current
  classification and is not promoted by this decision.
- Fractional quantities must be represented explicitly if later supported; they
  must not alter the whole-share first-proof acceptance criteria.
- Hyperliquid and IBKR adapters must implement the same common lifecycle rather
  than introducing parallel strategy or evidence paths.

## Deferred questions

This ADR does not decide:

- the final `OrderIntent` schema;
- the internal event-bus or queue implementation;
- Alpaca order-type policy and timeout values;
- the precise small-money allocation;
- whether MSFT or AAPL will ever be approved for whole-share micro-live use;
- Hyperliquid live deployment;
- the IBKR implementation milestone;
- an FX venue.

Those decisions require their own bounded implementation or verification work.
