# Quant Factory Operator Interface Reconstruction

> **Status:** Current reconstruction direction under Decisions 337–339. Owner approval
> is required before application implementation. `docs/MILESTONES.md` remains
> the sole authority for current phase, queue, blockers, and next action.

## Purpose

The October 7, 2026 unaided owner walkthrough found the seventh Dashboard to
Compare interface iteration unusable. The correction is an operator-interface
reconstruction over the existing proven backend, not a list of isolated button
or wording fixes. It is a greenfield presentation and interaction system inside
the retained architecture, not a greenfield technical rewrite.

Retain persistence, evidence, lineage, execution gates, Plotly Dash, Dash AG
Grid, licensed VectorBT Pro, the generic runtime, and useful design research.
Replace the page hierarchy and state presentation that prevent the owner from
understanding what is happening, what happened, what survived, what requires
authority, and what is permitted now.

This specification does not authorize implementation, tests, browser
automation, deployment, a Candidate, a pull request, a VectorBT Pro upgrade,
protected evidence, paper/live trading, orders, or capital.

## Required source order

After compaction or handoff, do not reconstruct current direction from older
chat or read the repository chronologically. Read:

1. `AGENTS.md`;
2. current phase and active work in `docs/MILESTONES.md`;
3. the current index and Decisions 337–339 in `docs/DECISIONS.md`;
4. this specification;
5. the October 7 VPS handoffs:
   `/home/ubuntu/quant-factory-owner-handoff-2026-10-07/quant-factory-rebuild-planning-handoff.md`
   and
   `/home/ubuntu/quant-factory-owner-handoff-2026-10-07/quant-factory-owner-walkthrough-and-defects.md`;
6. the historical page references under
   `docs/assets/dashboard/operator-workflow-approved/` as content inventories
   and failure evidence, not visual targets; and
7. for Results only, the retained Greenfield source and screenshots under
   `/home/ubuntu/.codex/visualizations/2026/09/18/01a0b224-cc29-7182-93c9-6ce5e2c0ce45/`.

Older decisions, milestone records, mockups, and acceptance packages remain
historical evidence. They do not override current Tier 1 or Decisions 337–339.

## Authority correction

Decision 336's measured Results performance remains accepted: 3.863 seconds to
usable Overview and 5.424 seconds to the interactive chart were adequate for
the private beta. Its conclusions that the interface was usable, R12 was
complete, and Candidate research was next are superseded by Decision 337.

The October 5 browser passes proved limited mechanical behavior. They reached
routes, rendered some states, used direct fixture URLs, and observed no browser
errors. They did not prove persisted-run discovery, Compare selection,
post-run Candidate eligibility, representative current state, or unaided owner
comprehension.

## Product model

Quant Factory is a high-throughput automated filtration system with
exception-based owner authority. Owner- and LLM-authored QF Candidate packets
enter the same provider-neutral conveyor. Deterministic validation, bounded
repair, prior-work checks, immutable study construction, VectorBT parameter and
variant evaluation, screening, OOS, walk-forward, robustness, and Monte Carlo
remove weak or invalid work and surface the rare survivors. The owner needs
visibility into:

- active, queued, blocked, and completed agent or campaign work;
- Candidates entering and leaving each gate;
- test status and evidence outcome;
- fixed objectives, bounds, budgets, and stop rules;
- reasons evidence passed, failed, or became invalid;
- lineage from idea through Candidate, setup, run, evidence, and decision; and
- every exception or survivor requiring owner authority.

Ordinary in-policy Candidates progress without a per-item owner click after a
future campaign-level research lane is authorized. Autonomy does not authorize
agents to change parameters after seeing results, expand a search from its
precommitted bounds, tune the two screened-out MES Candidates, inspect
protected evidence, promote an edge, or activate paper/live trading.

## Design evidence

### Greenfield Results

The Greenfield preview is the approved Results interaction reference. It
requires a chart-first selected-run workspace, visible identity, separate Bars
and View controls, linked chart and completed-trade ledger, progressive
disclosure, resizable chart/report regions, normal-flow Metrics and Trades,
Change run, and Reset layout.

