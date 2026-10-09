# Quant Factory documentation governance

Repository documentation is active instruction material. Superseded directives
are removed from the active tree and remain recoverable in Git history; they
are not retained beside current instructions as historical alternatives.

## Closed authority map

1. `AGENTS.md` — stable operating and repository rules.
2. `docs/MILESTONES.md` — sole current goal, phase, queue, sequence, blockers,
   and next action.
3. `docs/DECISIONS.md` — concise decisions that still change current behavior.

Supporting documents define one named mechanism only. They never contain a
current queue, visual target, completion claim, or competing authority.

## Frontend authority

- Sole visual contract:
  `docs/assets/dashboard/current-visual-contract/dashboard.html`
- Product behavior: `docs/factory-operating-contract.md`
- Runtime architecture: ADR 0016.
- Execution discipline: `.agents/skills/quant-factory-frontend/SKILL.md`.

No other mockup, screenshot, preview, acceptance package, UI direction file,
CSS file, deployed page, browser test, local branch, or historical decision
controls frontend implementation. The other six workflow surfaces have no
active visual authority until individually approved after Dashboard acceptance.
Repository tooling enforces the contract checksum and rejects known superseded
paths or directives.

## Lifecycle

- Accepted current behavior stays concise in Tier 1 or its named contract.
- Rejected proposals, superseded directives, old milestone narratives, and
  obsolete visual assets are deleted from the active tree after any still-valid
  nonvisual invariant is moved to its current owner.
- Git history is the archive. Do not create `legacy`, `archive`, `old`, or
  `historical` copies inside the active repository.
- Generated proof debris, screenshots, browser captures, temporary databases,
  logs, caches, releases, and repeated backups are removed when their slice
  ends unless they are the current approved contract.
- Distinguish proposed, implemented, tested, merged, deployed, and explicitly
  owner-accepted states.
- Only the owner changes mandate, priority, acceptance, deployment, paper/live,
  broker, order, or capital authority.

## Completion

Documentation cleanup is complete only when Tier 1 agrees, the authority guard
passes, the normal documentation check passes, and the change is published
through the repository's branch/PR process. Local uncommitted files are not the
canonical source of truth.
