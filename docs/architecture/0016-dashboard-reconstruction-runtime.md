# ADR 0016: Dashboard reconstruction runtime

- **Status:** Accepted
- **Date:** 2026-10-09

## Decision

Quant Factory remains a Plotly Dash application over the existing backend,
persistence, evidence, lineage, and authority boundaries. The rejected
presentation is removed; it is not retained as a local legacy implementation.
The replacement presentation will live under `dashboard.ui`; removed
`dashboard.app`, `dashboard.application`, `dashboard.pages`,
`dashboard.components`, `dashboard.callbacks`, and `dashboard.assets` paths
are prohibited so the former implementation cannot become a scaffold again.

The production component responsibilities are:

- Dash Mantine Components: default navigation, layout, panels, drawers,
  modals, alerts, badges, and commodity controls;
- Dash Core Components: analytical state and controls when they are the
  appropriate Dash primitive;
- Dash AG Grid: dense sortable/filterable Candidate and run records; and
- Plotly plus VectorBT Pro: analytical charts and evidence.

The authoritative visual contract is only
`docs/assets/dashboard/current-visual-contract/quant-factory-reconciled-mockups.html`.
Its checksum is enforced by repository tooling. No other mockup, preview,
screenshot, historical page, or external design source controls presentation.

## Runtime invariants

- One persistent `dcc.Location` owns browser location state.
- Navigation changes require an explicit user action.
- Routes hydrate only the active surface and the minimum state required for
  stable selection; expensive inactive charts, tables, trades, and histories
  are not mounted or loaded.
- Shared state comes from the projection defined in
  `docs/factory-operating-contract.md`; pages do not redefine lifecycle,
  evidence, eligibility, or authority.
- Exact Candidate/run selection survives refresh and deep links when that
  identity still exists. Missing identities fail visibly and never substitute
  a fixture.
- Callbacks are registered against real components. Hidden legacy component
  trees are prohibited.
- Loading, empty, stale, failed, unavailable, and inactive states are truthful
  and compact. Illustrative values from the visual contract are never runtime
  data.
- Every interactive-looking element performs its promised action or exact
  drill-down. Non-actions do not look interactive.

## Acceptance sequence

Dashboard is the only first production slice. Its local real render uses an
identified read-only persisted-state snapshot, the default Mantine layer, and
the retained analytical stack. It must pass technical, controls, secondary
interface audit, actual/reference visual comparison, and independent
trader-workflow adversarial review before owner visual review. Only explicit
owner approval permits a private deployment. Unaided owner use of that deployed
Dashboard closes comprehension. No other surface begins before both owner
checkpoints.

If Mantine presents a demonstrated compatibility or load blocker, work stops
for an owner decision before any fallback component strategy. A standalone
React application requires a separate owner decision.
