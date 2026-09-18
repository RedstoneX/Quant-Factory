# Isolated OneCLI v2.4 configuration proof

This directory defines a fresh synthetic OneCLI stack for ADR 0010 testing. It
is not an upgrade procedure, does not attach existing state, and does not
authorize real credential use, broker access, orders, or agent activation.

The stack contains PostgreSQL, one-shot migrations, API, web, and gateway. It
publishes no host ports. Control and actor networks are internal; only the
gateway joins both. No runner, Docker socket, external data, or existing volume
is attached.

Create a mode-`0600` environment file outside the checkout, for example:

```bash
deployment/onecli-v2/preflight.sh \
  /srv/quant-factory/deploy/onecli-proof/onecli-v2.env
```

Use only synthetic values and a fresh unique project. The preflight inspects
the rendered services without starting them and emits only a fixed safe
summary. Stop if an existing project, volume, container, or network could be
adopted.

The proof requires exact destination/path/method allow rules, an independent
catch-all block, missing-identity denial, restart persistence, ordered audit
evidence, full cleanup, and bounded reflection scans. A successful health
check, login, or synthetic request is not ADR 0010 acceptance.

Rollback means stopping the unique proof project while retaining its fresh
volumes for review. Delete only resources whose exact owned identities were
recorded. Never use an existing state volume as a rollback target.
