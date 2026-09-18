# Milestone 23 Acceptance

Milestone 23 proves the complete equity research workflow before strategy
discovery. Decision 277 records explicit owner acceptance for the current
dashboard/operator experience. That acceptance does not replace the remaining
objective evidence or itself close the gate.

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
- [x] The project owner explicitly accepts the current dashboard/operator
      experience under Decision 277.
- [ ] The Milestone 23 gate result is recorded after every remaining objective
      criterion passes or fails.

## Target-evidence audit — 2026-09-18

This read-only audit distinguishes historical licensed-target evidence from
proof of the current public source. It does not accept Milestone 23 or replace
the unchecked criteria above.

- Both running research services on the documented OVH target were healthy and
  exposed VectorBT Pro 2026.4.7 on CPython 3.12.14. The public CI and local
  portable environments do not contain VectorBT Pro; their green results prove
  portability only, not licensed-engine behavior.
- The target SPYM parquet contained 53,528 rows and 944,659 bytes. Its SHA-256,
  `0fac9de8cb97568c7ee5ae00532277d960c316989ccd65296c394f0dfa44a5ab`,
  matched the committed SPYM manifest exactly.
- The latest inspected successful SPYM record was created on 2026-09-03 from
  historical source revision
  `79721a67f712c2b440aaeabcb57e7738f1c9fe08`. It recorded VectorBT Pro
  2026.4.7, and all seven expected persisted artifacts were present and passed
  checksum validation: dataset manifest, equity curve, metrics, parameter
  results, run summary, trades and orders, and validation evidence.
- At the audit, canonical public `main` was
  `fc36677a456e408c8d85e1c06a551118db5028f2`. The historical target revision
  is not an object in the sanitized public repository, so the historical run
  cannot establish behavior for current `main` or for later workflow merges.
- Target health and the Backtest Results route both returned HTTP 200. This
  establishes reachability only. It does not prove current-source SPYM
  execution, persisted dashboard behavior, browser lifecycle, or the complete
  operator workflow.
- The deployed runtime and host did not provide a current licensed pytest and
  Playwright/browser runner, and no current-revision browser evidence was
  found. The existing integrated SPYM test proves real VectorBT execution,
  persisted artifacts, reproduction, review, and dashboard service callbacks
  when run in a licensed environment; the browser suite adds the required
  real-browser evidence. Neither was rerun during this read-only audit.

The smallest future target proof is to wait for the applicable workflow pull
requests to merge, freeze the resulting public revision, and build a disposable
OVH candidate/test runner from that revision using the existing authorized
private VectorBT Pro build input. Mount the hash-matched SPYM data read-only and
use fresh isolated state. First run
`tests/test_milestone21c_spym_fixture.py::test_spym_saved_configuration_launches_vectorbt_and_persists_lineage`
and
`tests/test_milestone23_acceptance.py::test_milestone23_successful_spym_workflow_compare_reproduce_and_review`.
Then run the complete `tests/browser/` selection with Playwright and a browser
installed, require zero skips, and retain JUnit and browser diagnostics. This
disposable proof must not mutate the production runtime; any later production
update remains a separate backed-up, validated deployment slice.

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
