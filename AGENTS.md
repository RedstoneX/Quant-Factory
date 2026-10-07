# Quant Factory Codex Instructions

## Mission and authority

Quant Factory is Terry's private, single-operator quantitative research system.
Its primary purpose is to **find, reject, and rigorously validate defensible
trading edges**. Converting a qualified edge into consistent income is
secondary. Infrastructure, dashboard work, broker integration, and deployment
exist only to serve those goals.

The closed Tier 1 authority set is:

1. `AGENTS.md` — stable Codex operating contract.
2. `docs/MILESTONES.md` — the only authority for current phase, active queue,
   blockers, sequencing, and milestone status.
3. `docs/DECISIONS.md` — accepted owner decisions and supersessions.

Start substantive work by reading `docs/MILESTONES.md`, then the current
decision index at the top of `docs/DECISIONS.md`, then only the decisions and
supporting material required by the task. Supporting documents cannot create
current priority, status, or authority. Follow
`docs/DOCUMENTATION_GOVERNANCE.md` for documentation changes.

Codex is the sole active project agent toolchain. Do not load, invoke, rely on,
update, or follow `CLAUDE.md` or `.claude/**` during normal project work.

Only the owner changes mandate, accepts milestones, authorizes deployment, or
approves paper/live trading and capital exposure.

## Current sequencing rule

Follow the queue in `docs/MILESTONES.md`. The current sequence is:

**standardized non-executing intake -> owner handoff -> owner-approved candidate
research -> validation -> execution-vehicle comparison -> paper operation ->
live operation later.**

Complete objective dashboard and operator-workflow criteria before the owner
handoff gate. Reuse the completed generic backend, audited MES run, approved
chart-first UX work, licensed VectorBT Pro, mature components, and existing
tests. Do not rebuild the backend, create a second frontend or orchestration
layer, or introduce enterprise-scale infrastructure for this private
single-user product. When `docs/MILESTONES.md` records the technical pass, stop
at the owner walkthrough and explicit handoff-acceptance gate unless Terry
reports a product defect or changes the mandate.

QF Candidate v1 is the accepted provider-neutral intake boundary. During the
standardized-intake milestone, Quant Factory may parse, validate, persist,
display, edit, import, and export Candidate packets, but it must not fetch
external sources, choose an LLM provider, implement a candidate, launch a
backtest, or profitability-test another strategy unless Tier 1 is separately
advanced. External LLMs and a future optional built-in analyzer must produce
the same Candidate contract; no model is a required dependency.

For external research, use QF Research Context v1 as the portable companion to
QF Candidate v1. The context supplies the current mandate, prior-work
dispositions, relevant data snapshot, deduplication rules, and Candidate output
contract. It is a supporting snapshot rather than Tier-1 authority; Quant
Factory still re-checks current Tier-1 and local evidence before research.

Prior work is scoped evidence, not automatic family rejection. A tested or
rejected Candidate closes only its explicit hypothesis/rules/parameter space.
Do not infer that ORB, momentum, mean reversion, channel breakout, gap reversal,
or any other broader family is exhausted unless Tier 1 contains an explicit
owner decision closing that family.

Before candidate research begins, the owner explicitly accepts one bounded
Candidate packet and its evidence contract. The current intraday evidence
boundaries then apply unless the owner changes them.

## Default working mode

Quant Factory is a private single-user MVP. The default working sequence is:

**outcome -> reuse -> smallest implementation -> decisive proof -> deliver ->
stop**

### Direct Mode — default

Use Direct Mode for routine implementation, bug fixes, UI work,
configuration, private operations, redeploys, and other reversible work that
reuses established architecture.

In Direct Mode:

- work directly;
- do not use an adversary or implementation preflight;
- do not delegate unless genuinely independent substantial work will save more
  time and cost than coordination consumes;
- do not perform broad audits, speculative architecture, adjacent cleanup, or
  repeated unrelated testing;
- do not create another owner gate for ordinary consequences of already-
  authorized work; and
- deliver and stop as soon as decisive evidence proves the requested owner-
  visible outcome.

### Private-beta economy and retention

Until Terry explicitly accepts a revision as viable for go-live, the private
review service is a disposable single-owner beta rather than a production
release process.

- Consolidate related UI corrections locally and deploy once for the owner
  walkthrough; do not package, back up, deploy, and re-verify every visual
  adjustment separately.
- Do not create a database or state backup for a reversible private-beta UI,
  copy, configuration, or code deployment. Back up only before an accepted
  go-live, a genuine persistent/schema migration or destructive state change,
  or an explicit owner request.
- For a dashboard-only beta change, rebuild and restart only the dashboard
  unless another service actually changed.
