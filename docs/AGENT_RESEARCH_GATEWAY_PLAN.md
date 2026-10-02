# Quant Factory Agent Research Gateway

> This remains a supporting implementation specification. Decision 323 and
> `docs/MILESTONES.md` authorize ARG-0 through ARG-6; Tier 1 remains the sole
> authority for current status and sequencing. ARG-7 remains optional and is
> not authorized without a demonstrated client need.

## Purpose

Build a provider-neutral research gateway so external AI agents can interact
with Quant Factory without becoming part of Quant Factory's core architecture.

The intended agents include:

- Codex running on the Quant Factory OVH host;
- Claude Code running on the same OVH host;
- Grok Bot running on its own hosted cloud computer and reaching the OVH host
  through restricted SSH;
- future agents or LLM products that can use a CLI, SSH, MCP, REST, or another
  thin adapter.

The gateway is not an LLM provider integration. Quant Factory must not call
OpenAI, Anthropic, xAI, Google, OpenRouter, or another model vendor as a required
dependency. Agents call Quant Factory.

The design goal is:

```text
Research agent
    |
    | provider-specific environment
    v
thin transport adapter
    |
    v
QF Research Gateway
    |
    +-- current research context
    +-- prior-work search
    +-- QF Candidate validation/submission
    +-- permitted research-run requests
    +-- structured results/evidence
    +-- research notes/lineage
    |
    v
existing Quant Factory services
```

Quant Factory remains the laboratory, durable memory, evidence authority, and
governance boundary. The LLM remains replaceable.

## Why this architecture

The gateway must solve two different problems without coupling them:

1. **transport** — how an agent reaches Quant Factory;
2. **research authority** — what an agent is allowed to do once connected.

Do not make SSH, MCP, REST, or a specific model vendor the domain architecture.
They are adapters around one stable gateway contract.

The preferred first implementation is:

- local CLI + Unix-domain-socket gateway for agents already on the OVH host;
- restricted SSH + the same CLI for Grok Bot or another remote agent;
- no new public QF TCP listener;
- MCP only as an optional later adapter if a client benefits from it;
- REST only as an optional later adapter if a non-shell integration requires it.

## Current external-agent assumptions

These are integration assumptions, not Quant Factory authority.

### Codex

Codex is already installed on the OVH host. It should call the gateway locally.
No network port is needed.

### Claude Code

Claude Code is already installed on the OVH host. It should call the same local
gateway. No network port is needed.

### Grok Bot

Current xAI documentation describes Grok Bot as running on a persistent hosted
cloud computer with browser, filesystem, and terminal access. Its browser
session can remain signed in after the owner completes login, CAPTCHA, passkey,
or 2FA. xAI also documents private-network access patterns for TCP services such
as SSH.

Relevant upstream references at design time:

- https://docs.x.ai/grok-bot/overview
- https://docs.x.ai/grok-bot/get-started
- https://docs.x.ai/grok-bot/private-networks
- https://docs.x.ai/grok-bot/approvals-security-and-privacy

Re-verify these capabilities before implementation because external product
behavior can change.

Grok's intended role is browser-heavy reconnaissance where authenticated site
interaction is useful, such as TradingView, Reddit, X, GitHub, papers, strategy
blogs, or other websites the owner is entitled to access.

Grok must not receive unrestricted administrative access to the OVH host merely
because it has a terminal.

## Non-goals

This project does not:

- make an LLM part of Quant Factory's core runtime;
- replace QF Candidate v1;
- replace QF Research Context v1;
- let agents edit Quant Factory source code through the research gateway;
- let agents write directly to the Quant Factory database;
- let agents access broker credentials;
- create paper or live trading authority;
- permit protected-data access unless separately authorized;
- permit paid-data acquisition;
- permit unlimited parameter search or automated curve fitting;
- permit an agent to declare a strategy qualified;
- let a remote agent bypass owner gates;
- require MCP;
- expose a new public web service by default.

## Architectural placement