Its broader lesson is interaction quality: the primary object dominates;
related evidence is visibly connected; controls are direct and local; detail
does not precede the task; selections have visible consequences; and the user
can recover the layout. Those principles may inform other pages, but the
Greenfield layout itself is Results-only.

### Historical page references

Repository-owned page references remain useful as content inventories, domain
facts, and evidence of approaches that failed unaided use. They are not
contracts for composition, shell, visual language, density, styling, or
interaction. No later page may claim conformance merely by reproducing them.

### Dashboard convention

Dashboard answers **What is happening now?** It summarizes and supports
drill-down through the owning pages. It does not own intake, setup, launch,
approval, or investigation.

## Architecture to retain

- Existing backend services, persistence, artifacts, evidence, and lineage.
- Candidate identity and immutable versioning.
- Candidate-to-configuration and configuration-to-run bindings.
- Exactly-once launch, campaign budgets, bounded automated progression, and
  explicit exception/survivor gates.
- Plotly Dash, VectorBT Pro, Plotly, and Dash AG Grid.
- Mounted-route architecture with lightweight inactive routes.
- Greenfield Results evidence and useful domain content identified in the
  historical page references.
- Protected-evidence, promotion, paper/live, broker, and capital boundaries.

Retained architecture is still verified at its owning boundary. It is not
assumed correct merely because it exists.

## Architecture to correct

- Historical Candidate acceptance used as current eligibility.
- Page-local summaries that disagree about the same persisted state.
- Dashboard workflow-action logic.
- Overlapping or ambiguous page responsibilities.
- Generic status that mixes orchestration, evidence, decision, and authority.
- Empty states that hide persisted work.
- Controls that appear editable or actionable when they are not.
- Direct fixture URLs used instead of visible discovery.
- Acceptance based on empty, earlier, or non-representative states.
- Results behavior that diverges from Greenfield without an owner decision.
- The seventh iteration's dark-sidebar, pale-canvas, card/status-heavy visual
  system and its page-local interaction patterns.

## Shared factory state

Define one read-only presentation projection from existing authoritative
records before rebuilding page bodies. Do not create a second database,
orchestrator, or evidence source.

Keep these dimensions independent:

| Dimension | Meaning | Examples |
|---|---|---|
| Candidate lifecycle | Position in the factory | Draft, validating, repairing, duplicate, bounded, implementation blocked, eligible, screening, validating evidence, screened out, qualified |
| Run status | Orchestration state | Not run, queued, running, succeeded, failed, cancelled |
| Evidence outcome | Research conclusion | Not run, passed, failed screen, insufficient, invalid |
| Authority state | Durable permission | In-policy automation, exception hold, paper-lane eligible, paper-lane inactive |
| Current eligibility | What is permitted now | Intake only, repair eligible, bounded study eligible, queued, review evidence, no rerun or tuning |
| Current attention | Owner involvement | None, unresolved meaning, prior-work judgment, cost/data authority, paper-lane authority, system intervention |

Do not collapse these into generic labels such as **Accepted**, **Ready**, or
**Failed**.

The shared factory snapshot supplies qualified edges, queued/running/completed
tests, Candidate counts at each gate, owner interventions required, classified run
failures and system problems, readiness with observation time, autonomous
activity, latest findings, and current authority boundaries. Every page may
add local detail but may not redefine the same truth.

## Automated filtration implementation contract

This section is the implementation contract for Decision 339. It replaces the
old assumption that every Candidate waits for owner acceptance or a manual
launch. It does not activate research; the campaign policy values below must be
configured and separately authorized before unattended execution.

### One conveyor, separate state dimensions

The implementation must derive one lifecycle projection without overwriting
the existing run, evidence, or authority records:

```text
received -> validating -> repairing -> study_planning -> implementation_check
         -> eligible -> queued -> screening -> OOS -> walk_forward
         -> robustness -> Monte_Carlo -> qualified_survivor
```

At any gate the Candidate may instead become `duplicate_closed`,
`screened_out`, `invalid`, `implementation_blocked`, `budget_blocked`, or
`exception_hold`. These are lifecycle outcomes, not synonyms for a failed run.
Existing persisted `ready_for_review` and `owner_approved` values are historical
compatibility inputs; new eligibility comes from policy evaluation rather than
renaming either value.

