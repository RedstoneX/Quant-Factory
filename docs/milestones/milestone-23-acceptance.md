# Milestone 23 Acceptance

> **Current sequencing (Decision 298):** Essential dashboard review and
> reconciliation are complete through Step 11. Step 12 is Terry's clickable
> direction review. Real saved-result connections, the complete browser
> workflow, final acceptance, and beta remain Steps 13–16. Never deploy merely
> to prove deployment.

Milestone 23 proves the complete equity research workflow before any strategy
can advance toward paper activation. Decision 287 narrowly permits controlled,
bounded research for an owner-approved, source-attributed hypothesis with
predeclared evidence boundaries before this milestone closes. It does not waive
this checklist or authorize open-ended optimization or data mining,
protected-test inspection, automatic promotion, paper orders, or live work.

Decision 279 supersedes Decision 277's acceptance for the former Results-page
experience. Decisions 280–281 establish the chart-first direction and validated
preview constraints. Decision 282 records hands-on owner approval of the
detailed selected-run Results specification and authorizes implementation.
Decision 293 fulfills Decision 282's bounded-design owner review for the
required Find & Compare surface and authorizes its first thin implementation
after the synthetic responsiveness/data-path check. The bounded design is
approved and the implementation/testing evidence merged through PR #74 at
`5db5784cea925f4484f06eb78de9aea5b8e4acf2`; deployment, target validation,
final owner acceptance, and the remaining objective evidence are still
required when this gate is explicitly resumed. They are not active follow-up
work. Any future expansion beyond this accepted surface requires new owner
review and is outside this criterion.

Decision 291 authorizes only the verified R07 selected-run inspection blocker
correction and supersedes Decision 287's good-enough/frozen treatment only for
that defect. The correction reuses the existing application and must fail
closed for missing interval, unit and protected-data facts. It merged through
PR #70 at `4eaa03c761ffc4e90c4d1cf909c5f62d11bc614f` after focused,
portable real-browser, independent-review, and required-CI evidence passed.
That evidence does not establish licensed-target proof, deployment, the
scalable multi-run surface, complete beta, Milestone 23 closure, or renewed
owner acceptance.

Decision 283 separately requires safe caching for exact repeat research
computations while preserving distinct durable run tickets and preventing
cache reuse from masquerading as independent evidence. Its architecture,
storage, eviction, implementation sequence and explicit Reproduce policy still
require a bounded design. This record does not infer that caching is implemented
or add an unreviewed cache design as a Milestone 23 acceptance criterion.

## Required scenario matrix

| Area | Required evidence |
|---|---|
| Shell and routing | Direct links, refresh, back/forward, sidebar and home navigation, active state, unknown route, and no renderer errors |
| Launch and monitoring | Approved saved configuration launches once, status is visible, refresh preserves identity, and inactive pages cannot mutate state |
| Results | The selected-run truthful price chart is primary; separate Bars (`1m`/`5m`/`15m`/`1D`) and View (`Full run`/`1D`/`1W`/`1M`) controls preserve the immutable backtest period and exact trade events; persisted entry/exit markers map to containing bars and link to the grouped trade ledger; equity, drawdown, benchmark, assumptions, lineage, review, and validation outcomes remain reachable and render only from persisted evidence |
| Run analysis, compare and reproduce | Hundreds or thousands of persisted runs can be aggregated, sliced, ranked, filtered and selected by maximum drawdown, total return, profitable-trade measures and other useful evidence dimensions; one run opens in Results, multiple selected runs can feed Compare; compatible runs compare; a reproduced run retains parent/configuration identity and creates a distinct run record |
| Review | Human decision and rationale persist durably and conflicts fail before mutation |
| Failure and recovery | Controlled failure, retry, timeout, cancellation, stale recovery, restart, missing artifact, and corrupt lineage are understandable and fail closed |
| Responsive operation | Desktop exposes three resettable chart/report resize edges while Metrics and Trades grow in normal page flow without nested vertical scrolling and retain comfortable bottom breathing room; tablet and mobile stack chart then report; every size preserves navigation, hierarchy, selected state, visibly larger and readable trade typography, and complete operator actions |

The successful integrated proof uses the real SPYM VectorBT Pro fixture.
Deterministic synthetic fixtures remain appropriate for failure and recovery
scenarios. No scenario may fabricate metrics, reconstruct missing evidence, or
weaken protected-data boundaries.

If computation-cache work is sequenced into Milestone 23 after bounded design,
its evidence must prove exact input isolation, protected-data partitioning,
artifact integrity, fail-closed rejection of failed/partial/corrupt/unknown
work, durable lifecycle preservation for each explicit request, and no
inflation of independent evidence counts. Until then, the existing no-cache
research-computation behavior is not misrepresented as a completed cache.

## Acceptance checklist

- [x] The detailed responsive chart-first selected-run Results specification
      is explicitly approved under Decision 282.
