# Paper Worker and Read-Only Observer

> **Historical implementation / do not deploy:** Paper-runtime work is dormant.
> The existing worker and `deployment/paper` stack use the superseded ADR 0010
> transport and are retained only as implementation evidence. Their safety
> requirements remain inputs, but a new ADR 0013-compatible credential and
> isolation design must be reviewed before a paper milestone can activate any
> worker.

## Security boundary

The retained design required an independently deployable, paper-only worker
with separate identity, fixed paper endpoint, credentials, state, network
policy, journal, and audit evidence. Any replacement must prevent research
processes from calling the broker or mutating worker state directly.

The first planned capability was a read-only observer permitting only the
declared paper account and positions GET operations. A replacement must not
submit, replace, cancel, or list orders, and its health output must contain only
sanitized state.

## Required configuration

- dedicated paper account label: `Dedicated Paper Account`
- external runtime root: `QF_STATE_ROOT`, for example
  `/srv/quant-factory/state/paper-observer`
- fixed HTTPS paper origin and public certificate verification
- expected account binding supplied through protected metadata
- orders disabled by construction

No credential value, account identifier, response body, or private gateway
coordinate belongs in Git, logs, health output, or evidence artifacts.

Future paper credentials remain in a separately scoped Bitwarden Secrets
Manager project. Paper use requires a distinct project grant, machine/service
identity, and OS privilege boundary that prevents the research client from
querying paper or live secrets. The current research project grant cannot
establish paper or live isolation. A worker loads its credentials at service
startup; order handling never queries Bitwarden.

## Acceptance

Before authenticated deployment, prove:

1. exact allow rules and catch-all denial;
2. missing, wrong, expired, and revoked identity fail closed;
3. account ownership and endpoint binding are verified without exposing values;
4. a protected journal precedes each gateway mutation;
5. crash recovery is idempotent at every mutation boundary;
6. foreign paths/resources are never adopted or deleted;
7. restart preserves policy while revoked identities remain rejected;
8. ordered audit evidence correlates every allowed and denied request;
9. bounded leak scans find no credential or account value;
10. the observer still has no order path.

These checks do not activate paper execution. Order activation additionally
requires a qualified edge, the applicable research/operator gates recorded in
MILESTONES, broker-neutral submission/reconciliation proof, duplicate
prevention, restart safety, capacity controls, and explicit milestone/owner
authorization. Formal Milestone 23 closure is not independently inferred as a
paper prerequisite when current MILESTONES defines a narrower applicable gate.
