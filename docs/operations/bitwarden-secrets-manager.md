# Bitwarden Secrets Manager Runbook

> This runbook implements Decision 312 and ADR 0013. Current phase and next
> action remain authoritative only in [`docs/MILESTONES.md`](../MILESTONES.md).

## Standard identity and boundary

- machine account: `Codex`
- project: `Quant Factory`
- CLI: pinned official `/usr/local/bin/bws`
- launcher: root-owned `/usr/local/bin/qf-bws`
- encrypted machine token:
  `/etc/credstore.encrypted/qf-bws-codex-token.cred`
- CLI authentication state: `/home/ubuntu/.config/bws/state`, with directories
  mode `0700` and regular files mode `0600`

The token and secret values never belong in Git, chat, shell history, command
arguments, dotenv files, logs, artifacts, or dashboard output. `qf-bws`
decrypts the token into the environment of one short-lived `bws` process.
It is a general project-scoped CLI wrapper, not a named-secret enforcement
boundary; every caller must check that its exact key resolves once.
The VPS root boundary is trusted: systemd host-key encryption blocks ordinary
plaintext file reads but does not protect against root or loss of both the host
key and encrypted credential.

The verified host installation uses official `bws` 2.1.0 for Linux x86_64.
The release archive SHA-256 is
`ba8233c3a4aee5d43e3c73bbd04d99e9bc5aba13bbbfd06d89b073abe732b860`.
Do not replace it with an unpinned latest release; verify the release asset and
`bws --version` before changing `/usr/local/bin/bws`.

## Initial token installation or rotation

Create or rotate a machine-account token in Bitwarden, then enter it privately
on the VPS without echo or a plaintext staging file:

```bash
umask 077
QF_CRED_TMP="$(mktemp)"
trap 'rm -f "$QF_CRED_TMP"' EXIT
read -rsp 'Bitwarden machine token: ' QF_BWS_TOKEN; echo
printf '%s' "$QF_BWS_TOKEN" | sudo systemd-creds encrypt \
  --with-key=host --name=qf-bws-codex-token - - >"$QF_CRED_TMP"
unset QF_BWS_TOKEN
sudo install -d -o root -g root -m 0700 /etc/credstore.encrypted
sudo install -o root -g root -m 0600 "$QF_CRED_TMP" \
  /etc/credstore.encrypted/qf-bws-codex-token.cred
rm -f "$QF_CRED_TMP"
trap - EXIT
```

Revoke the prior token after the replacement verifies. Never paste a token into
a command argument or save it in a shell profile.

## Verification

Verify the launcher and exact project without returning secret values:

```bash
qf-bws project list --output json \
  | jq -e '.[] | select(.name == "Quant Factory") | .id' >/dev/null
test -z "$(find /home/ubuntu/.config/bws -type d ! -perm 0700 -print -quit)"
test -z "$(find /home/ubuntu/.config/bws -type f ! -perm 0600 -print -quit)"
```

For a required secret, require exactly one matching key before use. Do not
print `.value`, use table output for secrets, or enable shell tracing. A free
provider metadata/authentication call may prove a credential; paid data still
requires the bounded experiment and owner cost authority.

## Runtime use

Interactive research commands may retrieve one named secret immediately before
launch and pass it only in the reviewed child environment. A future systemd
worker must use `LoadCredentialEncrypted=` for the machine token, fetch only its
authorized runtime secrets during service startup, and retain them in process
memory. Never query Bitwarden synchronously while creating, submitting,
replacing, or cancelling an order.

Research access does not establish paper or live isolation. Those domains need
separate Bitwarden projects/grants, machine or service identities, OS
privileges, endpoints, and the applicable Tier 1 activation authority.

## Failure and recovery

Missing or duplicate named secrets, failed systemd decryption, non-root
encrypted-credential ownership, credential mode other than `0600`, nonprivate
`~/.config/bws` state, revoked/expired grants, CLI version drift, project
mismatch, or Bitwarden unavailability fail closed.
Rotate the token in Bitwarden, replace the encrypted credential, verify the
exact project and one harmless provider call, then revoke the old token.
