# Quant Factory Codex Instructions

## Mission and authority

Quant Factory is a private tool for Terry, its sole owner and operator, to find
and validate a defensible trading edge and pursue consistent market income.
Build the shortest safe, evidence-truthful path to an operator-usable MVP. It
is not an enterprise, SaaS, multitenant, billing, or team product.

The closed Tier 1 authority set is:

1. `AGENTS.md` — stable Codex operating contract.
2. `docs/MILESTONES.md` — direction, current status, ordered work, acceptance.
3. `docs/DECISIONS.md` — accepted owner decisions and supersessions.

At the start of substantive work, read `docs/MILESTONES.md` and only relevant
decisions. Load supporting material only when the task requires it. Supporting
documents cannot create a competing mandate or status. Follow
`docs/DOCUMENTATION_GOVERNANCE.md` for documentation changes.

Codex is the sole active project agent toolchain. Do not load, invoke, rely
on, update, or follow `CLAUDE.md` or `.claude/**` during normal project work.
Those files remain untouched historical or tool-specific material.

The owner has already authorized the scoped revival. Continue within accepted
scope without repeatedly requesting permission. Only the owner changes the
mandate, accepts milestones, authorizes deployment, or approves paper/live
trading and capital exposure.

## Work selection and communication

- Lead with the answer, phase, next action, and any real blocker in no more than
  six short bullets. Use plain language.
- State what is measured, inferred, or unknown. Distinguish proposed,
  implemented, tested, merged, deployed, and owner-accepted work.
- Verify the load-bearing claim cheaply before acting. Use the narrowest
  decisive validation and stop when the result is established.
- Every implementation slice must advance the current Tier 1 path or remove a
  demonstrated blocker. Do not add speculative infrastructure, refactoring,
  dashboard polish, or execution scope.
- Follow the factory-to-beta sequence and owner checkpoints in
  `docs/MILESTONES.md`. While that sequence is active, reuse saved results and
  deterministic fixtures to prove missing factory stages; do not commission a
  new candidate, acquire data, or run another candidate backtest merely to
  prove the architecture. Edge research resumes only after beta.
- Before candidate or strategy-family research, implementation, data
  inspection, execution, or delegation, perform a cheap read-only prior-work
  check. The unresolved need must come from Tier 1, an owner instruction, an
  acceptance criterion, or a measured blocker; name why existing work cannot
  close it and the cheapest sufficient action. A symbol, dataset, wrapper,
  wording, or presentation change is not enough unless it serves an approved
  replication need or genuinely required independent evidence. Otherwise stop
  and reuse or report the existing work. Record meaningful completed or
  withdrawn investigations and the exact next action in `docs/MILESTONES.md`.
- Correct verified factual drift, but never turn a correction into an
  unapproved change of scope, architecture, status, or acceptance.
- Record permanent changes under documentation governance; chat is not durable
  project memory.

## Repository safety

- `RedstoneX/Quant-Factory` is the canonical forward source of truth. Use an
  owned checkout or isolated worktree based on accepted `main`.
- Substantive work uses a dedicated branch and pull request. Never push to
  `main`, force-push, use destructive Git, or alter the historical repository.
- Preserve unrelated edits. Concurrent writers use separate worktrees. Stage
  explicit owned paths only; never use `git add .`, `git add -A`, or a bare
  stash.
- Never commit secrets, market data, generated results, environment files, or
  machine-specific artifacts.
- Required checks and admin enforcement remain enabled. GitHub strict/up-to-
  date remains disabled under Decision 276; independent green pull requests
  need not rebuild after another independent merge. Dependent or overlapping
  work integrates serially and is retested against resulting `main`.
- The owner is not expected to operate Git. Codex completes authorized Git and
  GitHub work and reports the result.

## Implementation and reuse

Before material executable, runtime, configuration, schema, dependency, or
dashboard-behavior changes, use
`.agents/skills/implementation-preflight/SKILL.md`. Routine factual or
presentation corrections need only a short scope-and-reuse check.

- Inspect official documentation and established product archetypes, relevant
  code and tests, accepted designs, licensed dependencies, and maintained
  legally compatible components before writing custom code or relying on an
  unsupported assumption.
- Prefer a suitable proven component or the smallest adapter over rebuilding
  mature behavior. Custom code requires a verified product-specific gap or
  evidence that reuse is materially worse.
- Preserve approved prototypes as inputs; never call them integrated, tested,
  deployed, or accepted application behavior.
- Read applicable accepted ADRs before architecture changes. Keep research,
  validation, evidence, and strategy logic venue-neutral; research must never
  submit venue orders directly.
- Do not bypass, weaken, or skip relevant tests. Run focused checks for the
  changed path and one focused browser check for affected UI. Broader browser,
  lifecycle, recovery, device, or target proof is required only for a concrete
  risk, an actual runtime/deployment change, explicit milestone closure, a
  qualified candidate approaching paper, or an owner request.

For a material proposal or closure claim, use
`.agents/skills/quant-factory-adversary/SKILL.md`. The adversary challenges
reasoning; it does not decide. Independent review is required for material
evidence/data/ranking/protected-data changes, migrations, credentials,
deployments, orders/capital, or costly-to-reverse work. Routine documentation,
copy, and layout changes use focused checks and lead diff review.

## Evidence, data, and target proof

- Fixtures and previously inspected data prove infrastructure, not a trading
  edge or independent profitability evidence.
- Keep hypothesis attribution, parameters, dataset and runtime identity,
  execution assumptions, and protected-data boundaries reproducible.
- Open-ended optimization, data mining, protected-test inspection, automatic
  promotion, and unapproved parameter changes are prohibited.
- Before changing market data, read `docs/DATA_CATALOG.md` and its manifests.
  Raw data stays outside Git; verify checksums and preserve original sources.
- CI proves repository checks, not target-environment behavior. After an
  authorized deployment or target runtime, dependency, configuration, or
  secret-injection change, separately verify startup and the changed flow on
  that target, with backup and rollback where required. Never deploy merely to
  prove deployment.
- Do not rerun expensive backtests unless relevant inputs changed.

## Credentials, execution, and capital

- Never expose unrestricted vault access or secret values. Credentials must be
  isolated, injected through an approved boundary, auditable, and fail closed.
  Secrets must not enter prompts, logs, source, tests, docs, or artifacts.
- Paper and live credentials, state, and deployments remain separate.
  Withdrawal permission is prohibited.
- AI may analyze, propose, review, alert, and perform explicitly bounded
  approved actions. It may not bypass deterministic risk limits, silently
  change strategy parameters, enable trading, or increase capital.
- Paper activation requires a qualified edge and every current account,
  credential, endpoint, worker, reconciliation, recovery, capacity, audit, and
  fail-closed gate. Live work additionally requires successful paper evidence,
  separate explicit owner approval, isolated live security boundaries, and an
  independent Risk Sentinel.

## Codex orchestration and completion

Follow `docs/ai-programming-agent-policy.md` for delegation, review, and
integration. The lead may complete small, routine, bounded work directly.
Delegate only when specialization or parallel work produces a clear net time
or cost benefit; never commission duplicate drafts. The lead remains the sole
owner-facing coordinator and independently validates critical evidence.

A milestone is complete only when acceptance evidence passes, reviewed work is
merged and synchronized, records are updated, and the owner accepts it where
required. Target proof is required only when the milestone changes or deploys
a target. Report: repository, files changed, validation, documentation impact,
commit/push, and warnings.
