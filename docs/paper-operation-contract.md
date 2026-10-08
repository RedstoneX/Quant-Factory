# Quant Factory Paper operation contract

**Status: FUTURE BUILD / NOT ACTIVATED.** Current phase and authority remain in
[`MILESTONES.md`](MILESTONES.md). Decision 341 authorizes only the dormant
handoff seam and inactive Dashboard destination described here.

## Product relationship

Quant Factory Research finds and validates an edge. Quant Factory Paper then
operates a qualified strategy against Alpaca Paper and measures forward
behavior. They are two isolated operating domains of the same product, not one
privileged process and not an environment toggle.

QAMC remains a separate project. A later implementation may inspect and adapt
its proven Alpaca connectivity, charts, order ledger, reconciliation, or
operational patterns after a bounded reuse review. Quant Factory must own the
adapted code and its tests. It must not depend on a running QAMC service, read
or write QAMC databases, share credentials or deployment identity, or report
QAMC observations as Quant Factory evidence.

## Narrow data flow

```text
qualified survivor + execution-vehicle decision
  -> deterministic eligibility decision under an activated paper-lane policy
  -> immutable qf.paper-handoff.v1 manifest
  -> isolated paper admission checks
  -> Alpaca Paper worker, journal and reconciliation
  -> read-only paper status projection
  -> Quant Factory Paper dashboard
```

Research never emits orders and never receives paper credentials. Paper never
rewrites research evidence. A read-only status projection may return package,
deployment, health, and forward-evidence identities; it may not provide an
order channel back through the Research dashboard.

## Handoff package

The implemented seam in `execution/paper_handoff.py` carries only:

- handoff, Candidate, strategy/version and source-run identity;
- evidence-bundle and executable-strategy-package references plus SHA-256
  digests;
- execution-vehicle and instrument identity;
- deterministic eligibility decision and passed-gate identities;
- activated paper-lane policy and paper-risk-policy identity;
- source revision and UTC creation time.

The package carries no code bytes, account identifier, credential, endpoint,
broker session, order, position or P&L. Package creation is not admission,
deployment or trading authority.

## Future admission and operation

After Terry explicitly activates a bounded paper lane, the paper admission
service must independently and fail-closed verify:

1. schema, identity, checksums, lineage and immutable artifact availability;
2. current lane-policy identity and non-revoked authority;
3. every predeclared evidence/eligibility gate and the execution-vehicle
   decision;
4. current Alpaca support for the requested asset and order semantics;
5. executable package compatibility, data freshness and market schedule;
6. capacity, duplicate deployment, exposure and paper-risk limits;
7. isolated paper account, endpoint, credential grant, journal and deployment
   binding; and
8. recovery, reconciliation, pause and kill-switch readiness.

An ordinary survivor that passes all gates may be admitted automatically. A
missing or ambiguous value, unsupported vehicle, duplicate, exhausted capacity,
policy expansion, or integrity mismatch stops admission. Paper-to-live remains
an explicit owner decision and a different security domain.

The operating loop is deterministic code: signal evaluation, risk checks,
idempotent order intent, Alpaca adapter, journal, broker observation,
reconciliation and state transition. No OpenRouter or other LLM is required or
permitted to hold execution authority. AI may analyze evidence and alert the
owner outside the order path.

## Dashboard boundary

The Research Dashboard has one contextual **Paper trading** link and no paper
P&L. The Paper dashboard owns:

- active/paused/retired paper deployments and their package identity;
- broker-observed realized and unrealized P&L, equity and drawdown;
- positions, orders, fills, rejections and missed/expired signals;
- model-to-broker reconciliation and execution deviation;
- data, worker, broker and credential-health observations without secret
  values; and
- risk state, automatic pauses, recovery state and audit timeline.

Historical backtest returns and paper results remain visibly distinct. Before
activation the Paper destination states **Not active**, reads no broker state,
and exposes no controls that can submit an order.

## Future proof gates

Later implementation is not complete until each gate is proved separately:

- package/admission contract tests and incompatible-package rejection;
- isolated Alpaca Paper account, endpoint and credential identity;
- idempotency, duplicate prevention and ambiguous-submission recovery;
- broker snapshots, order/fill lifecycle and model-to-broker reconciliation;
- stale data, mismatch, repeated rejection, risk breach and kill-switch faults;
- paper Dashboard correctness and working read-only controls;
- visual conformance and performance with representative deployments; and
- Terry's unaided comprehension and separate activation approval.

None of those later proofs is supplied by the dormant seam, existing fixtures,
QAMC behavior, a page render, or an agent statement that the system looks good.
