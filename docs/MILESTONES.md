# Quant Factory Milestones

This is the operational source of truth for product direction, current status,
ordered work, milestone scope, and acceptance.

## Current phase

| Item | Current truth |
|---|---|
| Goal | Give Terry, the sole operator, the shortest safe way to find or reject a defensible trading edge. |
| Phase | Milestone 25 controlled research is active under Decision 287. Milestone 23 technical and operator acceptance remains pending. |
| Active work | R07: validate and inspect the approved MES five-minute opening-range breakout (ORB) path using the existing research system; R05 is the next repository-local work for the owner-accepted economical dashboard direction. |
| Finding | Reference parity passed, but all 30 bounded baseline ORB variants screened out on already-inspected development/reference data. No edge qualified. |
| Next action | R05: produce the small connected-screen blueprint and bound the first essential beta slice under Decision 292. R07's backed-up private deployment, target validation, and operator inspection remain separately unauthorized and target-dependent. |
| Blocked | Open-ended optimization, protected-test evaluation, automatic promotion, paper activation, futures execution, and live trading. |

## Product direction and boundaries

- Quant Factory is a private, single-operator research system, not an
  enterprise, SaaS, multitenant, billing, or team product.
- The priority is an operator-usable MVP that produces truthful, reproducible
  evidence. Reuse existing Quant Factory code, VectorBT Pro, licensed
  dependencies, approved prototypes, and suitable maintained components before
  custom work.
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
| R07 | 1 | in_progress | none | The Decision 288 MES ORB adapter produced four successful isolated screening runs and 32 ranked rows; exact reference parity passed and all 30 matrix variants screened out. Preserved evidence passed checksum, integrity and disposable application read-path validation. The Decision 291 selected-run correction merged through PR #70 at `4eaa03c761ffc4e90c4d1cf909c5f62d11bc614f`; focused, portable real-browser, independent-review, and required-CI evidence passed. It is not deployed, target-validated, operator-accepted, full beta, or Milestone 23 completion. |
| R05 | 8 | in_progress | none | Decision 292 accepts an economical reuse-first dashboard direction. The next repository-local deliverable is a small connected-screen blueprint; no executable implementation or completion evidence exists. Any scalable multi-run portion still requires the Decision 282 bounded-design owner review and acceptance before implementation. Cache work, complete workflow acceptance and renewed owner acceptance remain pending. |
| R06 | 9 | pending | R07 | Preserve completed paper-observer preparation. Authenticated runtime work and activation remain deferred until a defensible edge qualifies and every execution gate passes. |
<!-- active-work:end -->

## Current execution path

| Step | Status | Evidence or next action |
|---:|---|---|
| 1. Inventory an attributed candidate | Complete for the first candidate | Decision 288 selected the existing MES five-minute, 09:30 New York ORB specification. |
| 2. Approve the hypothesis and boundaries | Complete for this candidate | The owner approved the fixed reference-first plan and bounded 30-variant matrix. |
| 3. Connect it to existing research | Complete | The thin durable adapter was validated at `0f7701fd6d3823b9603576777df441dd92df45a8` and merged through PR #65 at `a5c10c676bbbc3c3043ca80f87dcbbac6e750509`. |
| 4. Persist, rank, and filter results | Complete for this screen | Four successful runs persisted 2 reference rows and 30 ranked matrix rows. |
| 5. Inspect through the dashboard | Owner/target-dependent | The artifacts and disposable read path passed, and the bounded selected-run correction is merged. Backed-up private deployment, target validation, and operator inspection require separate owner authorization and remain target-dependent. |
| 6. Continue bounded research | Pending | Use Milestone 25 safeguards; any new executable candidate needs explicit owner approval and predeclared evidence boundaries. |
| 7. Activate paper trading | Gated | Requires a qualified edge and every Milestone 24 execution gate. |
| 8. Automate paper forward testing | Gated | Milestone 26 follows successful paper activation and reconciliation proof. |
| 9. Consider micro-live trading | Far future | Milestone 27 requires successful paper evidence and separate explicit owner approval. |

## Milestone roadmap

Milestones 1–22 are complete.

| # | Milestone | Acceptance summary | Status |
|---:|---|---|---|
| 16–22 | Infrastructure, persistence, orchestration, lineage, dashboard foundation, equity fixture, and unified validation | Durable records, reproducible evidence, normalized outcomes, and protected-data gates | Complete |
| 23 | End-to-End Equity Research Factory Acceptance | ADR 0008 browser lifecycle, complete operator workflow, renewed Results acceptance, and every objective gate | **Pending; Decision 291 authorizes only the verified R07 selected-run blocker correction** |
| 24 | Portable Deployment and Alpaca Paper-Execution MVP | Portable restore and bounded paper workflow after a qualified edge and every execution gate | Preparation retained; activation deferred |
| 25 | Controlled Equity Strategy Intake, Discovery and Survivor Validation | Approved, attributed ideas become bounded experiments and survivors pass predeclared evidence gates | **In progress; MES ORB reference parity passed, but all 30 baseline variants screened out and no edge qualified** |
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

Milestone 23 remains the complete equity research workflow acceptance gate.
Decision 287's narrow research exception does not waive it. A non-programming
operator must be able to launch an approved fixture experiment, monitor it,
inspect provenance, assumptions, charts, signals, trades and validation, compare
and reproduce runs, record a decision, verify lineage, and understand failures
without Python, terminal output, raw CSV/JSON, or SQLite.

Current slices:

- **23A — Scenarios and fixtures:** frozen. **Complete.**
- **23B — Automated full-system acceptance:** supporting evidence implemented;
  keep the complete scenario inventory green.
- **23C-1 — Review/design:** selected-run design approved. A separate scalable
  multi-run design remains pending.
- **23C-2 — Implementation:** durable run tickets are merged. The bounded
  Decision 291 R07 selected-run correction merged through PR #70 at
  `4eaa03c761ffc4e90c4d1cf909c5f62d11bc614f`; its focused, portable
  real-browser, independent-review, and required-CI evidence passed. The
  complete selected-run/Milestone 23 implementation is not claimed.
- **23C-3 — Browser/operator acceptance:** renewed owner acceptance, real-browser
  lifecycle evidence, and the complete workflow remain pending.
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
  Results; multiple selections can feed Compare. Its exact design is pending.
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

### Repository and CI history

- **R01 — completed 2026-09-18:** Decision 275 published the reviewed,
  clean-history public repository as canonical while retaining the original as
  a private read-only archive. Production was not modified.
- Decision 276 keeps required checks and admin enforcement enabled while
  `strict`/up-to-date remains disabled. Independent green pull requests need not
  queue behind refresh builds; overlapping or dependent work still integrates
  serially and is retested against resulting `main`.

Readable completed incident history is retained in
[`docs/milestones/milestone-23-acceptance.md`](milestones/milestone-23-acceptance.md#incident-history).

## Governing references

- [Owner decisions](DECISIONS.md), especially Decisions 278–291.
- [Milestone 23 acceptance record](milestones/milestone-23-acceptance.md).
- [Dashboard product requirements](dashboard-product-requirements.md).
- [MES ORB specification](strategies/mes-opening-range-breakout.md).
- [ADR 0008: dashboard architecture](architecture/0008-dashboard-mounted-route-architecture.md).
- [ADR 0011: durable research run tickets](architecture/0011-durable-research-launch-claims.md).
