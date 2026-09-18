# Quant Factory Dashboard UI Direction

## Purpose

Preserve the agreed visual and usability direction for the Quant Factory dashboard so future implementation does not depend on chat history.

This document governs the Milestone 23C dashboard presentation direction. ADR
0008 governs the permanent dashboard architecture. This document does not
authorize backend changes, framework migration, deployment, paper execution,
promotion, or Milestone 24 work.

## Framework Decision

Quant Factory remains a Plotly Dash application.

The polished examples shown on Plotly's public Dash site demonstrate that Dash can support a substantially stronger interface, but they are not untreated default styling. Their quality comes from deliberate layout, component selection, CSS, charts, controls, and information architecture.

Reference:

- https://plotly.com/dash/

The project should improve the existing Dash application rather than replace it.

## Product Direction

Quant Factory should read as a trading research and validation product, not as a stack of administrative forms.

Operator-facing screens use product concepts first:

- strategy;
- experiment;
- backtest;
- configuration;
- validation result.

Internal run IDs, artifact IDs, configuration hashes, recovery controls, and diagnostics remain available only as secondary traceability and maintenance metadata.

Research and forward-testing interfaces are visualization-led. Their primary information hierarchy is:

1. strategy, instrument, timeframe, test period, and validation result
2. Key performance metrics
3. equity and portfolio value
4. drawdown
5. completed trades, trade P&L, wins, and losses
6. validation evidence
7. configuration and execution assumptions
8. raw technical metadata, recovery tools, and operator events

Technical detail must remain available, but should be visually secondary.

## Approved Dashboard Information Architecture

The approved visible navigation is:

- **Strategy Research:** Market Data, Strategy Review, Backtest Results, Compare Backtests.
- **Paper Trading:** Paper Trading Overview, Strategy Monitor.
- **System:** System Status, Data Sources.
- **Settings:** bottom utility link.

The Home route remains available through the Quant Factory brand link and is the
workspace entry point.

## Public concept mockups

The public-safe concept mockups are under `docs/assets/dashboard/approved/`.
Every image is labelled **CONCEPT MOCKUP — SYNTHETIC DATA** and uses the
fictional **Demo Operator** identity:

1. `01_research_data_catalog.png` — Research Data Catalog.
2. `02_research_experiment_overview.png` — Research Experiment Overview.
3. `03_research_backtest_detail.png` — Research Backtest Detail.
4. `04_research_compare_experiments.png` — Research Comparisons.
5. `05_paper_strategy_fleet_overview.png` — Paper Strategy Fleet Overview.
6. `06_paper_strategy_detail.png` — Paper Strategy Detail.
7. `07_system_infrastructure_overview.png` — System Infrastructure Overview.

The mockups define visual direction and information architecture. Their
synthetic values are not implemented functionality, operational evidence, or
account data.

## Visual References

### Traders Casa

Reference:

- https://traderscasa.com/

Use for:

- unified light visual system
- restrained colors
- clean modern cards
- portfolio-value presentation
- compact summary metrics
- visible wins and losses
- readable entry and exit markers
- consistent spacing and hierarchy

### TradeZella

Reference:

- https://www.tradezella.com/

Use for:

- results-first analytical hierarchy
- trading metrics and summary cards
- chart prominence
- strategy and performance reporting
- drawdown and risk visibility
- trade review presentation
- progressive disclosure of deeper analysis

### Plotly Dash examples

Reference:

- https://plotly.com/dash/

Use for:

- compact application layout
- readable controls
- sliders and range sliders
- tabs
- charts
- data grids
- responsive information density
- clear separation between controls and results

Do not copy branding or proprietary layouts exactly.

## Control Guidelines

Use sliders only for bounded numeric controls where visual adjustment is useful, such as:

- entry threshold
- exit threshold
- rolling window
- stop-loss percentage
- take-profit percentage
- risk allocation
- slippage assumptions
- commission sensitivity
- bounded parameter ranges

Do not use sliders for:

- configuration IDs
- hashes
- timestamps
- exact identifiers
- categorical execution policies
- raw technical metadata
- values requiring precise free-form entry

Use dropdowns, toggles, text inputs, read-only fields, or tables where those controls are more appropriate.

## 23C Baseline Reset

Milestone 23C is re-baselined around the controlled ADR 0008 dashboard
architecture refactor before additional feature implementation. Prior partial
visual work remains useful implementation evidence, but it is not a current
browser-acceptance pass.

Required architecture baseline:

- modular Plotly Dash application;
- one persistent `dcc.Location`;
- permanent application shell and sidebar;
- permanent mounted route containers containing the real page components needed
  by registered callbacks;
- pathname-driven route-container visibility and active navigation state;
- page-owned callbacks;
- reusable components;
- no dynamic `page-content.children` routing as the active routing mechanism.

Browser-lifecycle acceptance remains pending and must cover direct deep links,
manual refresh, back/forward navigation, sidebar navigation, brand/Home
navigation, unknown routes, selected/active navigation state, page identity
after page-local callbacks mount, and absence of Dash renderer
missing-component errors.

