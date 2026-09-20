# Quant Factory Milestones

This is the operational source of truth for product direction, current status,
ordered work, milestone scope, and acceptance.

## Current phase

| Item | Current truth |
|---|---|
| Goal | Give Terry, the sole operator, the shortest safe way to find or reject a defensible trading edge. |
| Phase | Milestone 25 controlled research is active under Decisions 287 and 294. Milestone 23 remains an eventual pre-paper product gate, not the current queue. |
| Active work | R08: implement and run the owner-approved SPYM intraday-momentum transfer test within fixed evidence boundaries. |
| Finding | MES ORB is concluded and rejected as an edge candidate; it proved early screening, durable results, ranking and dashboard reading, but not the complete filtration chain. Find & Compare is merged, and Terry found the reviewed image good and intuitive. |
| Next action | Finish and review the fixed SPYM adapter, then run one bounded development/reference screen. |
| Blocked | Open-ended optimization, protected-test evaluation, automatic promotion, unapproved parameter changes, paper activation, futures execution, and live trading. Deployment, portability, broad Milestone 23 closure, and paper-runtime work are dormant until their trigger occurs. |

## Product direction and boundaries

- Quant Factory is a private, single-operator research system, not an
  enterprise, SaaS, multitenant, billing, or team product.
- The priority is an operator-usable MVP that produces truthful, reproducible
  evidence. Consult official documentation and established product archetypes,
  then reuse existing Quant Factory code, VectorBT Pro, licensed dependencies,
  approved prototypes, and suitable maintained components before custom work
  or unsupported assumptions.
- The dashboard is the normal operator interface. Decision 291 supersedes only
  Decision 287's good-enough/frozen treatment for the verified selected-run R07
  inspection blocker. The bounded correction does not restore dashboard-first
  sequencing, close Milestone 23, or authorize broad dashboard work. Decision
  292 supersedes only Decision 287's dashboard freeze to permit the bounded
  blueprint and later owner-approved thin essential-beta slices; it does not
  expand Decision 291 or restore dashboard-first sequencing. It does not
  authorize a new framework, global rewrite, deployment or broad polish.
- Fixtures validate infrastructure and are not active profitability candidates.
  Previously inspected data is not independent evidence. Research must reject
  false edges, preserve evidence, and keep strategy and validation logic
  venue-neutral. Research cannot submit venue orders.
- The active path is: attributed candidate → owner-approved hypothesis and
  evidence boundaries → smallest adapter to the existing VectorBT batch path →
  durable results → ranking/filtering → inspection in the existing dashboard.

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R08 | 1 | in_progress | none | MES ORB completed its bounded path and was rejected. Terry approved the SPYM transfer test under Decision 296 on 2026-09-20: use only the checksum-matching owned EQUS.MINI dataset, one fixed intraday rule, and the stated cost and eligibility boundaries. The adapter is in progress; finish/review it, then run one bounded development/reference screen through the existing engine, persistence, ranking/filtering, and dashboard. |
<!-- active-work:end -->

## Current execution path

| Step | Status | Evidence or next action |
|---:|---|---|
| 1. Inventory an attributed candidate | Completed for the current shortlist; reconcile before next cycle | On 2026-09-19 a read-only, source-attributed shortlist recorded ETF market intraday momentum (recommended), turn-of-month (alternative), and pre-holiday effect (alternative). No code, data acquisition, or backtest occurred; no candidate was selected. |
| 2. Approve the hypothesis and boundaries | Approved | Terry approved the SPYM intraday-momentum transfer test and its fixed evidence boundaries on 2026-09-20; see Decision 296 and `docs/strategies/spym-intraday-momentum.md`. |
| 3. Connect it to existing research | In progress | Finish and review the candidate-specific mixed-price adapter using the existing VectorBT research path; do not change the common engine, schema, or dashboard. |
| 4. Persist, rank, and filter results | Pending this candidate | Preserve distinct durable runs and truthful progression through every applicable filter after the bounded SPYM screen; the ORB path proves only early infrastructure behavior. |
| 5. Inspect through the dashboard | Capability merged; the current candidate cycle has not reached this step | Find & Compare and the selected-run correction are merged; Terry found the reviewed Find & Compare image good and intuitive. Persistent deployment is not needed for the current research step. |
| 6. Continue bounded research | Active | Use Milestone 25 safeguards; each new executable candidate needs explicit owner approval and predeclared evidence boundaries. |
| 7. Activate paper trading | Gated | Requires a qualified edge and every Milestone 24 execution gate. |
| 8. Automate paper forward testing | Gated | Milestone 26 follows successful paper activation and reconciliation proof. |
| 9. Consider micro-live trading | Far future | Milestone 27 requires successful paper evidence and separate explicit owner approval. |

