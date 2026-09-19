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

Decision 287 supersedes Decision 274's dashboard-first active order and
Decision 286's active Results-completion priority. The current shortest path is
inventory of source-attributed candidates → one named, source-attributed
hypothesis selected for explicit owner approval → the thinnest necessary
adapter into the existing VectorBT batch-research path → durable results and
evidence → ranking/filtering → inspection in the existing dashboard. Every
implementation slice must directly advance one path step or remove a
demonstrated blocker; the lead and independent reviewer reject slices without
that trace. Reuse the existing engine, persistence and interface. Do not build
a replacement engine, dashboard, framework or speculative platform.

The dashboard remains essential, and the owner accepts the existing dashboard
as good enough to proceed with the controlled path. It is frozen unless a
verified defect blocks operation. That limited acceptance does not close
Milestone 23 or accept or deploy the pending repair. The validated Results
repair remains preserved outside canonical `main`, unmerged and undeployed;
the accepted later multi-run and safe-cache requirements remain pending.

Milestone 23 remains pending. Decision 279 records the owner's rejection of
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
Decision 287 permits controlled, bounded, source-attributed candidate intake,
discovery and research/backtesting under Milestone 25 safeguards before
Milestone 23 closes. Executable candidate launch requires explicit owner
approval of its named, source-attributed hypothesis and predeclared evidence
boundaries. Open-ended optimization or data mining, protected-test evaluation
and automatic promotion remain blocked. Decision 288 supplies that first
selection and approval: the existing MES five-minute, 09:30 New York ORB
specification, reference-first and then limited to its existing 30-variant
matrix. Reuse its verified dataset/manifest, strategy code, VectorBT engine,
durable evidence path and current dashboard. At executable validation revision
`0f7701fd6d3823b9603576777df441dd92df45a8`, four successful isolated runs
persisted 32 ranked rows (2 reference plus 30 matrix), exact 30-minute/zero-
offset parity passed in both directions, and all 30 matrix variants screened
out. Each run persisted seven registered artifacts plus its integrity manifest.
An initial disk-full attempt was partial invalid evidence and was excluded; a
fresh isolated retry succeeded. This remains development/reference evidence
only and does not establish an edge, promotion, deployment, paper activation,
or live authority. R07 and Milestone 25 remain in progress. The next action is
repository integration, followed by inspection in the existing dashboard and
only narrow repairs for verified operational blockers. Decision 278
accepts ADR 0011's safer durable run-ticket design and authorizes its
implementation. That bounded implementation is merged in canonical source for
Run test, historical relaunch, and reproduction. PR #50 adds focused
stale-recovery coverage beside the claim-core suite in required Portable CI;
separate browser-fixture recovery evidence remains retained. Production
deployment, current licensed-target SPYM proof,
the complete operator workflow, and Milestone 23 acceptance remain unproven;
the source implementation does not close Milestone 23. Paper activation still
requires a defensible edge and every unchanged execution gate. Live capital
remains far future and requires separate explicit owner approval.

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
