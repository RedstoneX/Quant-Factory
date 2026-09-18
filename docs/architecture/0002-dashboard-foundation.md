# ADR 0002: Dashboard Foundation

- **Status:** Accepted
- **Date:** 2026-07-06

## Context

Quant Factory requires an early visual decision interface because raw logs and CSV output create unnecessary cognitive load. The interface must support experiment review now and later grow into validation, paper-trading, and live-operation workflows.

The project already uses VectorBT Pro, Pandas, and Plotly-compatible analysis. The integration-first policy requires evaluating mature dashboard and reporting tools before building a custom interface.

## Decision

Quant Factory will **assemble a minimal custom dashboard using Plotly Dash**.

The selected foundation is:

- Plotly Dash for the application shell and reactive callbacks
- VectorBT Pro for portfolio analytics and chart generation
- Plotly figures for equity, drawdown, and later trading visualizations
- the existing experiment runner and ranked output as the initial data contract
- a small dashboard adapter to reconstruct the selected portfolio and expose its evidence
- a temporary local, Git-ignored review-state file until the experiment database exists

The dashboard is custom only at the workflow layer. It will not reimplement portfolio calculations, plotting primitives, or generic reporting.

## Selected components

### Adopt directly

- Plotly Dash
- VectorBT Pro portfolio analysis and plotting
- Plotly chart objects
- Pandas-backed result tables

### Extend selectively

- the experiment runner with a read-only dashboard adapter
- QuantStats later for optional generated deep-dive reports

### Use as design inspiration only

- Qubit Quants VectorBT Pro Dash example
- Forven operator, gauntlet, and lifecycle patterns

## Rejected alternatives

### Adopt the Qubit Quants dashboard substantially as-is

Rejected because it is an older tutorial-specific implementation, current compatibility is uncertain, and the publication page restricts reproduction unless the linked source repository provides a separately verified permissive license.

### Adopt Forven components

Rejected because Forven is AGPL-3.0 and its full architecture is much broader than the present need. Quant Factory may reimplement concepts but will not copy or embed Forven code.

### Use Streamlit as the primary long-term interface

Rejected as the primary framework. Streamlit remains acceptable for isolated prototypes, but Dash provides more explicit and durable control for the intended operational workflow.

### Build a separate JavaScript front end

Rejected because it would add unnecessary development, integration, and maintenance cost.

### Use QuantStats as the dashboard

Rejected because QuantStats is a report and analytics library, not an experiment-selection and strategy-lifecycle application.

## Milestone 7B scope

The first dashboard will include:

- experiment selector
- strategy identity and version
- data provenance and date range
- ranked parameter table
- selected parameter set
- key metrics
- equity curve
- drawdown chart
- execution assumptions
- review status: unreviewed, reject, revise, or watchlist
- optional review note

It will not include advanced validation, paper trading, broker connectivity, AI generation, or portfolio allocation.

## Consequences

- Dash becomes a long-term application dependency.
- The first UI can remain local and single-user.
- Selected portfolio reconstruction must be efficient and must not rerun the full parameter grid unnecessarily.
- Review-state persistence is intentionally temporary until the experiment database milestone.
- VectorBT Pro API usage must be verified against the installed version during implementation.
- QuantStats integration remains optional and deferred.
- Forven and Qubit Quants are pattern sources, not code dependencies.

## Deferred decisions

- exact Dash table component (superseded for current Milestone 23C by Decision 273: Dash AG Grid)
- container and remote deployment model
- authentication
- formal dashboard design system
- experiment database schema
- validation-gauntlet presentation
- paper/live monitoring layout
- QuantStats report embedding or linking
