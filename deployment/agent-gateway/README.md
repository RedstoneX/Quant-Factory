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
database or artifact tree.

The service socket is `/run/quant-factory/agent-gateway.sock` and has mode
`0660`, owner `qf-gateway`, group `qf-agent-access`. Local examples:

```bash
qf-agent --agent codex-local context get
qf-agent --agent claude-local candidate list
```

Remote SSH accepts only the documented `qf-agent` grammar. Candidate and note
payloads use stdin (`-`); SCP, SFTP, PTY, shell, forwarding, and arbitrary file
paths are denied.

Rollback uses `rollback.sh`. It stops the gateway container, empties the remote
authorized-key file, and removes the local user's access-group membership. It
deliberately retains gateway audit state and Candidates already accepted into
Quant Factory. Reprovisioning restores access without a QF schema migration.
