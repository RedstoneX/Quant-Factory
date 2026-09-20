# ADR 0010: Agent Credential Gateway

- **Status:** Accepted
- **Date:** 2026-07-28

## Context

Quant Factory needs to let bounded agents call approved APIs without exposing
the underlying credentials. Personal password-manager vaults are unrelated to
the project and must not become agent-access dependencies.

The evaluated open-source options were OneCLI, Agent Vault, Infisical, and a custom Bitwarden SDK integration.

## Decision

1. **OneCLI is the selected first credential gateway for evaluation and initial implementation.**
2. Agent Vault was recorded as a fallback candidate, but that pursuit is superseded as current work. OneCLI remains selected; replacing it requires separate explicit owner instruction. Current work and ordering are maintained in MILESTONES.
3. Infisical is deferred because its broader secrets-management platform is unnecessary for the initial single-operator system.
4. A custom password-manager SDK integration is rejected for the initial implementation because Quant Factory would need to build and maintain the missing gateway, policy, and audit layers. Personal vaults are not part of the project architecture.
5. This decision supersedes Decision 31 and related Bitwarden-first wording in earlier project documentation.

## Required proof of concept

Before OneCLI is adopted beyond evaluation, it must demonstrate that:

- a bounded Codex agent can call a harmless test API without receiving the real credential;
- the agent cannot print, retrieve, or reconstruct the underlying secret;
- credentials can be restricted by agent, destination host, and path or operation where supported;
- denied destinations fail closed;
- requests and denials are auditable;
- configuration survives a controlled restart;
- secrets do not appear in prompts, process output, logs, GitHub, or generated artifacts.

## Operating boundaries

- Begin with harmless test credentials, then paper-trading credentials only.
- Paper and live credentials remain separate.
- Withdrawal permissions are never granted to the trading system.
- Live credentials are not introduced until credential isolation, deterministic risk controls, and independent supervision pass acceptance.
- Agents receive only the minimum approved capability and never unrestricted credential-vault access.

Decision 269 retains OneCLI and requires separate explicit instruction before
replacement or resumed Agent Vault evaluation. The failed fresh-local proof
is evidence against its tested configuration, not proof about another
deployment. The blocked fallback investigation remains historical evidence.

Decision 271 (2026-09-03) creates a narrow sequencing exception: the owner
explicitly authorizes the one-shot operator-controlled fixed Alpaca paper
account GET through existing OneCLI before general gateway proof or upgrade.
The gateway retains underlying keys; only redacted authentication/account
metadata may be reported. This exception authorizes no orders, live access,
account reuse, worker activation, or general gateway adoption. The proof
criteria above remain required for adoption; the diagnostic cannot satisfy
or waive them. Follow the runbook for the bounded procedure and MILESTONES
for its outcome.

## Version and deployment boundary

The 1.45.0 isolated proof and current upstream are different evidence. Public
source for v2.4.0 rejects missing identity for HTTP and CONNECT and removes
unauthenticated self-hosted admin sessions; the proxy regression test already
exists in v2.0.0. Its default-deny policy still excludes uncredentialed traffic,
while explicit catch-all `BLOCK` rules can independently cover uncredentialed
traffic. Source support does not prove that a complete destination boundary is
configured or working at runtime, including secret-response filtering.
Supported version/configuration and deployment isolation should be assessed
before introducing a maintained vendor fork. A v1-to-v2 migration
changes login, database schema and service topology; it requires private
legacy-account adoption and backup/restore planning. See the
[upstream review and source links](../operations/credential-gateway.md#upstream-source-review-and-upgrade-boundary)
for exact revisions and limitations.

## Consequences

- General gateway adoption requires the proof above; the one-shot operator
  authentication exception is limited to Decision 271.
- Prefer supported upstream configuration and releases when they satisfy the
  boundary; source review alone does not establish target acceptance.
- A replacement gateway requires separate explicit owner instruction.
- Personal password managers are not the Quant Factory agent credential manager.