### Automatic gates

For every imported Candidate, one idempotent coordinator must:

1. parse the non-executable packet and retain its source bytes and identity;
2. validate schema, provenance, intraday mandate, safety boundaries, and
   testable semantics;
3. apply only permitted normalization or bounded repair, always as a new
   immutable version when content changes;
4. compare exact identity and economic meaning with prior Candidates, studies,
   and closed work;
5. compile fixed rules, variables, conditional relationships, and structural
   variants into an immutable study plan;
6. precommit data period and splits, costs, execution assumptions, objective,
   ranking/rejection metrics, evidence gates, multiplicity policy, and budgets;
7. resolve a versioned strategy adapter and prove that its configuration
   matches the Candidate and study checksum;
8. admit the study only when the active campaign has enough remaining authority
   and budget, then create exactly one durable launch claim;
9. use the existing `CandidatePipelineRuntime` and `FactoryFilterChainService`
   to stop or advance through screening, OOS, walk-forward,
   robustness/regime, and Monte Carlo from persisted evidence; and
10. materialize full portfolios, charts, trades, and evidence only for the
    predeclared finalist set, then route a genuine survivor to the separately
    governed paper boundary.

Every gate writes its input identity, policy version, outcome, reason codes,
observation time, and next eligibility. Replaying the same Candidate and policy
must reopen the same outcome or resume safely; it must not create another run.

### Repair boundary

| Treatment | Permitted behavior |
|---|---|
| Deterministic normalization | Safe YAML/JSON canonicalization, canonical enum aliases, lossless units/time-zone normalization, deduplication of identical values, and explicit Quant Factory defaults such as the currently authorized fee model. Retain a field-level diff and provenance. |
| LLM-assisted repair | At most two attempts, each producing a child Candidate version with source references, changed fields, rationale, and validation result. It may make already-supported meaning explicit; it may not create unsupported strategy meaning. |
| Immediate policy rejection | Out-of-mandate market/holding rules, forbidden executable or trading instructions, invalid bounds, or an exact closed-work duplicate. Persist the reason; do not ask for an owner click. |
| Exception hold | Meaning remains ambiguous, economic-equivalence deduplication is uncertain, required authority/data is unavailable, or an implementation choice would materially change the hypothesis. Show the smallest decision needed. |
| Prohibited repair | Invent source facts, alter the hypothesis, add indicators or variants, widen a range, change the objective/data split/costs after results, weaken a gate, refine a failed region, inspect protected evidence, or promote an edge. |

Repair exhaustion is a normal terminal intake outcome. It must not loop, quietly
fall back to a guess, or turn the owner into a general packet editor.

### Study and search rules

The study compiler—not the dashboard—owns the executable research contract.
It must produce a canonical `StudyPlan` identity containing:

- Candidate and version, strategy adapter and version, instrument, bar interval,
  session, direction, date range, calendar, and data identity;
- fixed values; bounded variables and classifications; conditional
  relationships; separately identified structural variants; reference
  configuration; and total Cartesian size;
- execution costs, sizing, timing, cash, leverage, and annualization basis;
- exact objective, ranking order, rejection metrics, screening thresholds,
  OOS split, walk-forward policy, robustness neighborhood, regimes, cost stress,
  Monte Carlo policy, and finalist count;
- grid, conditional-grid, or random-subset method; sample seed when relevant;
  chunk size; concurrency; time/compute/cost limits; and artifact-retention
  policy; and
- campaign-policy version, study checksum, creation time, and complete lineage.

VectorBT Pro evaluates this declared space efficiently; it does not choose a
new hypothesis or silently enlarge the space. Search returns lightweight
ranking/rejection metrics. Full artifacts are recomputed only for declared
finalists. Selection favors stable neighboring regions and downstream evidence,
not the single best historical return. Local refinement is a new precommitted
study version and is allowed only when the campaign policy explicitly defined
that refinement before seeing the triggering results.

### Campaign authority and budgets

The research lane remains disabled until one durable campaign policy specifies
all of the following values:

