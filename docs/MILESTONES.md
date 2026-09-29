# Quant Factory Milestones

This file is the **only authority for current product direction, active work,
sequencing, blockers, and milestone status**. Historical evidence remains in
`docs/DECISIONS.md`, milestone records, strategy specifications, and Git
history; those supporting documents do not create a competing queue.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable trading edges. |
| Secondary goal | Convert qualified edges into consistent income using capital-efficient execution; approximately $100/day is a later scaling objective, not a forced daily quota. |
| Phase | **Backend-first intraday edge discovery.** The generic research pipeline is substantially built and connected. |
| Active work | Identify and bound a genuinely new short-duration S&P/Nasdaq directional hypothesis, then run it through the existing factory after the required owner approval. |
| Existing assets | VectorBT Pro research, screening, OOS, walk-forward, robustness, Monte Carlo, protected-test gates, persistence, lineage, candidate launch claims, and persisted filter handoffs exist. Validated MES/MNQ 5-minute history covers roughly 2019-05 through 2026-02. |
| Known product gap | The current dashboard has useful technical evidence but the owner no longer considers it sufficiently intuitive/viable as the long-term interface. The successful chart-first prototype remains the UX reference. |
| Deferred | Broad dashboard repair, deployment, portability, options/futures broker expansion, paper activation, and live work unless they become a measured blocker or the later phase activates them. |
| Next action | Perform a prior-work/source check and present one short-duration S&P/Nasdaq directional hypothesis with fixed evidence boundaries and existing-data fit. |
| Hard boundaries | No blind optimization, protected-test inspection, automatic promotion, paid data without a defined experiment, paper/live orders, or capital exposure. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R09 | 1 | in_progress | none | Backend research infrastructure is connected; owner reset on 2026-09-29 makes edge discovery the active priority and defers non-blocking dashboard work. |
<!-- active-work:end -->

## Operating sequence

### Phase 1 — Edge discovery — ACTIVE

Research the underlying market behavior first.

Initial market universe:

- S&P 500 exposure: MES and SPY;
- Nasdaq-100 exposure: MNQ and QQQ.

Existing validated MES/MNQ data should be reused before buying additional data
when it can answer the research question.

Each executable candidate requires:

1. named hypothesis and source/rationale;
2. instrument and timeframe;
3. entry and exit logic;
4. bounded parameter ranges;
5. execution/cost assumptions;
6. training/OOS/protected-data boundaries;
7. predeclared screening and validation conditions;
8. explicit owner approval before candidate launch.

Only one principal candidate family should be active unless independent
parallel work clearly reduces time/cost without duplicating the same question.

### Phase 2 — Validation

Survivors use the existing connected factory:

**screening -> chronological OOS -> walk-forward -> parameter/regime robustness
-> Monte Carlo -> protected-test gate.**

Do not rebuild these engines merely because a new strategy uses them. Repair
only a measured adapter/integration defect encountered by the real candidate.

The first objective is positive, stable out-of-sample expectancy with
acceptable drawdown and robustness. Do not screen for a requirement to make
$100 every individual day.

### Phase 3 — Execution-vehicle comparison

Only after a directional edge survives enough evidence to justify execution
research, determine the most capital-efficient way to express it.

Relevant initial vehicles may include:

- MES;
- MNQ;
- SPY 0DTE long calls/puts;
- QQQ 0DTE long calls/puts;
- SPXW 0DTE long calls/puts.

Do not require all vehicles for every edge.

The initial 0DTE use case is simple leveraged directional exposure with premium
risk capped at the amount paid, not a complex volatility/spread platform.
Contract selection may use ATM/modestly ITM location, delta, liquidity,
bid/ask spread, quote size, and account-size constraints. Those variables choose
the implementation; they do not define the directional edge.

Historical options research must use defensible actual quote/execution evidence.
Before paying for Alpaca OPRA or Databento OPRA, estimate the exact bounded data
need and choose the cheaper sufficient source. Do not download the full options
market by default.

### Phase 4 — Trader-usable dashboard

The present dashboard is **not accepted as the long-term usable interface**.
Earlier browser, integrity, and implementation evidence remains valid for what
it actually proved; the owner's current usability judgment supersedes any claim
that the present product is sufficiently intuitive for normal operation.

Dashboard work resumes when either:

1. a promising/qualified edge makes an operator UI valuable; or
2. a demonstrated UI deficiency materially blocks research inspection or
   decision-making.

The successful chart-first prototype and Find & Compare research are retained
as design evidence. **Reproduce the UX, not the prototype code.**

Reuse mature components and the existing backend. Custom code should primarily
bind Quant Factory-specific state/evidence to maintained chart, grid, layout,
tab, filtering, and panel components. No greenfield frontend or custom generic
chart/grid/docking system without a measured gap and owner-approved scope.

