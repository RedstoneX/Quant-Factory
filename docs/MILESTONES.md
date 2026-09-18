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
objective technical evidence, and renewed operator acceptance. Decision 279
records the owner's rejection of the current Results-page comprehension and
flow and supersedes Decision 277's acceptance for that experience. Decision
280 accepts a chart-first replacement direction: a truthful selected-run price
chart with persisted entry/exit markers is primary and links to a grouped trade
ledger. TradingView's backtesting Strategy Report is the primary UX reference;
QAMC informs panel, resizing, and link mechanics only, not information density.
Decision 281 accepts the validated preview's separate Bars and View controls,
truthful interval aggregation, exact trade-event preservation, resettable
desktop resizing, normal-flow report content, responsive stacking, and trade
typography that is visibly larger and more readable while deferring final
palette selection. The remaining
detailed specification or mockup, implementation, deployment, tests, and
renewed operator acceptance remain pending. Decision 278 accepts ADR 0011's
safer durable run-ticket architecture and
authorizes implementation, but that implementation and its required evidence
remain pending. Systematic discovery, optimization, protected-test evaluation,
paper-order activation, and live work remain blocked except for the bounded
offline and deployment preparation already authorized and retained.

Decision 274 sets the current order:

1. Complete the remaining Milestone 23 dashboard gates, including the detailed
   Decisions 280–281 chart-first Results specification, implementation,
   evidence, and renewed owner acceptance.
2. Conduct controlled strategy intake and research under Milestone 25 until a
   defensible edge qualifies.
3. Resume remaining Milestone 24 paper activation only after the qualifying
   edge and all execution gates pass.
4. Run automated paper forward testing and reconciliation under Milestone 26.
5. Treat Milestone 27 micro-live testing as far-future work requiring separate
   explicit owner approval.

Decision 275 is implemented without changing this product sequence. The
sanitized clean-history public repository is canonical; the original remains a
private, read-only historical archive, and the production runtime was not
modified. Decision 276 permanently keeps required checks and admin enforcement
while setting `strict`/up-to-date to false unless the owner changes it, so
independent green pull requests do not queue behind refresh builds. Dependent
or overlapping work still integrates serially and is retested against the
resulting `main`.

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R05 | 1 | in_progress | none | Complete and obtain owner approval for the detailed Decisions 280–281 chart-first Results specification/mockup, then implement and validate it; preserve accepted ADR 0011 durable run tickets and prove the remaining browser, workflow, failure-handling, licensed-target, test, documentation/status, and renewed operator-acceptance gates; editable/new Setup authoring remains unclaimed because no approved current fixture exposes a runner-consumed editable field |
| R06 | 9 | pending | none | Preserve completed paper-observer preparation; authenticated runtime work remains deferred under Decision 274 |
<!-- active-work:end -->

## Completed repository remediation

- **R01 — completed 2026-09-18:** published the reviewed clean-history
  repository at the canonical public name; retained the original as a private,
  read-only historical archive; preserved the all-rights-reserved/no-license
  posture; proved required-check enforcement with controlled PR #1; and proved
  non-strict independent-PR throughput with PRs #2 and #3. The cutover did not
  modify the production runtime or change the Milestone 23 gate.

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

### Verified Setup-authoring limitation — 2026-09-18

At public revision `6b98d7712f571da4670e51f7fe2f4c828dadca1d`,
review of the accepted fixture specifications and launch paths found no
approved editable configuration field that a current runner consumes. The
[SPYM 21C parameter definitions](../strategies/spym_rsi_mean_reversion_fixture.py)
are fixed, single-value, and non-optimizable; its
[runner](../prefect_spike/spym_vectorbt_fixture.py) uses the fixed SPYM
market-data, parameter, and execution helpers. The
[generic deterministic Prefect fixture](../prefect_spike/fixture_flow.py)
receives saved parameter and execution objects but does not use variants to
determine its execution result. [PR #23](https://github.com/RedstoneX/Quant-Factory/pull/23)
was therefore closed rather than presenting a synthetic fee edit as supported
operator capability.

This is a verified capability limitation, not a new owner decision and not by
itself a Milestone 23 closure blocker. The Tier 1 contract above requires the
operator to “create or select” an approved configuration, and current `main`
retains the truthful select-existing path. Editable/new Setup authoring remains
unclaimed. Implementing it requires a separately accepted, bounded contract
whose actual fixture runner consumes the exposed field; no such runner change
is proposed or authorized here.

## Operational milestone sequence

| # | Milestone | Acceptance summary | Status |
|---:|---|---|---|
| 16–22 | Infrastructure, persistence, orchestration, lineage, dashboard foundation, equity fixture, and unified validation | Durable records, reproducible evidence, normalized outcomes, and protected-data gates | Complete |
| 23 | End-to-End Equity Research Factory Acceptance | ADR 0008 browser lifecycle, complete operator workflow, renewed Results-page acceptance, and every objective gate pass | **Pending — technical hard discovery gate** |
| 24 | Portable Deployment and Alpaca Paper-Execution MVP | Portable restore plus bounded paper workflow after a qualified edge and every execution gate | Preparation retained; activation deferred |
| 25 | Controlled Equity Strategy Intake, Discovery and Survivor Validation | Approved, attributed ideas become bounded experiments; survivors pass predeclared evidence gates | Pending — follows M23 |
| 26 | Automated Alpaca Paper Forward Testing and Reconciliation | Eligibility, deployment, monitoring, reconciliation, recovery, and paper fault injection pass | Pending |
| 27 | Alpaca Micro-Live Proof and Independent Risk Sentinel | Separate approval, isolated live domain, independent supervision, and failure acceptance pass | Pending — far future |
| 28–30 | Compliant crypto proof and multi-venue V1 | Legal/operational eligibility, isolated adapters, evidence, reconciliation, and recovery pass | Deferred |

## Milestone 23 slices

- **23A — Scenarios and fixtures:** frozen. **Complete.**
- **23B — Automated full-system acceptance:** supporting evidence implemented;
  keep the complete scenario inventory green.
- **23C-1 — Review/design:** Decisions 280–281 accept the chart-first Results
  direction and the validated preview controls and layout constraints. The
  remaining detailed responsive specification or mockup and its owner approval
  remain pending before broad implementation.
- **23C-2 — Implementation:** accepted ADR 0011 durable run-ticket work remains
  authorized but not complete. Broad Results redesign waits for the detailed
  Decisions 280–281 specification approval and must preserve ADR 0008, Plotly
  Dash, VectorBT Pro, and service boundaries.
- **23C-3 — Browser/operator acceptance:** renewed owner acceptance of the
  implemented replacement plus real-browser lifecycle and complete end-to-end
  workflow evidence remain pending.
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
