# Quant Factory Decisions

This clean-history log preserves the accepted decision set needed to operate
the public project. Detailed private operational history remains in the
private archive. New decisions are appended and supersede earlier decisions
explicitly.

## Foundation and product direction

1. The clean-history public Quant Factory repository is canonical and is the
   sole forward source of truth after Decision 275's completed controlled
   cutover. The original repository is retained privately as read-only
   historical evidence. Repository documentation is durable project memory.
2. The closed Tier 1 authority set is `AGENTS.md`, `docs/MILESTONES.md`, and
   `docs/DECISIONS.md`. Supporting documents cannot create competing mandate,
   status, or roadmap authority.
3. Quant Factory is infrastructure first, evidence first, and operating-proof
   first. Plotly Dash is the operator interface and VectorBT Pro is the licensed
   research engine. Decision 287 supersedes dashboard-first active sequencing.
4. Research, validation, evidence, and strategy logic remain venue-neutral.
   Research cannot submit venue orders directly.
5. Deterministic fixtures prove infrastructure; their results are not
   profitability evidence or deployment approval.

## Research and evidence

6. Data provenance, adjustment policy, validation status, identity, and
   checksums are required. Downloaded market data and generated results remain
   outside Git.
7. Hypotheses and parameter ranges require attribution and explicit approval.
   Reference reproduction precedes bounded exploration; protected data cannot
   participate in selection.
8. Screening, chronological out-of-sample, walk-forward, robustness, and
   Monte Carlo evidence retain distinct pass, fail, invalid, and insufficient-
   evidence outcomes.
9. Evidence decisions never execute protected tests, promote a strategy, or
   authorize deployment automatically.

## Dashboard architecture

10. ADR 0008 is the accepted dashboard baseline: one persistent
    `dcc.Location`, one permanent shell, permanently mounted route containers,
    pathname-driven visibility, page-owned callbacks, reusable components,
    and mandatory browser-lifecycle acceptance.
11. Dynamic `page-content.children` replacement is prohibited as the active
    routing mechanism. Hidden compatibility content and test-only presentation
    behavior are prohibited.
12. Operator language and decision-useful visuals are primary. Technical IDs,
    hashes, storage details, and diagnostics belong in labelled drill-downs.
13. The target flow is Home → Ideas → Set up → Run test → Results → Compare.
    During Milestone 23, Ideas is non-executing and may capture safe drafts or
    source references only. External retrieval and backtesting remain gated.

## Execution and security

14. Alpaca Paper Trading is the first execution venue. SCHX is the broad-
    market whole-share execution fixture; SPYM remains an ingestion and
    deterministic research fixture.
15. Paper and live deployments are separate security domains. A configuration
    change cannot convert paper execution into live execution.
16. Real-capital activation requires successful paper evidence, explicit human
    approval, isolated credentials and state, authenticated private networking,
    deterministic risk controls, and an independent Risk Sentinel.
17. OneCLI is the selected first credential gateway, subject to ADR 0010.
    Agents never receive unrestricted vault access or underlying secret values.
    Paper and live credentials remain separate; withdrawal permission is
    prohibited.
18. The broker-neutral journal records a durable submission claim before a
    broker call. Ambiguous submissions are never retried automatically;
    reconciliation and restart behavior fail closed.

## Repository and agent operation

19. Substantive work uses dedicated branches and pull requests. Direct pushes
    to `main`, force pushes, blanket staging, destructive Git, and anonymous
    stashes are prohibited.
20. CI execution and target-environment proof are separate. Required-check
    enforcement is proven only when a controlled failing check blocks merging
    and the restored green path passes.
21. Independent pull requests use required status checks with GitHub's strict/
    up-to-date option disabled under Decision 276. They do not refresh or
    serialize merely because an independent pull request merged first.
    Overlapping or dependent changes remain serialized and retested against
    the resulting `main`.
22. Codex is the sole active project agent toolchain. During the scoped
    revival, the Codex lead orchestrates multiple bounded workers,
    independently validates critical evidence, and remains the sole owner-
    facing coordinator.

## Current accepted sequence

256. **Scoped revival authority.** The project owner authorized the current
     bounded revival, including root-cause repair, extensive testing, and
     reviewed repository operations. This did not accept Milestone 23,
     authorize discovery or orders, or permit live capital.

259. **Parallel research deployment preparation.** Portable research-only
     packaging, migration preparation, and isolated target validation may
     proceed while Milestone 23 owner review is pending. This does not complete
     Milestone 24 or authorize execution.

262. **Parallel execution preparation.** Broker-neutral contracts, isolated
     paper-adapter implementation, offline tests, and target validation may
     proceed without paper-order activation. Credential use remains subject to
     ADR 0010 and the account-ownership boundary.

266. **Authoritative research runtime.** Research runtime migration is
     authorized only after backup, reconciliation, authenticated private
     access, restart, restore, and rollback checks. Production coordinates and
     evidence remain external to the public repository.

269. **Credential gateway selection.** OneCLI remains selected; replacement or
     resumed fallback evaluation requires separate explicit owner instruction.

