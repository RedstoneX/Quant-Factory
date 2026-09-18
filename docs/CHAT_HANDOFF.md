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

Milestone 23 is the active gate. Decision 277 records owner acceptance of the
current dashboard/operator direction, so no repeat acceptance prompt is needed
after the remaining implementation, browser-lifecycle, end-to-end workflow,
failure-handling, test, and documentation/status gates pass. Those objective
gates remain pending and strategy discovery remains blocked. Decision 274 then
orders controlled Milestone 25 research until a defensible equity edge
qualifies, followed by paper activation only after every execution gate passes.
Live capital remains far future and requires separate explicit owner approval.

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
