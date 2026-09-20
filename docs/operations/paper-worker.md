# Paper Worker and Read-Only Observer

> **Deferred under Decision 294:** Paper-runtime work is dormant until a
> qualified edge and the existing paper gates activate it. The procedure and
> safety requirements below remain authoritative when that occurs.

## Security boundary

The paper worker is independently deployable and paper-only. It has separate
identity, fixed paper endpoint, credentials, state, network policy, journal,
and audit evidence. Research processes cannot call the broker or mutate worker
state directly.

The first deployed capability is a read-only observer permitting only the
declared paper account and positions GET operations. It cannot submit, replace,
cancel, or list orders. Health output contains only sanitized state.

## Required configuration

- dedicated paper account label: `Dedicated Paper Account`
- external runtime root: `QF_STATE_ROOT`, for example
  `/srv/quant-factory/state/paper-observer`
- fixed HTTPS paper origin and public certificate verification
- expected account binding supplied through protected metadata
- orders disabled by construction

No credential value, account identifier, response body, or private gateway
coordinate belongs in Git, logs, health output, or evidence artifacts.

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
requires Milestone 23 acceptance, a Milestone 25-qualified edge, broker-neutral
submission/reconciliation proof, duplicate prevention, restart safety,
capacity controls, and explicit milestone authorization.
