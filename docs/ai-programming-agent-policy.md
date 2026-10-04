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

The Codex lead is the sole owner-facing coordinator. It follows the default
sequence **outcome -> reuse -> smallest implementation -> decisive proof ->
deliver -> stop**, resolves conflicts, integrates reviewed changes, and keeps
the owner informed concisely.

Workers/subagents own only their assigned scope. They do not expand scope,
contact the owner, create new product requirements, or treat findings as
accepted decisions.

## Direct-first allocation

Default to direct execution. Delegate only genuinely independent substantial
work when the expected wall-clock or cost benefit clearly exceeds coordination
overhead. Do not delegate simple operations, routine implementation, focused
checks, or work the lead can complete faster directly.

Possible parallel candidates include:

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

## Direct and Escalated modes

Direct Mode covers routine implementation, bug fixes, UI work, configuration,
private operations, redeploys, and other reversible reuse of established
architecture. Work directly without adversary, implementation preflight, broad
audit, speculative architecture, adjacent cleanup, unrelated repeated tests,
or new owner gates for ordinary consequences of existing authority.

For the private single-owner beta, iteration is local and consolidated. Use
focused checks while correcting the owner-visible workflow, then create one PR,
one required CI run, and one private deployment at the walkthrough boundary.
Do not create per-iteration backups or retain per-iteration releases, images,
screenshots, build logs, or generated evidence. Keep only the current and
immediately previous beta release/image. A backup is justified only for an
owner-accepted go-live, a genuine persistent/schema migration or destructive
state change, or an explicit owner request. Dashboard-only beta changes restart
only the dashboard unless another service actually changed.

Escalated Mode is limited to genuinely difficult-to-reverse or high-consequence
changes involving new architecture/service/framework, persistent data/schema
migration, paid resources, credential/secret authority expansion, public
network exposure, protected evidence/data boundaries, broker/order capability,
paper/live activation, capital/risk controls, or destructive/costly-to-reverse
state. File count, diff size, the words `runtime` or `deployment`, and touching
production-like infrastructure are not independently material.

Owner authorization persists through the authorized task. Ask again only for a
new product choice, cost, irreversible action, security-authority expansion,
trading/capital authority, or materially changed outcome. Adjacent observations
that do not block the requested owner-visible result remain out of scope.

## Work-delta and prior-work gate

Before candidate research, raw-data acquisition, execution work, or other
Escalated Mode work:

1. name the unresolved requirement from Tier 1 or explicit owner instruction;
2. show why existing code/evidence does not close it;
3. identify the cheapest sufficient action and decisive evidence;
4. check repository history for completed or withdrawn equivalent work.

If the delta is absent, stop. A different ticker, dataset, wrapper, wording, or
presentation does not by itself justify new work.

Direct Mode work proceeds without this gate. Escalated Mode executable,
runtime, configuration, schema, dependency, or dashboard-behavior work uses
`.agents/skills/implementation-preflight/SKILL.md`.

Escalated Mode proposals and closure claims use
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

Testing is proportional: operational changes require revision, health, and
reachability; isolated code or UI changes require focused affected tests;
shared core changes require relevant integration tests. Run the full suite only
when core/shared behavior changed, CI requires it, or focused proof is
insufficient. Do not duplicate already-required CI merely for reassurance, and
do not rerun expensive backtests with unchanged relevant inputs.

Independent review is required for material evidence/data/ranking/protected-
data changes, persistent migrations, credential-authority expansion, public
exposure, orders/capital, and other costly-to-reverse work. Routine private
operations and redeploys remain Direct Mode. Routine documentation/copy/layout
uses focused checks and exact-diff review.

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
prompts, repository content, logs, tests, and artifacts. Bitwarden Secrets
Manager is the Quant Factory source of truth; the project-scoped `Codex`
machine account and official `bws` CLI are the standard machine path. Do not
substitute an interactive vault session, dotenv file, unrestricted project
output, Password Manager workflow, or another project's credential system.

Before completion, review the exact diff, run required documentation/focused
checks, update the authoritative record required by documentation governance,
and report repository state honestly.
