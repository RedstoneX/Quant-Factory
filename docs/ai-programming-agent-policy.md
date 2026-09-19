# Quant Factory AI Programming Agent Policy

- **Status:** Accepted
- **Scope:** public repository work and the owner-authorized revival

## Roles

The project owner makes mandate, milestone-acceptance, deployment, and capital
decisions. The lead assistant coordinates architecture, documentation,
repository integration, and owner communication. Claude Code is the primary
agent for sustained local implementation outside the scoped revival.

During the revival, Decision 270 requires multiple bounded workers matched to
task complexity. The lead defines scope, assigns disjoint ownership,
independently validates critical evidence, integrates results, and remains the
single owner-facing coordinator. Workers do not contact the owner, expand
scope, spawn descendants, or present unverified claims as decisions.

Every worker prompt includes the objective, repository/ref, applicable
authorities, owned paths, allowed actions, exclusions, expected output,
decisive validation, stop conditions, and a polling budget. Concurrent writers
use separate worktrees or directories.

## Routing and implementation

Read-only inspection, documentation, status, and comparison use the smallest
safe tool. Sustained multi-file implementation, iterative debugging, runtime
work, and dependency-sensitive testing use the primary programming agent.
Before executable implementation, run the project implementation preflight,
inspect current code/tests/ADRs, bound the smallest safe change, and state the
validation and exclusions.

The preflight must also inventory reusable project code and tests, licensed
dependencies, owner-approved prototypes, and mature maintained components or
reference implementations. Compare functional fit, license, security,
maintenance, integration cost, and data/evidence truthfulness. Prefer reuse or
adaptation. Custom implementation requires a verified gap or evidence that
reuse is materially worse, with the rationale recorded before coding. Do not
rebuild mature commercial-grade behavior for architectural neatness or
speculative flexibility. Small domain adapters and safety or evidence controls
remain allowed where necessary; incompatible or unverified licensing remains
a stop condition. Prototype approval is design input, not proof of application
integration, testing, deployment, or final operator acceptance.

The controlling priority is the shortest safe, evidence-truthful path to an
operator-usable MVP that can validate or reject a trading edge. Reuse is a
means to that result, not an end or a mandate to prolong evaluation after a
suitable path is established.

Decision 287 supersedes Decision 286's active selected-run Results completion
priority. Preserve the validated Results repair as unmerged and undeployed
work, and freeze further dashboard implementation, polish, redesign and
deployment unless a verified defect blocks operation. The owner accepts the
existing dashboard as good enough to proceed with the controlled MVP research
path; that limited acceptance does not accept or deploy the pending repair,
close Milestone 23, or waive its remaining technical gates.

The active shortest path is inventory of source-attributed candidates → one
named, source-attributed hypothesis selected for explicit owner approval → the
thinnest necessary adapter into the existing VectorBT batch-research path →
durable results and evidence → ranking/filtering → inspection in the existing
dashboard. Executable candidate launch requires that owner approval and
predeclared evidence boundaries. Use the existing engine, persistence, evidence
and interface. Do not substitute a new research engine, dashboard, framework,
generic platform layer or speculative architecture. Before assigning or
accepting a slice, the lead records which exact path step it advances and the
smallest decisive proof. An independent reviewer verifies that trace as a hard
boundary and rejects a slice that does not directly advance the path or remove
a demonstrated blocker. Unrelated dashboard work, generic infrastructure,
speculative refactoring and execution expansion are rejected, not deferred
inside the active slice.

Controlled, bounded, source-attributed candidate intake, discovery and
research/backtesting may proceed under Milestone 25 safeguards while Milestone
23 remains pending. Open-ended optimization or data mining, protected-test
evaluation, automatic promotion, paper orders and live work remain outside
this authority.

Preserve unrelated work. Use dedicated branches and pull requests; do not
force-push, push directly to `main`, stage the entire tree, or use anonymous
stashes. Never weaken a test or acceptance criterion to obtain a pass.

Decision 276 keeps required checks and admin enforcement enabled while setting
GitHub's strict/up-to-date requirement to `false` unless the owner changes the
decision. Independent green pull requests do not rebase, update, rebuild, or
serialize solely because another independent pull request merged first. CI
concurrency is per ref and no merge queue is used. Dependent or overlapping
changes still integrate serially and are retested against the resulting
`main`.

## Evidence and CI

CI execution is not merge enforcement and CI is not target-environment proof.
A required gate is proven only by a disposable controlled failure that causes
GitHub to block merging, followed by a restored green path. Never merge the
deliberate failure or use an override.

On 2026-09-18 GitHub API evidence re-confirmed on the canonical public
repository `strict: false`, the three required checks (`Documentation
contracts`, `Portable tests`, and `Dependency review`), `enforce_admins: true`,
repository auto-merge and merged-branch deletion enabled, per-ref workflow
concurrency, no merge queue, and no force push or branch deletion. Controlled
PR #1 failed the required `Portable tests` check and was blocked, then passed
every required check after correction and was closed without merging.
Independent same-base PRs #2 and #3 were both green. After #3 merged, #2
remained `CLEAN` and `MERGEABLE` with unchanged Test run `35301119002` and
Dependency Review run `35301119008`, received no refresh run, and was closed
unmerged.

After dependency, secret-injection, runtime configuration, or equivalent
environment-input changes, separately verify loading, startup, and relevant
behavior in the actual target environment. Evidence must not contain secrets
or place orders.

## Credential and trading safety

Agents never receive unrestricted vault access or underlying secret values.
The preferred flow is restricted identity or placeholder → approved gateway
policy/injection → permitted destination. Credentials and denials must be
auditable and fail closed. Begin with harmless test credentials, then paper
credentials only. Paper and live credentials remain separate; withdrawal
permission is prohibited.

Deterministic services enforce execution, exposure, loss, stale-data,
connectivity, and kill-switch rules. AI may analyze, propose, review, alert,
and perform explicitly bounded approved actions. It may not bypass controls,
silently change strategy parameters, enable live trading, increase capital, or
retrieve broader credentials. Live activation always requires explicit human
approval and isolated credentials, state, deployment, and independent risk
supervision.
