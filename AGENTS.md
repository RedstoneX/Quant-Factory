# Quant Factory Codex Instructions

## Mission and authority

Quant Factory is Terry's private, single-operator system for finding,
rejecting, and rigorously validating defensible trading edges. Converting a
qualified edge into consistent income is secondary. Infrastructure, UI,
deployment, and broker work exist only to serve those goals.

The closed Tier 1 authority set is:

1. `AGENTS.md` — stable operating contract.
2. `docs/MILESTONES.md` — sole authority for current phase, queue, blockers,
   sequence, and milestone status.
3. `docs/DECISIONS.md` — accepted owner decisions and supersessions.

Before substantive work, read `docs/MILESTONES.md`, the current index at the
top of `docs/DECISIONS.md`, and only the decisions and supporting material the
task requires. Supporting documents cannot set current priority, status, or
authority. Follow `docs/DOCUMENTATION_GOVERNANCE.md` for documentation changes.

Codex is the sole active project agent toolchain. Only Terry may change the
mandate, accept milestones, authorize deployment, or approve paper/live
trading and capital exposure.

## Current sequence and gates

Follow the queue in `docs/MILESTONES.md`:

**provider-neutral Candidate intake -> automated validation, bounded repair,
and prior-work checks -> immutable bounded studies -> VectorBT screening and
staged validation -> survivor review -> execution-vehicle comparison -> paper
operation -> live operation later**

Complete the objective dashboard and operator-workflow criteria before owner
handoff. Reuse the generic backend, audited MES run, approved visual contract,
licensed VectorBT Pro, mature components, and existing tests. Do not rebuild
the backend, add another frontend or orchestration layer, or introduce
enterprise infrastructure for this single-user product.

When `docs/MILESTONES.md` records a technical pass, owner gate, or blocked
owner decision, stop there. Do not substitute deferred work unless the active
milestone or Terry explicitly authorizes it. A reported defect authorizes its
smallest root-cause correction; it does not reopen adjacent scope.

QF Candidate v1 is the provider-neutral intake boundary. During the current
R12 design gate, Quant Factory may parse, validate, persist, display, edit,
import, and export Candidate packets but no research campaign is active.
External LLMs, owner-authored submissions, and any future built-in analyzer
must produce the same Candidate contract; no model is required. After Tier 1
separately activates an automated research lane, an ordinary in-mandate
Candidate may progress without per-item owner approval through deterministic
validation, provenance-preserving normalization, bounded repair,
deduplication, immutable study construction, screening, and staged validation
within the accepted budgets and evidence policy.

Use QF Research Context v1 as the portable companion for external research. It
is a supporting snapshot of mandate, prior work, data, deduplication rules,
and the Candidate output contract. Re-check current Tier 1 and local evidence
before acting on it.

Before unattended Candidate research, Terry must accept the campaign-level
mandate, data authority, compute/concurrency budgets, repair limits, search
bounds, evidence gates, and stop conditions. Terry does not approve every
ordinary Candidate or parameter combination. Route only genuine exceptions to
the owner: unresolved strategy meaning, disputed prior-work equivalence,
mandate or cost expansion, paid/protected data, paper-lane activation or
material expansion, and all live/capital authority. Inside an already activated
paper lane, an ordinary eligible survivor may cross automatically through the
Decision 341 handoff. Prior work closes only its stated hypothesis,
rules, and parameter space; it does not close a broader strategy family unless
Tier 1 says so.

The operator information architecture has seven named surfaces: Dashboard,
Submit Strategies, Factory runs, Candidates, Results, Compare Selected, and the
external Paper Trading destination. Dashboard is the live oversight front
door. Candidates is the high-density survivor/ranking surface. Compare Selected
is a secondary action from Candidates, not a primary workflow or promotion
gate. Paper Trading remains a separate project reached by an external link;
Quant Factory shows only package/handoff state. Dashboard has its own exact
approved contract. The other six surfaces share the approved workspace
contract; implement them in milestone order and stop after each owner-visible
surface for acceptance.

## Frontend and visual acceptance

