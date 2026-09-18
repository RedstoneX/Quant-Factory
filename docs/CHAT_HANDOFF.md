# Quant Factory Chat Handoff

This page is startup navigation only. It does not define current status,
mandate, or acceptance.

## Start here

Read the closed Tier 1 authority set before acting:

1. [`AGENTS.md`](../AGENTS.md) — working contract, safety, evidence, and Git rules.
2. [`docs/MILESTONES.md`](MILESTONES.md) — product direction, current status,
   ordered work, and acceptance.
3. [`docs/DECISIONS.md`](DECISIONS.md) — accepted decisions and supersessions.

Then read [`DOCUMENTATION_GOVERNANCE.md`](DOCUMENTATION_GOVERNANCE.md), the
[agent policy](ai-programming-agent-policy.md), and the ADRs, specifications,
or runbooks relevant to the task. `README.md` and this page are derived
navigation, not competing authorities.

## Current resume point

Decisions 284–285 fix the product and implementation boundary. Quant Factory
is Terry's private single-operator trading-research system, not an enterprise,
SaaS, sales, multitenant, billing, or team product. Before custom work, agents
must evaluate existing project code, licensed dependencies, approved
prototypes, and mature maintained legally usable components; custom code is
only for a verified gap or when reuse is materially worse. The approved
Results prototype remains implementation input, not a claim of integration,
testing, deployment, or final acceptance.

Milestone 23 is the active gate. Decision 279 records the owner's rejection of
the former Results-page comprehension and flow. Decisions 280–281 establish
the chart-first direction and validated preview constraints. Decision 282
records the owner's hands-on approval of the detailed selected-run Results
specification as intuitive, including chart pan/zoom, panel resizing, Metrics,
Trades and Change run, and authorizes implementation. Decision 282 also
requires a separate scalable multi-run surface to aggregate, slice, rank,
filter and select hundreds or thousands of persisted runs; its exact UI,
architecture and name remain to be designed. Selected-run implementation,
deployment, testing, licensed-target proof, renewed acceptance of the eventual
implemented experience, and the remaining browser-lifecycle, end-to-end
workflow, failure-handling, and documentation/status gates remain pending.
Decision 283 requires safe, validated reuse for exact repeat research
computations while preserving a distinct durable run ticket and lifecycle for
every explicit request. Its cache architecture, storage, eviction,
implementation sequence and explicit Reproduce recomputation policy remain to
be designed; no computation-cache implementation is claimed.
Strategy discovery remains
blocked. Decision 278
accepts ADR 0011's safer durable run-ticket design and authorizes its
implementation. That bounded implementation is merged in canonical source for
Run test, historical relaunch, and reproduction. PR #50 adds focused
stale-recovery coverage beside the claim-core suite in required Portable CI;
separate browser-fixture recovery evidence remains retained. Production
deployment, current licensed-target SPYM proof,
the complete operator workflow, and Milestone 23 acceptance remain unproven;
the source implementation does not close Milestone 23.
Decision 274 then orders controlled Milestone 25 research until a defensible
equity edge qualifies, followed by paper activation only after every execution
gate passes. Live capital remains far future and requires separate explicit
owner approval.

Decision 275 is implemented: this clean-history public repository is the sole
forward source of truth, and the original remains a private, read-only
historical archive. The cutover did not modify the production runtime.
Decision 276 keeps required checks and admin enforcement but permanently
disables strict/up-to-date unless the owner changes it: independent green PRs
need no refresh build after an unrelated merge, while dependent or overlapping
work still integrates and retests serially. Publication does not grant a
source-code license: the project is all rights reserved.

## Mechanism references

- [ADR 0008](architecture/0008-dashboard-mounted-route-architecture.md) defines
  the mounted-route Dash architecture and browser acceptance.
- [ADR 0011](architecture/0011-durable-research-launch-claims.md) defines the
  accepted, source-implemented durable research run-ticket contract and its
  still-pending deployment and Milestone 23 evidence boundaries.
- [Milestone 23 acceptance](milestones/milestone-23-acceptance.md) defines the
  scenario matrix and readable incident history.
- [ADR 0007](architecture/0007-portable-deployment-and-alpaca-first-roadmap.md)
  defines portable deployment and environment separation.
- [ADR 0010](architecture/0010-agent-credential-gateway.md) and the
  [credential gateway runbook](operations/credential-gateway.md) define
  credential isolation and fail-closed proof.
- [Paper worker runbook](operations/paper-worker.md) defines the read-only
  observer boundary.
- [Data catalog](DATA_CATALOG.md) and committed manifests govern dataset
  identity.

Verify path, branch, HEAD, upstream, and dirty state before editing. Use a
dedicated branch or isolated worktree, preserve unrelated changes, run the
narrowest decisive validation first, and never infer acceptance from stale
evidence.
