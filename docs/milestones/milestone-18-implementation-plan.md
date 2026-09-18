# Milestone 18 Implementation Plan

## Objective

Implement the minimum stable run-orchestration layer that makes approved Quant Factory fixtures launchable, observable, retryable, cancellable, and recoverable without replacing Quant Factory's trading-governance database or Prefect's technical workflow authority.

## Authority boundary

- Prefect owns technical workflow execution, retries, task/flow logs, timeout handling, and technical state.
- Quant Factory owns strategy/configuration identity, trading run identity, lifecycle evidence, provenance, artifacts, reviews, and dashboard-facing research records.
- Prefect flow-run IDs and Quant Factory run IDs remain distinct.
- Prefect IDs are technical metadata, never research artifacts or configuration identity.

## Reuse decision

Adopt Prefect 3 in local self-hosted mode with a dedicated `PREFECT_HOME`.

Do not build custom schedulers, worker managers, retry engines, workflow consoles, or log engines.

## Milestone slices

### Slice 18A — Stable run service

Create one repository-level run service that:

- accepts an existing immutable configuration ID;
- creates one Quant Factory run ID;
- launches one approved deterministic fixture through Prefect;
- stores the Prefect flow-run reference as technical run metadata;
- reconciles Prefect states into Quant Factory run states;
- prevents duplicate launch of the same Quant Factory run ID;
- exposes dashboard-oriented read methods for current state and recent runs.

Acceptance:

- one fixture launches through the service;
- Prefect and Quant Factory identities remain separate;
- success and failure reconcile correctly;
- duplicate run launch is rejected safely;
- no market data, VectorBT execution, or strategy discovery is added.

### Slice 18B — Structured operator logs

Expose a bounded log-view model that combines:

- Prefect technical log references and retrieval;
- Quant Factory lifecycle transitions and error summaries;
- timestamps, severity, source, and run identity.

Quant Factory must not copy the full Prefect log stream into SQLite.

### Slice 18C — Retry, cancellation, timeout, and stale-run recovery

Implement:

- approved retry through Prefect;
- cancellation request and final-state reconciliation;
- timeout-to-failed behavior;
- stale-running detection after process/server interruption;
- explicit recovery or terminal failure rules.

Cancellation must be proven before Milestone 18 can complete.

### Slice 18D — Saved configuration launch contract

Define the dashboard-facing launch contract for approved immutable configurations. The dashboard itself remains Milestone 20.

### Slice 18E — Milestone acceptance

A deterministic fixture must be launchable, observed, failed, retried, cancelled, recovered from stale state, and completed through a stable service with full tests and no terminal or raw-file requirement in the eventual dashboard integration path.

## Exclusions

- strategy discovery or optimization;
- market-data downloads;
- real backtests;
- production workers or distributed execution;
- Prefect Cloud;
- Redis, PostgreSQL, Docker, Celery, or another orchestrator;
- dashboard implementation beyond stable service/query contracts;
- artifact schema redesign reserved for Milestone 19.

## First implementation boundary

Begin only Slice 18A. Do not implement logs, cancellation, stale-run recovery, dashboard pages, or later slices until Slice 18A is independently reviewed and accepted.
