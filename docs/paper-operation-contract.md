# External paper-system handoff contract

**Status: future integration; not activated.** Current phase and authority are
defined only in `docs/MILESTONES.md` and `docs/DECISIONS.md`.

Quant Factory ends at an immutable handoff package and an external destination
link. It does not run an Alpaca worker, store paper credentials, maintain a
paper-order journal, reconcile broker state, display paper P&L, or provide
paper-order controls.

The paper-trading system is a separate project and operating domain. It may
reuse suitable QAMC implementation patterns or code after its own review, but
its runtime, database, credentials, deployment, monitoring, dashboard, and
availability are never Quant Factory dependencies.

## Quant Factory responsibility

After a paper lane is separately authorized, Quant Factory may create a
`qf.paper-handoff.v1` manifest using `execution/paper_handoff.py`. The package
contains only:

- handoff, Candidate, strategy/version, and source-run identities;
- evidence-bundle and executable-package references plus SHA-256 digests;
- execution-vehicle and instrument identities;
- the deterministic eligibility decision and passed-gate identities;
- paper-lane and paper-risk-policy identities;
- source revision and UTC creation time.

The package contains no code bytes, account identifier, credential, endpoint,
broker session, order, position, or P&L. Creating it is not admission,
deployment, or trading authority. The Dashboard may show package/handoff status
and one external link to the paper system—nothing more.

## External paper-system responsibility

The separate paper project owns Alpaca connectivity, credentials, admission,
signal execution, risk controls, idempotency, order/fill journals,
reconciliation, recovery, monitoring, P&L, and its operator dashboard. It must
independently verify the handoff schema, identities, checksums, lineage,
eligibility, policy authority, executable compatibility, market support,
capacity, duplicate deployment, and risk limits before accepting a package.

No OpenRouter or other LLM holds order authority. AI may analyze evidence and
raise alerts outside the deterministic order path.

Paper-to-live remains a separate owner decision and security domain. No
Quant Factory implementation, fixture, page render, or agent statement proves
paper readiness or authorizes an order.
