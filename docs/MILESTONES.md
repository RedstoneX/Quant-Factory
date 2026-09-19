# Quant Factory Milestones

This is the single operational source of truth for product direction, current
status, ordered work, milestone scope, and acceptance.

## Product direction

Quant Factory is a private, single-operator system for Terry to find and
validate a trading edge and pursue consistent market income. It is not an
enterprise, SaaS, software-sales, multitenant, billing, or team-platform
project; capabilities needed only for hypothetical external customers require
separate owner approval.

The controlling delivery priority is the shortest safe, evidence-truthful path
to an operator-usable MVP that can validate or reject a trading edge. Reuse is
a means to that outcome, not an end or a reason to delay operator value.

Quant Factory is infrastructure first, evidence first, and operating-proof
first. Plotly Dash remains the normal operator interface; Python, terminal
output, SQLite, CSV, JSON, and logs are implementation details. Decision 287
supersedes the former dashboard-first active order: the owner accepts the
existing dashboard as good enough to proceed with the controlled MVP research
path, and further dashboard work is frozen unless a verified defect blocks
operation. That limited acceptance does not close Milestone 23 or accept or
deploy the pending repair.

Decision 285 requires reuse before custom implementation. Existing Quant
Factory code, VectorBT Pro and other licensed dependencies, owner-approved
prototypes, and mature maintained legally usable components are evaluated
before new code. Custom work is limited to verified gaps or cases where reuse
is materially worse; the approved Results prototype remains implementation
input without being misrepresented as integrated, tested, deployed, or finally
accepted product behavior.

The factory must reject false edges, preserve reproducible evidence, paper
trade only qualified strategies, reconcile model and venue state, and expose
capital only after explicit human approval and independent risk controls.
Fixtures validate infrastructure and are not active profitability candidates.

## Current phase

Milestones 1–22 are complete. Milestone 23 is pending dashboard replacement
implementation, objective technical evidence, and renewed acceptance of the
eventual implemented Results experience. Decision 279
records the owner's rejection of the former Results-page comprehension and
flow and supersedes Decision 277's acceptance for that experience. Decision
280 accepts a chart-first replacement direction: a truthful selected-run price
chart with persisted entry/exit markers is primary and links to a grouped trade
ledger. TradingView's backtesting Strategy Report is the primary UX reference;
QAMC informs panel, resizing, and link mechanics only, not information density.
Decision 281 accepts the validated preview's separate Bars and View controls,
truthful interval aggregation, exact trade-event preservation, resettable
desktop resizing, normal-flow report content, responsive stacking, and trade
typography that is visibly larger and more readable while deferring final
palette selection. Decision 282 records the owner's hands-on approval of the
detailed selected-run Results specification and authorizes implementation.
The owner also requires a separate scalable multi-run analysis surface for
aggregating, slicing, ranking, filtering and selecting hundreds or thousands
of persisted runs; one run opens in Results and multiple selections can feed
Compare. Its exact UI, architecture and name remain to be designed.
Decision 283 additionally requires safe caching so exact repeat research
computations are materially faster than rebuilding all computation. Each
explicit request must still retain a distinct durable run ticket and lifecycle;
cache reuse must be validated, traceable, isolated by every result-changing
input and protected-data partition, and must not count as independent evidence.
Failed, partial, corrupt, or unknown work is never reusable. Cache architecture,
storage, schema, eviction, implementation sequence, and explicit **Reproduce**
recomputation policy remain a bounded design task rather than an approved
solution or claimed implementation.
Decision 287 supersedes Decision 286's active Results-completion priority and
Decision 274's dashboard-first active order. The dashboard remains essential,
but further Results implementation, polish, redesign and deployment are frozen
unless a verified defect blocks the active operator path. The validated Results
repair produced under Decision 286 is preserved outside canonical `main`; it
remains unmerged and undeployed and therefore is not current product behavior.
This reprioritization does not close Milestone 23, accept or deploy the pending
repair, waive remaining technical gates, or cancel the accepted multi-run and
safe-cache requirements.

