# Dashboard Foundation Evaluation

## Executive recommendation

Quant Factory should **assemble a minimal custom dashboard on Plotly Dash**, using VectorBT Pro and Plotly figures as the visualization engine, the existing `ExperimentResult`/CSV output as the first data contract, and selected reporting ideas from QuantStats. It should not adopt another complete dashboard substantially as-is.

This is the shortest path because the project already uses Python, Pandas, Plotly-compatible VectorBT Pro outputs, and a typed experiment runner. Dash provides the interaction and application shell without requiring a separate front-end stack. The first dashboard should remain local, read-only except for a simple human review status, and deliberately small.

## Evaluation criteria

Candidates were assessed for:

- fit with the current Python 3.12 and VectorBT Pro workflow
- ability to display equity, drawdown, metrics, provenance, and parameter comparisons
- support for experiment and run selection
- extensibility toward validation, paper trading, and live monitoring
- amount of custom code and operational complexity
- licensing and reuse restrictions
- maintenance risk and lock-in
- ability to support clear human decisions

## Candidate comparison

| Candidate | Classification | Strengths | Limitations | Decision |
|---|---|---|---|---|
| VectorBT Pro plotting and portfolio analysis | Adopt directly | Native portfolio metrics and Plotly-compatible figures; current project dependency; strongest semantic fit | Not a complete application shell or workflow/state system | Adopt as chart and analysis engine |
| Plotly Dash | Adopt directly as framework | Python-native reactive application model; MIT license; mature; long-term extensibility; natural fit with Plotly and VectorBT Pro | Requires explicit layout, callbacks, and state design | Selected application foundation |
| Qubit Quants VectorBT Pro Dash example | Design/reference only | Demonstrates VectorBT portfolio and strategy tabs in Dash; proves technical fit | Published in 2023; tutorial page restricts reproduction; project maturity and current compatibility are uncertain | Use only as architectural inspiration unless code license is independently verified |
| QuantStats | Extend/use selectively | Broad return analytics and HTML tear sheets; Python 3.10+; optional Plotly conversion | Report-oriented rather than interactive workflow; overlaps with VectorBT metrics; additional dependency surface | Use later for generated deep-dive reports, not as the dashboard foundation |
| Forven | Design inspiration only | Strong operator workflow, gauntlet states, paper/live concepts, visual status model | AGPL-3.0; broader architecture than needed; direct code integration would impose reciprocal licensing obligations | Do not copy or embed code; selectively reimplement workflow ideas |
| Streamlit | Limited secondary role | Very fast prototypes; Apache-2.0; simple Python model | Rerun-centric state model and reduced control become awkward for a long-lived operational interface | Do not use as primary foundation; acceptable only for isolated prototypes |
| Full greenfield web front end | Reject now | Maximum control | Highest development and maintenance cost; duplicates mature framework capabilities | Reject |

## Detailed findings

### VectorBT Pro

VectorBT Pro remains the source of truth for portfolio analysis and plotting. Its portfolio objects expose performance statistics, equity/value views, drawdowns, trades, and other analysis outputs. Those capabilities should be wrapped, not reproduced.

For Milestone 7B, the dashboard should either:

1. reconstruct the selected portfolio deterministically from the experiment configuration and selected parameters, or
2. consume a future persisted run artifact that includes the required series.

The current ranked CSV alone is enough for the table and metrics but not enough for an equity or drawdown chart. Milestone 7B should therefore add a narrow, reusable dashboard-data adapter that can reconstruct the selected run without changing strategy behavior.

### Plotly Dash

Dash is selected because it is built for reactive Python data applications and uses Plotly figures directly. It is suitable for a local WSL-hosted app now and can later be containerized. Its callback model is more explicit than Streamlit's rerun model, which is useful once the interface contains strategy selection, run comparison, review state, paper status, and monitoring.

Open-source Dash is MIT-licensed. No paid Dash Enterprise feature is required for the local single-user phase.

### Qubit Quants example

The Qubit Quants tutorial is valuable evidence that a VectorBT Pro portfolio can be exposed through a Dash interface with separate simulation and strategy views. However, the tutorial is dated January 2023 and its publication page says its content may not be reproduced without permission. Unless the linked repository has a clear permissive software license, Quant Factory should not copy its code.

Its useful ideas are:

- separate experiment and strategy views
- direct reuse of VectorBT/Plotly figures
- a thin Dash shell around portfolio outputs

### QuantStats

