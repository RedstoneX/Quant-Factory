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

Preserve unrelated work. Use dedicated branches and pull requests; do not
force-push, push directly to `main`, stage the entire tree, or use anonymous
stashes. Never weaken a test or acceptance criterion to obtain a pass.

## Evidence and CI

CI execution is not merge enforcement and CI is not target-environment proof.
A required gate is proven only by a disposable controlled failure that causes
GitHub to block merging, followed by a restored green path. Never merge the
deliberate failure or use an override.

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