## Milestone roadmap

Milestones 1–22 are complete.

| # | Milestone | Acceptance summary | Status |
|---:|---|---|---|
| 16–22 | Infrastructure, persistence, orchestration, lineage, dashboard foundation, equity fixture, and unified validation | Durable records, reproducible evidence, normalized outcomes, and protected-data gates | Complete |
| 23 | End-to-End Equity Research Factory Acceptance | ADR 0008 browser lifecycle, complete operator workflow, renewed Results acceptance, and every objective gate | **Pending eventual pre-paper gate; broad closure work is dormant** |
| 24 | Portable Deployment and Alpaca Paper-Execution MVP | Portable restore and bounded paper workflow after a qualified edge and every execution gate | Preparation retained; portability, deployment and activation dormant |
| 25 | Controlled Equity Strategy Intake, Discovery and Survivor Validation | Approved, attributed ideas become bounded experiments and survivors pass predeclared evidence gates | **In progress; MES ORB rejected, SPYM selected under Decision 296, adapter review in progress; no SPYM run or result claimed** |
| 26 | Automated Alpaca Paper Forward Testing and Reconciliation | Eligibility, deployment, monitoring, reconciliation, recovery, and paper fault injection | Pending |
| 27 | Alpaca Micro-Live Proof and Independent Risk Sentinel | Separate approval, isolated live domain, independent supervision, and failure acceptance | Pending; far future |
| 28–30 | Compliant crypto proof and multi-venue V1 | Legal and operational eligibility, isolated adapters, evidence, reconciliation, and recovery | Deferred |

## Gates and accepted requirements

### Controlled research

Decision 287 permits controlled, bounded, source-attributed research before
Milestone 23 closes. Every executable candidate requires explicit owner approval
of the named hypothesis and predeclared evidence boundaries. Open-ended
optimization or data mining, protected-test inspection, automatic promotion,
paper orders, and live work remain blocked.

### Milestone 23

Milestone 23 remains the eventual complete equity research workflow acceptance
gate before paper activation; this catalog is not the current work queue.
Focused checks protect each changed path now. The full browser/lifecycle,
recovery, device and target matrix resumes only for a concrete blocker, an
actual deployment/runtime change, explicit Milestone 23 closure, a qualified
candidate approaching paper, or an owner request.

Decision 287's narrow research exception does not waive it. A non-programming
operator must be able to launch an approved fixture experiment, monitor it,
inspect provenance, assumptions, charts, signals, trades and validation, compare
and reproduce runs, record a decision, verify lineage, and understand failures
without Python, terminal output, raw CSV/JSON, or SQLite.

Current slices:

- **23A — Scenarios and fixtures:** frozen. **Complete.**
- **23B — Automated full-system acceptance:** supporting evidence implemented;
  preserve the complete scenario inventory and run the full matrix when the
  gate is explicitly resumed.
- **23C-1 — Review/design:** selected-run design approved. A separate scalable
  multi-run design remains pending.
- **23C-2 — Implementation:** durable run tickets are merged. The bounded
  Decision 291 R07 selected-run correction merged through PR #70 at
  `4eaa03c761ffc4e90c4d1cf909c5f62d11bc614f`; its focused, portable
  real-browser, independent-review, and required-CI evidence passed. The
  complete selected-run/Milestone 23 implementation is not claimed.
- **23C-3 — Browser/operator acceptance:** renewed owner acceptance, real-browser
  lifecycle evidence, and the complete workflow remain pending and dormant
  until the gate is resumed.