- Retain at most the current and immediately previous private-beta release and
  image. Remove superseded extracted releases, images, build archives/logs,
  temporary environments, screenshots, and generated test evidence once the
  current revision is healthy.
- Do not retain browser captures or repeated proof artifacts as durable
  evidence when the owner performs browser QA. Keep only the accepted decision,
  source revision, and the minimum required health/reachability record.
- Cleanup is part of completing the slice. Do not let temporary beta artifacts
  accumulate into a later cleanup project.

### Cost, time, and stop discipline

For this one-owner experiment, attention, elapsed time, tokens, compute, and
disk are product resources. Spend them only on the shortest path to the
requested owner-visible outcome.

- Every tool call must answer a necessary question or advance the requested
  deliverable. If its result would not change the next action, do not run it.
- A Direct Mode plan has at most five short steps. Do not create a new planning
  layer, audit, matrix, evidence package, alternative implementation, or mockup
  unless the owner explicitly requests it or the current outcome cannot be
  produced without it.
- Do not run an unchanged check twice, locally duplicate required CI, or create
  proof of already decisive proof. One passing focused check is enough for one
  isolated defect.
- Do not retry the same failed operation more than twice. After the second
  failure, diagnose the specific blocker, choose one materially different
  approach, or stop and report it. Never poll or rebuild indefinitely.
- If a Direct Mode task runs for 15 minutes without producing new
  owner-visible progress, stop and reassess scope, necessity, and the cheapest
  remaining path. Tell Terry before continuing an unexpectedly expensive path.
- If Terry asks whether work is necessary, wasteful, stuck, paused, or looping,
  stop nonessential work and answer that question from current evidence before
  resuming. Do not defend sunk cost by continuing.
- A reported UI defect authorizes the smallest correction to that defect. Do
  not redesign adjacent surfaces, generate multiple variants, add responsive
  renderings, or build infrastructure unless explicitly requested.
- Once the requested result is delivered or the active milestone reaches an
  owner-only gate, stop. Do not substitute cleanup, research, refactoring, or
  another queued item unless Terry requests it.

### Root-cause implementation discipline

- Correct the violated contract at its owning boundary; do not mask it in the
  dashboard, fixtures, artifact copy, or a caller-specific exception.
- For evidence-sensitive calculations, persist or deterministically derive the
  measurement basis from the approved configuration, fail closed when that
  basis is ambiguous, and label the basis in the resulting evidence.
- A test must exercise the corrected behavior and assert the resulting value or
  state. Argument-capture tests alone do not prove a numerical or evidence fix.
- Treat an initial implementation as provisional until the exact diff and its
  assumptions have been checked against representative real data. Do not merge
  or deploy a draft that has an unresolved review finding.
- When a review finds a root-cause defect, stop packaging work, replace the
  faulty design, rerun one focused proof, and obtain the required review before
  delivery.

### Escalated Mode — exception

Use heavier preflight, review, or independent challenge only when the task
introduces a genuinely difficult-to-reverse or high-consequence change involving
one or more of:

- a new architecture, service, or framework;
- a persistent data or schema migration;
- paid resources;
- expansion of credential or secret authority;
- public network exposure;
- protected evidence or data boundaries;
- broker or order capability;
- paper or live activation;
- capital or risk controls; or
- destructive or costly-to-reverse state.

File count, diff size, the words `runtime` or `deployment`, and touching
production-like infrastructure do not by themselves make work material or move
it into Escalated Mode.

Owner authorization persists through the authorized task. Ask again only for a
genuinely new product choice, cost, irreversible action, security-authority
expansion, trading or capital authority, or materially changed outcome. Do not
turn adjacent observations into work; if they do not block the requested
owner-visible result, leave them alone.

Before candidate research, data acquisition, execution work, or other
Escalated Mode work, state in no more than six short bullets:

- current phase;
- exact unresolved requirement;
- why existing code/evidence does not already close it;
- cheapest sufficient action;
- evidence that will close it;
- explicit exclusions or authority boundary.

If any item is missing, do not invent work. Reuse existing evidence or report
that no new work is justified.

After operator handoff and before new candidate-family work, perform a cheap
read-only prior-work check.
A new symbol, dataset, wrapper, wording, or presentation is not by itself a new
requirement. Do not repeat completed or withdrawn strategy work without a
genuinely new hypothesis or independent-evidence need.

Stop a slice when the decisive question is answered. More possible work is not
a reason to continue.

When `docs/MILESTONES.md` records an explicit owner gate or blocked owner
decision, **stop there**. Do not substitute deferred or later-phase work while
waiting—not dashboard repair, deployment, broker integration, paper/live work,
or another candidate family—unless the active milestone explicitly authorizes
that parallel work or the owner gives a new instruction.

## Direct-first orchestration