The active shortest path is candidate/source inventory → one named, source-
attributed hypothesis selected for explicit owner approval → the thinnest
necessary adapter into the existing VectorBT batch-research path → durable
results → ranking/filtering → inspection in the existing dashboard.
Decision 288 selects and approves the existing MES five-minute, 09:30 New York
opening-range breakout specification for that first controlled path. Its
cataloged 2019–2026 extent was already inspected, so it is development/reference
evidence rather than an untouched protected test; its earlier baseline failure
and optimistic sensitivity are not a qualified edge. At executable validation
revision `0f7701fd6d3823b9603576777df441dd92df45a8`, the thin durable adapter
completed four successful isolated screening runs: two reference runs and two
matrix runs persisted 32 ranked rows (2 reference plus 30 matrix), and the
30-minute/zero-offset reference matched the corresponding matrix rows exactly
in both directions. Every matrix variant remained screened out. Each run
persisted seven registered artifacts plus its integrity manifest. This is
development/reference integration evidence only; it establishes no edge,
promotion, deployment, paper activation, or live authority. Decision 287 authorizes
controlled, bounded, source-attributed candidate intake, discovery and
research/backtesting under Milestone 25 safeguards before Milestone 23 closes.
Executable launch requires the owner's explicit approval of the named,
source-attributed hypothesis and predeclared evidence boundaries. Open-ended
optimization or data mining, protected-test evaluation and automatic promotion
remain blocked. Decision 278
accepts ADR 0011's
safer durable run-ticket architecture and
authorizes implementation. Its schema-5 core, shared launch service, and Run
test, historical-relaunch, and reproduction integrations are implemented,
tested, and merged in the canonical source through PRs #35–#38; PR #42 adds
the claim-core suite to required Portable CI and separately merges focused
claim-aware stale-recovery evidence. At revision
`5462c796809e83634959cbd3e7fa75b81ec2e309`, those merged changes establish
canonical-source implementation and focused/browser-fixture evidence only.
PR #50 separately adds the focused stale-recovery suite to required Portable
CI after proving its portability in a clean Python 3.12 environment. Neither
the anchored source evidence nor this CI enforcement establishes production
deployment, current licensed-target SPYM proof, the complete end-to-end
workflow, renewed Results acceptance, or Milestone 23 completion. Paper-order
activation and live work remain blocked except for the bounded offline and
deployment preparation already authorized and retained.

Decision 287 sets the current order:

1. Inventory and assess controlled, source-attributed strategy candidates.
   **Completed for the first candidate under Decision 288.**
2. Select one named, source-attributed hypothesis and obtain explicit owner
   approval plus predeclared evidence boundaries before executable launch.
   **Completed by Decision 288 for the existing MES five-minute ORB
   specification and its fixed reference-first plan.**
3. Connect that approved candidate through the thinnest necessary adapter to
   the existing VectorBT batch-research path without building a replacement
   engine, and produce durable runs and evidence. **Implemented and validated
   in the isolated branch at revision `0f7701fd6d3823b9603576777df441dd92df45a8`;
   repository integration remains pending.**
4. Rank and filter durable results in the smallest reusable form needed for
   decision-making. **The bounded matrix persisted all 30 ranked rows; no
   variant survived screening.**
5. Inspect selected results in the existing dashboard; change it only for a
   verified operational blocker. **Next after repository integration.**
6. Continue controlled, bounded research under Milestone 25 safeguards until a
   defensible edge qualifies.
7. Resume remaining Milestone 24 paper activation only after the qualifying
   edge and all unchanged execution gates pass.
8. Run automated paper forward testing and reconciliation under Milestone 26.
9. Treat Milestone 27 micro-live testing as far-future work requiring separate
   explicit owner approval.

Decision 275's repository cutover remains implemented and does not alter the
Decision 287 product sequence. The
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
| R07 | 1 | in_progress | none | Decision 288's thin durable MES ORB adapter is implemented and isolated-runtime validated at executable revision `0f7701fd6d3823b9603576777df441dd92df45a8`: four successful runs persisted 32 ranked rows (2 reference plus 30 matrix), exact 30-minute/zero-offset parity passed in both directions, and every matrix variant screened out; best long was 15 minutes/2 ticks with 5.42477% return, 0.458798 Sharpe, 4.19045% maximum drawdown and 1,227 trades; best short was 30 minutes/0 ticks with -5.52201% return, -0.453648 Sharpe, 7.55715% maximum drawdown and 1,049 trades; each run persisted seven registered artifacts plus its integrity manifest; an initial disk-full attempt was partial invalid evidence and was excluded, then a fresh isolated retry succeeded; all evidence remains development/reference only and establishes no edge, promotion, deployment, paper or live authority; next integrate the reviewed branch, then inspect the runs in the existing dashboard and repair only verified operational blockers |
| R05 | 8 | pending | none | Preserve the validated selected-run Results repair outside canonical main; it remains unmerged and undeployed; freeze further dashboard implementation, polish, redesign and deployment unless R07 exposes a verified operational blocker; the owner accepts the existing dashboard as good enough for the controlled path, but Milestone 23 and the accepted later multi-run/cache requirements remain pending |
| R06 | 9 | pending | R07 | Preserve completed paper-observer preparation; authenticated runtime work remains deferred until a defensible edge qualifies and every unchanged execution gate passes |
<!-- active-work:end -->

