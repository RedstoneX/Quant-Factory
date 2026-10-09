# Quant Factory

Quant Factory is Terry's private, single-operator quantitative research system.
Its primary purpose is to **find, reject, and rigorously validate defensible
trading edges**. VectorBT Pro is the licensed research engine; the dashboard is
an operator surface, not the purpose of the project.

## Current direction

The active sequence, summarized from `docs/MILESTONES.md`, is:

**operator-interface reconstruction -> campaign-policy acceptance -> automated Candidate filtration and staged validation -> survivor review -> execution-vehicle comparison -> paper operation -> live operation later.**

Backend completion is recorded. The generic candidate runtime now reuses the existing screening, OOS, walk-forward, robustness, Monte Carlo, protected-test, persistence, lineage, durable-launch, and filter-handoff infrastructure. It stops at the protected-test gate and does not expand protected-data authority.

The deployed operator interface was owner-rejected. Its technical evidence is
retained, but its presentation has no design authority. Quant Factory is a
high-throughput automated filtration system: ordinary in-policy Candidates
progress without per-item owner approval, while exceptions, survivors, and
paper/live authority route to the owner. Current work is defined only in
`docs/MILESTONES.md`; product behavior is defined in
`docs/factory-operating-contract.md`.

The fixed Decision 310 MES overnight-gap reversal screen completed and was
rejected after negative total and annualized returns and Sharpe below 0.5. No
new strategy selection, proposal, optimization, screening, or profitability
test occurs before operator and campaign-policy acceptance. After activation,
automated research is restricted to **intraday/day-trading directional edges** unless the owner
changes the mandate: minutes-to-hours holding, flat by the strategy's defined
session boundary, and no overnight or multi-day carry. The SPY turn-of-month
idea remains out of scope under that mandate.

No paid market-data acquisition, external deployment, options execution
adapter, futures broker stack, paper activation, or live-capital work is
authorized by the current product-completion phase.

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
- Keep credentials in the `Quant Factory` Bitwarden Secrets Manager project
  and retrieve only the exact required secret through the `Codex` machine account.
- Paper and live are separate security domains and require explicit gates.

## Existing foundation

The repository already contains:

- typed market-data, calendar, validation, cache, and provenance layers;
- strategy contracts and registry;
- VectorBT Pro experiment execution;
- screening, OOS, walk-forward, robustness, and Monte Carlo engines;
- durable run claims, persistence, artifacts, lineage, and review records;
- a generic durable candidate runtime connected to the persisted filter-chain coordinator;
- reusable read models for persisted Results evidence and exact run selection;
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
