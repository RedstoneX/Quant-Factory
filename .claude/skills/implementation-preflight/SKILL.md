---
name: implementation-preflight
description: Perform the required read-only Quant Factory preflight before changing application code, tests, schemas, migrations, dependencies, configuration, dashboard behavior, generated artifacts, or runtime state. Use at the start of implementation and whenever the milestone, branch, worktree, or task scope changes materially.
---

# Implementation preflight

Establish routing, authoritative scope, repository state, the smallest safe
change, and acceptance evidence before implementation.

## Read-only boundary

During preflight:

- do not edit or create files;
- do not install or update dependencies;
- do not start, stop, or restart services;
- do not acquire, import, regenerate, move, or delete market data;
- do not stage, commit, push, merge, rebase, reset, clean, switch, or fetch;
- do not create persistent project-agent files or services. Read-only helpers may report to the lead under the agent policy; they may not write, contact the project owner, or spawn descendants.

Stop and report any authority conflict instead of inventing policy.

## 1. Apply the routing gate

Answer:

1. Under ordinary routing, can ChatGPT complete and verify the task directly?
   If the lead is orchestrating, apply the agent-policy qualification and
   delegate any implementable task rather than doing it inline.
2. If not, can one bounded WSL action complete and verify it safely?
3. What exact local implementation, runtime, dependency, debugging, or
   multi-file capability requires Claude Code?

Documentation-only work, planning, roadmap maintenance, source-of-truth
synchronization, read-only inspection, status, diff, comparison, counting, and
explanation do not require a programming agent under the ordinary routing
gate. When the lead is actively orchestrating, however, any such work that can
be delegated must be routed to the cheapest suitable worker; do not implement
it inline. If delegation is unavailable, return the blocker to the lead.
Report the routing result before continuing.

## 2. Verify repository state

Confirm:

- working directory is `QF_REPO_ROOT` (for example `/srv/quant-factory/repo`) or a task-owned isolated
  worktree derived from that repository;
- current branch, HEAD, and configured upstream;
- concise working-tree status;
- five most recent commits;
- dedicated task branch and intended PR base; main is the integration baseline,
  not the normal destination for direct edits/pushes.

Treat a Windows workspace or second clone as non-authoritative unless repository
governance explicitly changes. Stop before implementation if:

- the path is wrong or HEAD is detached;
- the intended task branch is not based on the reviewed integration baseline, or its ownership and existing changes are unclear;
- merge conflicts exist;
- local changes overlap the task and cannot be preserved safely;
- recorded and local repository state materially disagree.

## 3. Read authoritative context

Read, in order:

1. `CLAUDE.md`;
2. `AGENTS.md`;
3. `docs/ai-programming-agent-policy.md`;
4. `docs/DOCUMENTATION_GOVERNANCE.md`;
5. the active scope in `docs/MILESTONES.md`;
6. relevant entries in `docs/DECISIONS.md`;
7. `docs/CHAT_HANDOFF.md` when continuity context is needed;
8. relevant accepted ADRs, specifications, runbooks, recent Git history, code,
   and tests.

Read the active milestone's detailed specification and current scenario matrix
when one exists. Do not hard-code a scenario count or ask the user to repeat
facts already recorded.

For market-data work, also read `docs/DATA_CATALOG.md`, inspect
`data/manifests/`, and resolve the untracked local data-root configuration
before any data action.

If authorities conflict, apply the precedence in
`docs/DOCUMENTATION_GOVERNANCE.md`, report the contradiction, and stop when it
changes the implementation.

## 4. Confirm revival understanding and bound the implementation

For the initial revival, the lead must present the closed Tier 1 mapping
(AGENTS, MILESTONES, DECISIONS), product intent, current evidence, and intended
scope to the project owner before application code. The owner confirmed the scoped
full-authority revival on 2026-09-02; cite Decision 256 and continue within that
scope rather than asking again. The authorization includes root-cause repair,
extensive testing, and reviewed push/merge operations, while preserving the
Milestone 23 gate and the prohibition on live capital.

Identify:

- active milestone and explicitly authorized slice;
- factual gap between current and required behavior;
- smallest safe, testable implementation unit;
- files and systems likely to change;
- behavior that must remain unchanged;
- explicit exclusions and deferred work;
- focused automated tests and manual evidence required;
- whether complete-suite, browser, live-backtest, or external-service validation
  is actually required;
- documentation impact under the governance checklist;
- the decisive assertion to verify before acting, including actual test counts,
  causal reproduction, counterexamples, and dated source evidence as relevant;
- any unattributed constraint whose source remains unverified and needs the project owner;
- any pre-existing issue outside scope, reported without treating discovery as
  repair authorization;
- worker ownership and complete initial prompts if parallel help is justified,
  including no descendants/direct owner escalation and an explicit polling budget.

Do not broaden the task or begin a later milestone. Decisions 259 and 262 are
the scoped exceptions permitting research-only deployment engineering,
deployment preparation, broker-neutral contracts, isolated paper-adapter
implementation and tests, an isolated research deployment after technical
checks, and OVH target validation in parallel with Milestone 23. Harmless or
paper credentials require ADR 0010 credential-isolation proof and the
documented account-ownership boundary; these exceptions do not authorize
paper-order activation, M24 completion, discovery,
protected tests, optimization, or live capital. Do not introduce a strategy
candidate before the discovery gate passes. Add a deterministic acceptance
fixture only when the authoritative scenario matrix proves existing fixtures
insufficient.

Decision 266 separately authorizes an authoritative OVH research-runtime
migration after documented backup, reconciliation, private-access, restart,
restore, and rollback checks; it does not authorize M23 acceptance, paper
orders, discovery, optimization, or live capital.

## 4a. Complete the reuse-before-build assessment

Before proposing custom executable code, inventory the relevant:

- existing Quant Factory implementation, tests, adapters, and assets;
- licensed dependencies and their supported capabilities, including VectorBT
  Pro where applicable;
- owner-approved prototypes that must remain implementation input;
- mature maintained external components or reference projects that may solve
  the need legally and safely.

Use `docs/component-reuse-audit.md` as the existing inventory starting point
where relevant. Its individual evaluations are historical until revalidated
for the current task; do not repeat settled research without a changed
requirement, dependency, license, or material new candidate.

For each plausible candidate, compare functional fit, license and legal use,
security, maintenance health, integration cost, and truthful handling of
Quant Factory data and evidence. Prefer adapting or integrating a suitable
proven component. Do not recreate mature commercial-grade dashboard,
charting, grid, panel, or research-engine behavior for architectural neatness,
local control, or speculative future flexibility.

Custom code is allowed only for a verified project-specific gap or when the
comparison shows reuse is materially worse. State the selected reuse, the
remaining gap, and why each custom portion is necessary. The rule does not bar
the smallest domain adapter, evidence-integrity check, or safety control, and
does not authorize copying or adding a dependency without a compatible
license. Distinguish prototype/reference behavior from integrated, tested,
deployed, and operator-accepted product behavior.

## 5. Apply Quant Factory acceptance rules

- Use the real SPYM VectorBT Pro fixture in the successful integrated Milestone
  23 workflow; do not replace that final proof with a purely synthetic fixture.
- Deterministic failure, retry, timeout, cancellation, recovery, and integrity
  fixtures remain valid where the accepted scenario matrix specifies them.
- Browser evidence is required for operator acceptance. Service and callback
  tests may support it but do not replace the full browser workflow.
- Preserve training, validation, walk-forward, and lockbox isolation.
- Protected state may change only through the accepted durable evidence path.
- Run focused tests first. Run the complete suite only when milestone acceptance
  or the bounded task explicitly requires it.
- Do not rerun expensive backtests unless relevant inputs changed or final
  validation requires them.

## 6. Report the preflight

Return exactly these concise sections:

```text
Routing
Repository
Active scope
Factual gap
Reuse assessment
Smallest safe change
Files and systems in scope
Validation
Documentation impact
Blockers or deviations
```

If there is no blocker, the initial revival understanding is confirmed, and the
user already authorized implementation, continue with the bounded task. If preflight alone was requested, authority is missing,
scope would expand, or a stop condition is present, stop after the report and
request the specific decision required.
