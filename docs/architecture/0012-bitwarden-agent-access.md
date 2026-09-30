# ADR 0012: Bitwarden Agent Access

- **Status:** Accepted
- **Date:** 2026-09-30
- **Authority:** Decision 311
- **Supersedes:** ADR 0010 as current Quant Factory credential architecture

## Context

Quant Factory already has a dedicated, owner-controlled Bitwarden Password
Manager vault containing its provider, broker, and service credentials. Earlier
documentation incorrectly excluded that vault from project architecture and
selected a separate credential gateway. The project needs repeatable agent
access to narrowly selected existing vault items without copying values into
Git, host dotenv files, prompts, logs, or artifacts.

Bitwarden Agent Access is Bitwarden's official agent-oriented access protocol
and CLI. It can pair a remote client with an owner-controlled trusted credential
provider, cache pairing state, select a Password Manager item, and inject a
chosen item field into a reviewed child-process environment with `aac run`.

## Decision

1. The dedicated Quant Factory Bitwarden Password Manager vault is the durable
   credential source of truth.
2. Official Bitwarden Agent Access (`aac`) is the standard agent access path.
   The provider remains owner-controlled and authenticated to that vault.
3. Each invocation selects the exact approved item ID where available and maps
   only the required field into the environment of a reviewed command using
   `aac run`. This is safe-use policy, not an Agent Access authorization
   boundary: `aac` accepts arbitrary child commands and a pairing can query any
   item visible to the trusted provider when the provider approves.
4. Agent Access state and item bindings stay outside Git. Initialize its state
   under `umask 077`, require the state directory to be mode `0700` and regular
   files to be mode `0600`, and verify those modes before credential use.
5. Pin and verify the upstream `aac` release. Agent Access is early-preview
   software; upgrades require source/version verification and focused
   regression proof before use.
6. Pin the approved relay endpoint in private external configuration. Protocol
   encryption protects credential contents, not relay availability or traffic
   metadata; endpoint drift and relay loss must fail closed.
7. Research, paper, and live use remain separate authority domains. A general
   research pairing is not technical isolation for paper or live credentials;
   those phases require a separately proven provider/vault-access boundary.
8. Fail closed if the provider is unavailable or locked, the pairing is
   invalid, the exact item or field is absent, file permissions are unsafe, or
   the approved relay identity is unavailable.

The following are not substitutes for this architecture:

- an interactive `bw` session used as a persistent runtime;
- a repository or host dotenv file containing credential values;
- unrestricted or JSON-formatted vault output;
- migration to Bitwarden Secrets Manager without a separate owner decision;
- a credential gateway belonging to another project.

## Secret-handling boundary

Never expose or persist the Bitwarden master password, `BW_SESSION`, pairing
token, credential value, unrestricted item output, or response body containing
private account data. `BW_SESSION` may exist only inside the trusted provider
process. Agent Access necessarily persists cached session and pre-shared-key
material in its private state; that material must not exist anywhere else.
Pairing and item selection occur in a private owner session, not chat or
repository content.

The client transiently receives the selected full credential record in process
memory before `aac run` maps requested fields to the child environment. It does
not synchronize the vault to disk, but this makes the client and its operator a
vault-reading trust boundary. Do not use an output mode that returns the real
credential to the calling agent. Logs and durable evidence may record only
redacted status, selected integration identity, version, permission checks,
timestamps, and success/failure classes.

## Persistence boundary

Cached pairing state avoids rebuilding access for every call, but does not make
the trusted provider continuously available. The provider must be running and
the Bitwarden vault must be unlocked. Provider-side approval may be cached only
for its configured in-memory window and can be lost on provider restart. No
unattended or reboot-persistent claim is valid until the deployed provider
lifecycle, reconnect behavior, and denial behavior have been proven.

## Acceptance evidence

Before a real Quant Factory credential is used, the integration must prove:

1. pinned client identity and checksum/source verification;
2. private state directory and file modes after pairing and restart;
3. successful cached reconnect without exposing tokens or item values;
4. exact item-ID and field selection through one harmless reviewed command,
   while acknowledging that the pairing and CLI are not scoped to them;
5. denial when the provider is locked/unavailable, the item or field is wrong,
   permissions drift, or the relay identity drifts;
6. bounded scans showing no secret in output, logs, Git, process arguments, or
   generated artifacts;
7. rotation, revocation, and re-pair recovery;
8. timeout recovery that clears or denies a stale provider prompt before retry;
9. a synthetic credential proof before the first real credential request.

For Decision 310, the first real use is limited to injecting the existing
Databento item into the fixed free symbology preflight. It does not authorize a
paid data request, strategy change, paper/live activation, order, or capital
exposure.

## Consequences

Existing obsolete gateway code and deployment proofs may remain as clearly
labelled historical evidence, but they must not be deployed or cited as current
credential authority. Current procedure is documented in
[`docs/operations/bitwarden-agent-access.md`](../operations/bitwarden-agent-access.md).
Current implementation status and next action remain solely in
[`docs/MILESTONES.md`](../MILESTONES.md).
