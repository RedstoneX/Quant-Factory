# ADR 0004: Adopt before building remaining infrastructure

- Status: Accepted
- Date: 2026-07-09

## Context

Quant Factory is a single-user, dashboard-first trading research system. Its distinguishing requirements are trading evidence, protected-data governance, lifecycle decisions and execution reconciliation. Generic experiment tracking, workflow orchestration, tables, charts, scheduling and optimization are not novel project requirements.

Milestone 17 implemented a narrow SQLite governance store. Before further infrastructure work, mature alternatives were reviewed across experiment tracking, orchestration, dashboards, optimization and complete trading platforms.

## Decision

1. Retain the narrow Quant Factory SQLite governance store after its identified correctness fixes.
2. Do not add MLflow, Aim or Trackio now because they would duplicate run storage and UI while not replacing trading-specific governance.
3. Use a bounded Prefect 3 self-hosted compatibility spike as the entry gate for Milestone 18.
4. If the spike passes, Prefect owns workflow execution state, retries, schedules, cancellation, logs and the technical operations UI.
5. Plotly Dash remains the primary operator interface and Quant Factory's database remains authoritative for trading configuration, evidence, lifecycle and human review.
6. The historical component selection was Dash Mantine Components, Dash AG Grid
   Community, existing VectorBT/Plotly figures and official examples rather
   than generic dashboard components. Decision 273 supersedes the Mantine
   preference for current Milestone 23C work: use Dash Bootstrap Components for
   responsive layout and controls while retaining Dash AG Grid Community.
7. Keep generated artifacts in the filesystem and index them in the database rather than building an object store.
8. Evaluate Optuna only after the strategy-discovery gate for bounded approved optimization.
9. Do not replace VectorBT Pro with a complete alternative trading platform.
10. Every future milestone must pass an explicit adopt-before-build review.

## Prefect compatibility gate

Prefect is accepted for Milestone 18 only if a bounded local spike demonstrates:

- compatibility with Python 3.12 and the current environment;
- reliable self-hosted server startup and shutdown;
- wrapping one deterministic fixture without changing numerical behavior;
- clean mapping between Prefect states/logs and Quant Factory run records;
- workable cancellation, retry and stale-run representation;
- acceptable resource use on the target machine;
- coexistence of the Prefect technical UI and Dash operator UI without conflicting authority.

Failure of the spike must be documented by criterion. Only the specific missing orchestration capability may then be custom-built.

## Consequences

- The Milestone 17 correction remains necessary because the retained database is authoritative for trading governance.
- Milestone 18 is no longer a greenfield orchestration implementation.
- The full dashboard remains custom only at the product-workflow level; generic controls, tables and chart engines are adopted.
- Additional dependencies are introduced only after a compatibility spike and explicit acceptance.

The detailed comparison is recorded in `docs/component-reuse-audit.md`.