The lead is the sole owner-facing coordinator and executes directly by
default. Parallelize only when genuinely independent substantial work produces
a clear net time or cost benefit after coordination overhead.

- Do not delegate simple operations, routine implementation, focused checks,
  or work the lead can complete faster directly.
- Split only substantial independent work with non-overlapping scope and a
  measured reason that parallel execution is beneficial.
- Serialize dependencies, overlapping writes/state, protected evidence
  transitions, and work where parallelism would increase risk.
- Use the cheapest/faster available subagent model that can reliably complete
  each bounded task. Escalate to stronger reasoning models for architecture,
  strategy/evidence judgment, difficult debugging, security, or costly-to-
  reverse decisions.
- Do not hard-code a model vendor/name into durable policy; capabilities and
  prices change.
- Give every subagent a narrow objective, owned paths or read-only scope,
  required inputs, output format, token/cost discipline, and stop condition.
- Never commission duplicate agents to solve the same problem unless explicit
  independent review is required.
- Reuse worker findings; the lead must not redo completed analysis merely to
  produce its own version.
- Optimize for correctness, owner-visible completion, wall-clock time, and
  token/cost efficiency together. Coordination is work and must justify itself.

Follow `docs/ai-programming-agent-policy.md` for the detailed procedure.

## Repository safety

- `RedstoneX/Quant-Factory` is the canonical forward source of truth.
- Substantive work uses a dedicated branch and pull request. Never push directly
  to `main`, force-push, use destructive Git, or alter historical evidence.
- Concurrent writers use separate worktrees/branches and non-overlapping owned
  paths. Preserve unrelated edits.
- Never commit secrets, raw market data, generated results, environment files,
  or machine-specific artifacts.
- Required checks and admin enforcement remain enabled. Independent green PRs
  need not rebuild solely because another independent PR merged; dependent or
  overlapping work integrates serially and is retested.
- The owner is not expected to operate Git. Codex completes authorized Git and
  GitHub work and reports the result.

## Reuse before custom implementation

For Escalated Mode executable, runtime, configuration, schema, dependency, or
dashboard-behavior changes, use
`.agents/skills/implementation-preflight/SKILL.md`.

Prefer existing Quant Factory code, licensed dependencies, owner-approved
designs, official examples, and mature maintained legally compatible
components. Custom code is limited to the smallest verified Quant
Factory-specific gap.

For dashboard work, the approved chart-first prototype is a **UX reference, not
an implementation mandate**. Reproduce the required experience using mature
components and thin adapters; do not rebuild generic charting, grid, docking,
layout, or component systems.

UI references are page-local. The standalone chart-first preview and Decisions
280–282 apply to the selected-run **Results** experience only. They do not
control Dashboard, Ideas, Set up, Run test, Compare, or support-page
composition. Each of those pages follows only its own entry in the approved
reference manifest. Shared typography, spacing, control language, and
progressive-disclosure principles may carry across pages only when they do not
replace or contradict that page's own contract.

Repository-owned references under
`docs/assets/dashboard/operator-workflow-approved/` are the visual and
interaction contract for the current operator workflow. Use their source
structure when it exists; do not reinterpret a screenshot, layer a broad late
CSS override over a conflicting legacy page, or leave an old dense renderer
mounted and merely hide it. The reference HTML/CSS is design evidence, not
permission to copy unsafe standalone behavior or create a second frontend.
Page conformance requires the specified visible regions, real working actions,
absence of prohibited legacy content, and active-route loading behavior; text
presence or component-count tests alone do not establish conformance. Terry's
walkthrough remains the browser acceptance gate.

Before changing an operator page, write down the one target page, its exact
repository reference, the representative data/state to render, the reported
defect, and the permitted change. Do not combine pages or substitute a
different page's reference. Before merge or deployment during the active R12
trust-recovery work:

- render the actual page at the same desktop viewport and a comparable,
  meaningful state as its approved reference;
- open and visually inspect both the approved reference and the actual render;
- list and correct material differences in composition, hierarchy, spacing,
  visible data, control affordance, and primary action;
- exercise the safe read-only controls and transitions needed for that page;
  and
- show Terry the reference and actual render side by side and obtain approval.

A loading screen, empty shell, blocked state, route change, HTTP 200, correct
URL, visible text, or absence of browser errors is not representative page
proof unless that exact state is the reported defect. Navigation-only evidence
may be called a routing smoke check; it must never be reported as a working
page or end-to-end workflow. A workflow pass requires every included page to
show its meaningful state and the transition to the next safe action.

For an Escalated Mode proposal or closure claim, use
`.agents/skills/quant-factory-adversary/SKILL.md`. Independent review remains
required for material evidence/data/ranking/protected-data changes, migrations,
credential-authority expansion, public exposure, orders/capital, or other
costly-to-reverse work. Routine private operations and redeploys remain Direct
Mode.