270. **Revival orchestration.** All task execution in the scoped revival uses
     bounded workers matched to complexity. The lead orchestrates and
     independently validates critical evidence.

271. **One-shot authentication exception.** A fixed operator-controlled paper
     account GET may verify authentication through the gateway without
     exposing keys. It authorizes no orders, worker activation, account reuse,
     live access, or general gateway adoption.

272. **Dedicated paper-account boundary.** A dedicated simulated account is
     reserved for Quant Factory. Its identity and credentials remain private;
     this allocation does not authorize paper orders.

273. **Milestone 23C direction.** Retain Plotly Dash and VectorBT Pro, use Dash
     AG Grid and Dash Bootstrap Components where appropriate, show persistent
     run status/evidence/decision/next action, keep technical detail in labelled
     drill-downs, and obtain page-spec and browser/operator acceptance.

274. **Dashboard-first strategy qualification (accepted 2026-09-17).** Finish
     Milestone 23 dashboard and operator acceptance first. Then conduct
     controlled strategy intake and research under Milestone 25 until a
     defensible edge qualifies. Resume paper activation only after the edge and
     every account, credential, endpoint, worker, reconciliation, and safety
     gate pass. Automated paper evidence follows under Milestone 26. Micro-live
     work is far future and requires separate explicit owner approval.

275. **Clean-history public repository migration (accepted and implemented
     2026-09-18).** The sanitized clean-history public repository now holds the
     canonical name and is the sole forward source of truth. The original is
     retained privately as a read-only archive and was neither rewritten nor
     deleted. The public repository contains no credentials, private
     infrastructure, machine-specific state, licensed packages, downloaded
     data, generated results, or private operational evidence. Publication
     grants no source-code license; all rights are reserved. The cutover did
     not modify the production runtime and does not authorize strategy
     discovery, paper activation, live capital, or a production deployment.

276. **Parallel pull-request throughput policy (accepted and implemented
     2026-09-18).** The owner permanently sets
     `required_status_checks.strict` to `false` unless the owner later changes
     this decision. Required checks remain `Documentation contracts`,
     `Portable tests`, and `Dependency review`; `enforce_admins` remains true;
     repository auto-merge and merged-branch deletion remain enabled; CI
     concurrency remains per ref; and no merge queue is used. Independent
     green pull requests may merge without rebasing, updating, rebuilding, or
     serializing merely because another independent pull request merged first.
     Overlapping or dependent changes still integrate serially and are retested
     against the resulting `main`. GitHub API verification on 2026-09-18
     re-confirmed these settings after the canonical cutover. Controlled PR #1
     proved enforcement: its first revision failed `Portable tests` and was
     blocked, its corrected revision passed all three required checks, and the
     PR was closed without merging. Independent same-base PRs #2 and #3 proved
     throughput: both were green; after #3 merged, #2 remained `CLEAN` and
     `MERGEABLE` with its original Test run `35301119002` and Dependency Review
     run `35301119008`, received no refresh run, and was closed unmerged.

277. **Current dashboard/operator experience accepted (accepted 2026-09-18).**
     The owner explicitly accepts the current dashboard/operator direction and
     authorizes autonomous work through the remaining Milestone 23 objective
     gates. Once those gates pass, no additional dashboard-acceptance prompt is
     required before proceeding under Decision 274 to controlled Milestone 25
     strategy intake and research. This acceptance does not close Milestone 23
     or waive implementation conformance, ADR 0008 browser lifecycle, the
     complete end-to-end operator workflow, automated tests, failure handling,
     documentation and `dashboard/project_status.py` synchronization, or any
     research, protected-data, credential, paper, execution, and live-capital
     safety boundary. Strategy discovery remains blocked until the objective
     Milestone 23 gate passes. If a material redesign invalidates the accepted
     experience, record that change and do not represent this acceptance as
     covering the redesigned experience.

278. **Durable research run tickets accepted (accepted 2026-09-18).** The
     owner approved the safer operator design in ADR 0011: Quant Factory must
     persist an accepted research-run identity before launching the fixture so
     refreshes, duplicate delivery and retries reopen the same test rather
     than silently losing or duplicating it. If external submission cannot be
     proved, the dashboard must show a truthful unknown state and must not
     automatically launch again. This accepts the bounded in-request design
     and authorizes its implementation and validation across every enabled
     fixture-launch entry point. It does not claim implementation is complete,
     make research computation survive dashboard-process loss, close
     Milestone 23, authorize the separate worker/deployment architecture,
     change production, or relax any research, credential, paper, execution or
     live-capital gate.

279. **Results-page acceptance withdrawn; renewed design review required
     (accepted 2026-09-18).** After using the current Results page, the owner
     explicitly rejected its comprehension and task flow. This supersedes
     Decision 277's acceptance and no-repeat-acceptance rule for that
     experience; it does not erase that the earlier acceptance occurred.
     Correctness repairs for selected-run persistence, row activation, and
     truthful state remain authorized and required. Before broad Results-page
     redesign, produce a concise research-grounded page specification or
     mockup and obtain renewed owner acceptance. The proposed direction is a
     top-to-bottom task flow, essential overview before detail, progressive
     disclosure for diagnostics, compact keyboard-accessible selectable run
     history with explicit date and time, and responsive columns without
     avoidable horizontal scrolling or large dead space. This decision does
     not accept a replacement design, change ADR 0008, close Milestone 23, or
     relax any research, credential, execution, paper, or live-capital gate.