The gateway must respect ADR 0014 and the enforced one-way dependency graph.

Preferred ownership:

```text
agent transport adapters
        |
        v
research gateway application service
        |
        +--> research_intake
        +--> orchestration
        +--> persistence
        +--> backtesting/validation result readers
        |
        v
existing Quant Factory components
```

The gateway is an outer adapter/application boundary. Existing core components
must not import the gateway.

If a new package is required, prefer a narrow name such as:

```text
agent_gateway/
    contracts.py
    service.py
    cli.py
    audit.py
```

Do not create a second orchestration engine. The gateway calls existing Quant
Factory services and contracts.

## Stable gateway contract

The first implementation should expose a provider-neutral CLI. Example command
shape:

```bash
qf-agent context get
qf-agent prior search --query "opening range breakout"
qf-agent candidate validate candidate.yaml
qf-agent candidate submit candidate.yaml
qf-agent candidate get <candidate-id>
qf-agent candidate list
qf-agent run request <candidate-id>
qf-agent run status <run-id>
qf-agent run results <run-id> --format json
qf-agent run evidence <run-id> --format json
qf-agent research note add --candidate <id> --file note.md
qf-agent lineage get <candidate-id>
```

Exact names may follow existing project naming, but the capability boundaries
must remain explicit.

All machine-facing output should support deterministic structured JSON. Human
text output may exist as a convenience.

## Research authority levels

The gateway must distinguish connectivity from authority.

### Level 0 — context/read

Allowed:

- retrieve QF Research Context;
- search prior research;
- list/get Candidates;
- inspect non-protected run summaries;
- inspect permitted evidence;
- inspect lineage and prior dispositions.

Not allowed:

- create durable Candidates;
- launch computation;
- change decisions.

### Level 1 — draft/intake

Adds:

- validate Candidate YAML;
- submit a draft QF Candidate;
- attach source references and research notes;
- request deduplication/prior-work analysis.

A submitted Candidate is not automatically approved for research.

### Level 2 — development research

Adds only when the applicable owner/Tier-1 gate authorizes it:

- request a development-stage test for an owner-approved Candidate;
- monitor the run;
- retrieve structured results;
- submit a new Candidate hypothesis based on evidence.

The gateway must enforce the same research gates as the dashboard/current
runtime. It must not create a parallel bypass.

### Level 3 — validation progression

Optional future authority only.

If later authorized, an agent may request permitted progression through existing
validation stages. Quant Factory remains the authority that decides whether a
stage is eligible.

### Never through this gateway

The agent research gateway must not provide:

- broker order submission;
- paper-order activation;
- live-order activation;
- capital allocation;
- credential retrieval;
- direct secret access;
- direct protected-test evidence access unless separately designed and
  explicitly authorized.

Paper/live remains a different security domain.

## Anti-overfitting rule

The gateway must not become an automated parameter optimizer disguised as an
agent loop.

The governing rule is:

> A failed test rejects the exact tested hypothesis/rules/search space. A
> materially changed idea becomes a new Candidate with explicit lineage and
> rationale.

An agent may reason from failure, but it may not silently mutate parameters and
rerun indefinitely.

Each materially changed hypothesis must preserve:

- parent Candidate/run identity;
- reason for change;
- evidence cited from the previous result;
- which rule changed;
- why the new hypothesis is materially different;
- what would falsify it;
- bounded parameter/search space.

Quant Factory should be able to reconstruct the research tree.

## Recommended agent roles

The gateway must remain neutral, but initial workflows may exploit different
agent strengths.

### Grok Bot — browser reconnaissance

Best suited for:

- authenticated TradingView research;
- Reddit discussions;
- X/social discovery;
- websites that require normal browser interaction;
- collecting source URLs, claims, scripts, public indicators, or hypotheses.

Expected flow:

```text
Grok browser research
      |
      v
restricted SSH
      |
      v
qf-agent CLI
      |
      v
QF Candidate / prior work / results
```

### Claude Code — hypothesis analysis

Potential uses:

- reading longer research material;
- comparing hypotheses;
- interpreting failure modes;
- drafting bounded Candidate variants;
- reasoning about falsification criteria.

It connects locally through the same gateway.

### Codex — implementation-aware research

Potential uses:

- examining Python packages/libraries;
- checking whether a proposed rule is implementable with existing QF
  capabilities;
- preparing adapter changes after separate implementation authorization;
- interacting with the same research contract.

Codex does not receive broader research authority merely because it can edit the
repository in a separate developer role.

## Host security model

### Accounts

Use separate identities for service ownership, remote research access, and
normal administration.

Recommended logical accounts:

| Identity | Purpose | Login | Sudo | QF source write | Secrets |
|---|---|---:|---:|---:|---:|
| `qf-gateway` | gateway service process | no interactive login | no | no | minimum runtime-only |
| `qf-research` | remote agent SSH identity | restricted | no | no | none |
| existing operator/developer identities | administration/development | existing policy | existing policy | as already authorized | existing policy |

Do not hard-code a numeric Linux UID in the public repository. At provisioning,
create the account with the host's normal UID allocation and record the actual
numeric UID only in private operational inventory if needed.

Suggested provisioning intent:

```text
qf-gateway:
  system/service account
  no password
  non-login shell
  owns gateway runtime files/socket only

qf-research:
  dedicated non-sudo account
  key-only SSH
  no password login
  no direct repository write access
  no DB file access
  no secrets
  only permitted to invoke the gateway wrapper
```

### Local gateway transport

Preferred local transport:

```text
/run/quant-factory/agent-gateway.sock
```

Suggested ownership model:

```text
owner: qf-gateway
group: qf-agent-access
mode: 0660
```

Only explicitly approved local users are members of `qf-agent-access`.

The gateway service should run under `qf-gateway` with a restricted systemd
unit.

### Remote Grok SSH

Do not give Grok a general-purpose shell account.

Use a dedicated SSH key for the Grok hosted computer and restrict the key in
`authorized_keys`.

Preferred pattern:

```text
restrict,command="/usr/local/bin/qf-agent-ssh-gateway" <public-key>
```

The forced-command wrapper should inspect `SSH_ORIGINAL_COMMAND` and allow only
the approved `qf-agent` command grammar.

Explicitly deny:

- shell escape;
- arbitrary command execution;
- sudo;
- SSH agent forwarding;
- X11 forwarding;
- TCP port forwarding;
- Unix socket forwarding unless specifically required;
- SCP/SFTP unless a later requirement proves it necessary.

Candidate YAML and research-note input should be accepted through stdin or a
gateway-owned upload mechanism rather than unrestricted filesystem transfer.

If direct SSH exposure is already part of the VPS's security posture, reuse the
existing hardened SSH endpoint. Do not open a second public port for the
gateway.

A future Tailscale/zero-trust path may replace direct SSH if that materially
improves the existing host posture, but it is not required for the first
implementation.

### Network exposure

Default:

- no new public QF TCP port;
- no public MCP listener;
- no public REST listener;
- local agents use Unix socket/CLI;
- remote Grok uses existing SSH transport.

If a future model can only use remote MCP/REST, add a separate reviewed adapter
behind authenticated private networking or a controlled tunnel. Do not change
the core gateway contract.

## Process isolation

The gateway service should use systemd hardening appropriate to its actual
needs. Evaluate at implementation time:

- `NoNewPrivileges=yes`;
- `PrivateTmp=yes`;
- `ProtectSystem=strict` where compatible;
- explicit `ReadWritePaths=` only for required runtime locations;
- restricted home access;
- capability bounding;
- memory/process limits;
- restart policy;
- dedicated environment file outside the repository if runtime configuration
  is required.

Do not add controls blindly if they break licensed VectorBT/runtime behavior;
prove the final sandbox against real gateway functions.

## Secret boundary

The gateway should normally need **no broker secret**.

If a research service needs an existing data credential, it should call the
existing approved QF service boundary rather than revealing the secret to the
agent.

