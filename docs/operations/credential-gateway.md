# Credential Gateway Runbook

> **Deferred under Decision 294:** Credential-gateway runtime work is not the
> current research queue. Use this procedure when an approved authenticated
> integration or qualified paper candidate requires it; all isolation and
> fail-closed requirements remain authoritative.

## Boundary

OneCLI is the selected first credential gateway, subject to ADR 0010. This
runbook never accepts raw secret values. Use only public templates, restricted
identities, fixed destinations and operations, and value-free evidence.

Required flow:

```text
restricted actor or placeholder
  -> explicit gateway policy and credential injection
  -> approved destination and operation
```

The agent must not receive, print, reconstruct, log, or persist the underlying
credential. Denied destinations, paths, methods, missing identity, stale
attestation, and revoked identity must fail closed and remain auditable.

## Safe proof order

1. Use harmless synthetic credentials and an adversarial local fixture.
2. Verify exact allow and catch-all denial behavior for HTTP and CONNECT.
3. Verify administration is inaccessible to the restricted actor.
4. Verify restart persistence and ordered allow/deny audit records.
5. Scan bounded output, logs, state, and artifacts for secret reflection.
6. Remove temporary identities, grants, policies, and proof state.
7. Introduce a dedicated paper credential only through an operator-controlled
   private session after account ownership and all prior checks pass.

Paper and live credentials are separate. Withdrawal permission is prohibited.
A successful authentication request does not prove general isolation, adopt a
gateway deployment, activate a worker, or authorize an order.

## Configuration

Use external files below `QF_DEPLOY_ROOT` and `QF_STATE_ROOT`; for example:

- `/srv/quant-factory/deploy/gateway/runtime.env`
- `/srv/quant-factory/deploy/gateway/secrets.env`
- `/srv/quant-factory/state/gateway`

Files containing credentials stay outside Git with restrictive ownership and
permissions. Evidence records names, policy identities, status classes, and
timestamps only; never values, account identifiers, or response bodies.
