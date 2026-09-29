# Quant Factory

Quant Factory is Terry's private, single-operator quantitative research system.
Its primary purpose is to **find, reject, and rigorously validate defensible
trading edges**. VectorBT Pro is the licensed research engine; the dashboard is
an operator surface, not the purpose of the project.

## Current direction

The active sequence is:

**edge discovery -> validation -> execution-vehicle comparison -> dashboard
repair -> paper operation -> live operation later.**

Backend edge discovery is the current priority. The existing screening, OOS,
walk-forward, robustness, Monte Carlo, protected-test, persistence, lineage,
and filter-handoff infrastructure should be reused rather than rebuilt.

The current dashboard retains useful technical and historical acceptance
evidence, but the owner no longer considers it sufficiently intuitive or viable
as the long-term operating interface. Its successful chart-first prototype and
Find & Compare research remain UX references. Dashboard repair resumes after a
promising edge exists or sooner if the UI becomes a measured research blocker.

Initial active research is focused on short-duration directional behavior in
S&P 500 and Nasdaq-100 markets. Existing validated MES/MNQ data should be reused
where it can answer the question. A surviving edge may later be compared through
MES/MNQ and capital-efficient long 0DTE implementations such as SPY, QQQ, or
SPXW. Execution-vehicle details do not substitute for finding the edge.

No paid market-data acquisition, options execution adapter, futures broker
stack, deployment, paper activation, or live-capital work is justified until a
defined experiment or qualified edge creates the requirement.

## Project authority

Do not derive current work from README or older design/acceptance documents.

1. [AGENTS.md](AGENTS.md) — Codex operating contract.
2. [docs/MILESTONES.md](docs/MILESTONES.md) — current goal, phase, queue,
   blockers, next action, and milestone status.
3. [docs/DECISIONS.md](docs/DECISIONS.md) — accepted owner decisions and
   supersessions.

Supporting ADRs, specifications, runbooks, data catalogs, and milestone records
provide architecture, procedure, facts, or historical evidence only.

## Core principles

- Evidence truth before attractive backtests.
- Reuse mature components and existing project code before custom building.
- One genuinely new research question at a time; do not repeat completed work.
- Parallelize independent Codex work when it improves elapsed time/cost.
- Keep research venue-neutral and separate from broker order submission.
- Protected data never participates in selection.
- Paper and live are separate security domains and require explicit gates.

## Existing foundation

The repository already contains:

- typed market-data, calendar, validation, cache, and provenance layers;
- strategy contracts and registry;
- VectorBT Pro experiment execution;
- screening, OOS, walk-forward, robustness, and Monte Carlo engines;
- durable run claims, persistence, artifacts, lineage, and review records;
- a connected persisted filter-chain coordinator;
- Plotly Dash Results and Find & Compare work;
- broker-neutral execution contracts and conservative Alpaca paper preparation.

Implementation is not evidence of profitability. Current work and exact
limitations are recorded only in
[docs/MILESTONES.md](docs/MILESTONES.md).

## Repository structure

- `strategies/` — strategy definitions and signal logic.
- `backtesting/` — experiment and validation engines.
- `orchestration/` — durable launch and filter coordination.
- `market_data/` — providers, validation, catalog integration.
- `persistence/` — research/evidence storage.
- `dashboard/` — operator interface.
- `execution/` — broker-neutral contracts and later paper/live boundaries.
- `docs/` — Tier 1 authorities plus supporting evidence and specifications.
- `tests/` — deterministic and browser checks.

Raw market data, generated results, credentials, and machine-specific state do
not belong in Git.
