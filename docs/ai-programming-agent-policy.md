# Quant Factory Codex Agent Policy

- **Status:** Accepted
- **Scope:** Codex work in the canonical public repository

This procedure supports `AGENTS.md`; it does not create product direction or
current status. Tier 1 remains authoritative.

## Roles

The owner controls mandate, priority, milestone acceptance, deployment,
paper/live authority, and capital. The Codex lead is the sole owner-facing
coordinator. It defines slices, delegates when proportionate, validates
critical evidence independently, integrates reviewed work, and keeps the
owner informed in plain language.

Workers receive no project ownership. They do not contact the owner, expand
scope, spawn descendants, or treat unverified findings as decisions. A worker
stops and reports when its boundaries conflict, required authority is absent,
or decisive validation cannot be completed.

## Bounded delegation

Decision 270 requires bounded workers for task execution during the scoped
revival: the lead orchestrates and validates rather than implementing inline.
Parallelize independent work that materially shortens the critical path; do
not create duplicate implementation drafts. Match worker and review effort to
the cost and risk of the slice.

Every worker prompt states:

- objective and reason the slice advances current Tier 1 work;
- canonical repository, base revision, branch, and owned worktree;
- authorities and evidence to read;
- owned paths and allowed actions;
- explicit exclusions and stop conditions;
- required validation and final report; and
- whether owner contact or descendant workers are prohibited.

Concurrent writers use separate worktrees or directories. The lead checks the
base revision, ownership, diff, validation output, and reported uncertainty
rather than accepting a worker summary at face value.

## Preflight and adversary

Before executable, runtime, configuration, schema, dependency, dashboard, or
material scope changes, apply
`.agents/skills/implementation-preflight/SKILL.md`. The result bounds the
smallest change, reuse, exclusions, stop conditions, validation, and
documentation impact before implementation starts.

Before a material proposal or closure claim, apply
`.agents/skills/quant-factory-adversary/SKILL.md`. Material triggers include
priority or scope changes; architecture, framework, or dependency choices;
custom build over reuse; changes to strategy parameters or evidence,
protected-data, ranking, or promotion boundaries; production deployment;
paper/live authority; and beta, milestone, or edge-readiness claims.

When delegation is available, the adversary is a separate read-only Codex
subagent. It argues against the proposal and returns no verdict. The lead
dispositions each material objection as `CHANGED` with evidence or `REJECTED`
with reasons before proceeding. Routine status, factual read-only work,
housekeeping, verified factual corrections, and already approved mechanical
execution without scope change are exempt.

## Implementation and review

An implementation slice owns only the paths named in its prompt. Preserve
unrelated work. Use dedicated branches and pull requests; never push directly
to `main`, force-push, blanket-stage the tree, use destructive Git, or weaken a
test or acceptance criterion to obtain a pass.

Run the narrowest decisive checks first. Broaden validation only for a
specific remaining risk. Expensive backtests are not repeated when inputs and
relevant implementation are unchanged.

Use an independent reviewer for material executable changes, security or
trading controls, migrations, production deployment, or other work where an
uncaught error has meaningful cost. Keep review bounded to the owned diff,
scope compliance, load-bearing evidence, and decisive checks. Review is not a
second implementation or an open-ended audit.

The lead resolves review findings, confirms required checks, and integrates
only reviewed work whose evidence matches its claim. Overlapping or dependent
pull requests integrate serially and are retested on resulting `main`.
Independent green pull requests follow Decision 276 and do not rebuild merely
because another independent pull request merged.

## Evidence and target validation

Distinguish proposed, implemented, tested, merged, deployed, and accepted.
Label measured, inferred, and unknown claims. Check the single load-bearing
claim behind a proposal or completion report independently.

CI execution is not merge enforcement and neither is target-environment
proof. Required enforcement needs a controlled failing check that blocks
merge followed by a restored green path. Environment-input changes require
separate loading, startup, and behavior proof on the authorized target. Do not
place orders or expose secrets during validation.

## Safety and integration

Research cannot submit venue orders. Open-ended optimization, protected-test
inspection, automatic promotion, paper activation, live work, and capital
changes remain unavailable without their Tier 1 gates and owner authority.
Credentials remain isolated, least-privilege, auditable, and absent from
prompts, repository content, logs, tests, and evidence.

Before completion, review the exact diff, run documentation checks, update the
authoritative record required by `docs/DOCUMENTATION_GOVERNANCE.md`, and report
local/remote reconciliation honestly. A commit, pull request, merge, or agent
statement cannot by itself establish milestone completion or owner acceptance.