### Phase 5 — Paper operation

After a qualified edge and minimum usable operator interface exist, resume the
paper path.

Alpaca remains the preferred first paper venue where it supports the required
instrument because the existing project already contains broker-neutral
contracts, journal/reconciliation/recovery work, and an Alpaca paper boundary.

The current Alpaca adapter is intentionally restricted to whole-share
equity/ETF orders. Extend it for options only when a qualified candidate
requires options paper execution. Do not build option order infrastructure to
perform historical options research.

Interactive Brokers, NautilusTrader, or another futures stack is justified only
if surviving evidence requires futures execution or another venue capability.
Do not add it for future optionality.

Paper activation still requires explicit owner approval and all credential,
identity, idempotency, reconciliation, restart, duplicate-prevention, capacity,
audit, and fail-closed gates.

### Phase 6 — Live operation

Dormant. Requires successful paper evidence, separate owner approval, isolated
live credentials/state/deployment, deterministic risk controls, and an
independent Risk Sentinel.

## Current implementation truth

### Research backbone — reuse, do not rebuild

Implemented and tested infrastructure includes:

- typed market-data/provider/validation layers;
- VectorBT Pro experiment execution;
- strategy contracts and registry;
- durable research launch claims;
- screening;
- chronological OOS;
- walk-forward;
- parameter/regime robustness;
- Monte Carlo;
- protected-data gating;
- SQLite persistence, artifacts, checksums, lineage, and review records;
- persisted stop-or-advance filter coordination;
- selected-run Results and Find & Compare implementation/evidence.

Implementation presence is not profitability evidence.

### Data

Validated existing research assets include:

- MES 5-minute Databento history, roughly 2019-05-05 through 2026-02-13;
- MNQ 5-minute Databento history, roughly 2019-05-05 through 2026-02-13;
- M2K and MSFT validated legacy history;
- limited SPY one-minute Alpaca IEX history;
- SPYM operational fixture history.

QQQ and historical listed-options datasets are not currently catalogued as
validated research assets. Acquire them only for a defined experiment.

### Execution

Broker-neutral execution contracts already support contract quantities.
Existing Alpaca paper code is preparation for a conservative whole-share
equity/ETF subset; it is not an options adapter and does not authorize paper
orders.

## Milestone status

Milestones 1–22 remain completed historical infrastructure work.

| Milestone | Current status |
|---|---|
| M23 — Research Factory / dashboard acceptance | Technical evidence retained; formal closure deferred. Historical owner acceptance is not a current claim that the UI is sufficiently usable. M23 does not block bounded edge research; relevant safety/operability gates remain before paper. |
| M24 — Portable deployment / Alpaca paper preparation | Preparation retained; deployment and activation dormant. |
| M25 — Controlled strategy intake and edge validation | **ACTIVE**, refocused on short-duration S&P/Nasdaq edge discovery. |
| M26 — Automated paper forward testing/reconciliation | Pending a qualified edge, minimum usable UI, and paper gates. |
| M27 — Micro-live / independent Risk Sentinel | Pending; far future. |
| M28–M30 — Additional venues/asset classes | Deferred until evidence creates a real requirement. |

## Prior work that must not be repeated blindly

- MES opening-range breakout screening is concluded and rejected as an edge
  candidate; retain it as infrastructure/reference evidence.
- SPYM intraday momentum and SPY Donchian/RSI work are historical fixture or
  candidate evidence, not current profitability candidates.
- The MSFT five-minute ORB transfer proposal was withdrawn as unnecessary
  repeated strategy-family work.
- The dashboard design research succeeded in establishing an intuitive
  chart-first UX direction, but custom prototype/application duplication was
  not the economical implementation path.

Before commissioning new research, reconcile these records and any later
candidate history.

## Gates retained

- Research never submits venue orders.
- Fixtures/previously inspected data are not independent edge evidence.
- Protected data cannot participate in parameter or candidate selection.
- No automatic promotion.
- No credentials or paid data without the active requirement.
- Paper and live are separate security domains.
- Live capital requires separate owner authorization.

## Supporting records

Read only when the task needs them:

- `docs/DATA_CATALOG.md` and `docs/DATA_SOURCES.md` — dataset/provider facts;
- `docs/milestones/milestone-23-acceptance.md` — historical M23 evidence and
  incident record;
- `docs/QUANT_FACTORY_DASHBOARD_UI_DIRECTION.md` — retained dashboard UX
  specification;
- `review/dashboard-integration/**` on its review branch — retained prototype
  and integration evidence;
- strategy specifications under `docs/strategies/`;
- accepted ADRs for architecture relevant to the task.
