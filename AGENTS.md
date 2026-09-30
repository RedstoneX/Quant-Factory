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

Follow the queue in `docs/MILESTONES.md`. The default sequence is:

**edge discovery -> validation -> execution-vehicle comparison -> dashboard
repair -> paper operation -> live operation later.**

Do not make dashboard completion, deployment, broker integration, portability,
or generic infrastructure a prerequisite for edge research unless a measured
blocker proves that it is one.

The current dashboard's historical technical evidence is retained, but the
owner does not consider the present interface sufficiently intuitive or viable
as the long-term operator product. Dashboard work is therefore deferred unless
it blocks research or the active milestone explicitly resumes it.

## Work-delta gate

Before candidate research, implementation, data acquisition, execution work,
or material delegation, state in no more than six short bullets:

- current phase;
- exact unresolved requirement;
- why existing code/evidence does not already close it;
- cheapest sufficient action;
- evidence that will close it;
- explicit exclusions or authority boundary.

If any item is missing, do not invent work. Reuse existing evidence or report
that no new work is justified.

Before new candidate-family work, perform a cheap read-only prior-work check.
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

## Parallel-first orchestration

The lead is the sole owner-facing coordinator, but it should **parallelize by
default when dependencies allow**.

- Split independent read-only analysis, audits, research, testing, and bounded
  implementation into concurrent streams when this reduces wall-clock time.
- Serialize only genuine dependencies, overlapping writes/state, protected
  evidence transitions, or work where parallelism would increase risk.
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
- Optimize for **correctness, wall-clock completion, and token/cost efficiency**
  together. Do not minimize agent count at the expense of serial bottlenecks,
  and do not create an uncontrolled agent swarm.

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

Before material executable, runtime, configuration, schema, dependency, or
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

For a material proposal or closure claim, use
`.agents/skills/quant-factory-adversary/SKILL.md`. Independent review remains
required for material evidence/data/ranking/protected-data changes, migrations,
credentials, deployments, orders/capital, or costly-to-reverse work.

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
the exact diff is reviewed, focused checks pass, documentation impact is
handled, and repository state is synchronized. A milestone is complete only
when its acceptance criteria pass and owner acceptance is recorded where
required.

Report concisely: question answered, change, evidence, pass/fail/insufficient,
next justified action, and warnings. Do not repeat project history unless it is
needed to explain the decision.