- **23D — Recovery and integrity:** preserve failure, retry, timeout,
  cancellation, stale-recovery, missing-artifact, and corrupt-lineage coverage.
- **23E — Gate decision:** record an explicit pass or fail after all criteria.
- **23F — Post-acceptance hygiene:** bounded, no-functional-change cleanup only
  after 23E.

Plotly Dash remains the application framework. ADR 0008 requires one persistent
location and shell, permanently mounted
route containers, pathname-driven visibility, page-owned callbacks, and real-
browser lifecycle acceptance. The workflow remains Home → Ideas → Set up → Run
test → Results → Compare. Ideas remains non-executing during this milestone: it
does not retrieve external content, execute code, launch a backtest, approve a
strategy, or place an order.

Decision 278's schema-5 durable ticket core and Run test, historical relaunch,
and reproduction integrations are merged through PRs #35–#38. PR #42 added
claim-core checks to required Portable CI and merged focused claim-aware stale-
recovery evidence; PR #50 added that stale-recovery suite to required Portable
CI. Revision `5462c796809e83634959cbd3e7fa75b81ec2e309` proves canonical-source
implementation and focused/browser-fixture evidence, not current licensed-target
SPYM behavior, production deployment, the complete workflow, or acceptance.

The exact Milestone 23 checklist, target-evidence audit, and append-only incident
record live in
[`docs/milestones/milestone-23-acceptance.md`](milestones/milestone-23-acceptance.md).

### Paper and live trading

Paper activation requires explicit owner approval, a qualified edge, verified
account ownership, isolated credentials, a fixed paper endpoint, worker
identity, idempotent submission, broker reconciliation, restart recovery,
duplicate prevention, capacity controls, complete audit evidence, and
fail-closed behavior. Paper and live are separate security domains. Live
additionally requires successful paper evidence, separate later owner approval,
isolated live credentials/state/deployment, authenticated private networking,
and an independent Risk Sentinel.

### Accepted but not active

- **Selected-run Results:** Decisions 279–282 withdrew the former acceptance and
  approved a chart-first replacement: persisted price bars and exact entry/exit
  events, linked grouped trades, direct pan and wheel zoom, separate Bars
  (`1m`/`5m`/`15m`/`1D`) and View (`Full run`/`1D`/`1W`/`1M`) controls,
  resettable resizable chart/report panels, normal-flow Metrics and Trades,
  responsive stacking, and readable trade typography. Decision 291 authorizes
  the narrow R07 usability correction using the existing page; it merged
  through PR #70 at `4eaa03c761ffc4e90c4d1cf909c5f62d11bc614f` after
  focused, portable real-browser, independent-review, and required-CI evidence
  passed. It is not deployed, target-validated, renewed-owner-accepted, full
  beta, or Milestone 23 completion. Final
  palette selection remains deferred.
- **Multi-run analysis:** hundreds or thousands of persisted runs must be
  aggregated, sliced, ranked, filtered, and selected by return, drawdown,
  profitable-trade measures, and other useful evidence. One run opens in
  Results; multiple selections feed Compare. The bounded Find & Compare design
  and implementation are merged. Standard metric labels merged through PR #77
  at `9495a36a45af2bfe1288ab7cba840a4eed8ef54e`; broader additions are
  deferred unless research exposes a blocker.
- **Exact-repeat cache:** Decision 283 requires faster exact repeats while every
  request keeps a distinct durable ticket and lifecycle. Reuse must be validated,
  traceable, isolated by every result-changing input and protected-data boundary,
  and never count as independent evidence. Architecture, storage, invalidation,
  eviction, sequencing, and Reproduce behavior remain undecided.
- **Setup authoring:** review at `6b98d7712f571da4670e51f7fe2f4c828dadca1d`
  found no approved editable field consumed by a current runner. PR #23 was
  closed instead of presenting a synthetic fee edit as real capability. The
  truthful select-existing path remains; editable authoring is unclaimed and is
  not by itself a Milestone 23 closure blocker.

## Evidence and history

### MES ORB screening — 2026-09-19

- Four successful isolated runs persisted 32 ranked rows: two references and 30
  matrix variants. The 30-minute, zero-offset references matched their matrix
  rows exactly in both directions.