For every operator-facing frontend, UI, UX, styling, interaction, or visual-
conformance task, load and follow
`.agents/skills/quant-factory-frontend/SKILL.md` before editing. The two
non-overlapping repository-owned contracts are:

- `docs/assets/dashboard/current-visual-contract/dashboard.html` for Dashboard;
- `docs/assets/workspaces/current-workflow-contract/workspaces.html` for
  Candidates, Results, Factory runs, Submit Strategies, Compare Selected, and
  the external Paper Trading destination.

The Dashboard contract also establishes the shared modern visual language and
component treatment. The workspace contract establishes the remaining pages'
composition, hierarchy, controls, drill-downs, and cross-page workflow. Do not
reinterpret an approved surface, omit its regions, or create another design
direction unless Terry explicitly requests one.

Existing backend, persistence, state semantics, lineage, Plotly, and AG Grid
contracts are accepted and frozen for the Dashboard visual checkpoint. Build
the presentation only under `dashboard.ui` from the current contract. Do not
change SQL, persistence, schemas, lineage, orchestration, evidence logic,
scaling, performance paths, or backend tests during that checkpoint. Do not
create a second composition root, parallel shell, alternate visual target, or
duplicate presentation state.

The first production slice is Dashboard only. It uses Dash Mantine Components
as the default production UI layer for navigation, layout, panels, drawers,
alerts, badges, and commodity controls. Work is split by a hard owner gate:

1. Build only the real Mantine visual shell at 1440 by 980 using the contract's
   representative state, clearly labeled local visual proof. Do not connect
   persistence, build data projections, register production callbacks, optimize,
   run backend tests, deploy, or implement another surface. Show Terry the real
   render beside the exact contract and stop.
2. After Terry approves that render, bind existing read-only state and add the
   approved controls without changing the composition. Run the private review
   service at its established tailnet URL and stop only after giving Terry the
   reachable URL. A screenshot is not the Gate B deliverable.

The representative first render is not operational truth and may never be
deployed. Abandon Mantine only for a demonstrated blocker and stop for an owner
decision before choosing a fallback. A standalone React frontend requires a
separate owner decision.

Run the Dashboard directly for implementation and owner acceptance. Do not add
it to the research Compose stack. Prefect and the agent gateway remain
containerized factory infrastructure. The Dashboard private-review target is a
normal Linux service at the established tailnet URL. Dashboard
unavailability must not stop active filtration work or mutate research state.

Use the stack by responsibility: Mantine for the polished application and
commodity component layer; Dash Core Components for analytical state and
controls when they are the appropriate Dash primitive; Dash AG Grid for dense
sortable/filterable Candidate and run data; Plotly plus VectorBT for analytical
charts and evidence. Use components because they improve the approved workflow,
not to showcase a library.

Dashboard must answer what is happening now: running and queued work, failures,
throughput, genuine exceptions, evidence survival, data readiness, and newly
qualified survivors. Candidates is the gold-discovery surface: it defaults to
survivors and supports high-density ranking, sorting, and filtering by return,
drawdown, Sharpe, OOS performance, robustness, and paper eligibility. Selecting
one exact survivor opens its Results charts, trades, drawdown, evidence, and
lineage; Compare Selected remains a secondary multi-selection action.

The Dashboard composition is exact: polished rail and header, four current-state
cards, Candidate universe, selected finding, Factory now, Top survivors, and
contextual drawers. Do not add, remove, reorder, restyle, or substitute regions
before the first visual checkpoint. Later truthful empty, inactive, stale, or
unavailable states must preserve its hierarchy compactly. At scale, existing
read models aggregate the full population server-side and hydrate bounded
cohorts; complete sorting/filtering remains in Candidates. Scale work is not
authorized during the visual checkpoint.

Every element styled as interactive must work. A summary metric, chart mark,
status, alert, or table aggregate that promises deeper analysis must open the
exact filtered records or contextual detail. If no drill-down exists, remove
the interactive styling. Do not make every decoration clickable merely to meet
this rule.