- allowed instruments, holding style, sessions, strategy families, data
  sources, and date horizons;
- maximum active Candidates, studies per Candidate, structural variants,
  parameter combinations or random samples, finalists, and concurrent runs;
- per-study and campaign-wide wall time, compute, storage, and material-cost
  ceilings;
- retry limits, the two-attempt repair limit, infrastructure-failure circuit
  breaker, cancellation behavior, and campaign expiry;
- mandatory objectives, costs, data splits, multiplicity controls, evidence
  stages and thresholds; and
- permitted automatic outcomes plus the protected-data, paper, live, broker,
  and capital boundaries that remain closed.

Missing policy values fail closed. Budget exhaustion pauses admission; it does
not truncate a study, alter its method, or seek owner approval Candidate by
Candidate. A policy change creates a new version and affects only work that has
not begun unless an explicit migration is approved.

### Owner and system queues

The owner queue contains only:

- unresolved semantic meaning after bounded repair;
- uncertain economic equivalence with prior closed work;
- requested mandate, paid-data, material-cost, or protected-boundary expansion;
- a strategy-adapter decision that changes the hypothesis rather than merely
  implementing it;
- a survivor requiring a new execution vehicle or paper-policy expansion; or
- activation or material expansion of paper/live/broker/capital authority.

Infrastructure outages, ordinary code defects, exhausted retries, corrupt
artifacts, and worker failures go to a distinct system-intervention queue.
Ordinary validation rejection, duplication, screening failure, and downstream
evidence failure are recorded and closed automatically. They are not owner
decisions.

### Required implementation slices

1. Add a read-only lifecycle/eligibility projection and map historical states
   without rewriting sealed records.
2. Add a versioned campaign-policy evaluator and canonical `StudyPlan`
   compiler using QF Candidate and parameter-governance contracts.
3. Add immutable repair lineage, prior-work classification, budget admission,
   and typed exception/system queues.
4. Replace `owner_approved_candidate_screening_only` as the launch predicate
   with policy-derived eligibility while retaining exactly-once durable claims
   and historical compatibility.
5. Connect eligible studies to the existing generic runtime and filter chain;
   do not build another orchestrator.
6. Rebuild the Candidate workspace as the high-volume intake, study,
   execution, evidence-timeline, and exception surface over those shared
   services. Do not preserve Ideas, Set up, and Run test as mandatory pages.
7. Add survivor handoff to the separately activated ADR 0006 paper lane; do not
   automate paper-to-live promotion.

Known compatibility seams are explicit implementation work, not reasons to
preserve the manual workflow:

| Current seam | Required correction |
|---|---|
| `research_intake/qf_candidate.py` | Preserve import safety and current limits, but replace the `ready_for_review`/`owner_approved` decision path with versioned validation, repair, policy eligibility, and historical-state mapping. |
| `orchestration/research_launch_claims.py` | Replace `owner_approved_candidate_screening_only` with a versioned campaign-policy eligibility identity while preserving the durable claim, idempotency, and fail-closed recovery contract. |
| `orchestration/candidate_pipeline_runtime.py` | Reuse the generic runtime; consume the immutable StudyPlan identity rather than a manually approved configuration assumption. |
| `orchestration/filter_chain.py` | Retain its persisted evidence-derived stop/advance behavior; expose typed outcomes to the shared factory projection. |
| Candidate dashboard callbacks/pages | Remove ordinary accept/launch controls and render automatic state, repair lineage, budgets, exceptions, and survivor authority from shared services. |

Implementation must update the contracts and their focused tests together. It
must not change sealed Candidate/run evidence or migrate historical review
records into false automatic-policy decisions.

### Focused proof

Use a deterministic, non-market fixture set containing: a clean Candidate; a
syntax-only repair; repair exhaustion; an exact duplicate; uncertain
economic-equivalence; a mandate violation; a missing adapter; a budget-exceeded
study; an ordinary screening rejection; and a downstream evidence rejection.
Prove that clean in-policy work reaches the queue without an owner click;
repairs create immutable lineage; duplicate replay creates no second run; every
failure stops with a typed persisted reason; the existing filter chain alone
controls downstream progression; only declared finalists receive full
artifacts; no protected, paper, live, broker, or capital boundary is crossed;
and only true exceptions or survivors appear in the owner queue. This proof is
separate from the page-level technical, control, visual, and unaided-owner
acceptance gates.