- R07 is concluded: MES ORB is rejected as an edge candidate and retained only
  as infrastructure and historical research evidence.
- Every baseline variant screened out. Best long: 15 minutes/2 ticks, 5.42477%
  return, 0.458798 Sharpe, 4.19045% maximum drawdown, and 1,227 trades. Best
  short: 30 minutes/0 ticks, -5.52201% return, -0.453648 Sharpe, 7.55715%
  maximum drawdown, and 1,049 trades.
- Every run persisted seven registered artifacts and an integrity manifest. An
  initial disk-full attempt was partial invalid evidence and was excluded; a
  fresh isolated retry succeeded.
- The catalog extent was already inspected. These results are development and
  reference evidence, not an independent observation, protected test, qualified
  edge, promotion, deployment, paper, futures-execution, or live authority.
- Evidence and checksums from the successful isolated screening runs are
  preserved in owner-only external host storage outside production and remain
  undeployed. Checksum, database integrity, artifact structure, metric agreement
  and a disposable current-main application read path passed on 2026-09-20.
  Decision 291's bounded truthful-rendering correction merged through PR #70 at
  `4eaa03c761ffc4e90c4d1cf909c5f62d11bc614f`; focused, portable
  real-browser, independent-review, and required-CI evidence passed. Deployment,
  target validation, operator acceptance, full beta, and Milestone 23
  completion remain pending.

### Candidate shortlist investigation — 2026-09-19

- A read-only, source-attributed shortlist assessed [ETF market intraday
  momentum](https://doi.org/10.1016/j.jfineco.2018.05.009) (recommended),
  [turn-of-month](https://doi.org/10.2469/faj.v64.n2.11) (alternative), and
  [pre-holiday effect](https://doi.org/10.1111/j.1540-6261.1990.tb03731.x)
  (alternative).
- Status and reason: completed inventory only; no candidate was selected,
  because Terry's approval and fixed evidence boundaries were still pending.
- Data limitation measured at review: intraday momentum lacked sufficient
  catalogued ETF minute history; turn-of-month and pre-holiday lacked a
  suitable catalogued multi-year adjusted broad-market dataset. No code was
  written, no market data was acquired, and no candidate was backtested. The
  shortlist is research context, not edge or profitability evidence. Reconcile
  this record before commissioning another candidate inventory or
  implementation.

### Find & Compare — 2026-09-20

- The bounded reuse-first implementation merged through PR #74 at
  `5db5784cea925f4484f06eb78de9aea5b8e4acf2`; focused tests, a focused browser
  check, independent review, and required CI passed.
- Standard trader-facing metric labels merged through PR #77 at
  `9495a36a45af2bfe1288ab7cba840a4eed8ef54e`.
- Terry reviewed the image and described it as good and intuitive. This accepts
  the reviewed direction, not deployment, the full Milestone 23 matrix, or
  complete workflow acceptance.
- R05 is concluded as a merged source slice. Persistent deployment and broad
  Milestone 23 closure are dormant rather than active follow-up work.

### Repository and CI history

- **R01 — completed 2026-09-18:** Decision 275 published the reviewed,
  clean-history public repository as canonical while retaining the original as
  a private read-only archive. The older private preview/runtime was not
  modified.
- Decision 276 keeps required checks and admin enforcement enabled while
  `strict`/up-to-date remains disabled. Independent green pull requests need not
  queue behind refresh builds; overlapping or dependent work still integrates
  serially and is retested against resulting `main`.

Readable completed incident history is retained in
[`docs/milestones/milestone-23-acceptance.md`](milestones/milestone-23-acceptance.md#incident-history).

## Governing references

- [Owner decisions](DECISIONS.md), especially Decisions 278–294.
- [Milestone 23 acceptance record](milestones/milestone-23-acceptance.md).
- [Dashboard product requirements](dashboard-product-requirements.md).
- [MES ORB specification](strategies/mes-opening-range-breakout.md).
- [ADR 0008: dashboard architecture](architecture/0008-dashboard-mounted-route-architecture.md).
- [ADR 0011: durable research run tickets](architecture/0011-durable-research-launch-claims.md).
