# Milestone 23 Acceptance

Milestone 23 proves the complete equity research workflow before strategy
discovery. Automated evidence supports the decision; only explicit operator
acceptance closes the gate.

## Required scenario matrix

| Area | Required evidence |
|---|---|
| Shell and routing | Direct links, refresh, back/forward, sidebar and home navigation, active state, unknown route, and no renderer errors |
| Launch and monitoring | Approved saved configuration launches once, status is visible, refresh preserves identity, and inactive pages cannot mutate state |
| Results | Equity, drawdown, benchmark, signals, trades, assumptions, lineage, and validation outcomes render from persisted evidence |
| Compare and reproduce | Compatible runs compare; a reproduced run retains parent/configuration identity and creates a distinct run record |
| Review | Human decision and rationale persist durably and conflicts fail before mutation |
| Failure and recovery | Controlled failure, retry, timeout, cancellation, stale recovery, restart, missing artifact, and corrupt lineage are understandable and fail closed |
| Responsive operation | Desktop, tablet, and mobile preserve navigation, hierarchy, selected state, and complete operator actions |

The successful integrated proof uses the real SPYM VectorBT Pro fixture.
Deterministic synthetic fixtures remain appropriate for failure and recovery
scenarios. No scenario may fabricate metrics, reconstruct missing evidence, or
weaken protected-data boundaries.

## Acceptance checklist

- [ ] The approved page specification is implemented within ADR 0008.
- [ ] Focused and complete relevant automated tests pass.
- [ ] Browser lifecycle checks pass for every registered route.
- [ ] The operator completes launch → monitor → inspect → compare → reproduce →
      review without Python, terminal, raw JSON/CSV, or SQLite.
- [ ] Failures explain impact and the next safe action.
- [ ] Documentation and `dashboard/project_status.py` agree.
- [ ] The project owner explicitly records pass or fail.

## Incident history

This section is append-only in the public repository. Private coordinates,
identifiers, evidence hashes, and recovery locations remain in the private
archive.

<!-- incident-history:start -->

### 2026-09-02 — Revival baseline reconciliation

Impact: historical notes understated implemented dashboard and workflow
capabilities while an earlier test snapshot still contained failures. The
project re-inspected current code, preserved existing behavior, repaired only
reproduced defects, and retained Milestone 23 as pending operator acceptance.

### 2026-09-03 — Routing and runtime evidence separated from acceptance

Impact: automated routing, recovery, and deployment checks could have been
mistaken for product acceptance. Documentation now separates code presence,
test evidence, runtime reachability, deployment revision, and explicit operator
acceptance. ADR 0008 browser lifecycle remains mandatory.

### 2026-09-17 — Dashboard-first sequence restored

Impact: execution preparation had begun to outrank the operator-facing product.
Decision 274 restored dashboard/operator acceptance as priority 1, retained
completed paper preparation, and deferred activation until a defensible edge
and every execution gate pass.

### 2026-09-18 — Public repository sanitization

Impact: publishing the private repository directly would have exposed private
operational history. Decision 275 selected a clean-history public snapshot,
retaining only generalized incident continuity here and preserving the full
record in a private read-only archive.

<!-- incident-history:end -->