280. **Chart-first Results direction accepted; detailed replacement still
     pending (accepted 2026-09-18).** The owner accepts a chart-first direction
     for the replacement Results experience. The selected persisted run's
     truthful OHLC/price chart is the primary workspace, with entry and exit
     markers at the persisted trade points and a linked ledger grouped by
     completed trade; selecting a trade must bring its entry/exit context into
     view and identify the corresponding chart markers. TradingView's current
     Strategy Report and backtesting-results interaction, in its chart-first
     Supercharts context, is the primary UX reference. This reference excludes
     TradingView's live-trading, brokerage, order-entry, position, and account
     surfaces. QAMC may inform panel docking, resizing, and chart/ledger-link
     mechanics, but not its information density or compressed content
     hierarchy. This supersedes only Decision 279's report-first or purely
     top-to-bottom implication; Decision 279's withdrawn acceptance and renewed
     review gate remain in force. A detailed responsive mockup or concise page
     specification, its owner approval, implementation, deployment, automated
     and browser testing, and renewed acceptance of the implemented Results
     experience all remain pending. This direction does not change ADR 0008,
     accept Milestone 23, authorize production changes, begin strategy
     discovery, or relax any research, credential, execution, paper, or
     live-capital gate.

281. **Validated Results preview controls accepted; full replacement still
     pending (accepted 2026-09-18).** The owner accepts these additional
     Results requirements from the validated chart-first preview. The chart
     has separate, always-visible controls labelled **Bars:** `1m`, `5m`,
     `15m`, `1D` and **View:** `Full run`, `1D`, `1W`, `1M`; bar interval,
     visible range, and the immutable persisted backtest period are distinct
     concepts. Bar changes are visualization-only and use persisted OHLC or
     truthful aggregation from persisted finer-grained OHLC. The validated
     preview renders 53,528 one-minute bars, 13,340 five-minute bars, 4,474
     fifteen-minute bars, and 173 daily bars. A trade retains its exact
     persisted event timestamp and price while its visual marker maps to the
     containing aggregated bar; an interval that cannot be rendered truthfully
     remains visible but unavailable with a plain-language reason. On desktop,
     three subtle resize edges support vertical resizing from the chart top,
     shared chart/report boundary, and report bottom; **Reset layout** restores
     the approved default without losing selected run, tab, trade, or evidence.
     Metrics and Trades grow in normal page flow, have no nested vertical
     scrolling, and retain comfortable bottom breathing room. Smaller layouts
     stack chart then report responsively, and trade-ledger and trade-detail
     typography is visibly larger and more readable. The validated preview
     measured 52 pixels of bottom space and increased the relevant trade styles
     by two CSS pixels; those measurements are implementation evidence, not
     universal fixed requirements. Palette revision is deferred; temporary
     acceptance of the preview palette does not establish a final palette.
     These are owner-specific requirements even where another reference
     product behaves differently. This supplements Decision 280 but
     does not approve the remaining detailed design, claim application
     implementation or deployment, accept Milestone 23, authorize production
     changes, or relax any research, credential, execution, paper, or
     live-capital gate.

282. **Selected-run Results specification approved; scalable multi-run
     analysis required (accepted 2026-09-18).** After hands-on use of the
     private interactive Results preview, the owner explicitly approved the
     detailed selected-run design as intuitive and authorized its application
     implementation. The approval includes the primary price chart, direct
     chart pan and mouse-wheel zoom, resizable chart/report panels, the
     Metrics summary and supporting chart, the grouped Trades view, and the
     secondary **Change run** interaction. The owner withdrew the momentary
     suggestion that zoom should require a Control-key modifier after
     confirming that the existing interaction already worked. This completes
     the 23C-1 selected-run design approval gate; it does not claim that the
     application is implemented, deployed, tested, licensed-target validated,
     or accepted in its eventual implemented form.

     At VectorBT scale, the product must also provide a separate scalable
     multi-run analysis surface for hundreds or thousands of persisted runs.
     It must support aggregation, slicing, ranking, filtering and selection by
     maximum drawdown, total return, profitable-trade measures and other useful
     evidence dimensions. One selected run continues to open in Results;
     selecting multiple runs can feed Compare. The surface's name, precise
     information architecture, controls and implementation remain to be
     designed and are not approved merely by this requirement. This decision
     does not change ADR 0008, deploy production, accept Milestone 23, begin
     strategy discovery, authorize protected-data evaluation or credentials,
     activate paper execution, or permit live capital.

