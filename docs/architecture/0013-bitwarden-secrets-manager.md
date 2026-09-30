# ADR 0013: Bitwarden Secrets Manager

- **Status:** Accepted
- **Date:** 2026-09-30
- **Authority:** Decision 312
- **Supersedes:** ADR 0012 and ADR 0010 as current credential architecture

## Context

Quant Factory needs reusable unattended access to provider and later broker
credentials on its VPS. Password Manager plus Agent Access was verified, but it
depends on an unlocked provider and approval lifecycle. The owner created a
Bitwarden Secrets Manager machine account named `Codex`, granted it to the
`Quant Factory` project, and selected that service as the project's standard
machine credential path.

## Decision

1. Bitwarden Secrets Manager is the durable machine-access source of truth.
2. `Codex` is the Quant Factory machine account and `Quant Factory` is its
   current project. Grants remain limited to required projects.
3. Use a pinned official `bws` CLI. Store its machine-account token outside the
   repository as a root-owned systemd encrypted credential; never as a dotenv
   file, shell-history entry, command argument, or long-lived shell export.
4. The root-owned `qf-bws` launcher decrypts the machine token directly into
   the child environment and executes `bws`. It never prints the token. The
   launcher permits ordinary `bws` subcommands and is not a named-secret
   authorization boundary.
5. Callers must enforce an exact unique secret name and pass its value only to
   the authorized child process. Unrestricted project output and secret values
   are not logs or evidence.
6. Long-running workers acquire credentials at service startup. Broker order
   handling never performs a Bitwarden network call.
7. Research, paper, and live remain distinct authority domains. Before paper or
   live activation, create and prove separate Secrets Manager project/grant and
   OS/service boundaries rather than treating the research grant as isolation.
8. Missing credentials, duplicate secret names, failed decryption, expired or
   revoked grants, CLI drift, and Bitwarden unavailability fail closed.

The VPS root boundary is trusted. Host-key encryption prevents casual or
unprivileged plaintext reads, but root—or an attacker with both the systemd
host key and encrypted credential—can decrypt the machine token. It is not a
substitute for host hardening or encrypted storage.

Password Manager, Agent Access, interactive `bw` sessions, repository or host
dotenv files, and another project's gateway are not substitutes for this
machine path. The installed Agent Access proof may remain as historical tooling
but is not a Quant Factory runtime dependency.

## Accepted host evidence

The VPS has verified official `bws` 2.1.0, a root-owned mode-`0600` encrypted
machine credential, a root-owned `/usr/local/bin/qf-bws` launcher, and private
`~/.config/bws/state` permissions (`0700` directories and `0600` files). The
launcher listed the exact `Quant Factory` project, retrieved the unique named
Databento secret without displaying it, and authenticated a free Databento
metadata request. The plaintext handoff was removed after encrypted-credential
verification. The superseded Agent Access listener was stopped and its cached
pairing/session state removed. Current runtime status and future work remain
authoritative only in [`docs/MILESTONES.md`](../MILESTONES.md).

## Operations

Use [`operations/bitwarden-secrets-manager.md`](../operations/bitwarden-secrets-manager.md)
for installation, rotation, verification, and service-use procedure.