Agent-visible commands must never return:

- Bitwarden access tokens;
- API keys;
- broker credentials;
- private SSH keys;
- database credentials;
- environment files containing secrets.

Secret values must be redacted from logs and structured errors.

## Database boundary

Agents do not receive direct SQLite/PostgreSQL access.

The gateway uses existing persistence services/repositories.

Do not grant `qf-research` filesystem permissions to the production database.

All writes must be semantic operations such as:

- submit Candidate;
- add research note;
- request permitted run;
- record agent attribution.

## Audit model

Every gateway request that can change durable state should record:

- request/event ID;
- timestamp;
- agent identity;
- transport identity;
- command/capability;
- Candidate/run IDs involved;
- authority level;
- accepted/rejected outcome;
- denial reason where applicable;
- parent lineage when creating a variant.

Do not log secret material or unrestricted browser content.

Recommended logical agent identities:

```text
codex-local
claude-local
grok-remote
```

These are audit identities, not authorization by themselves.

## Prompt-injection containment

Grok and other browser agents will intentionally consume untrusted web content.

Treat everything retrieved from TradingView, Reddit, X, blogs, GitHub, or other
sites as untrusted research input.

The gateway must not interpret external text as executable instructions.

An agent compromised by prompt injection should still be unable to:

- modify QF source;
- retrieve secrets;
- write directly to the DB;
- change Tier 1;
- enable paper/live;
- escape the allowed command set.

The security model must assume the research agent can behave incorrectly.

## Source provenance

A Candidate created by an agent should preserve source provenance sufficient to
audit where the idea came from.

At minimum:

- source URL or stable identifier;
- source type;
- title/author when available;
- retrieval timestamp;
- concise claim being relied on;
- agent that collected it.

Do not copy copyrighted source material unnecessarily. Store the hypothesis and
short evidence summary, not wholesale website contents.

## Multi-agent collision control

Two agents may research simultaneously, but they must not unknowingly duplicate
the same Candidate.

Before durable Candidate creation, the gateway should run the existing
prior-work/deduplication checks.

Use deterministic Candidate IDs and/or content identities already present in QF
where possible.

When equivalent submissions race:

- one becomes canonical;
- the other receives the existing Candidate identity and duplicate disposition;
- do not launch duplicate tests.

## Agent research loop

The target loop is:

```text
1. Read current QF Research Context
2. Search prior work
3. Research external sources
4. Form a bounded hypothesis
5. Produce QF Candidate v1
6. Validate and submit
7. Obtain required owner approval when applicable
8. Request permitted development test
9. Read structured result/evidence
10. Explain success/failure
11. Stop, or create a materially different child Candidate with lineage
```

The LLM does not directly modify the backtest implementation in order to
improve its result. Implementation changes follow the normal project authority
and code-review path.

## Proposed implementation milestones

These are design milestones inside this specification. They are **not active
project milestones** until `docs/MILESTONES.md` explicitly activates them.

## ARG-0 reuse inventory (completed 2026-10-02)

| Gateway capability | Existing Quant Factory owner | Reuse decision |
|---|---|---|
| Research context | `research_intake.qf_research_context` | Reuse `build_research_context` / deterministic export. |
| Candidate parsing, validation, import safety | `research_intake.qf_candidate` | Reuse unchanged QF Candidate v1 validation and import-status boundary. |
| Durable Candidate record | `PersistenceService.idea_drafts` | Reuse schema-v7 `idea_drafts`; deterministic gateway content ID supplies deduplication. |
| Saved setup and Candidate-to-configuration link | `PersistenceService` configuration and idea operations | Read existing link; gateway does not create implementations or configurations. |
| Durable run identity and at-most-once dispatch | `CandidateRunService` / `DurableResearchLaunchService` | Reuse existing claim and idempotency contract. |
| Candidate execution and validation sequence | `CandidatePipelineRuntime` plus injected Prefect launcher | Reuse the existing pipeline; no second orchestrator. |
| Run status/results | `PersistenceService` run and result repositories | Project only permitted non-protected structured fields. |
| Evidence validation | `ValidationEvidenceArtifactService` and persisted manifests | Reuse validated readers and fail closed for OOS/protected records. |
| Architecture enforcement | ADR 0014, `config/architecture.json`, `tools/check_architecture.py` | Add one outer component and retain zero/zero/zero. |

