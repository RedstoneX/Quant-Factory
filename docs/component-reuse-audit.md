# Quant Factory Component Reuse Audit

- **Status:** Supporting inventory; Decision 285 and `AGENTS.md` are
  authoritative.
- **Current-use rule:** Revalidate candidate fit, license, security,
  maintenance, integration cost, and evidence truthfulness for the bounded
  task. Individual evaluations below are historical until that current
  preflight occurs.

## Rule

Decision 285 requires Quant Factory to adapt or integrate suitable maintained
components instead of recreating them. Custom code is limited to verified
project-specific gaps or cases where reuse is materially worse, with the
rationale recorded in implementation preflight. Small domain adapters,
evidence-integrity checks, and safety controls remain allowed where necessary;
unlicensed or incompatibly licensed copying is never allowed.

Quant Factory is Terry's private single-operator trading-research system under
Decision 284. Enterprise, SaaS, sales, multitenant, billing, customer, and team
features are not selection criteria unless separately approved.

## Decisions

Decision 273 (2026-09-03) supersedes the earlier Mantine-primary and
Bootstrap-fallback recommendation for the Milestone 23C dashboard direction.
The earlier recommendation is retained in the historical rationale below;
current implementation planning uses Dash Bootstrap Components for responsive
layout and controls and Dash AG Grid Community for interactive tables.

| Capability | Decision | Component |
|---|---|---|
| Portfolio simulation and analytics | Adopt | VectorBT Pro |
| Financial charts | Adopt | VectorBT Pro and Plotly |
| Research application | Extend | Existing Plotly Dash app |
| Responsive UI components | Adopt | Dash Bootstrap Components |
| Interactive result tables | Adopt | Dash AG Grid Community |
| Large time-series rendering | Adopt when needed | Plotly Resampler |
| Workflow orchestration, retries, schedules and technical run UI | Pilot, then adopt | Prefect 3 self-hosted |
| Trading governance and lifecycle records | Retain thin custom layer | Existing Quant Factory SQLite package |
| Generic experiment tracker | Do not add now | MLflow, Aim and Trackio evaluated |
| Parameter optimization | Adopt later after infrastructure gate | Optuna and Optuna Dashboard |
| Full MLOps suite | Reject as excessive | ClearML |
| Asset-centric data orchestrator | Reject for current scale | Dagster |
| Complete replacement trading platform | Reject | LEAN, Freqtrade, NautilusTrader and FinRL do not complement the chosen VectorBT Pro core efficiently |

## Experiment tracking review

### MLflow

MLflow already provides runs, parameters, metrics, tags, artifacts, SQL-compatible storage, search, comparison, parent/child runs and a tracking UI. It is mature, but its model lifecycle does not replace protected holdouts, immutable parameter locks, insufficient-evidence status, trading lifecycle decisions or paper/live reconciliation. Adding it now would create a second run store or require replacing Milestone 17 while the custom trading dashboard would still be required.

Decision: do not add MLflow now. Reconsider for multi-user or remote tracking later.

### Aim

Aim provides local experiment tracking, filtering, grouping, comparison and a strong UI under Apache-2.0. It remains training-metadata focused and would add another store and UI without eliminating the trading governance layer.

Decision: do not adopt. Use its comparison workflow as a design reference.

### Trackio

Trackio is lightweight, local-first, MIT licensed, Python 3.10+, and includes a forkable Svelte dashboard, CLI, API and SQL querying. It is the best lightweight fallback, but adopting it now would introduce a second frontend technology and still require trading governance.

Decision: do not adopt as system of record.

### Optuna

Optuna and Optuna Dashboard are appropriate for bounded optimization studies and SQLite-backed trial visualization. They are not a complete experiment, governance or deployment lifecycle.

Decision: adopt later only for approved optimization after Milestone 23.

### Sacred and ClearML

Sacred overlaps existing configuration and persistence without supplying the required product interface. ClearML is a broad MLOps suite whose server, agent and platform surface is excessive for the current single-user factory.

Decision: reject both for V1.

## Orchestration review

### Prefect 3

Prefect is the preferred Milestone 18 component because it provides native Python flows, state tracking, retries, caching, failure handling, schedules, events, pauses, self-hosted operation and a modern technical UI. Existing Quant Factory runners can be wrapped rather than rewritten.

The Prefect UI should serve as the technical operations console. Plotly Dash remains the simplified primary operator product and reads authoritative trading metadata from the Quant Factory database.

Decision: run one bounded compatibility spike before broad integration.

### Dagster and larger workflow engines

Dagster is mature but its asset-centric architecture is heavier than this experiment-run workflow. Airflow, Temporal, Luigi, Kestra and similar systems require more infrastructure or larger architectural changes than Prefect.

Decision: reject for V1 unless the Prefect spike fails.

## Trading platform review

QuantConnect LEAN, Freqtrade, NautilusTrader, FinRL and related platforms provide valuable complete or specialized systems, but adopting one would replace rather than complement VectorBT Pro or would narrow the project to a different asset class or research method.

Decision: retain VectorBT Pro. Reuse only design ideas for brokerage adapters, dry-run controls, protections and operational status.

## Dashboard reuse plan

The owner-approved interactive Results prototype is implementation input and
must be reused or adapted where it remains technically and legally suitable.
It is not by itself integrated, tested, deployed, or renewed operator-accepted
application behavior.

The earlier Milestone 20 component recommendation was:

- Plotly Dash pages and callbacks;
- VectorBT Pro Plotly figures;
- Dash Mantine Components for navigation, cards, forms, modals, notifications, loading states and theming;
- Dash AG Grid Community for histories, results, trades, artifacts and comparisons;
- Dash Bootstrap Components only if current Bootstrap integration makes it cheaper;
- Plotly Resampler only when chart size creates a measured problem;
- official Dash examples as implementation patterns.

Do not build raw HTML component systems, a second React/Svelte frontend, a generic experiment dashboard, or enterprise grid features without a specific requirement.

For current Milestone 23C planning, Decision 273 supersedes that component
preference: use Dash Bootstrap Components for responsive layout and controls,
and Dash AG Grid Community for interactive tables. This does not authorize a
framework rewrite.

## Why retain the custom SQLite package

After the identified correctness fixes, the package remains justified because it is a narrow trading-governance store for:

- strategy lifecycle classifications;
- immutable normalized trading configurations;
- validation stages and statuses;
- data and execution provenance;
- artifact validation and availability;
- human review history;
- future locks, protected intervals and promotion decisions.

Replacing it now with a generic tracker would require migration and adapters while still needing this trading-specific layer. It must not expand into a custom workflow engine, artifact store or visualization framework.

## Revised path

1. Apply the small Milestone 17 correctness fixes.
2. Do not add MLflow, Aim or Trackio.
3. Run a bounded Prefect compatibility spike before Milestone 18 implementation.
4. If accepted, use Prefect for execution states, retries, schedules, cancellation and technical monitoring.
5. Keep artifacts in the local filesystem and index them in the Quant Factory database; do not build an object store.
6. Build the dashboard from existing Dash component libraries and VectorBT figures.
7. Evaluate Optuna only when controlled strategy discovery begins.

## Anti-greenfield gate

Before each remaining milestone, document:

1. mature components evaluated;
2. selected component and license;
3. functionality adopted unchanged;
4. the thin Quant Factory adapter required;
5. functionality intentionally not built;
6. fallback if the compatibility spike fails.

No custom implementation of orchestration, generic run comparison, scheduling, retries, large tables, chart rendering, artifact storage or optimization is allowed without a documented reason that the selected mature component cannot meet the acceptance requirement.
