# Agent Research Gateway operations

This directory provisions the host identities and client side of ADR 0015.
Current authority and milestone status remain in Tier 1.

Provision from a reviewed release as root:

```bash
QF_GATEWAY_SOURCE_ROOT=/path/to/release \
QF_GATEWAY_PUBLIC_KEY='ssh-ed25519 AAAA... grok-qf' \
sh deployment/agent-gateway/provision.sh
```

Omit `QF_GATEWAY_PUBLIC_KEY` until the owner supplies the public key generated
on the Grok-hosted computer. The script never creates or accepts a remote
private key. It writes numeric host identities to the root-only
`/opt/quant-factory-gateway/identity.env`; source those values into the private
deployment environment before starting `agent-gateway`.

Provisioning grants the gateway container's separately configured UID only the
existing runtime GID needed by SQLite/artifact persistence. The remote
`qf-research` account is not a member of that runtime group and cannot read the
database or artifact tree. The mounted data-location map is group-readable but
remains non-writable; it contains paths and integrity policy, not credentials.

The service socket is `/run/quant-factory/agent-gateway.sock` and has mode
`0660`, owner `qf-gateway`, group `qf-agent-access`. Provisioning creates two
distinct bearer credentials and stores only their SHA-256 digests in the
server-side identity registry. Start each local program with its credential
path in the inherited environment; the agent can then bootstrap without
claiming its own identity:

```bash
QF_AGENT_CREDENTIAL_FILE=/opt/quant-factory-gateway/credentials/codex-local.token codex
QF_AGENT_CREDENTIAL_FILE=/opt/quant-factory-gateway/credentials/claude-local.token claude
qf-agent --pretty bootstrap
```

Both programs may run under the same Linux account. The bearer credential,
not the username, executable name, or a caller-supplied agent label, selects a
server-registered record containing `agent_id`, `provider`, `client`,
`transport`, and `authority_level`. Because the two programs share one OS
security principal, the credentials provide trustworthy gateway attribution,
not hostile isolation between those local programs. Strong mutual isolation
would require separate operating-system principals or sandboxes.

To add a future local client, provision a new random credential and add its
digest and provider-neutral metadata to the root-owned registry; Quant Factory
core logic does not change. A new transport still requires its own reviewed
adapter. See `docs/AGENT_RESEARCH_OPERATING_CONTEXT.md` for the common research
rules.

Remote SSH accepts only the documented `qf-agent` grammar. Candidate and note
payloads use stdin (`-`); SCP, SFTP, PTY, shell, forwarding, and arbitrary file
paths are denied.

Rollback uses `rollback.sh`. It stops the gateway container, empties the remote
authorized-key file, and removes the local user's access-group membership. It
deliberately retains gateway audit state and Candidates already accepted into
Quant Factory. Reprovisioning restores access without a QF schema migration.