283. **Safe exact-repeat research caching required (accepted 2026-09-18).**
     The owner requires exact repeat research computations to be materially
     faster through safe cache reuse rather than rebuilding all computation.
     Every explicit run request still creates and retains its own durable run
     ticket, lifecycle, identity, lineage and operator-visible outcome. A cache
     hit may reuse only computed artifacts that are validated, traceable and
     isolated by every input that can change the result, including code and
     runtime identity, immutable configuration, dataset identity, execution
     assumptions, engine/version inputs, evidence stage and protected-data
     partition. Failed, partial, corrupt, mismatched, stale, or unknown work is
     never reusable. Reusing one computation does not create an independent
     evidence observation or increase sample count.

     This accepts the product requirement, not a cache architecture. Identity
     and keying mechanism, storage, schema, locking, concurrency, invalidation,
     retention/eviction, target topology, implementation sequence and operator
     presentation require a bounded design and validation before implementation.
     Whether the explicit
     **Reproduce** action must force recomputation, may use a cache only as a
     verification aid, or may expose a separate choice remains undecided. The
     existing ADR 0011 durable claim and fail-closed submission behavior remain
     authoritative. This decision does not claim a computation cache exists,
     close Milestone 23, begin discovery or protected testing, deploy production,
     use credentials, activate paper execution, or permit live capital.

     Documentation-impact assessment: `AGENTS.md`, `docs/MILESTONES.md`,
     `docs/CHAT_HANDOFF.md`, `README.md`, the dashboard product requirements,
     infrastructure inventory and Milestone 23 acceptance record are updated;
     this decision log is appended. An ADR is not yet applicable because no
     architecture has been selected. No operating runbook changes because no
     cache has been implemented or deployed.

284. **Private single-operator product boundary (accepted 2026-09-18).** The
     owner clarifies that Quant Factory is built privately for Terry as its
     single owner/operator, solely to find and validate a trading edge and
     pursue consistent income in the markets. It is not an enterprise product,
     SaaS offering, software-sales project, multitenant service, billing
     system, customer-onboarding product, or team platform. Features whose
     purpose is only hypothetical external customers, organizations, roles,
     subscriptions, or commercial distribution are out of scope unless the
     owner separately approves them. This boundary does not weaken the
     evidence, reproducibility, credential isolation, execution safety, or
     capital-approval controls that protect the owner's research and money.
     The controlling delivery priority is the shortest safe, evidence-truthful
     path to an operator-usable MVP that can validate or reject a trading edge.

285. **Reuse before custom implementation (accepted 2026-09-18).** Before
     writing custom executable code, agents must inventory and evaluate the
     relevant existing Quant Factory code and tests, licensed dependencies
     including VectorBT Pro, owner-approved prototypes, and mature maintained
     external components or reference projects that may already solve the
     need. The comparison covers functional fit, compatible licensing and
     legal use, security, maintenance health, integration cost, and truthful
     handling of Quant Factory data and evidence. A suitable proven component
     is adapted or integrated instead of recreated. Custom code is limited to
     a verified product-specific gap or a case where reuse is materially worse
     under that comparison, and the implementation preflight records the
     inventory, selected reuse, remaining gap, and rationale.

     Reuse is a means to Decision 284's controlling operator-usable MVP
     outcome, not an independent product goal. Once a suitable safe and
     evidence-truthful path is established, the rule does not authorize more
     component research or integration work that delays operator value.

     Agents must not recreate mature commercial-grade dashboard, charting,
     grid, panel, or research-engine behavior merely for architectural
     neatness, local control, or speculative future flexibility. This is not
     an absolute ban on the smallest necessary domain adapter,
     evidence-integrity check, or safety control, and it does not authorize
     copying or depending on code without a compatible license. An
     owner-approved prototype is preserved as implementation input rather than
     independently greenfielded without a documented reason. Prototype
     approval remains distinct from application integration, automated and
     browser testing, licensed-target proof, deployment, and renewed operator
     acceptance. For the current Results work, the approved interactive
     prototype remains available to the beta path; it is not itself the
     deployed beta.

     Documentation-impact assessment: `AGENTS.md` and the agent policy are
     updated for permanent behavior; `docs/MILESTONES.md` is updated for the
     single-operator direction and active Results work; `docs/CHAT_HANDOFF.md`
     and `README.md` are updated so future work and public orientation inherit
     the boundary; the implementation-preflight skill and dashboard product
     requirements are updated as the relevant procedure and specification;
     the existing component-reuse audit is retained as the supporting
     inventory and aligned to this rule; this decision log is appended. No ADR
     applies because no architecture or dependency is selected, and no
     deployment or operating runbook changes because this decision changes
     implementation selection behavior only.

