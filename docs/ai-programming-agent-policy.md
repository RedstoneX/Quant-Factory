# Quant Factory Codex Agent Policy

- **Status:** Accepted
- **Scope:** Codex work in the canonical public repository
- **Authority:** Supports `AGENTS.md`; it does not create product priority or
  current status.

Current sequencing comes only from `docs/MILESTONES.md`. Do not infer the next
task from an older decision, ADR, specification, README, or historical milestone
record.

## Roles

The owner controls mandate, priority, milestone acceptance, deployment,
paper/live authority, and capital.

The Codex lead is the sole owner-facing coordinator. It plans the minimum
sufficient slices, orchestrates parallel work, resolves conflicts, validates
load-bearing evidence, integrates reviewed changes, and keeps the owner informed
concisely.

Workers/subagents own only their assigned scope. They do not expand scope,
contact the owner, create new product requirements, or treat findings as
accepted decisions.

## Parallel-first allocation

Default to parallel work when tasks are independent and doing so improves
elapsed time without compromising evidence or repository safety.

Good parallel candidates include:

- read-only documentation/code inventories;
- independent source research;
- test execution on independent scopes;
- data/provider cost or capability checks;
- non-overlapping implementation paths;
- independent review after the implementation diff is stable.

Serialize when tasks:

- depend on an earlier result;
- write overlapping files or shared mutable state;
- transition protected evidence or promotion state;
- touch credentials, deployment, orders, or capital where ordering is part of
  the safety boundary.

Choose the cheapest/faster available model that can reliably perform the task.
Use stronger reasoning capability for architecture, strategy/evidence judgment,
hard debugging, security, or costly-to-reverse work. Do not hard-code model
names into durable project policy.

Every delegated task states:

- objective and why it advances the active milestone;
- repository/base and owned paths or explicit read-only scope;
- exact authorities/evidence to read;
- allowed actions and exclusions;
- expected output;
- token/cost discipline;
- decisive validation;
- stop condition.

Do not commission duplicate implementations or duplicate research. A second
agent on the same question is justified only for explicit independent review or
a materially different bounded specialty.

The lead consumes worker results instead of repeating their work. Independently
verify only the load-bearing facts needed to integrate or decide.

## Work-delta and prior-work gate

Before candidate research, material implementation, raw-data acquisition, or
execution work:

1. name the unresolved requirement from Tier 1 or explicit owner instruction;
2. show why existing code/evidence does not close it;
3. identify the cheapest sufficient action and decisive evidence;
4. check repository history for completed or withdrawn equivalent work.

If the delta is absent, stop. A different ticker, dataset, wrapper, wording, or
presentation does not by itself justify new work.

Routine factual documentation and mechanical corrections use a brief
scope/reuse check. Material executable, runtime, configuration, schema,
dependency, or dashboard-behavior work uses
`.agents/skills/implementation-preflight/SKILL.md`.

Material proposals and closure claims use
`.agents/skills/quant-factory-adversary/SKILL.md`. The adversary argues
against the proposal; the lead dispositions objections and remains responsible
for the decision within owner authority.

## Implementation and integration

Substantive changes use dedicated branches and pull requests. Preserve
unrelated work. Concurrent writers use separate branches/worktrees and
non-overlapping paths. Never push directly to `main`, force-push, blanket
stage, weaken acceptance criteria to obtain a pass, or alter historical
evidence.

Prefer existing project code, licensed dependencies, approved designs, and
mature maintained components. Custom code must close a verified project-specific
gap.

Run the narrowest decisive tests for the changed path. Add browser lifecycle,
recovery, target, or device proof only when the changed risk requires it, an
actual deployment occurs, a milestone is being closed, or the owner requests
it. Do not rerun expensive backtests with unchanged relevant inputs.

Independent review is required for material evidence/data/ranking/protected-
data changes, migrations, credentials, deployment, orders/capital, and
costly-to-reverse work. Routine documentation/copy/layout uses focused checks
and exact-diff review.

Overlapping or dependent PRs integrate serially and retest on resulting
`main`. Independent green PRs follow Decision 276 and do not rebuild merely
because another independent PR merged.

## Evidence and safety

Distinguish proposed, implemented, tested, merged, deployed, and accepted.
Label measured, inferred, and unknown.

Research cannot submit venue orders. Open-ended optimization, protected-test
inspection, automatic promotion, paper activation, live work, and capital
changes remain unavailable without their Tier 1 gates and owner authority.

Credentials remain least-privilege, isolated, auditable, and absent from
prompts, repository content, logs, tests, and artifacts. The dedicated Quant
Factory Bitwarden Password Manager vault is the source of truth; official
Bitwarden Agent Access is the standard injection path. Do not substitute an
interactive vault session, dotenv file, unrestricted vault output, or another
project's credential system.

Before completion, review the exact diff, run required documentation/focused
checks, update the authoritative record required by documentation governance,
and report repository state honestly.
