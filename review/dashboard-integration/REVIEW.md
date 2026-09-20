# Dashboard integration review package

Status: **review material only**. Nothing in this directory is merged,
deployed, operator-accepted, or evidence of profitability.

## Bottom line

The economical integration path is to keep the canonical Dash application and
reuse Plotly, VectorBT Pro outputs, and the existing persistence/evidence
services. The local R07 patch does that; it does not introduce a replacement
dashboard. Review should still remove any patch portion that is not necessary
to render the preserved R07 evidence truthfully.

The approved standalone preview remains useful as a visual contract, but its
HTML/CSS/JavaScript duplicate application responsibilities and should not
become a second product. The uncommitted component and asset drafts are
references with different contracts, not ready-made integrations.

## Status by item

| Item | Standalone | Integrated locally | Tested | Merged | Deployed | Accepted |
|---|---|---|---|---|---|---|
| Approved chart-first prototype | Yes | No | Historical preview evidence exists | No | Separate static preview only | Owner-approved design; implemented application not accepted |
| R07 patch `31cf941` | No | Yes, on a local branch | Focused/local evidence exists; no current browser proof | No | No | No |
| `results_workspace.py` draft | Yes | No | No integration proof | No | No | No |
| CSS/JS workspace draft | Yes | No | Standalone contract tests only | No | No | No |
| Canonical Results implementation on `main` | No | Yes | Repository checks passed | Yes | Current production revision is older | Milestone 23 acceptance pending |

“Tested” does not imply licensed-target proof, browser acceptance, deployment,
operator acceptance, or profitable behavior.

## What is reused

- Plotly Dash remains the application shell and routing framework.
- Plotly remains the chart renderer; no chart package is recreated.
- VectorBT Pro remains the research/portfolio engine. No licensed package code
  is included here.
- Existing run persistence, artifact integrity, evidence classification,
  ranking, Results view models, and trade-explorer components remain the data
  and UI boundaries.
- Canonical implementation lineage already on `main`: [`419aa0d`](https://github.com/RedstoneX/Quant-Factory/commit/419aa0d10b1c9bb961c376900120b4eb5661f453), [`49349ec`](https://github.com/RedstoneX/Quant-Factory/commit/49349ec095ff38d888a81e239d28e862b5f3b8db), and [`16c9756`](https://github.com/RedstoneX/Quant-Factory/commit/16c9756828823c83fbf39a486bd852f3e7d14269).

## Duplication and overlap

- The standalone prototype reimplements the page in static HTML/CSS/JS and
  requires a fixed evidence shape. It is a design reference, not application
  code.
- The standalone Python component overlaps canonical Results chart, report,
  and trade-link behavior.
- The workspace CSS/JS draft creates another resize/tab/control contract and
  has not been proved against the application callback lifecycle.
- The local R07 patch touches existing components rather than adding a second
  framework, but it spans 14 files and includes Compare behavior. Review should
  retain only behavior required for truthful R07 inspection or demonstrably
  reusable controlled-research operation.
- Historical local revision [`54c9dcb`](https://github.com/RedstoneX/Quant-Factory/commit/54c9dcb82aa9852e115af7cce6cf78b6fe0787ce)
  remains unmerged. It overlaps current Results work and retained a browser
  failure; it is evidence of prior work, not a merge candidate.

## Smallest integration path

1. Review the patch against base `44d85db` and the verified R07 rendering gaps.
2. Retain only the existing-stack changes needed to show 15/15 ranked rows,
   native 5-minute/index-point prices, USD fees/P&L, development/reference
   classification, and not-promotion-eligible status.
3. Run focused adapters/models/components tests and required repository checks.
4. Obtain current-revision browser proof before claiming browser readiness.
5. Merge only after review. Consider a backed-up private deployment as a
   separate owner-authorized slice; do not add portability, containers, or
   paper-execution infrastructure.
6. After this dashboard slice, return to proving the complete research-factory
   pipeline and closing beta blockers. Do not begin a broad edge search until
   the minimum research architecture and operator workflow are beta-ready.

## Smallest usable operator workflow

1. Find and select a saved research run.
2. Inspect its chart and linked entry and exit events.
3. Inspect its trades, costs, metrics, and complete ranked results.
4. Understand whether the run passed or screened out and what its evidence can
   and cannot establish.
5. Return to run history and reopen the same run without losing selection,
   review, or layout state.

That final state-preservation behavior is required, but it does not have
current-revision browser proof.

## Blockers and limits

- `31cf941` is unpushed, unmerged, and undeployed.
- There is no current-revision target browser proof.
- The deployed research runtime predates R07; R07 evidence is preserved
  externally and is not in production.
- Direct current container defaults and the full installed-version set were
  not verified.
- The old and standalone drafts use different data and interaction contracts.
- The Python component hardcodes a dollar price axis/hover format, which is
  wrong for MES index-point prices.
- No result here qualifies an edge, authorizes promotion, or supports paper or
  live trading.

## Economic review and estimate

Git records changes, not elapsed labor, so time already spent cannot be
measured from repository history. The patch size is measurable: 14 files,
581 insertions, and 66 deletions relative to base.

**Estimate, not measured:** for this dashboard integration only, if no new
defect appears, bounded review, removal of unnecessary overlap, required checks,
and merge should take about 1–3 development hours. A separately authorized
backed-up deployment and operator inspection would add about 1–3 hours.
Combined uncertainty range: **2–6 development hours**. This is not an estimate
for completing the research factory or reaching full beta. It excludes new
design, portability/container work, new research, and repairs uncovered by
browser or target validation.

## Package map

- [Source manifest](SOURCE_MANIFEST.md)
- [R07 sanitized facts](evidence/R07_FACTS.md)
- [Runtime and test evidence](evidence/RUNTIME_EVIDENCE.md)
- [Historical prototype browser report](evidence/PROTOTYPE_BROWSER_REPORT.md)
- [Synthetic preview reproduction](REPRODUCTION.md)
- [Public safety and omissions](PUBLIC_SAFETY.md)
- `patches/` — review patch for local commit `31cf941`
- `prototype/` — exact safe CSS/JavaScript references, sanitized derivatives, and a synthetic-data generator
- `drafts/` — clearly labelled uncommitted standalone references

## Canonical references

Do not duplicate these authorities; review them on `main`:

- [`docs/MILESTONES.md`](../../docs/MILESTONES.md)
- [`docs/dashboard-product-requirements.md`](../../docs/dashboard-product-requirements.md)
- [`docs/architecture/0008-dashboard-mounted-route-architecture.md`](../../docs/architecture/0008-dashboard-mounted-route-architecture.md)
- [`docs/QUANT_FACTORY_DASHBOARD_UI_DIRECTION.md`](../../docs/QUANT_FACTORY_DASHBOARD_UI_DIRECTION.md)
- [`docs/strategies/mes-opening-range-breakout.md`](../../docs/strategies/mes-opening-range-breakout.md)
- [`docs/assets/dashboard/approved/`](../../docs/assets/dashboard/approved/)
