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

Codex is the sole active project agent toolchain. During normal project work,
do not load, invoke, rely on, update, or follow `CLAUDE.md` or `.claude/**`.
Only Terry may change the mandate, accept milestones, authorize deployment, or
approve paper/live trading and capital exposure.

## Current sequence and gates

Follow the queue in `docs/MILESTONES.md`:

**standardized non-executing intake -> owner handoff -> owner-approved
candidate research -> validation -> execution-vehicle comparison -> paper
operation -> live operation later**

Complete the objective dashboard and operator-workflow criteria before owner
handoff. Reuse the generic backend, audited MES run, approved UX work,
licensed VectorBT Pro, mature components, and existing tests. Do not rebuild
the backend, add another frontend or orchestration layer, or introduce
enterprise infrastructure for this single-user product.

When `docs/MILESTONES.md` records a technical pass, owner gate, or blocked
owner decision, stop there. Do not substitute deferred work unless the active
milestone or Terry explicitly authorizes it. A reported defect authorizes its
smallest root-cause correction; it does not reopen adjacent scope.

QF Candidate v1 is the provider-neutral intake boundary. During standardized
intake, Quant Factory may parse, validate, persist, display, edit, import, and
export Candidate packets. It may not fetch external sources, select an LLM
provider, implement a candidate, launch a backtest, or test profitability until
Tier 1 advances. External LLMs and any future built-in analyzer must produce
the same Candidate contract; no model is required.

Use QF Research Context v1 as the portable companion for external research. It
is a supporting snapshot of mandate, prior work, data, deduplication rules,
and the Candidate output contract. Re-check current Tier 1 and local evidence
before acting on it.

Before candidate research, Terry must accept one bounded Candidate packet and
its evidence contract. Prior work closes only its stated hypothesis, rules,
and parameter space; it does not close a broader strategy family unless Tier 1
says so.

## Working mode

The default sequence is:

**outcome -> reuse -> smallest implementation -> decisive proof -> deliver ->
stop**

### Direct Mode

Use Direct Mode for routine implementation, bug fixes, UI work,
configuration, private operations, redeploys, and other reversible reuse of
established architecture.

- Work directly without implementation preflight or adversarial review.
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

The chart-first prototype is a UX reference, not an implementation mandate.
Do not rebuild generic chart, grid, docking, layout, or component systems.
UI references are page-local: the standalone chart-first preview and
Decisions 280–282 govern only selected-run **Results**. Every other page
follows its own approved manifest entry. Shared visual language may carry over
only when it does not replace that page's contract.

References in `docs/assets/dashboard/operator-workflow-approved/` are the
current visual and interaction contract. Use their source structure where it
exists. Do not reinterpret screenshots, hide a conflicting legacy renderer,
or patch over it with broad late CSS. Reference HTML/CSS is design evidence,
not permission to copy unsafe standalone behavior or create another frontend.
Conformance requires the specified regions, meaningful real state, working
actions, absence of prohibited legacy content, and correct active-route
loading.

Before changing an operator page, record the single target page, exact
reference, representative state, reported defect, and permitted change. For
the active R12 trust-recovery work, before merge or deployment:

1. render the actual page at the reference desktop viewport and a comparable
   meaningful state;
2. inspect the approved reference and actual render side by side;
3. correct material differences in composition, hierarchy, spacing, data,
   affordances, and primary action;
4. exercise the page's safe read-only controls and transitions; and
5. show Terry both renders and obtain approval.

A loading or empty state, route change, HTTP 200, expected text, or clean
console proves only that condition unless it is the reported defect. Call
navigation-only evidence a routing smoke check. A workflow pass requires each
included page to show meaningful state and its transition to the next safe
action. Terry's walkthrough is the browser acceptance gate.

## Proportional proof and private-beta operations

Use the smallest proof that answers the requirement:

- operational change: revision, health, and reachability;
- isolated code or UI change: focused affected non-browser tests;
- shared core change: relevant integration tests; and
- full suite: only when shared/core behavior, CI, or insufficient focused
  proof requires it.

Do not run automated browser tests or browser checks in CI. For active R12
corrections, Terry authorizes narrow Playwright inspection only as a visual
instrument: one desktop viewport, the private review service or local
equivalent, the repository-approved reference, and the exact page/workflow
under repair. Do not create a browser harness, test multiple devices, mutate
research evidence, or replace component/callback tests with browser checks.

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
- Every executable Candidate needs a named hypothesis, source/rationale, fixed
  parameter boundaries, execution assumptions, data boundaries, and declared
  pass/fail evidence.
- Prohibit open-ended optimization, blind data mining, protected-test
  inspection, automatic promotion, and unapproved parameter changes.
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