286. **Selected-run Results beta cost and sequencing boundary (accepted
     2026-09-18).** The owner sets a temporary six-development-hour planning
     ceiling for the remaining selected-run Results beta work. Agents must
     measure and report effort honestly; the figure is a stop-control, not a
     completion guarantee or permission to invent stopwatch precision. If the
     work cannot reach the beta within the ceiling, agents stop and report the
     evidence instead of silently expanding time or scope.

     The remaining beta path contains exactly three bounded slices, in order:
     (1) reuse and integrate the approved selected-run page and working chart
     behavior with the existing application and persisted results; (2) make
     only focused browser fixes demonstrated by that integration; and (3)
     perform a backed-up, validated deployment to the existing private OVH
     research target. Each slice uses one bounded implementer and the cheapest
     capable independent reviewer while the lead orchestrates and independently
     validates. All reviewer effort counts inside the same
     six-development-hour ceiling. The reviewer is limited to the owned diff,
     decisive evidence, and boundary compliance; review is not a second implementation, broad
     audit, discretionary redesign, or duplicate-test exercise.

     These slices add no new framework, chart/grid/panel system or
     architecture, or paid dependency, and they do not replace the approved
     behavior. Computation caching, scalable multi-run design or Explorer
     work, aesthetic polish, and broad refactoring are excluded unless
     recorded evidence demonstrates that an item blocks the selected-run beta.
     If the intended thin integration expands, work stops for a reuse and
     remaining-budget reassessment. This decision sequences rather than
     cancels Decisions 282–283: the accepted multi-run analysis and safe-cache
     requirements remain later work, outside these three slices unless they
     become demonstrated beta blockers. It does not weaken evidence
     truthfulness, licensed-target proof, backup, rollback, browser validation,
     credential isolation, execution safety, or Milestone 23 acceptance.
     The dashboard remains the essential interface for its single operator,
     but the beta MVP need not be perfect. While work is active, agents provide
     at least hourly progress reports stating the current slice, selected
     reuse, boundary compliance, scope pressure, and next action.

     Documentation-impact assessment: `AGENTS.md`, `docs/MILESTONES.md`, the
     agent policy, implementation-preflight skill, dashboard product
     requirements, component-reuse audit, and `docs/CHAT_HANDOFF.md` are
     updated. `README.md` is not applicable because its public product
     orientation and reuse-first rule remain accurate. No ADR applies because
     this selects no new architecture or dependency. No runbook change applies
     because the existing backed-up OVH deployment procedure remains
     authoritative and no deployment occurs in this documentation change.

287. **MVP strategy-ingestion and backend priority (accepted 2026-09-19).**
     The owner reprioritizes the shortest path to a usable trading-research MVP.
     This decision explicitly supersedes Decision 274's dashboard-first active
     order and Decision 286's active priority to finish and deploy the
     selected-run Results beta. It does not erase those decisions or their
     evidence. The dashboard remains the essential single-operator interface.
     The owner explicitly accepts the existing dashboard as good enough to
     proceed with the controlled MVP research path, and further dashboard work
     is frozen unless a verified defect blocks operation. This acceptance is
     limited to proceeding with that path: it does not accept or deploy the
     pending repair, close Milestone 23, or waive its remaining technical gates.
     The validated Results repair produced under Decision 286 remains preserved
     outside canonical `main`; it is unmerged and undeployed and must not be
     represented as current product behavior.

     The active shortest path is: inventory and assess source-attributed
     strategy candidates → select one named, source-attributed hypothesis for
     explicit owner approval → connect it through the thinnest necessary
     adapter to the existing VectorBT batch-research path → durable results and
     evidence → ranking/filtering → inspection of selected results in the
     existing dashboard. Reuse the existing research engine, persistence,
     evidence and dashboard capabilities. Do not create a replacement engine,
     dashboard, framework or speculative platform layer. Every implementation
     slice must directly advance one step in this path or remove a demonstrated
     blocker to it. The lead and independent reviewer must reject unrelated
     dashboard work, generic infrastructure, speculative refactoring,
     execution expansion or any other slice without that direct trace.

     This authorizes controlled, bounded, source-attributed candidate intake,
     discovery and research/backtesting under Milestone 25 safeguards before
     Milestone 23 closes. Executable launch of a candidate requires the owner's
     explicit approval of its named, source-attributed hypothesis and the
     applicable predeclared evidence boundaries. This does not claim that
     ingestion, ranking/filtering or the complete backend path is implemented.
     To the extent Decisions 277 and 279–283 state that all strategy discovery
     remains blocked until Milestone 23 passes, this decision supersedes only
     that sequencing restriction for this controlled path.
     It does not authorize open-ended optimization or data mining, protected-
     test evaluation, automatic strategy promotion, paper orders or live work.
     Milestone 23 remains pending; its remaining technical gates and the
     accepted later multi-run and safe-cache requirements are not cancelled.

     Paper and live gates are unchanged. Paper activation still requires a
     qualified edge and every account, credential, endpoint, worker,
     reconciliation, recovery, capacity, audit and fail-closed gate. Live work
     remains far future and additionally requires successful paper evidence,
     separate explicit owner approval, isolated live credentials/state/
     deployment, authenticated private networking and an independent Risk
     Sentinel.

     Documentation-impact assessment: `AGENTS.md` and the agent policy are
     updated for permanent slice-selection and review behavior;
     `docs/MILESTONES.md` is updated for direction, current phase, active work
     and milestone status; `docs/CHAT_HANDOFF.md` and `README.md` are updated
     because their dashboard-first resume guidance would otherwise be
     misleading; the dashboard product requirements, infrastructure completion
     inventory and component-reuse audit are aligned; ADR 0003 is annotated to
     record its limited sequencing supersession while preserving its product
     architecture and paper/live gates; this decision log is appended. No new
     ADR or runbook applies because no architecture, dependency, deployment or
     operating procedure is introduced.