- [ ] The approved selected-run Results specification is implemented within
      ADR 0008.
      A bounded Decision 291 slice now implements truthful R07 five-minute
      rendering, linked MES trades, complete ranked rejection rows, evidence
      limits and an exact-run reopen link; the full criterion remains open.
- [x] A bounded design is reviewed for the required scalable multi-run
      aggregation, slicing, ranking, filtering and selection surface; one run
      opens in Results and multiple selected runs can feed Compare.
      Decision 293 fulfills this review for the bounded Find & Compare surface;
      its implementation/testing evidence merged through PR #74. Deployment,
      target validation and final owner acceptance remain pending.
- [ ] Bars and View controls remain distinct; truthful aggregation produces the
      expected persisted-fixture counts and preserves exact trade-event
      timestamps and prices while markers map to containing bars.
- [ ] Desktop chart/report edges resize and reset without losing selected state;
      Metrics and Trades have no nested vertical scrolling, the page retains
      comfortable bottom breathing room, and responsive layouts stack chart
      then report.
- [ ] Trade typography is visibly larger and more readable without hiding
      required evidence or causing page-level horizontal overflow; the validated
      preview's two-CSS-pixel increase is evidence, not a fixed acceptance value.
- [ ] Focused and complete relevant automated tests pass.
- [ ] Browser lifecycle checks pass for every registered route.
- [ ] The operator completes launch → monitor → inspect → compare → reproduce →
      review without Python, terminal, raw JSON/CSV, or SQLite.
- [ ] Failures explain impact and the next safe action.
- [ ] Documentation and `dashboard/project_status.py` agree.
- [ ] The project owner explicitly accepts the implemented replacement
      Results-page experience after the detailed-design, browser, and workflow
      evidence is available.
- [ ] The Milestone 23 gate result is recorded after every remaining objective
      criterion passes or fails.

### Decision 291 bounded Results evidence — 2026-09-20

- The bounded correction merged through PR #70 at
  `4eaa03c761ffc4e90c4d1cf909c5f62d11bc614f`. Focused tests, portable
  real-browser evidence, independent review, and required CI passed.

- Focused portable tests cover native/coarser interval handling, fail-closed
  unknown interval and protected-data state, MES index-point versus USD units,
  all ranked rows and rejection reasons, distinct recorded engine annualization
  and coverage-derived calendar CAGR, exact saved-run links and stale trade
  isolation.
- The existing real-browser Results acceptance fixture was reshaped to a
  disposable synthetic R07-like screening run. It proves normal history
  selection, exact-link open, refresh and back/forward identity, native 5-minute
  charting, linked trades, ranked rejection evidence, responsive layout and
  clean browser diagnostics for this source revision.
- This is portable synthetic browser evidence. It is not licensed-target,
  deployed-production, preserved-private-artifact, renewed operator-acceptance,
  complete-workflow, full-beta, or Milestone 23 gate evidence.

### Decision 293 merged Find & Compare evidence — 2026-09-20

- The synthetic server check handled 1,000 rows in 0.152 seconds (~438KB).
- The implementation merged through PR #74 at
  `5db5784cea925f4484f06eb78de9aea5b8e4acf2`; required checks passed.
- It reuses Compare with a full-history grid, one Results action for one
  selected saved test, 2–4 Compare selection, labelled top-ranked metric basis,
  interval/return/drawdown/win rate/Sharpe/trades, quick search/counts, reset,
  and native state persistence.
- Lead validation passed 25 selected unit/dashboard tests and one real-browser
  test. The 1,000-row browser page was ready in about 1.2 seconds with no
  horizontal overflow at 1440px.
- Profit Factor is not persisted and was intentionally not invented; later
  engine-level consideration is not a current blocker.
- Standard trader-facing labels merged through PR #77 at
  `9495a36a45af2bfe1288ab7cba840a4eed8ef54e`. The owner reviewed the image as
  good and intuitive.
- Deployment, target validation, final owner acceptance, and beta completion
  remain pending. Decision 298 resumed only the factory-to-beta sequence. The
  image review does not establish the full workflow or Milestone 23 acceptance.

### Decision 298 Steps 10–11 evidence — 2026-09-21

- The existing essential surfaces were retained: Setup; Run History inside
  Results; Find & Compare; Results; Evidence inside Results; and System. No new
  route, dashboard framework, charting package, or duplicate backend was added.
- PR #83 merged at `e8fa5f33613c8355e26d9ea3bef8aebd178de7bf` after 44 focused
  checks, three targeted real-browser lifecycle checks, one licensed VectorBT
  reconstruction check, and every required GitHub check passed.
- The change corrected Decision 298 status text and old checks that still
  expected pre-approved behavior. It did not implement Steps 13–16, deploy the
  application, prove a trading edge, or establish owner acceptance.

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

If an actual deployment, explicit Milestone 23 closure, or owner request later
activates target proof, the retained procedure is to freeze the applicable
public revision and build a disposable OVH candidate/test runner using the
existing authorized private VectorBT Pro build input. Mount the hash-matched
SPYM data read-only and use fresh isolated state. First run
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