Frontend acceptance has separate gates: technical truth, working controls,
visual conformance, and Terry's unaided comprehension. A route load, HTTP 200,
expected text, passing callback, clean console, or agent assertion cannot close
the visual or comprehension gates. Gate A is deliberately earlier and cheaper:
capture the real visual shell, compare it side by side with the contract, show
Terry, and stop before callbacks, backend work, audits, adversarial review,
merge, or deployment. After Terry approves appearance, Gate B adds truthful
state and controls and publishes the reversible private review service. Terry's
unaided use is the next checkpoint. Secondary audits and repository packaging
follow a successful walkthrough; they may not delay the first working URL or
stand in for it. Do not begin the next surface before that walkthrough passes.

## Working mode

The default sequence is:

**outcome -> reuse -> smallest implementation -> decisive proof -> deliver ->
stop**

### Direct Mode

Use Direct Mode for routine implementation, bug fixes, UI work,
configuration, private operations, redeploys, and other reversible reuse of
established architecture.

- Work directly without implementation preflight or adversarial review. The
  independent frontend review begins only in Gate B after Terry approves the
  Gate A appearance.
- Keep a plan to at most five short steps. Avoid broad audits, speculative
  architecture, adjacent cleanup, alternative implementations, and unrelated
  testing.
- Do not add an owner gate for ordinary consequences of authorized work.
- Delegate only when substantial independent work clearly saves more time and
  cost than coordination consumes.
- Deliver and stop when decisive evidence proves the requested visible
  outcome.

### Escalated Mode

Use Escalated Mode only for a genuinely difficult-to-reverse or
high-consequence change involving a new architecture/service/framework,
persistent data or schema migration, paid resources, expanded credential
authority, public exposure, protected evidence or data, broker/order
capability, paper/live activation, capital/risk controls, or destructive or
costly-to-reverse state. File count, diff size, deployment, runtime, or a
production-like system does not alone qualify.

For Escalated Mode executable, runtime, configuration, schema, dependency, or
dashboard-behavior changes, follow
`.agents/skills/implementation-preflight/SKILL.md`. Before candidate research,
data acquisition, execution work, or another Escalated Mode task, state these
six items concisely:

1. current phase;
2. exact unresolved requirement;
3. why existing code or evidence does not close it;
4. cheapest sufficient action;
5. evidence that will close it; and
6. exclusions and authority boundary.

If an item is missing, reuse existing evidence or report that no new work is
justified. Use `.agents/skills/quant-factory-adversary/SKILL.md` for an
Escalated Mode proposal or closure claim. Independent review is required for
material evidence/data/ranking/protected-data changes, migrations, expanded
credential authority, public exposure, orders/capital, or similarly costly
work.

Authorization persists for the authorized task. Ask again only for a new
product choice, cost, irreversible action, security authority, trading or
capital authority, or materially changed outcome. Leave adjacent observations
alone when they do not block the authorized outcome.

### Cost, time, and stop discipline

Attention, elapsed time, tokens, compute, and disk are product resources.

- Make only tool calls that can change the next action or advance the
  deliverable.
- Do not run an unchanged check twice, duplicate required CI locally, or prove
  an already decisive result. One focused pass is enough for one isolated
  defect.
- Do not retry the same failed operation more than twice. Then diagnose the
  blocker and choose a materially different approach or stop and report it.
  Never poll or rebuild indefinitely.
- After 15 minutes without owner-visible progress in Direct Mode, reassess the
  scope and cheapest path, and tell Terry before continuing an unexpectedly
  expensive approach.
- If Terry questions necessity, waste, delay, or looping, stop nonessential
  work and answer from current evidence before resuming.
- Correct a violated contract at its owning boundary. Do not mask it in UI,
  fixtures, artifact copies, or caller-specific exceptions.
- For evidence-sensitive calculations, persist or deterministically derive
  the approved measurement basis, fail closed when it is ambiguous, and label
  it in the evidence.
- Tests must exercise corrected behavior and assert the resulting value or
  state; captured arguments alone do not prove a numerical or evidence fix.
- Treat initial implementation as provisional until its exact diff and
  assumptions are checked against representative real data. Resolve review
  findings before merge or deployment. A root-cause finding stops packaging:
  replace the faulty design, rerun one focused proof, and obtain the required
  review.