288. **MES opening-range breakout selected for the first controlled candidate
     path (accepted 2026-09-19).** The owner explicitly prefers opening-range
     breakout (ORB) as the first strategy to test. The repository's existing
     named ORB implementation is the MES five-minute, 09:30 New York
     cash-session specification, so that strategy is selected and approved for
     Decision 287's bounded intake and backend path. This is a narrow research
     exception to the standing classification of MES ORB as a fixture; it does
     not authorize futures order execution or make the earlier results current
     profitability evidence.

     Reuse the registered long-only and short-only MES ORB strategies, the
     verified `futures_MES_5m_databento` dataset and manifest, the existing
     VectorBT experiment engine, durable run/evidence persistence, ranking and
     filtering, and the existing dashboard. The first controlled research plan
     begins with exact reference reproduction at the approved 30-minute range
     and zero-tick offset for each direction. Only after reference parity may
     it run the already approved bounded matrix of five range lengths (5, 15,
     30, 45 and 60 minutes) by three breakout offsets (0, 1 and 2 MES ticks)
     for the two separate directions: exactly 30 variants, with no added
     parameter, filter, indicator, exit, stop or target. Preserve the existing
     rules: one entry per session, next contiguous five-minute-bar-open fills,
     same-session exit, no overnight carry, one MES unit, the documented
     $0.62 fee per contract per side and baseline one-tick adverse slippage per
     side. Alternative optimistic or stress cost scenarios are not part of the
     first launch and require an explicitly bounded follow-up.

     The catalog extent through 2026-02-13 was already inspected by the legacy
     exploratory matrix and is therefore development/reference evidence, not
     an untouched protected test. The earlier baseline screened out all 30
     variants; optimistic sensitivity produced three provisional passes, but
     neither result qualifies an edge. The first durable-path run may verify
     interpretation, integration, persistence, ranking and inspection, but may
     not be counted as independent evidence or used for promotion. Any survivor
     claim requires a separately predeclared chronological out-of-sample,
     walk-forward and protected-data plan using evidence not already consumed
     by selection. Calendar-roll discontinuities remain an explicit limitation
     and must not be treated as market returns. The implementation preflight
     must reconcile the legacy runner's stale unresolved-roll metadata with the
     confirmed catalog provenance before executable launch.

     This decision does not authorize open-ended optimization or data mining,
     protected-test inspection, automatic promotion, new data acquisition,
     paper orders, futures order execution, live work, a replacement research engine,
     a dashboard redesign or production deployment. The next action is the
     thinnest necessary adapter from this approved specification into the
     existing durable VectorBT research path, with focused tests and independent
     review under Decision 287.

     Documentation-impact assessment: `AGENTS.md`, the agent policy,
     `CLAUDE.md` and the implementation-preflight skill are updated for the
     selected candidate and current preflight boundary; `docs/MILESTONES.md` is
     updated for the active queue and evidence limits; this decision log is
     appended; `docs/CHAT_HANDOFF.md` and `README.md` are updated so future work
     does not continue to say that no candidate is active; the MES ORB strategy
     specification and infrastructure inventory are updated to distinguish the
     current candidate from its historical fixture evidence; ADR 0003 is
     annotated for the narrow candidate exception. No new ADR applies because
     no architecture, dependency, deployment, security or data flow changes.
     `docs/DATA_CATALOG.md` and `docs/parameter-governance.md` remain accurate
     and supply the data and parameter boundaries. No runbook changes because
     no runtime or operating procedure changes in this documentation slice.