### Decision 288 validation record — 2026-09-19

This change is classified as implementation and validation evidence for the
already accepted Decision 288, not as a new owner decision or milestone
acceptance. `docs/MILESTONES.md` is updated for the verified status and next
action; `docs/CHAT_HANDOFF.md` is updated because future chats need the resume
point; and the MES ORB strategy specification is updated with the durable-run
commands and result boundary. `AGENTS.md`, the agent policy, `docs/DECISIONS.md`,
ADRs, `README.md`, runbooks, and `dashboard/project_status.py` are not applicable
because this record changes no mandate, architecture, deployment, operating
procedure, public orientation, or accepted dashboard status. R07 and Milestone
25 remain in progress.

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

Before Milestone 23 can close or any strategy can advance toward paper
activation, a non-programming operator must be able to
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

Decision 287 permits controlled, bounded, source-attributed candidate discovery
and research to use the existing dashboard before this full contract is
accepted; it does not waive the contract or authorize open-ended optimization,
data mining, protected tests or automatic promotion. The Milestone 23C flow
remains Home → Ideas → Set up → Run test → Results → Compare.
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
| 23 | End-to-End Equity Research Factory Acceptance | ADR 0008 browser lifecycle, complete operator workflow, renewed Results-page acceptance, and every objective gate pass | **Pending — dashboard work frozen unless it blocks R07** |
| 24 | Portable Deployment and Alpaca Paper-Execution MVP | Portable restore plus bounded paper workflow after a qualified edge and every execution gate | Preparation retained; activation deferred |
| 25 | Controlled Equity Strategy Intake, Discovery and Survivor Validation | Approved, attributed ideas become bounded experiments; survivors pass predeclared evidence gates | **In progress under Decision 287 safeguards; Decision 288's MES ORB reference parity passed, but all 30 bounded matrix variants screened out on development/reference evidence, so no edge qualified and open-ended optimization/data mining remains gated** |
| 26 | Automated Alpaca Paper Forward Testing and Reconciliation | Eligibility, deployment, monitoring, reconciliation, recovery, and paper fault injection pass | Pending |
| 27 | Alpaca Micro-Live Proof and Independent Risk Sentinel | Separate approval, isolated live domain, independent supervision, and failure acceptance pass | Pending — far future |
| 28–30 | Compliant crypto proof and multi-venue V1 | Legal/operational eligibility, isolated adapters, evidence, reconciliation, and recovery pass | Deferred |

## Milestone 23 slices

- **23A — Scenarios and fixtures:** frozen. **Complete.**
- **23B — Automated full-system acceptance:** supporting evidence implemented;
  keep the complete scenario inventory green.
- **23C-1 — Review/design:** **Selected-run design complete.** Decisions
  280–282 accept the chart-first direction, validated preview constraints and
  detailed responsive selected-run Results specification. The separate
  scalable multi-run analysis requirement is accepted, but its exact UI,
  architecture and name remain a design task rather than an approved solution.
- **23C-2 — Implementation:** ADR 0011 durable run tickets are implemented,
  tested, and merged in the canonical source for Run test, historical relaunch,
  and reproduction. Preserve that implementation and its fail-closed tests.
  Decision 287 supersedes Decision 286's active R05 completion priority. The
  validated repair remains preserved but unmerged and undeployed. Do not resume
  dashboard work unless the active R07 path exposes a verified operational
  blocker. ADR 0008, Plotly Dash, VectorBT Pro, service boundaries and the
  accepted later multi-run/cache requirements remain in force; no
  implementation or deployment is inferred.
- **23C-3 — Browser/operator acceptance:** renewed owner acceptance of the
  implemented replacement plus real-browser lifecycle and complete end-to-end
  workflow evidence remain pending.
- **23D — Recovery and integrity:** preserve failure, retry, timeout,
  cancellation, stale recovery, missing-artifact, and corrupt-lineage coverage.
- **23E — Gate decision:** record explicit pass or fail. Decision 287's
  controlled, bounded candidate path is authorized before a pass; open-ended
  optimization/data mining, protected-test evaluation, automatic promotion and
  order activation are not.
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

Decision 287 authorizes controlled, bounded, source-attributed candidate
intake, discovery and research/backtesting plus the existing batch-research,
durable-result, ranking/filtering and current-dashboard inspection path while
Milestone 23 remains pending. Executable launch requires explicit owner
approval of the named, source-attributed hypothesis and predeclared evidence
boundaries. Open-ended optimization or data mining, protected-test evaluation,
automatic promotion, paper-order activation and live work remain blocked until
their explicit milestone gate and approval.