True gaps are limited to the provider-neutral request/response contract; a
deterministic prior-work query; removable gateway audit, note, and lineage
storage; deterministic Candidate collision handling; protected-safe result
projection; Unix-socket service/CLI; and the forced-command SSH adapter. No
core research engine, persistence migration, model integration, dashboard
dependency, or orchestration replacement is required.

### ARG-0 — Current-interface inventory

Goal: prove which existing QF services can be reused.

Tasks:

- inventory current QF Candidate, Research Context, prior-work, orchestration,
  result, evidence, and persistence interfaces;
- map each proposed gateway capability to an existing service;
- identify only genuine missing contracts;
- confirm ADR 0014 dependency direction;
- confirm no second orchestration engine is needed.

Acceptance:

- written reuse map;
- no implementation yet;
- explicit list of any true gaps.

### ARG-1 — Local read-only gateway

Goal: allow local Codex/Claude to inspect QF through a stable provider-neutral
interface.

Capabilities:

- context get;
- prior search;
- Candidate list/get;
- run status/results for permitted non-protected records;
- lineage read.

Implementation:

- thin application service;
- structured JSON contract;
- local CLI;
- Unix-domain socket or equally private local IPC;
- audit identity.

Acceptance:

- Codex and Claude can independently execute the read-only workflow without
  importing the dashboard or constructing the whole application;
- architecture checks remain 0 SCC / 0 cyclic edges / 0 forbidden directions;
- no public network listener exists.

### ARG-2 — Candidate intake and audit

Goal: enable agents to create durable draft Candidates without research
execution authority.

Capabilities:

- Candidate validate;
- Candidate submit;
- research-note/source provenance;
- deduplication;
- lineage creation.

Acceptance:

- identical Candidate submitted by two agents is deduplicated;
- every durable write records agent attribution;
- invalid Candidate fails closed;
- direct DB write is unnecessary;
- R13 Candidate contract remains canonical.

### ARG-3 — Restricted Grok SSH path

Goal: let Grok's hosted computer reach the same gateway without exposing a new
QF service port.

Implementation:

- `qf-research` account;
- dedicated SSH key;
- forced-command gateway wrapper;
- explicit command allowlist;
- no sudo;
- no repository/database/secret access;
- no port/X11/agent forwarding;
- audit identity `grok-remote`.

Acceptance:

- Grok can fetch context, search prior work, validate/submit a Candidate, and
  retrieve permitted results;
- arbitrary shell command attempt is rejected;
- file/database/secret access attempt is rejected;
- no new externally listening QF port exists.

### ARG-4 — Development-run request boundary

Goal: allow an authorized agent to request an existing QF development test
without bypassing owner/Candidate gates.

Implementation:

- run request;
- eligibility/authority check;
- existing orchestration path only;
- run status/results/evidence retrieval;
- idempotent duplicate request handling.

Acceptance:

- unapproved Candidate cannot launch;
- approved Candidate uses the existing durable pipeline;
- duplicate request cannot create duplicate execution;
- no protected stage is crossed;
- no paper/live authority exists.

### ARG-5 — Evidence-aware research lineage

Goal: support autonomous reasoning without automated blind optimization.

Implementation:

- parent Candidate/run references;
- structured failure/success summaries;
- child-Candidate rationale;
- material-change declaration;
- bounded search-space declaration;
- research tree retrieval.

Acceptance:

- agent can explain why a new Candidate differs;
- lineage is durable and auditable;
- repeated parameter tweaking without a new Candidate is rejected;
- failed tests do not incorrectly close the entire strategy family.

### ARG-6 — Multi-agent pilot