Visible actions derive from current eligibility. Omit an unauthorized action
and explain why. Use disabled controls only when a visible prerequisite on the
same page can make the action valid.

For the current MES ORB/VWAP Candidate:

- historical acceptance authorized one proof test;
- the run succeeded mechanically;
- the evidence failed the initial screen;
- the Candidate is screened out;
- rerun and tuning are not eligible;
- sealed history may be reviewed; and
- new research begins with a different Candidate in the Candidate Universe.

## Information architecture

The inherited six-page sequence is superseded. It described backend stages as
pages and implied that the owner manually shepherds one Candidate through
Ideas, Set up, and Run test. The automated factory needs stable places to
observe the whole system, investigate one Candidate, inspect evidence, compare
survivors, and resolve rare exceptions.

The primary navigation is:

1. **Dashboard** — factory-wide oversight and the front door;
2. **Candidates** — the searchable Candidate Universe and selected-Candidate
   workspace;
3. **Results** — deep evidence for one selected run or finalist; and
4. **Compare** — comparison of compatible finalists, parameter regions, or
   surviving Candidates.

**Dashboard** is not replaced or renamed **Factory**. The factory is the
subject of the Dashboard. **Candidate workspace** is a selected mode inside
Candidates, not another primary navigation item. Intake and Exceptions are
capabilities within Dashboard/Candidates unless demonstrated volume later
justifies separate routes. System status remains a utility destination rather
than part of the research journey.

The normal movement is:

```text
owner/LLM intake -> automatic factory -> Dashboard/Candidate Universe
                                      -> Candidate workspace -> Results
                                      -> survivors -> Compare
                                      -> true exception -> precise owner action
```

The owner does not navigate Set up and Run test to keep normal work moving.
Generated study and execution state remain visible and auditable inside the
Candidate workspace.

## Surface contracts

### Dashboard

**Question:** What is happening in Quant Factory now?

Retain the route and useful semantic concepts. The shell, page composition,
styling, and interaction model are open to the new coherent product design.

The first viewport shows:

1. page identity and purpose;
2. truthful intake throughput, queued/running work, rejection flow, survivors,
   and owner-attention counts;
3. campaign readiness, budget/resource use, and observation time;
4. autonomous activity or **No research is running**;
5. exception and survivor gates; and
6. classified research failures and system problems.

The owner-approved first implementation slice leads with a **Current Factory
operations** panel above the analytical charts. It uses persisted run state to
show active and queued identities, stage/status, elapsed time, authoritative
or unavailable ETA, orchestration acknowledgement, and failure state. It does
not label paper or live trading as active research.

For the current state it must say: no research is running; two tests completed;
both fixed MES Candidates screened out; zero qualified edges; no Candidate
currently requires owner intervention; and new research requires a future
authorized automated campaign.

Remove **Capture idea**, **Inspect failure**, the dominant **Next action** card,
false **Active test** wording, and claims that persisted research is absent.
Navigation remains in the shell. Candidate investigation belongs in Candidates,
deep evidence belongs in Results, and infrastructure investigation belongs in
System status.

The dominant operational section is the interactive **Candidate Universe**. It
shows volume and movement across intake, repair, study planning, queue,
screening, validation, rejection, and survivor stages. Selection opens the
exact Candidate workspace; a chart mark, stage count, or exception count must
have a visible drill-down consequence.

Below the fold retain only decision-useful running/recent research, latest
findings, parameter-region/generalization views, evidence survival, data
readiness, rejection reasons, detailed attention items, and campaign lineage.
Evidence Survival must not consume large space when it conveys little. Empty
charts collapse to compact explanations until qualifying evidence exists.

### Candidates and Candidate workspace

**Question:** What Candidates exist, where is each one in the factory, and what
does the complete record show for the selected Candidate?