QuantStats is useful for optional, detailed return reports and tear sheets. It supports modern Python and can produce HTML reports. It should not own the primary interface because Quant Factory needs experiment selection, parameter comparison, provenance, validation state, and later paper/live workflow controls.

Recommended role:

- defer installation until a report is required
- generate a linked or downloadable deep-dive report for a selected strategy/run
- do not duplicate QuantStats metrics in the first dashboard when VectorBT already provides them

### Forven

Forven is the strongest workflow reference, especially for:

- pipeline stage visibility
- pass/fail or gauntlet presentation
- operator status panels
- paper/live mode separation
- strategy promotion and failure history

Forven is AGPL-3.0. Direct code reuse or network deployment of a derivative can trigger source-sharing obligations. Quant Factory should reimplement selected interaction concepts in its own code rather than importing Forven components.

### Streamlit

Streamlit is excellent for disposable analysis tools and could be used for a quick internal prototype. It is not selected for the main dashboard because the project is intended to become a persistent operational interface with increasingly complex state and callbacks.

## Adopt / extend / build decision

### Adopt

- Plotly Dash as the application framework
- VectorBT Pro and Plotly figures for charts and portfolio analytics
- Pandas tables and current experiment outputs as the initial data layer

### Extend

- the existing reusable experiment runner with a read-only dashboard adapter
- the existing result model with only the minimum information needed to reconstruct a selected portfolio
- QuantStats later as an optional report generator

### Build

Quant Factory must build:

- its own minimal layout and navigation
- experiment/run and parameter selection
- a dashboard data adapter
- review-status persistence
- strategy provenance and execution-assumption presentation
- later validation, paper, and live lifecycle views

### Do not build

- a plotting library
- duplicate portfolio metrics already provided by VectorBT Pro
- a general-purpose report engine
- a custom JavaScript front end
- paper/live controls in Milestone 7B
- an experiment database before its scheduled milestone

## Proposed Milestone 7B architecture

```text
Experiment configuration / ranked CSV
                |
                v
Dashboard data adapter
  - list available experiment outputs
  - load ranked result table
  - select parameter row
  - reconstruct selected portfolio deterministically
  - expose metrics, equity, drawdown, provenance, assumptions
                |
                v
Plotly Dash application
  - selectors and status controls
  - Plotly figures
  - metrics cards
  - ranked table
  - read-only provenance and assumptions
                |
                v
Small local review-state file
  - experiment ID
  - selected parameter identity
  - status: unreviewed/reject/revise/watchlist
  - optional note and timestamp
```

The review-state file should be local and Git-ignored. A proper experiment database remains deferred.

## Minimal dashboard screen and workflow

The first screen should contain:

1. Experiment selector.
2. Strategy name, version, and family.
3. Data provider, adjustment status, date range, and row count.
4. Ranked parameter table.
5. Selected parameter values.
6. Key metrics: total return, annualized return, Sharpe ratio, maximum drawdown, trade count, and win rate.
7. Equity curve.
8. Drawdown chart.
9. Execution assumptions: initial cash, fees, slippage, direction, leverage, timing limitation.
10. Human review status: unreviewed, reject, revise, or watchlist.
11. Optional short review note.

The workflow is:

- open one experiment
- scan ranked combinations
- select one row
- inspect its charts, metrics, provenance, and assumptions
- assign an initial review state

## Risks and unresolved questions

- The current CSV does not contain equity or drawdown series; the selected portfolio must be reconstructed or persisted separately.
- The exact VectorBT Pro plotting APIs installed in version 2026.4.7 must be verified during implementation through MCP and local inspection.
- Decision 273 supersedes the earlier standard-table preference for the current
  Milestone 23C direction: use Dash AG Grid for interactive result tables.
- Review-state storage is intentionally temporary until the experiment database milestone.
- Authentication is unnecessary for a local single-user app and is deferred.
- The application should avoid rerunning the full parameter grid when only one selected portfolio needs reconstruction.

## Features deferred

- out-of-sample, walk-forward, Monte Carlo, and regime views
- formal pass/fail validation gauntlet
- strategy promotion to paper or live
- paper orders, fills, positions, reconciliation, and alerts
- broker connectivity
- portfolio allocation and correlation views
- AI hypothesis generation or explanation
- multi-user authentication and permissions
- remote production deployment
- complete experiment database
- embedded QuantStats reports
- Figma design system

## Sources reviewed

- VectorBT Pro feature and analysis documentation
- Plotly Dash official repository and documentation
- Qubit Quants VectorBT Pro custom dashboard tutorial
- QuantStats official repository
- Forven public product and licensing information
- Streamlit official repository and licensing information