Goal: prove provider neutrality.

Pilot:

- Grok performs browser research and submits one bounded Candidate draft;
- Claude independently reviews the Candidate/reasoning through the gateway;
- Codex checks QF implementation/data feasibility;
- no agent is granted broader authority than required.

Acceptance:

- all three interact through the same gateway contract;
- no model-specific code exists in core QF;
- audit identifies each agent;
- conflicting/duplicate submissions are handled deterministically.

This milestone proves interoperability, not profitability.

### ARG-7 — Optional protocol adapters

Only build when a real client requires them.

Possible adapters:

- local stdio MCP;
- remote MCP over a private tunnel;
- REST/HTTPS;
- job queue.

Acceptance:

- adapter contains no domain authority;
- adapter calls the same gateway service;
- removal of the adapter does not affect Quant Factory research semantics.

## Testing requirements

Minimum automated coverage:

1. contract tests for every gateway operation;
2. permission tests by authority level;
3. invalid/unknown agent identity tests;
4. direct DB/source/secret access not required;
5. duplicate Candidate and duplicate run-request tests;
6. prompt-injection-style malicious input remains inert data;
7. redaction tests for errors/logs;
8. SSH forced-command allowlist tests;
9. local Unix-socket permission tests where practical;
10. architecture guard remains green;
11. existing Candidate and research pipeline tests remain green.

Target-environment proof is required for host security claims; CI alone does not
prove SSH/systemd/filesystem permissions.

## Operational acceptance checklist

Before declaring the gateway operational:

- [ ] current Tier 1 explicitly authorizes implementation;
- [ ] `qf-gateway` identity exists with correct ownership;
- [ ] `qf-research` identity exists with no sudo/password login;
- [ ] actual host UID/GID values recorded privately if operationally useful;
- [ ] gateway socket is not world-readable/writable;
- [ ] no new public QF listener exists;
- [ ] Grok key uses forced command and forwarding restrictions;
- [ ] local Codex path proven;
- [ ] local Claude path proven;
- [ ] remote Grok path proven;
- [ ] Candidate write audit proven;
- [ ] unapproved run denied;
- [ ] approved development run follows existing QF pipeline;
- [ ] paper/live functions absent;
- [ ] secret-redaction proof passes;
- [ ] architecture guard remains zero/zero/zero;
- [ ] rollback procedure tested.

## Rollback

The gateway must be removable without changing core research behavior.

Rollback should consist of:

1. stop/disable the gateway service;
2. remove remote SSH authorization;
3. remove local access-group memberships;
4. retain audit records and Candidates already accepted into QF;
5. leave existing QF Candidate/dashboard/research behavior functional.

No database migration should be required merely to disable agent access unless a
future separately approved feature proves otherwise.

## Implementation constraints for Codex/Claude

When this plan is activated:

- begin with ARG-0;
- inspect the actual repository before coding;
- reuse existing QF services;
- use Escalated Mode because this introduces a new service/security boundary;
- do not create a new orchestration engine;
- do not expose public MCP/REST simply for convenience;
- do not install a large agent framework unless an actual missing requirement
  cannot be met by the existing stack;
- do not change paper/live/broker authority;
- keep each slice independently testable;
- preserve ADR 0014 dependency direction;
- stop only for a genuinely new owner decision.

## Suggested owner authorization text

When Terry is ready to activate this project, an explicit instruction can be:

> I authorize implementation of the Quant Factory Agent Research Gateway using
> the provider-neutral plan in
> `docs/AGENT_RESEARCH_GATEWAY_PLAN.md`. Preserve the current roadmap and
> trading safety boundaries. Start with ARG-0 and continue autonomously through
> the authorized milestones using the local CLI/Unix-socket path for Codex and
> Claude and restricted SSH for Grok. Do not expose a new public QF port, add
> paper/live authority, access protected evidence, buy data, or expand secrets
> without a new owner decision.

That authorization should then be reflected in Tier 1 before implementation
proceeds.