The Candidate Universe is searchable, filterable, sortable, and designed for
hundreds of strategies and much larger parameter/variant cohorts. It preserves
selection while moving between overview and detail. Its default view favors
stage, family, campaign, disposition, recency, exception, survivor, and
resource/budget signals rather than long static descriptions.

The approved default population is **Survivors**: the gold that has explicitly
survived the recorded filtration gates. The grid supports sorting, filtering,
column reordering, and selection by Sharpe, net return, maximum drawdown, OOS
performance/retention, robustness, trade count, and paper eligibility. Missing
persisted metrics display **Unavailable** and are never synthesized. One
selection opens exact Results; two to four selections expose **Compare
selected** as a secondary action.

Survivor membership is fail-closed. The authoritative filter-chain outcome
appends one idempotent `ready_for_protected_test` marker to the screening run,
which remains the Candidate row and exact Results identity because it owns the
ranked metrics, portfolio, chart, and trades. Page loading reads that marker;
it does not replay validation artifacts or infer survival from labels.

The page owns:

1. **New idea**, **Import Candidate**, and **Download AI brief**;
2. high-volume intake queue and history with current validation, repair,
   duplicate, mandate, study, execution, evidence, and disposition state;
3. a clearly named selected Candidate with its separate lifecycle, run,
   evidence, authority, eligibility, and attention states;
4. compact hypothesis, sources, rules, rationale, disproof conditions, and
   provenance, with full static detail behind disclosure;
5. the immutable generated StudyPlan: instrument, timeframe, period, session,
   costs, execution assumptions, data, variables, structural variants,
   combination/sample and compute budgets, objective, multiplicity controls,
   evidence gates, adapter identity, and checksum;
6. queue and execution history, automatic repair/progression history, evidence
   timeline, stop reasons, artifacts, and complete lineage; and
7. an exception action only when deterministic policy cannot continue.

Downloading the AI brief changes no research state. Intake itself does not run
a test, but a valid Candidate may later progress automatically when the R15
campaign lane is activated and all policy gates pass. Do not ask the owner to
approve ordinary Candidates. Syntactic normalization and deterministic
defaults may repair packets automatically with provenance; an LLM repair loop
creates a new version and revalidates it. Unresolved meaning, disputed
prior-work equivalence, or mandate/cost/data expansion stops with a precise
exception. A change to study meaning creates a new Candidate or StudyPlan
version; it never edits a tested contract in place. A screened-out Candidate
remains read-only history, offers no rerun or tuning action, and links to its
sealed Results. Succeeded orchestration does not mean passed evidence.

The current **Ideas**, **Set up**, and **Run test** routes may be retained only
as temporary compatibility redirects during an authorized implementation.
They are not independent product destinations or acceptance units.

### Results

**Question:** What happened in this run or finalist, is its evidence usable,
and did it survive the next filter?

Restore Greenfield as the interaction anchor: visible persisted-run discovery,
selected-run identity and separate state dimensions, truthful OHLC and trade
markers, Bars and View controls, linked completed-trade ledger, normal-flow
Metrics and Trades, resize, Reset layout, and progressively disclosed evidence,
variants, assumptions, lineage, review, and technical detail.

Direct entry with persisted history must not strand the owner at **No run
selected** without a visible selector. A run reached from a Candidate workspace
may be preselected, but Results remains a cross-Candidate run browser.

Do not combine reconstruction with performance optimization, a VectorBT
upgrade, or new research.

### Compare

**Question:** Which persisted runs can be meaningfully compared, and where do
they differ?

Canonical persisted history and eligible finalists must be discoverable.
Excluded runs remain listed with their exclusion reason. Rename **Add persisted
run** to **Choose candidates/runs** or equivalent discovery language.

For two to four selections, show each identity and state, comparability
warnings, valid normalized equity and drawdown, aligned metrics and basis,
parameter/data/period/cost/execution differences, validation and review
differences, and links to each Results record. Compare selection is independent
of Results and never executes or changes research.

### Exceptions and system status

Exceptions are an owner-attention queue available from Dashboard and Candidates,
not a mandatory workflow page. Each item states what stopped, why automation
cannot decide, the exact decision or authority requested, consequences, and a
link to the affected Candidate. Ordinary rejections never appear here.

