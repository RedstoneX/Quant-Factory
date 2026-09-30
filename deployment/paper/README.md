# Historical Paper Observer Deployment

> **HISTORICAL / SUPERSEDED — DO NOT DEPLOY.** This stack uses the ADR 0010
> credential transport replaced by Decision 311 and ADR 0012.

The Dockerfile, Compose file, and sample configuration remain only as evidence
of the dormant read-only paper observer implementation. They are not current
Quant Factory deployment authority and must not be connected to real
credentials. Before paper activation, replace and independently review the
credential/provider, vault-access, OS privilege, network, recovery, and audit
boundaries under ADR 0012 and the then-current Tier 1 gate.

See [`docs/operations/paper-worker.md`](../../docs/operations/paper-worker.md)
for retained requirements and [`docs/MILESTONES.md`](../../docs/MILESTONES.md)
for current status.