After operator handoff and before a new candidate family, perform one cheap
read-only prior-work check. A different symbol, dataset, wrapper, wording, or
presentation is not a new requirement. Do not repeat completed or withdrawn
research without a new hypothesis or independent-evidence need.

## Orchestration and repository safety

The lead is the sole owner-facing coordinator and works directly by default.
Parallelize only substantial, independent, non-overlapping work with a clear
net time or cost benefit. Serialize dependencies, shared state, overlapping
writes, and protected-evidence transitions. Give each worker a bounded
objective, owned paths or read-only scope, inputs, output, budget discipline,
and stop condition. Use the cheapest capable model, avoid duplicate workers
unless independent review is required, and reuse worker findings. Do not
hard-code a model vendor or name into durable policy. Follow
`docs/ai-programming-agent-policy.md` for detailed procedure.

- `RedstoneX/Quant-Factory` is the canonical forward source of truth.
- Use a dedicated branch and pull request for substantive work. Never push to
  `main`, force-push, use destructive Git, or alter historical evidence.
- Concurrent writers use separate worktrees/branches and non-overlapping
  paths. Preserve unrelated edits.
- Never commit secrets, raw market data, generated results, environment files,
  or machine-specific artifacts.
- Keep required checks and admin enforcement enabled. Integrate and retest
  dependent or overlapping work serially; an independent green PR need not
  rebuild only because another independent PR merged.
- Codex completes authorized Git and GitHub work; Terry is not expected to
  operate Git.

## Reuse and dashboard work

Prefer existing Quant Factory code, licensed dependencies, approved designs,
official examples, and mature legally compatible components. Write only the
smallest verified Quant Factory-specific adapter or gap.

Do not confuse a new presentation with a technical rewrite.
Keep Plotly Dash, Dash Core Components, VectorBT Pro, Plotly, Dash AG Grid,
persistence, evidence, lineage, orchestration and authority gates. Use Dash
Mantine Components as the default polished UI layer. Do not rebuild generic
chart, grid, docking, layout or component systems when mature components meet
the approved interaction requirement.

The repository-owned Dashboard HTML is the sole Dashboard visual contract. The
repository-owned workspace HTML is the sole composition and workflow contract
for the other six named surfaces; it contains no Dashboard composition. No
external copy, earlier mockup, preview, screenshot, local implementation branch,
CSS, browser test, or deployed interface is a visual or implementation source.
Required product semantics also come from `docs/factory-operating-contract.md`.

Before changing an operator page, record the target page, owner-approved design,
proof state, owning state source, permitted change and proof plan. Keep source
code and runtime state distinct: a clean checkout must not contain a database,
but the Dashboard service must receive the external canonical database path via
`QUANT_FACTORY_DB_PATH`. A rejected checkout is prohibited as a UI source, not
as the location of canonical runtime state. Before any behavior merge:

1. render the actual page at the approved viewport and meaningful state;
2. inspect the new approved design and actual render side by side;
3. correct material differences in composition, hierarchy, spacing, data,
   affordances, and primary action;
4. exercise the page's safe read-only controls and transitions; and
5. run the normal Linux private-review service at the established tailnet URL;
6. show Terry the URL and state identity for unaided hands-on use; and
7. only after that walkthrough, perform the secondary audit and independent
   review required before merge.

A loading or empty state, screenshot, route change, HTTP 200, expected text, or
clean console proves only that condition unless it is the reported defect. A
workflow pass requires meaningful configured state and its transition to the
next safe action at the private URL. If the configured state source is missing,
stop before implementation completion; do not call an unavailable-state render
Gate B. Terry's walkthrough is the browser acceptance gate.

## Proportional proof and private-beta operations

Use the smallest proof that answers the requirement:

- operational change: revision, health, and reachability;
- isolated code or UI change: focused affected non-browser tests;
- shared core change: relevant integration tests; and
- full suite: only when shared/core behavior, CI, or insufficient focused
  proof requires it.

Do not run browser tests or visual comparisons in CI. For owner-authorized
frontend work, the current visual-proof rule permits bounded
read-only browser capture locally at one approved desktop viewport, the exact
surface and representative state under repair, and the repository-owned visual
contract. Do not create a broad browser suite, test unrelated routes or device
matrices, mutate research evidence, or replace component/callback tests with
visual inspection. Terry's unaided walkthrough remains the comprehension gate.