289. **Quant Factory adversarial proposal role (accepted 2026-09-20).** The
     owner explicitly requests a durable adversary role, based on the useful
     QAMC pattern but specific to Quant Factory, to keep the owner, lead and
     project goal aligned and reach the finish line with less drift and waste.
     The read-only `quant-factory-adversary` specialist challenges material
     proposals before they proceed. Its narrow mandatory triggers are changes
     to priority, scope, architecture, framework or dependency; custom-build
     choices over reuse; strategy parameters or evidence, protected-data,
     ranking or promotion boundaries; production deployment; paper/live
     authority; and beta, milestone, edge-readiness or comparable material
     closure claims.

     The specialist freshly reads Quant Factory's Tier 1 authorities and the
     relevant code and evidence rather than carrying a duplicate summary of
     project doctrine. It tests the proposal's load-bearing existence and
     current-state claim, direct trace to Decision 287's shortest path,
     reusable alternatives, proportionality to the single-owner MVP, cost and
     agent allocation, evidence truth, hidden gate expansion, and work that can
     be removed or deferred. It distinguishes measured, inferred and unknown
     claims and returns concise objections, the strongest contrary reading,
     any cheaper or shorter path, and unresolved unknowns. It returns argument,
     never approval, rejection, scoring, or a new gate. The lead must
     explicitly disposition every material objection as `CHANGED` with
     evidence or `REJECTED` with reasons before the proposal proceeds.

     This role supplements implementation preflight and independent review; it
     replaces neither. It is not required for routine status, read-only facts,
     housekeeping, verified factual documentation corrections, or already
     approved mechanical execution with no scope change. It cannot contact the
     owner, implement work, or create child agents. The owner retains mandate,
     milestone acceptance, deployment, paper/live and capital decisions. No
     universal per-commit or per-PR adversary gate is created.

     Documentation-impact assessment: `AGENTS.md`, the agent policy and
     `CLAUDE.md` are updated for permanent behavior and specialist routing; the
     implementation-preflight skill is updated for conditional invocation and
     objection disposition; `docs/CHAT_HANDOFF.md` is updated so future chats
     see the control immediately; this decision log is appended. `docs/MILESTONES.md`
     is not applicable because active product order, status, scope and
     acceptance do not change. No ADR applies because architecture,
     deployment, security, data flow and integration are unchanged. `README.md`
     is not applicable because public product orientation is unchanged. No
     runbook or specification applies because no operator, recovery, migration,
     incident or product procedure changes.

290. **Codex-only lean agent instruction system (accepted 2026-09-20).** The
     owner selects Codex as Quant Factory's sole active project agent and asks
     that the instruction system be optimized for Codex and kept lean. Normal
     Codex work must not load, invoke, rely on, update, or follow `CLAUDE.md` or
     `.claude/**`. Those files remain untouched historical or tool-specific
     material; this decision does not delete or rewrite them.

     This supersedes only the agent-allocation and tooling portions of earlier
     decisions and documents that describe Codex as retired or another agent
     as the primary implementation tool. It preserves Decision 270's bounded
     lead/worker orchestration through Codex subagents and Decision 289's
     independent adversary principle through native Codex skills. `AGENTS.md`
     is reduced to stable rules loaded for every session; current product state
     stays in `docs/MILESTONES.md`, decision history stays here, and detailed
     procedures are loaded only when relevant. Native skills under
     `.agents/skills/` provide implementation preflight and the material-
     proposal adversary without placing those procedures in every session.

     This decision changes agent tooling and instruction loading only. It does
     not change product direction, active work, milestone status or acceptance,
     architecture, deployment, strategy or evidence boundaries, credential
     authority, paper/live gates, or capital authority.

     Documentation-impact assessment: `AGENTS.md`, the agent policy, and this
     decision log are updated; the two native Codex skill procedures are added.
     `docs/CHAT_HANDOFF.md`, `README.md`, the infrastructure inventory, the
     current-status annotation on ADR 0009, and active agent-allocation or
     proof-actor wording in ADRs 0003 and 0010 are updated in the combined
     change so active navigation and procedures no longer route work to
     inactive tooling. The ADR 0003 and ADR 0010 wording corrections change no
     product architecture or credential gate.
     `docs/MILESTONES.md` is not applicable because product order, status,
     scope, and acceptance are unchanged. `CLAUDE.md` and `.claude/**` are not
     applicable and remain untouched by owner instruction. No new ADR applies
     because product architecture, deployment, security, data flow, and
     integration are unchanged. No product runbook or specification changes
     because no operator or runtime procedure changes.

291. **Narrow selected-run Results blocker correction authorized (accepted
     2026-09-20).** The owner confirms that truthful inspection of the first
     controlled MES ORB results is an operational blocker and authorizes the
     smallest correction to the existing selected-run Results page. This
     supersedes only Decision 287's treatment of the current Results behavior
     as good enough and frozen for this verified blocker. It does not restore
     Decision 286's former dashboard-first sequence or temporary planning
     ceiling, authorize broad dashboard work, or change the active controlled-
     research path.

     Reuse the existing Plotly Dash application, Plotly chart, persisted run
     adapter, AG Grid and trade explorer. Through normal navigation the owner
     must be able to select a saved R07-shaped run, inspect its recorded native
     five-minute chart and linked entry/exit trades, see recorded costs, returns,
     drawdown, all ranked rows and rejection reasons, understand its evidence,
     protected-data and promotion limits, and reopen the exact run without
     identity confusion. Missing interval, units or protected-data facts fail
     closed. MES prices remain index points while recorded fees and P&L remain
     USD. The persisted annualized-return metric remains unchanged and is
     labelled as an engine output whose calculation basis was not persisted;
     it is not relabelled as calendar CAGR. When persisted total return and
     parseable actual-coverage dates are both present, show calendar CAGR
     separately as a derived coverage-period value, not as engine annualization
     or a new screening metric; otherwise omit it.

     This is a selected-run usability correction, not the scalable multi-run
     surface, cache, redesign, new framework, schema change, research rerun,
     protected-data inspection, strategy change, deployment, beta completion,
     Milestone 23 acceptance, edge claim, paper activation or live authority.
     Current-revision focused and real-browser evidence plus independent review
     are required before integration. Deployment and renewed owner acceptance
     remain separate later steps.

     Documentation-impact assessment: `docs/MILESTONES.md` and the Milestone
     23 acceptance record are updated because active R07 inspection and
     selected-run implementation status change; the dashboard product
     requirements and infrastructure inventory are aligned to the narrow
     exception; `README.md` is updated because its public current-direction
     summary would otherwise retain the superseded freeze wording; this
     decision log is appended. `AGENTS.md`, the agent policy and ADR 0008 are
     not applicable because agent behavior, architecture, routing and
     dependencies do not change. No runbook applies because deployment and
     runtime operation are excluded.