## Proportional proof

- Operational change: verify revision, health, and reachability.
- Isolated code or UI change: run focused affected non-browser tests.
- Shared core change: run relevant integration tests.
- Run the full suite only when core/shared behavior changed, CI requires it, or
  focused proof is insufficient.
- Do not duplicate already-required CI merely for reassurance.
- During an unaccepted private-beta iteration, do not run full CI, create a PR,
  package a release, or deploy after each small correction. Batch the accepted
  correction set, use focused checks while iterating, then perform the required
  repository workflow once at the handoff boundary.
- **Do not run an automated browser test suite or browser checks in CI.** Terry
  owns final browser QA and the owner-visible walkthrough. For the active R12
  correction, Terry authorizes narrowly scoped Playwright inspection as a
  visual instrument: one desktop viewport, the private review service or a
  local equivalent, repository-owned approved references, and only the exact
  page/workflow under repair. Do not create a general browser harness, repeat
  multi-device renders, mutate research evidence, or substitute browser checks
  for focused component/callback tests. Remove temporary captures when the
  slice ends.

## Research and evidence

- **Current edge-discovery mandate is day trading / intraday only.** Candidate
  strategies must express a directional edge within one defined trading
  session, with expected holding periods measured in minutes to hours and no
  position carried beyond that strategy's session boundary. Multi-day swing,
  overnight-carry, turn-of-month, seasonal, and other calendar-hold strategies
  are out of scope unless the owner explicitly changes the mandate.
- Fixtures and previously inspected data prove infrastructure, not a trading
  edge or independent profitability evidence.
- Every executable candidate must have a named hypothesis, source/rationale,
  fixed parameter boundaries, execution assumptions, data boundaries, and
  predeclared pass/fail evidence.
- Open-ended optimization, blind data mining, protected-test inspection,
  automatic promotion, and unapproved parameter changes are prohibited.
- Keep signal discovery separate from the execution vehicle. Delta, liquidity,
  spreads, contract selection, or futures leverage describe how an edge is
  expressed; they do not substitute for the underlying edge.
- Initial discovery should prefer S&P 500 / Nasdaq-100 intraday behavior that
  can be screened economically on existing MES/MNQ data where appropriate and
  later validated on the intended SPY/QQQ/index underlying before any options
  claim. A candidate that requires overnight or multi-day holding fails current
  mission fit before backtesting.
- Before buying or downloading market data, identify the exact experiment and
  minimum data required. Compare provider cost only for that bounded need.
- Do not rerun expensive research when relevant inputs are unchanged.
- Research, validation, evidence, and strategy logic remain venue-neutral and
  must never submit broker orders directly.

## Credentials, execution, and capital

Bitwarden Secrets Manager is the durable credential source of truth and
machine-access standard for Quant Factory. Use the `Codex` machine account,
scoped to the `Quant Factory` project, through the pinned official `bws` CLI.
Its access token must remain outside Git and shell history, encrypted at rest
as a root-owned systemd credential, and exposed only to the short-lived `bws`
child process. Retrieve only a named secret for an authorized operation; never
print or persist secret values or unrestricted project output. Long-running
workers load required credentials once at service startup rather than querying
Bitwarden on an order path. Fail closed if the machine token, project grant,
named secret, or CLI verification is unavailable. Password Manager, Agent
Access, interactive `bw` sessions, dotenv files, and another project's
credential gateway are not the standard machine path. Research, paper, and
live credentials still require separate Bitwarden project/grant and OS/service
boundaries before those domains activate.

Paper activation requires a qualified edge plus the current account,
credential, endpoint, worker, idempotency, reconciliation, recovery, capacity,
audit, and fail-closed gates. Paper and live credentials/state/deployments stay
separate. Live additionally requires successful paper evidence, separate owner
approval, isolated live security boundaries, deterministic risk controls, and
an independent Risk Sentinel.

Never expose secret values or unrestricted vault access. AI may analyze,
propose, review, alert, and perform explicitly bounded approved actions; it may
not silently change strategy parameters, enable trading, increase capital, or
bypass deterministic risk controls.

## Completion

A slice is complete when its stated evidence answers the stated requirement,
the exact diff is reviewed, focused checks pass, and repository state is
synchronized. Update documentation only when the change alters durable
behavior, authority, current status, or a documented contract; an ordinary
bug fix or visual correction does not require another decision or status essay.
A milestone is complete only when its acceptance criteria pass and owner
acceptance is recorded where required.

Report concisely: question answered, change, evidence, pass/fail/insufficient,
next justified action, and warnings. Do not repeat project history unless it is
needed to explain the decision.
