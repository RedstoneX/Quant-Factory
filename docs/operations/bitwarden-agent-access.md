# Historical Bitwarden Agent Access Runbook

> **Superseded by Decision 312 and ADR 0013. Do not use Agent Access as the
> Quant Factory machine credential path.** Current procedure is
> [`bitwarden-secrets-manager.md`](bitwarden-secrets-manager.md); current status
> remains in [`docs/MILESTONES.md`](../MILESTONES.md).

## Authority and boundary

The dedicated owner-controlled Quant Factory Bitwarden Password Manager vault
is the credential source of truth. Official Bitwarden Agent Access (`aac`) is
the standard access path for approved Quant Factory commands.

The intended flow is:

```text
owner-controlled Bitwarden provider with an unlocked Quant Factory vault
  -> encrypted Agent Access pairing and cached session
  -> pinned `aac` client on the Quant Factory host
  -> exact item-ID and field mapping
  -> reviewed child process for the current invocation
```

The provider retains the Bitwarden login and `BW_SESSION`. For each approved
query, the remote client transiently receives the selected full credential
record in process memory; `aac run` then injects only mapped fields into the
child environment. Agent Access does not synchronize the vault to VPS storage,
but the client and its operator are a vault-reading trust boundary. Never print,
return as JSON, log, persist, or place a credential value in a command argument.

## Installation and state

Use the official Bitwarden Agent Access project and a pinned release. Record the
release version, source URL, checksum or signature evidence, install path, and
verification result without recording a secret. Do not silently track a moving
latest release.

Before the first Agent Access command:

```bash
umask 077
install -d -m 0700 "$HOME/.access-protocol"
```

After installation, pairing, reconnect, upgrade, and restart, verify that
`~/.access-protocol` is owned by the service user with mode `0700` and that its
regular files are mode `0600`. The state includes cached session and
pre-shared-key material required for reusable pairing. Stop on symlinks, foreign
ownership, group/world access, unexpected files, or permission drift. Do not
copy that state or put item bindings or Agent Access state in the repository.

## Private pairing

Pair only with the owner-controlled trusted provider serving the dedicated
Quant Factory vault. The pairing token, pre-shared key, provider coordinates,
session material, and vault output are secrets. Agent Access may persist the
pre-shared key and session material only in its protected state. Exchange
pairing material in the private channel supported by Agent Access, never through
chat, source control, shell history, tickets, screenshots, or durable evidence.

Confirm the provider and client fingerprints out of band. Cache only the
intended Quant Factory pairing. A cached pairing is reusable access state; it is
not proof that the provider is currently running, unlocked, or approving
requests.

## Exact credential selection

Store the exact Bitwarden item ID and field name in mode-`0600` configuration
outside Git. Item IDs are non-secret identifiers and may be visible in process
arguments; keeping them external prevents repository coupling, not disclosure.
Prefer an item ID over a domain lookup to avoid an ambiguous match. This selects
the intended record but does not restrict what the pairing can query.

For example, a reviewed wrapper may invoke the equivalent of:

```bash
umask 077
aac run --id "$QF_DATABENTO_ITEM_ID" \
  --env DATABENTO_API_KEY=password \
  -- /absolute/path/to/fixed-reviewed-command
```

The item ID is illustrative configuration, not repository content. A reviewed
wrapper should use a fixed executable and allowed arguments, reject extras, and
avoid debug tracing. This reduces mistakes but is not a security boundary for
an operator who can invoke `aac` directly. The child must not echo its
environment or include the credential in exception messages.

Do not use `aac connect --output json` or another value-returning mode for a
real credential. Do not export a credential into the long-lived shell.

## Preflight and evidence

Prove the path first with a synthetic item and harmless fixed command. Verify:

- pinned client identity and private state permissions;
- exact item and field mapping;
- successful child-process injection without stdout/stderr reflection;
- denial for a locked or unavailable provider, invalid pairing, wrong item,
  wrong field, and unsafe permissions;
- reconnect behavior after client and provider restart;
- revocation, rotation, and re-pair recovery;
- bounded scans of output, logs, process arguments, Git status, and generated
  artifacts for secret reflection.

Evidence records only the client version, non-secret pairing/session identity,
permission result, integration name, command identity, timestamp, outcome, and
redacted error class. It must not record an item title if that title is private,
an item value, account identity, provider coordinate, token, or response body.

## Availability and approval behavior

The trusted provider must be running with the Quant Factory vault unlocked.
Agent Access may require approval for a new credential query. Any auto-approval
window is provider memory, is time-bounded, and may be lost on provider restart.
Cached pairing state does not override those conditions. Correlate the displayed
query before approving. On a requester timeout, do not retry until the stale
prompt has been explicitly denied/cleared or the provider has restarted; a late
approval can transmit a credential after the original requester stopped waiting
and desynchronize subsequent requests in affected preview releases.

Treat a provider restart, vault lock, expired approval window, revoked session,
or relay loss/endpoint drift as a normal fail-closed condition. Pin the approved
relay endpoint in private external configuration and record only its approved
identity in evidence. The public relay can observe availability and traffic
metadata even though protocol encryption protects credential contents. Do not
replace the standard with a dotenv file, a copied secret, an interactive `bw`
session, or a different project's credential system to work around availability.

## Rotation, revocation, and separation

Rotate the value in the Quant Factory Bitwarden item, then repeat the bounded
injection and leak checks. Revoke a pairing or provider grant when the host,
provider, or operator session is no longer trusted. Delete only state whose
exact ownership has been established; preserve redacted audit evidence.

Research, paper, and live use remain separate authority domains. Agent Access
does not impose per-item scope on a pairing, so a general research pairing must
not be represented as paper/live isolation. Before paper or live activation,
prove a separate provider identity, vault-access and OS privilege boundary,
service identity, and state that prevent the research client from querying
those items. Paper and live access still require their Tier 1 activation gates
and explicit owner authority.

## Decision 310 Databento use

The first real use is narrowly bounded to the existing Quant Factory Databento
item and the fixed free `MES.c.0` symbology preflight. Confirm the estimator or
endpoint is free before the request. Stop before any paid data acquisition.
After the mapping preflight, follow `docs/MILESTONES.md` for the single accepted
screen and its owner-required stop gate.