The target Backtest Results presentation remains:

- evidence-backed default selected backtest;
- trader-facing terminology centered on strategy, backtest, configuration and
  strategy checks;
- chart-led backtest presentation;
- compact KPI strip;
- equity curve;
- cumulative trade P&L with completed-trade markers;
- drawdown with visible points and maximum-drawdown emphasis;
- trade-return distribution and win/loss summary;
- responsive Recent Trades grid;
- responsive Ranked Parameter Combinations grid;
- Selected backtest summary with technical IDs visually secondary;
- Strategy Checks, Trading Assumptions, Research History, Strategy Settings and
  Technical Details tabs.

Dedicated implementations remain pending for:

- Market Data/Data Catalog;
- Strategy Review/Experiment Overview;
- Backtest Results/Backtest Detail;
- Compare Backtests/Comparisons;
- Paper Trading Overview;
- Strategy Monitor;
- System Status;
- Data Sources;
- Settings.

Strategy Review is the approved research review concept. Legacy review routes
are not acceptance targets under the re-baselined Milestone 23 gate.

## Pending Dedicated Page Implementations

Pending pages should follow the approved mockup direction without copying sample data:

- Market Data/Data Catalog;
- Strategy Review/Experiment Overview;
- Compare Backtests/Comparisons;
- Paper Trading Overview;
- Strategy Monitor;
- System Status;
- Data Sources.

Paper Trading pages remain dependent on real strategy deployment, capital allocation, positions, orders, fills, P&L, reconciliation, and health data. Milestone 23C does not implement Paper Trading execution or broker integration.

## Data Integrity and Empty States

Dashboard visuals use persisted Quant Factory evidence exposed through existing service and adapter boundaries.

Rules:

- fixture-only evidence remains clearly identified;
- unsupported metrics and series are not fabricated;
- missing artifacts produce intentional empty states;
- unavailable KPI fields keep the compact metric layout and show an unavailable value;
- raw files, JSON, CSV, SQLite, and terminal output are implementation details rather than operator workflow.

## Architecture Preservation

ADR 0008 requires:

- route containers mounted once with real callback-owned components present;
- pathname-driven route visibility;
- no dynamic `page-content.children` replacement;
- direct deep links, manual Refresh and back/forward navigation to preserve
  route identity;
- page-owned callbacks that do not write URL or navigation state;
- expensive or mutating inactive-page callbacks gated against unintended work;
- existing service, persistence, evidence, orchestration, provider, and security boundaries.

## Responsive Data Presentation

Target grid behavior:

- centered grid headers and cells;
- responsive column profiles;
- wrapped headers;
- sensible minimum widths;
- horizontal scrolling at narrow widths rather than crushed columns;
- readable Recent Trades and Ranked Parameter Combinations grids.

## Recovery UX Finding

The stale-run recovery control is functional.

The visible timestamp was a placeholder, not an entered value. After an explicit ISO-8601 UTC timestamp was entered, the callback accepted it and returned:

`No stale fixture runs matched the supplied cutoff.`

Recovery is an advanced maintenance function. It should:

- remain available
- explain that it only affects stale `created` or `running` fixture runs
- require an explicit UTC cutoff
- avoid making placeholder text look like an entered value
- be collapsed or placed under Operations/Diagnostics

## Implementation Boundary

Preserve:

- existing workflows
- component IDs wherever practical
- callbacks
- services
- persistence
- orchestration
- acceptance evidence
- light mode only
- current functional behavior

Allowed:

- bounded Runs-page Python layout changes
- CSS refinement
- section reordering
- tabs or progressive disclosure
- moving existing charts and metrics
- compacting history and comparison
- improving control selection
- improving visual hierarchy

Not allowed:

- backend behavior changes
- service changes
- persistence changes
- orchestration changes
- framework migration
- dashboard rewrite
- unrelated page redesign
- deployment work
- paper or live execution
- Milestone 24 work
- commit or push before browser acceptance

## Resource Policy

Use resources in this order:

1. ChatGPT for planning, review, documentation, Git inspection, and bounded repository work
2. Direct WSL commands for inspection, documentation, tests, and small safe edits
3. Codex only for irreducible local implementation, coordinated dashboard layout changes, runtime debugging, or other work too complex for a safe bounded WSL patch

## Next Step

Use the ADR 0008 controlled dashboard architecture refactor as the foundation.

The immediate implementation scope is the dashboard shell and routing
architecture, not additional feature pages.
Traders Casa, TradeZella, and Plotly Dash examples remain the current visual
inspiration.

The goal is a clean, restrained, results-first interface with:

- primary decisions and metrics first;
- prominent equity and drawdown charts;
- progressive disclosure for evidence, assumptions, lineage, and diagnostics;
- no Paper or Live operational controls; and
- no commercial-grade polish before paper-trading work.

## Obsolete visual target

`docs/assets/dashboard/quant-factory-runs-visual-target.png`

This image is obsolete and non-authoritative. It mixed Research analysis with
Paper and Live operational information and no longer reflects the accepted
product separation.