Infrastructure failures and corrupt or missing artifacts belong to a separate
System status utility. They must not be presented as trading-strategy failures
or owner research decisions.

## Representative states

Each page is designed and proved with meaningful persisted states:

1. current factory: no active research, two screened-out MES Candidates, no
   qualified edge, no Candidate awaiting acceptance;
2. Candidate automatically validating or undergoing bounded repair;
3. eligible immutable study within an authorized campaign;
4. queued or running test;
5. completed screened-out test;
6. failed run or system problem with classified impact;
7. missing or corrupt evidence; and
8. comparable and non-comparable selections;
9. high-volume Candidate and parameter/variant cohorts; and
10. a genuine exception requiring owner authority.

The current factory state is Dashboard's first proof state. The screened-out
Candidate is the first Candidate-workspace and Results-discovery proof state.
Compare uses one comparable and one excluded persisted selection set. The
high-volume proof must show that navigation and comprehension do not depend on
opening every Candidate.

## Authorized implementation sequence

1. **Information architecture:** retain Dashboard as the front door; adopt
   Dashboard, Candidates, Results, and Compare as primary navigation; absorb
   Ideas, Set up, and Run test into the Candidate workspace; keep Exceptions
   contextual and System status separate.
2. **Shared truth:** trace existing records and establish the read-only
   lifecycle, eligibility, and factory snapshot. Stop if truth cannot be
   derived without inference.
3. **Shared product design:** approve the navigation, shell, common state
   language, Dashboard, and Candidate-workspace relationship before code.
4. **Dashboard:** implement the approved current-operations-first composition,
   then stop for owner review before deployment.
5. **Candidates:** implement the approved Survivors-first high-density Universe
   and exact Results/secondary Compare actions, then stop for owner review.
6. **Results:** restore discovery and Greenfield interaction; stop for approval.
7. **Compare:** repair finalist/run discovery before comparison presentation;
   stop for approval.
8. **Connected walkthrough:** record revision and starting state, use visible
   controls rather than fixture URLs, and keep each acceptance gate separate.
9. **Final authority:** only after owner acceptance, record the implemented
   pages, representative states, deployed revision, and remaining limitations.

Do not accumulate the product before review. One surface failing owner
comprehension stops progression.

## Four acceptance gates

### Technical correctness

Correct identities and state are read from authoritative persistence; evidence
is not fabricated; passive loading does not mutate state.

### Working controls

Every visible control performs its stated action in the representative state.
Unavailable actions are absent or truthfully blocked. Route navigation is not
a workflow proof.

### Visual conformance

Compare the meaningful state with its newly owner-approved design. Assess
composition, hierarchy, density, spacing, labels, affordances, and prohibited
legacy content. Results includes Greenfield interaction conformance.

### Unaided owner comprehension

Without developer narration, the owner can state what the page shows, what
happened, what needs attention, what actions are available, and what each
action authorizes. Only the owner closes this gate.

Passing one gate does not compensate for failing another.

## Stop rules

- Do not patch page-local wording over a shared state contradiction.
- Do not use empty state to prove populated behavior.
- Do not use direct fixture URLs to prove discovery.
- Do not call text presence, HTTP success, or a clean console visual or workflow
  acceptance.
- Do not start Candidate research, Results optimization, a VectorBT upgrade,
  infrastructure, deployment, or another task as substitute work.
- Preserve `/home/ubuntu/projects/Quant-Factory` and its uncommitted Compare
  changes.
- Stop after each owner-visible surface for explicit owner approval.

## Owner decisions and remaining gates

The owner approved the automated-filtration product model in Decision 339,
Dashboard-centered information architecture in Decision 340, and the
consolidated visual/workflow direction plus first Dashboard/Candidates
implementation slice in Decision 342. Remaining incremental gates are:

1. owner review of the implemented Dashboard and Candidates slice;
2. Results integration while preserving Greenfield interaction;
3. Compare integration and the distinct Exceptions/System-status presentation;
4. deployment; and
5. unaided owner comprehension on the deployed representative states.

Approval of one surface does not silently approve the next.
