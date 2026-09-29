# Quant Factory Documentation Governance

Repository documentation is durable project memory. The purpose of governance
is to keep Codex from reconstructing current direction from sprawling historical
material.

## Closed authority map

The Tier 1 set is closed to additions:

1. `AGENTS.md` — stable operating contract and orchestration rules.
2. `docs/MILESTONES.md` — **only** authority for current goal, phase, active
   queue, sequencing, blockers, next action, and milestone status.
3. `docs/DECISIONS.md` — append-only accepted owner decisions,
   supersessions, and the current-effective decision index.

Changing this set requires an explicit owner decision.

## Supporting documents

Supporting documents may explain a mechanism, requirement, procedure, or
historical evidence. They **must not maintain a competing current queue or
project-status narrative**.

| Information | Authority | Supporting role |
|---|---|---|
| Agent behavior/orchestration | `AGENTS.md` | `docs/ai-programming-agent-policy.md` |
| Current goal/status/order/next action | `docs/MILESTONES.md` | none |
| Accepted decisions/supersessions | `docs/DECISIONS.md` | ADR rationale where relevant |
| Architecture | accepted ADR | implementation rationale only |
| Product requirements | named specification | requirements only |
| Historical acceptance/incidents | milestone record | evidence only |
| Dataset/provider facts | data catalog/source policy | facts/provenance only |
| Startup navigation | `docs/CHAT_HANDOFF.md` | links to Tier 1 |
| Public orientation | `README.md` | concise purpose and links |

When a supporting document contains historical status language that could be
mistaken for current direction, place a short banner at the top pointing to
`docs/MILESTONES.md`. Do not continually synchronize long current-status
sections across supporting documents.

## Lifecycle and cleanup rules

- Preserve accepted decisions, test evidence, incident history, and useful
  research history. Cleanup does not mean deleting evidence.
- Retire duplicated plans by marking them historical/supporting or replacing
  their current-status prose with a Tier 1 pointer.
- ADRs describe architecture and rationale, not the active queue.
- Specifications describe requirements, not completion status.
- README and CHAT_HANDOFF remain short orientation documents.
- Investigations and rejected proposals remain discoverable but cannot silently
  reactivate work.
- Conceptual documents are labelled `CONCEPTUAL / NOT AUTHORIZED`.
- Do not create a new roadmap, status, handoff, or decision-summary file when
  Tier 1 can hold the information.

## Evidence and ratification

Distinguish proposed, implemented, tested, merged, deployed, and explicitly
accepted. Current-state claims require current repository/runtime evidence where
material.

Only the owner changes mandate, product priority, milestone acceptance,
deployment authority, or paper/live capital authority. Agent proposals, commits,
tests, and merges do not create owner acceptance.

Correct factual drift without inventing scope. If an older supporting document
conflicts with Tier 1, Tier 1 wins and the supporting document is corrected or
marked historical.

## Executable documentation controls

`tools/check_documentation.py` enforces the milestone active-work structure,
size and selected historical-record constraints. Preserve its marker-delimited
active-work table and append-only incident history.

CI execution is not target-environment proof. Runtime/deployment claims require
the applicable target proof separately.

## Documentation-impact assessment

For a durable change, evaluate:

| Change | Required authority |
|---|---|
| permanent agent behavior/allocation | `AGENTS.md` and agent policy |
| current direction/order/status/acceptance | `docs/MILESTONES.md` |
| accepted owner decision/supersession | append `docs/DECISIONS.md` |
| architecture/security/data-flow integration | relevant ADR |
| startup navigation | `docs/CHAT_HANDOFF.md` |
| public orientation | `README.md` |
| operator/recovery/migration procedure | named runbook/spec |
| dashboard-displayed project status | align `dashboard/project_status.py` |

Do not update unrelated supporting documents merely to restate the same current
status.

## Completion gate

Documentation cleanup is complete when:

- Tier 1 agrees internally;
- supporting docs do not claim a conflicting active queue;
- supersessions are explicit;
- historical evidence remains discoverable;
- documentation checks pass;
- the change is committed through the normal branch/PR process.

Completion reporting should identify the decision classification, files changed,
checks run, PR/commit state, and any unresolved contradiction.