292. **Economical reuse-first dashboard improvement direction accepted
     (accepted 2026-09-20).** The owner approves starting a bounded dashboard
     improvement direction to shorten the path to an operator-usable MVP. The
     approved chart-first Results experience remains the product anchor. Work
     must reuse the existing Plotly Dash application, Plotly, VectorBT Pro,
     persistence and suitable maintained prebuilt components. Reusable QAMC
     component patterns may be examined, but only technically and licensing-
     compatible parts may be adopted; no incompatible dependency or copied
     implementation is authorized.

     This supersedes only Decision 287's dashboard freeze to permit the
     bounded blueprint and later owner-approved thin essential-beta slices. It
     does not expand Decision 291's narrow R07 correction or restore
     dashboard-first sequencing.

     The first deliverable is a small connected-screen blueprint showing the
     essential beta journey and its existing data and callback connections.
     Only after that blueprint is bounded may thin slices improve the essential
     beta journey. Use cost-effective, bounded subagents where delegation is
     useful and keep review proportional to the slice. Inactive or secondary
     pages, a new framework, a global rewrite, deployment, paper/live work and
     broad polish are deferred. This direction does not approve an exact
     scalable multi-run UI, executable implementation, deployment, beta
     completion or owner acceptance of an eventual implementation. Any
     scalable multi-run portion of the blueprint remains subject to the
     Decision 282 bounded-design owner review and acceptance before code;
     agent-bounding alone does not authorize implementation.

     R07 remains priority 1 and its backed-up target deployment, validation and
     operator inspection remain separately unauthorized and target-dependent.
     R05 is the next repository-local work for the blueprint and bounded
     dashboard direction; this does not waive Milestone 23 gates, controlled-
     research safeguards or any execution and capital boundary.

     Documentation-impact assessment: `docs/MILESTONES.md`, the dashboard
     product requirements and `README.md` are updated to record the accepted
     direction and current order; this decision log is appended. `AGENTS.md`
     and the agent policy are not applicable because no stable operating rule
     changes. `CHAT_HANDOFF.md` is not applicable because this is navigation-
     only orientation that points to Tier 1 authorities. No ADR applies because
     no architecture or dependency is selected. No runbook applies because no
     operator or runtime procedure changes. The requirements document and
     README are updated as stated; no other governance row is implicated.

293. **Connected-screen dashboard blueprint explicitly approved (accepted
     2026-09-20).** Terry explicitly approves the bounded R05 connected-screen
     blueprint. Preserve **Home**, **Ideas**, **Set up**, **Run test**, and the
     approved chart-first **Results** experience. Economically reuse the
     existing **Compare** route as the separate **Find & Compare** surface.
     One selected saved test opens its exact **Results** view; selecting two to
     four saved tests feeds the existing **Compare** route. One table row
     represents one saved test, and any top-ranked variation metrics must be
     explicitly labelled as variation metrics.

     First run a cheap synthetic approximately 1,000-row responsiveness and
     data-path check. Only after that measured check may the smallest
     implementation slice be bounded. No new framework, schema, cache,
     backend store, or global restyle is authorized unless evidence proves one
     unavoidable. Broad redesign, deployment, backtests, market data,
     paper/live work, caching, export, and polish are deferred.

     This fulfills Decision 282's bounded-design owner review for the
     specifically defined **Find & Compare** surface and authorizes the first
     thin implementation slice after the synthetic check, strictly within the
     boundaries above. It remains accepted design and authorization to begin a
     bounded slice, not completed implementation, testing, deployment, beta
     completion, or operator acceptance. Any design expansion beyond this
     accepted surface requires new owner review before implementation. R05
     remains in progress; the synthetic check is its next repository-local
     action, followed by the authorized smallest slice.

     Documentation-impact assessment: `docs/DECISIONS.md`,
     `docs/MILESTONES.md`, and the dashboard product requirements are updated
     because this is a durable accepted design and changes R05's next action
     and evidence boundary. `AGENTS.md` and the agent policy are not
     applicable because no stable operating rule, delegation rule, or agent
     allocation changes. No ADR applies because no architecture, framework,
     dependency, schema, cache, backend store, deployment, security, data
     flow, or integration is selected. `CHAT_HANDOFF.md` is not applicable
     because Tier 1 authorities already contain the durable direction and no
     startup navigation changes. `README.md` is not applicable because public
     orientation is unchanged. No runbook or procedure applies because no
     operator, recovery, migration, runtime, paper, or live procedure changes.
