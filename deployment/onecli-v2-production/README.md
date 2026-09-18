# OneCLI v2.4 production deployment mechanism

This directory prepares a credentialless, reviewable deployment of the
official OneCLI services. It does not create an administrator, actor, grant,
policy, secret, broker connection, or order path.

## Boundaries

The stack contains PostgreSQL, one-shot migrations, API, web, and gateway. It
has no host port, public ingress, bind mount, Docker socket, or host filesystem
access. The control network is internal. Only the gateway joins control, the
external paper-read actor network, and bounded egress. The paper observer joins
only the actor network and has no direct egress.

External volumes and networks require exact ownership labels. They must be
fresh for this deployment and must never name, mount, or copy from another
project. Validators reject topology drift, host ports, foreign endpoints,
unexpected environment values, weak or reused secrets, symlinks, permissive
input modes, partial resource sets, and insufficient memory.

## Inputs and validation

Copy `runtime.env.example` and `secrets.env.example` below `QF_DEPLOY_ROOT`,
outside the checkout, and set mode `0600`. Public example paths are:

```text
/srv/quant-factory/deploy/onecli/runtime.env
/srv/quant-factory/deploy/onecli/secrets.env
```

Generate every secret independently and redirect it directly into the
protected file. Never put values in a terminal argument, transcript,
repository, report, or operator message.

Run preflight, provision only fresh owned resources, run preflight again, and
then render/start with the same exact files. Stop if migrations or health
checks fail. After startup, `verify-runtime.sh` checks image identity,
environment placement, user, capabilities, volumes, networks, routes, health,
resource limits, and absence of published ports without registry access.

## Authenticated observer boundary

`execution/paper_observer_bootstrap.py` defines the later fail-closed
transaction. It has no transport, Docker, subprocess, OneCLI, or broker client.
A separately reviewed adapter creates exact account/positions GET allows plus
a catch-all block for the `Dedicated Paper Account`, stages the restricted
capability and CA, proves policy across restart, performs one observation,
revokes identity, verifies correlated audit records, and removes only journal-
owned resources.

The controller never accepts credential values or deletes operator-imported
secret records. Crash recovery is inode- and journal-bound; foreign resources
are preserved and rejected. Public evidence omits account, actor, secret,
capability, balance, symbol, and raw-response values. A pass still reports
deployment readiness false and orders disabled.
