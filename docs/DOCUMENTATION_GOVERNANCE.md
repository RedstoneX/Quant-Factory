# Quant Factory Documentation Governance

Repository documentation is durable project memory. Chat, external notes,
runtime output, and recovery snapshots are not substitutes for accepted
repository authorities.

## Closed authority map

The Tier 1 set is closed to additions:

1. `AGENTS.md` — operating contract and work allocation.
2. `docs/MILESTONES.md` — product direction, current status, ordered work,
   milestone scope, and acceptance.
3. `docs/DECISIONS.md` — accepted owner decisions and supersessions.

Changing this set requires an explicit owner decision. Supporting documents
have these roles:

| Information | Primary authority | Supporting document |
|---|---|---|
| Agent and repository rules | `AGENTS.md` | `docs/ai-programming-agent-policy.md` |
| Product order, status, and acceptance | `docs/MILESTONES.md` | accepted ADRs and milestone records |
| Accepted decisions | `docs/DECISIONS.md` | accepted ADRs |
| Architecture rationale | accepted ADR | decision summary |
| Startup navigation | `docs/CHAT_HANDOFF.md` | Tier 1 links only |
| Public orientation | `README.md` | links only |
| Domain procedure | named specification or runbook | relevant ADR/milestone |

When documents conflict, the primary authority wins and the contradiction must
be corrected. Do not create parallel roadmap, status, decision, outcome, or
handoff authorities.

## Supporting-document lifecycle

- Operating procedures elaborate `AGENTS.md`; they cannot create new mandate.
- ADRs, specifications, runbooks, and data catalogs explain mechanisms; they
  do not establish implementation or acceptance status.
- Investigations and unaccepted ideas are clearly labelled and are retired
  after their useful findings move to the proper authority.
- Historical acceptance and incident records remain readable and separate from
  current work.
- Conceptual documents display `Status: CONCEPTUAL / NOT AUTHORIZED`.
- README and CHAT_HANDOFF remain orientation, never competing status.

## Evidence and ratification

- Distinguish proposed, implemented, tested, merged, deployed, and explicitly
  accepted work.
- Current-state claims cite a dated repository revision, runtime observation,
  or acceptance record. Old test output is not a fresh pass.
- Correct verified factual drift without another permission request, but do
  not silently change mandate, architecture, scope, or acceptance.
- Only the project owner ratifies product mandate, approval policy,
  architecture, and milestone acceptance. An agent's proposal, commit, or
  merge is not owner ratification.
- Attribute agent-chosen cuts or deferrals and explain why. Trace unattributed
  constraints; ask the owner if evidence cannot establish their authority.
- Use plain-language impact first and retain the technical evidence in the
  relevant record.

## Executable documentation controls

`tools/check_documentation.py` enforces:

- `docs/MILESTONES.md` is at most 100,000 UTF-8 bytes;
- one marker-delimited active-work table with columns `ID`, `Priority`,
  `Status`, `Depends`, and `Evidence`;
- unique IDs and positive priorities, valid statuses, resolvable acyclic
  dependencies, and nonempty evidence;
- optional dated owner decisions in the exact declared format;
- one nonempty, linked, append-only incident-history section in
  `docs/milestones/milestone-23-acceptance.md` when a resolvable base revision
  is provided.

`AGENTS.md` is a curated contract and is exempt from the milestone byte cap.
Completed incidents move to readable history before active work is pruned.
Unknown evidence remains unknown; malformed or partial checks do not establish
product defects or completion.

CI execution is not merge enforcement and CI is not target-environment proof.
Required enforcement needs a controlled failing check that blocks merging and
a restored green path. Runtime changes need separate loading, startup, and
behavior proof in the target environment.

## Decision states

Classify a change before documentation is updated:

1. **Idea** — exploratory and not authoritative.
2. **Investigation** — evidence gathering in a subordinate note.
3. **Accepted decision** — explicitly approved or directly instructed by the
   project owner.
4. **Implemented decision** — reflected in code, configuration, deployment, or
   operating procedure.
5. **Superseded decision** — retained with an explicit pointer to its
   replacement.

## Documentation-impact assessment

For every accepted decision, roadmap change, milestone completion,
architecture change, deployment decision, venue decision, or permanent
workflow change, answer every row:

| Question | Required action when yes |
|---|---|
| Does permanent agent behavior or allocation change? | Update `AGENTS.md` and the agent policy. |
| Does direction, order, scope, status, or acceptance change? | Update `docs/MILESTONES.md`. |
| Is this a durable decision or supersession? | Append to `docs/DECISIONS.md`. |
| Does architecture, deployment, security, data flow, or integration change? | Create or amend an ADR. |
| Must future chats know this immediately? | Update `docs/CHAT_HANDOFF.md`. |
| Would public orientation become misleading? | Update `README.md`. |
| Does operator, recovery, migration, or incident procedure change? | Update the named runbook/specification. |
| Does a milestone-completion fact change? | Record commit, validation, and status in `docs/MILESTONES.md`. |

Each row is marked updated or not applicable with a reason.

## Completion gate

Documentation is complete only when the change is classified, the impact
assessment is recorded, authorities are synchronized, supersessions remain
explicit, supporting links resolve, contradictions are removed, Git history
contains the change, and the completion report identifies each authority as
updated or not applicable.

Required report:

```text
Decision classification
Documentation impact
- AGENTS.md: updated / not applicable — reason
- MILESTONES.md: updated / not applicable — reason
- DECISIONS.md: updated / not applicable — reason
- ADR: updated / not applicable — reason
- CHAT_HANDOFF.md: updated / not applicable — reason
- README.md: updated / not applicable — reason
- Runbook/specification: updated / not applicable — reason
Consistency check
Commits
Local/remote reconciliation warning
```
