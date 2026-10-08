# ADR 0015: Agent Research Gateway Boundary

- **Status:** Accepted
- **Date:** 2026-10-02
- **Authority:** Decisions 323 and 339

## Context

Quant Factory already owns Candidate validation and persistence, portable
research context, durable research-launch claims, the generic candidate
pipeline, result persistence, and validated evidence contracts. External AI
research agents need a narrow way to use those capabilities without receiving
source, database, secret, protected-evidence, broker, or trading authority.

Transport and research authority are separate concerns. A model vendor,
protocol, or remote shell must not become part of the research domain model.

## Decision

`agent_gateway` is an outer application boundary. It may depend inward on
`research_intake`, `orchestration`, `persistence`, and validation/result
readers. Those components must not import it. Deployment composes the gateway
with the existing Prefect candidate launcher; the gateway does not implement a
second scheduler or pipeline.

The first transports are a provider-neutral CLI over a Unix-domain socket and
the existing SSH endpoint through a dedicated key-only forced-command account.
There is no gateway TCP listener. Local agents authenticate with distinct
high-entropy bearer credentials whose hashes bind server-side provider-neutral
identity records; the Unix peer credential separately limits which host users
may reach that path. The forced SSH account remains the remote transport
identity. Request fields cannot select an agent name, provider, client,
transport, or authority level.

QF Candidate v1 remains canonical. Candidate content receives a deterministic
identity for deduplication while the existing `idea_drafts` persistence
boundary remains the durable QF record. Gateway-only append-oriented audit,
research-note, and Candidate-lineage metadata lives in a separate SQLite store
so disabling the gateway requires no QF schema migration. Agents never receive
direct access to either database.

Level 2 run requests require all of: explicit gateway and active campaign
authority; deterministic Candidate eligibility under the mandate,
prior-work, ambiguity, data, budget, and bounded-study policy; a linked
immutable configuration; an available Candidate-lifecycle strategy; and
idempotent capacity in the campaign budget. The currently implemented
`owner_approved` status check remains a compatibility constraint until a
separately authorized change replaces it with this policy decision. Execution
uses the existing durable candidate pipeline and idempotency contract.
OOS/protected records fail closed at the gateway result boundary. The gateway
has no paper/live, broker, order, capital, secret-retrieval, data-purchase, or
source-edit operation.

## Security and operations

The gateway process uses a distinct non-login `qf-gateway` identity and creates
`/run/quant-factory/agent-gateway.sock` as owner `qf-gateway`, group
`qf-agent-access`, mode `0660`. Codex and Claude may run under the same trusted
local operating-system principal while retaining distinct registered audit
identities; this does not claim hostile isolation between processes owned by
that same principal. Remote access uses a distinct non-login
`qf-research` identity, a restricted authorized key, an exact command grammar,
and disabled shell, PTY, agent, X11, TCP, tunnel, and filesystem-transfer paths.
The SSH port is the existing host endpoint; no new public QF port is opened.

Untrusted source text is inert Candidate/note data. Request size limits,
structured errors, redaction, authority checks, and append-oriented audit apply
before state changes. The remote identity has no QF source, database, runtime,
or secret-file permission.

Rollback stops/removes the gateway service, removes the remote authorized key,
and removes local group memberships while retaining accepted Candidates and
audit history. Existing dashboard and research behavior remains unchanged.

## Consequences

The gateway is removable and provider-neutral. It adds a small application and
transport surface plus target-host identities and permissions, but no new QF
schema, public service, agent framework, model dependency, independent research
authority, or trading authority. Campaign-level research authority is defined
in Tier 1 and evaluated by Quant Factory, not granted by a gateway caller. ADR
0014's one-way boundaries and zero-violation guard remain controlling.
