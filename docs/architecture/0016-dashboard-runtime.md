# ADR 0016: Dashboard runtime

- **Status:** Accepted
- **Date:** 2026-10-09

## Decision

Quant Factory remains a Plotly Dash application over the existing backend,
persistence, evidence, lineage, and authority boundaries. The presentation
lives only under `dashboard.ui`; no parallel presentation composition root is
permitted.

Dashboard implementation and owner acceptance run directly, outside the
research Compose stack. Prefect and the agent gateway remain containerized
factory services. The private review Dashboard runs as a normal Linux service
at the established tailnet URL. Its process availability is operationally independent:
Dashboard failure may remove visibility and controls, but it must not stop or
change active filtration work. Paper trading remains a separate system with
its own stronger availability, reconciliation, and recovery requirements.

The production component responsibilities are:

- Dash Mantine Components: default navigation, layout, panels, drawers,
  modals, alerts, badges, and commodity controls;
- Dash Core Components: analytical state and controls when they are the
  appropriate Dash primitive;
- Dash AG Grid: dense sortable/filterable Candidate and run records; and
- Plotly plus VectorBT Pro: analytical charts and evidence.

The authoritative Dashboard contract is
`docs/assets/dashboard/current-visual-contract/dashboard.html`. The other six
workflow surfaces are controlled by
`docs/assets/workspaces/current-workflow-contract/workspaces.html`, while the
Dashboard contract supplies their shared modern visual language. Both checksums
are enforced by repository tooling. The workspace file's embedded older
Dashboard slide is excluded. No other mockup, preview, screenshot, historical
page, or external design source controls presentation.

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
- Callbacks are registered against real components. Hidden parallel component
  trees are prohibited.
- Loading, empty, stale, failed, unavailable, and inactive states are truthful
  and compact. Illustrative values from the visual contract are never runtime
  data.
- Every interactive-looking element performs its promised action or exact
  drill-down. Non-actions do not look interactive.

## Acceptance sequence

Dashboard proceeds in two gates. First, a local non-operational Mantine render
uses the reference's representative state solely to prove visual composition at
1440 by 980. It does not connect persistence, register production callbacks,
run backend work, or claim technical truth. Terry's approval of that real render
is required before the second gate may connect existing read-only projections
and working controls. The truthful implementation is connected to the external
canonical database through explicit read-only service configuration and
published to the private review URL. Unaided owner use is the next checkpoint.
Secondary interface and independent trader-workflow reviews follow that
walkthrough and precede merge. Dashboard is now accepted; later surfaces follow
the milestone queue and their repository-owned workspace contract one complete
surface at a time.

If Mantine presents a demonstrated compatibility or load blocker, work stops
for an owner decision before any fallback component strategy. A standalone
React application requires a separate owner decision.
