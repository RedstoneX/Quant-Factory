# Quant Factory Milestones

This is the single operational source of truth for product direction, current
status, ordered work, milestone scope, and acceptance.

## Product direction

Quant Factory is infrastructure first, evidence first, dashboard first, and
operating-proof first. Plotly Dash is the normal operator interface; Python,
terminal output, SQLite, CSV, JSON, and logs are implementation details.

The factory must reject false edges, preserve reproducible evidence, paper
trade only qualified strategies, reconcile model and venue state, and expose
capital only after explicit human approval and independent risk controls.
Fixtures validate infrastructure and are not active profitability candidates.

## Current phase

Milestones 1–22 are complete. Milestone 23 is pending dashboard implementation,
browser acceptance, and explicit operator acceptance. Automated research and
recovery evidence exists, but tests and reachability do not complete the gate.
Systematic discovery, optimization, protected-test evaluation, paper-order
activation, and live work remain blocked except for the bounded offline and
deployment preparation already authorized and retained.

Decision 274 sets the current order:

1. Complete Milestone 23 dashboard and operator acceptance.
2. Conduct controlled strategy intake and research under Milestone 25 until a
   defensible edge qualifies.
3. Resume remaining Milestone 24 paper activation only after the qualifying
   edge and all execution gates pass.
4. Run automated paper forward testing and reconciliation under Milestone 26.
5. Treat Milestone 27 micro-live testing as far-future work requiring separate
   explicit owner approval.

Decision 275 established the sanitized clean-history public repository without
changing this product sequence. The private archive is historical evidence;
the public repository is the forward source of truth.

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R05 | 1 | in_progress | none | Implement the approved Milestone 23C dashboard direction, then obtain browser and operator acceptance |
| R01 | 2 | in_progress | none | Complete public-repository required-check enforcement proof with strict/up-to-date disabled |
| R06 | 9 | pending | none | Preserve completed paper-observer preparation; authenticated runtime work remains deferred under Decision 274 |
<!-- active-work:end -->

Readable completed incident history is retained in
[`docs/milestones/milestone-23-acceptance.md`](milestones/milestone-23-acceptance.md#incident-history).

## Dashboard acceptance contract

Before strategy discovery resumes, a non-programming operator must be able to
inspect health; create or select an approved configuration; launch a fixture
experiment; observe status; inspect provenance, assumptions, charts, signals,
trades, and validation evidence; compare and reproduce runs; record a review;
verify lineage; and understand the next safe action without using implementation
tools.

ADR 0008 governs the implementation: one persistent `dcc.Location`, one
permanent shell, permanently mounted route containers, pathname-driven
visibility, page-owned callbacks, and browser-lifecycle acceptance. Tests do
not replace direct links, refresh, back/forward, active-navigation, selected-
state, responsive-layout, and renderer-error checks in a real browser.

The Milestone 23C flow is Home → Ideas → Set up → Run test → Results → Compare.
Ideas is non-executing during this milestone. It must not retrieve external
content, execute code, launch a backtest, approve a strategy, or place an order.

## Operational milestone sequence

| # | Milestone | Acceptance summary | Status |
|---:|---|---|---|
| 16–22 | Infrastructure, persistence, orchestration, lineage, dashboard foundation, equity fixture, and unified validation | Durable records, reproducible evidence, normalized outcomes, and protected-data gates | Complete |
| 23 | End-to-End Equity Research Factory Acceptance | ADR 0008 browser lifecycle and complete operator workflow pass; explicit operator approval recorded | **Pending — hard discovery gate** |
| 24 | Portable Deployment and Alpaca Paper-Execution MVP | Portable restore plus bounded paper workflow after a qualified edge and every execution gate | Preparation retained; activation deferred |
| 25 | Controlled Equity Strategy Intake, Discovery and Survivor Validation | Approved, attributed ideas become bounded experiments; survivors pass predeclared evidence gates | Pending — follows M23 |
| 26 | Automated Alpaca Paper Forward Testing and Reconciliation | Eligibility, deployment, monitoring, reconciliation, recovery, and paper fault injection pass | Pending |
| 27 | Alpaca Micro-Live Proof and Independent Risk Sentinel | Separate approval, isolated live domain, independent supervision, and failure acceptance pass | Pending — far future |
| 28–30 | Compliant crypto proof and multi-venue V1 | Legal/operational eligibility, isolated adapters, evidence, reconciliation, and recovery pass | Deferred |

## Milestone 23 slices

- **23A — Scenarios and fixtures:** frozen. **Complete.**
- **23B — Automated full-system acceptance:** supporting evidence implemented;
  keep the complete scenario inventory green.
- **23C-1 — Review/design:** approved direction exists; complete artifact
  approval remains pending.
- **23C-2 — Implementation:** authorized but not complete. Preserve ADR 0008,
  Plotly Dash, VectorBT Pro, and service boundaries.
- **23C-3 — Browser/operator acceptance:** pending implementation and explicit
  operator approval.
- **23D — Recovery and integrity:** preserve failure, retry, timeout,
  cancellation, stale recovery, missing-artifact, and corrupt-lineage coverage.
- **23E — Gate decision:** record explicit pass or fail. No discovery or order
  activation before a pass.
- **23F — Post-acceptance hygiene:** bounded no-functional-change cleanup only
  after 23E.

## Milestone 24 execution gates

Research cannot submit venue orders. Paper activation requires a qualified
edge plus verified account ownership, isolated credentials, fixed paper
endpoint, worker identity, idempotent submission, broker reconciliation,
restart recovery, duplicate prevention, capacity controls, complete audit
evidence, and fail-closed behavior. Paper and live remain separate security
domains. Live additionally requires successful paper evidence, separate owner
approval, isolated live credentials/state/deployment, private authenticated
networking, and an independent Risk Sentinel.

## Hard governance rule

No systematic strategy discovery, profitability search, candidate
optimization, protected-test evaluation, paper-order activation, or live work
may begin before its explicit milestone gate and approval. The current bounded
milestone is **23 — End-to-End Equity Research Factory Acceptance**.