### Private-beta economy and retention

Until Terry accepts a revision for go-live, treat the private review service
as a disposable single-owner beta:

- Batch related UI corrections, focused checks, repository workflow, and one
  deployment for the walkthrough.
- Back up only for accepted go-live, a persistent/schema migration, destructive
  state change, or an explicit request.
- Restart only services that changed; a dashboard-only change restarts only
  the dashboard.
- Retain at most the current and previous release/image. Once healthy, remove
  superseded releases, images, archives/logs, temporary environments,
  screenshots, browser captures, and generated test evidence.
- Keep only accepted decisions, the source revision, and minimum health and
  reachability evidence. Cleanup completes the slice.

## Research and evidence

- The edge-discovery mandate is intraday day trading: one defined session,
  expected holds of minutes to hours, and no position past the strategy's
  session boundary. Multi-day, overnight, seasonal, turn-of-month, and other
  calendar-hold work requires a mandate change.
- Fixtures and previously inspected data prove infrastructure, not an edge or
  independent profitability.
- Cast a wide strategy-level intake net, but keep each Candidate's VectorBT
  parameter and structural-variant space explicitly bounded before results are
  visible. Large vectorized searches are permitted only within accepted
  campaign compute, multiplicity, and evidence budgets.
- Every executable Candidate needs a named hypothesis, source/rationale, fixed
  parameter boundaries, execution assumptions, data boundaries, and declared
  pass/fail evidence.
- Prohibit open-ended optimization, blind data mining, protected-test
  inspection, automatic edge promotion, result-driven search expansion, and
  unapproved parameter changes. Automatic progression through declared
  research filters is expected and is not edge promotion.
- Keep signal discovery separate from execution vehicle. Delta, liquidity,
  spreads, contract selection, and leverage do not establish an edge.
- Prefer S&P 500/Nasdaq-100 intraday behavior that can be screened economically
  on existing MES/MNQ data, then validate on the intended SPY/QQQ/index
  underlying before an options claim. Reject a Candidate that requires
  overnight or multi-day holding before backtesting.
- Before buying or downloading data, define the experiment and minimum data,
  then compare provider cost for that bounded need. Do not rerun expensive
  research when inputs are unchanged.
- Keep research, validation, evidence, and strategy logic venue-neutral; they
  must never submit broker orders.

## Credentials, execution, and capital

Bitwarden Secrets Manager is the credential source of truth and machine-access
standard. Use the `Codex` machine account, scoped to the `Quant Factory`
project, through the pinned official `bws` CLI. Keep its access token outside
Git and shell history, encrypted at rest as a root-owned systemd credential,
and expose it only to the short-lived `bws` process.

Retrieve only an authorized named secret. Never print or persist secret values
or unrestricted project output. Long-running workers load required credentials
once at startup, never on an order path. Fail closed if the token, grant,
secret, or CLI verification is unavailable. Password Manager, Agent Access,
interactive `bw`, dotenv files, and another project's credential gateway are
not machine-access substitutes. Research, paper, and live domains require
separate Bitwarden grants and OS/service boundaries.

Paper activation requires a qualified edge and the current account, credentials,
endpoint, worker, idempotency, reconciliation, recovery, capacity, audit, and
fail-closed gates. Keep paper and live credentials, state, and deployments
separate. Live additionally requires successful paper evidence, separate owner
approval, isolated security boundaries, deterministic risk controls, and an
independent Risk Sentinel.

AI may analyze, propose, review, alert, and perform explicitly bounded approved
actions. It may not silently change strategy parameters, enable trading,
increase capital, expose vault access, or bypass deterministic risk controls.

## Completion

A slice is complete when its evidence answers the requirement, the exact diff
is reviewed, focused checks pass, repository state is synchronized, and
temporary artifacts are removed. Update documentation only for durable changes
to behavior, authority, status, or a contract. A milestone completes only when
its acceptance criteria pass and required owner acceptance is recorded.

Report concisely: question answered, change, evidence, pass/fail/insufficient,
next justified action, and warnings. Include project history only when needed
to explain the decision.
