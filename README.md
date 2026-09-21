# Quant Factory

A private, single-operator AI-assisted quantitative research system built for
its owner to find and validate a trading edge. It uses VectorBT Pro and Plotly
Dash, with a controlled path from historical research toward evidence-qualified
paper operation and far-future, tightly bounded live deployment. It is not an
enterprise, SaaS, software-sales, multitenant, billing, or team-platform
project.

## Current direction

Quant Factory is explicitly **evidence truthful and proportionate to one
operator**.

The dashboard is the primary user product and normal operating interface. Python modules, terminal commands, CSV files, JSON artifacts, and backend logs are implementation details.

Decision 285 requires reuse before custom implementation: evaluate the
existing project, licensed dependencies, owner-approved prototypes, and mature
maintained legally usable components before writing new code. Custom code is
reserved for verified gaps or cases where reuse is materially worse. Prototype
approval is implementation input, not proof that behavior is integrated,
tested, deployed, or finally accepted.

The immediate objective is to finish and test the existing factory and its
essential dashboard workflow through beta before testing another real strategy
for an edge. The SPYM run proved the licensed engine, durable results, first
filter, and dashboard reopening; its weak strategy row correctly screened out.
The remaining filter mechanics and essential dashboard-page reconciliation are
now merged. Step 12 is Terry's clickable direction review; real saved-result
connections, complete workflow proof, final acceptance, and beta remain Steps
13–16 in [MILESTONES](docs/MILESTONES.md). No new candidate run or data
acquisition is part of that path.

Decision 298 sets the current order: reconcile and prove the remaining filter
mechanics with saved evidence or deterministic fixtures → verify stop/advance
behavior → complete the essential dashboard workflow → owner review and
acceptance → beta → only then test new candidates for an edge. The bounded
selected-run correction and reuse-first Find & Compare surface are already
merged. Terry found the reviewed Find & Compare image good and intuitive;
standard labels merged through PR #77 at `9495a36`. This does not claim
deployment, beta, or full Milestone 23 acceptance.
Completed preparation within
Milestone 24A–24D is retained, while remaining authenticated observer work is
deferred. Resume paper activation only after an edge qualifies and all
unchanged execution gates pass. Paper trading may take significant time to
become viable; live trading is far-future work. Automated paper forward
testing, micro-live work, and other venues follow only at the later gates in
[MILESTONES](docs/MILESTONES.md).

Existing RSI, SPY Donchian, and MES ORB work remains historical fixture or
infrastructure evidence, not an active profitability candidate. The bounded MES
ORB path completed and rejected the candidate; it proved the early screening,
durable-result, ranking and dashboard-reading path, not the complete filtration
chain. No next candidate will be selected before beta.

Decision 287 permits controlled, bounded, source-attributed candidate intake,
discovery and research/backtesting under Milestone 25 safeguards before
Milestone 23 passes. Executable candidate launch requires explicit owner
approval of the named, source-attributed hypothesis and predeclared evidence
boundaries. Open-ended optimization or data mining, protected-test evaluation
and automatic promotion remain unauthorized. Decision 298 pauses that
candidate authority until beta; its safeguards remain in force for later.
Decision 279 records the owner's
rejection of the former
Results-page comprehension and flow. Decision 280 accepts a chart-first
replacement direction built around a truthful selected-run price chart,
persisted trade markers, and a linked grouped trade ledger. Decision 282
records the owner's approval of the detailed selected-run specification and
requires a separate scalable multi-run analysis surface. Decision 291's bounded
R07 rendering and exact-reopen correction merged through PR #70 at
`4eaa03c761ffc4e90c4d1cf909c5f62d11bc614f` after focused, portable
real-browser, independent-review, and required-CI evidence passed. It is not
deployed, target-validated, operator-accepted, full beta, or Milestone 23
completion. Decision 293's bounded Find & Compare implementation is merged;
broader multi-run expansion and the remaining objective gates are deferred.

Decision 283 requires safe caching for exact repeat research computations so
repeats can reuse validated work instead of rebuilding everything. Each
explicit request still has its own durable run record, lineage and lifecycle;
cache reuse must remain traceable, input-complete and protected-data safe, and
it cannot be counted as independent evidence. The cache architecture and
explicit Reproduce policy are not yet selected or implemented.

Decision 275 is implemented: this sanitized clean-history public repository is
the canonical source of truth, and the original repository is retained as a
private, read-only historical archive. The cutover did not modify the
older private preview/runtime. Decision 276 keeps required checks and admin enforcement
while disabling GitHub's strict/up-to-date requirement, so independent green
pull requests can merge without refresh builds. Dependent or overlapping work
still integrates serially and is retested. This repository operation does not
change the product sequence above. Public visibility grants no source-code
license; all rights are reserved.

## Start here

The closed Tier 1 set is:

- [AGENTS](AGENTS.md) — the working contract and agent allocation.
- [MILESTONES](docs/MILESTONES.md) — product intent, current status, ordered work, and acceptance.
- [DECISIONS](docs/DECISIONS.md) — owner decisions, attribution, and supersessions.

Supporting documents explain their assigned subject and do not create another current plan:

- [Documentation governance](docs/DOCUMENTATION_GOVERNANCE.md) — authority, document lifecycle, and completion checks.
- [Chat handoff](docs/CHAT_HANDOFF.md) — startup navigation.
- [Codex agent policy](docs/ai-programming-agent-policy.md) — detailed operating procedures.
- [Implementation preflight](.agents/skills/implementation-preflight/SKILL.md) and [adversarial proposal check](.agents/skills/quant-factory-adversary/SKILL.md) — on-demand Codex controls.
- [Dashboard product requirements](docs/dashboard-product-requirements.md) — operator behavior and requirements.
- [Portable deployment ADR](docs/architecture/0007-portable-deployment-and-alpaca-first-roadmap.md) — Docker portability, VPS topology, and post-23 direction.
- [Research deployment runbook](docs/operations/ovh-research-deployment.md) — portable Docker/Compose deployment, private access, backup, restore, and rollback.
- [Public repository migration runbook](docs/operations/public-repository-migration.md) — sanitized clean-history publication, private archival, controlled cutover, and required-check proof under Decision 275.
- [Execution isolation ADR](docs/architecture/0006-paper-live-execution-isolation.md) — paper/live security domains and independent supervision.
- [Venue and allocation ADR](docs/architecture/0009-execution-venues-and-programming-agent.md) — later venue decisions; its Codex allocation is superseded by the current agent policy.
- [Data catalog](docs/DATA_CATALOG.md) and [data-source policy](docs/DATA_SOURCES.md) — dataset identity, status, provider roles, and storage.

Detailed milestone sequencing lives in MILESTONES. Historical evidence and conceptual or investigative notes retain the supporting roles defined by documentation governance.

## Dashboard product standard

Before Milestone 23 closes or any strategy advances toward paper activation, a
non-programming operator must be able to use the dashboard to:

- inspect system and data-source health;
- launch an approved fixture experiment;
- select approved instruments, strategies and saved configurations;
- inspect data coverage, provenance, execution and cost assumptions;
- observe run status and failures;
- view equity, drawdown, benchmark, price/signals and completed trades;
- review screening, OOS, walk-forward, robustness and Monte Carlo evidence;
- understand pass, fail, invalid and insufficient-evidence reasons;
- compare multiple stored runs;
- record durable review decisions;
- reproduce a prior run;
- verify lineage and artifact status;
- operate without opening Python, CSV, JSON or terminal output.

## Initial equity execution proof

SPY remains the primary research benchmark, a highly liquid reference instrument, and the likely first listed-options instrument later.

Milestone 21E selected SCHX as the future broad-market whole-share paper and small-money execution fixture. Whole shares simplify accounting, reconciliation, deterministic testing, and portability during the first execution proof. The SCHX selection is infrastructure and execution evidence only; it is not profitability approval and does not authorize paper or live broker orders.

SPYM remains the completed Databento ingestion, deterministic execution and dashboard evidence fixture from Milestones 21B–21D. SPY results are not evidence for SPYM or SCHX, and SPYM evidence is not evidence for SCHX. Each instrument needs its own dataset identity, liquidity and spread evidence, corporate-action and ticker-history review, and explicit execution assumptions before any strategy is promoted on it.

Alpaca Paper Trading is the first planned execution adapter. The initial operating proof uses listed US equities or ETFs rather than SPX options or futures so order handling, reconciliation, restart safety, and risk controls can be proven with the lowest operational complexity.

The planned future execution policy is:

- patient limit entry at the bid or midpoint;
- a defined timeout;
- possible escalation toward a marketable limit while the signal remains valid;
- marketable-limit exits when execution is required;
- no assumption of passive bid/ask fills in backtests without suitable quote data and a defensible fill model.

## Portable deployment direction

**Deferred:** portability and deployment procedures are retained for later use
when Terry requests a persistent install, an actual runtime change is approved,
Milestone 23 closure resumes, or a qualified candidate approaches paper. They
are not current research work, and the project never deploys merely to prove it
can deploy.

Development uses the canonical public GitHub repository through its owned OVH
checkout. The retired Windows/WSL clone is not authoritative. Before Alpaca
paper execution, production services will be packaged with Docker and Docker
Compose so Quant Factory can move between authorized hosts without rebuilding
the Python environment manually.

The portable deployment unit is:

```text
Git repository
+ Dockerfiles and Compose configuration
+ environment-variable template without secrets
+ external persistent data
+ encrypted backups and tested restore procedure
```

Container images never contain broker credentials, private keys, databases, research artifacts, logs, or encryption secrets. SQLite remains acceptable for a single-writer deployment and may later be replaced only when concurrent service access requires it.

The intended deployable services are Quant Factory Core/dashboard, venue-specific execution workers, persistent storage, and an independent Risk Sentinel. MAC-address trust is not used between cloud hosts; private networking, WireGuard, mutual authentication, firewall allowlists, signed commands, heartbeats, and external audit evidence provide service identity and isolation.

WEEX is the preferred first crypto execution target, subject to legal, account, API, security, paper or sandbox, and operational eligibility verification. Hyperliquid and MEXC remain later comparison or fallback targets, not approved live venues. VPS location, VPNs, proxies, or containers must not be used to bypass an account or jurisdiction restriction. See ADR 0009.

## Existing technical foundation

The repository already contains:

- typed market-data provider, exchange-calendar, validation, cache and audit layers;
- a common strategy contract and fixed registry;
- a reusable VectorBT Pro experiment runner;
- explicit execution assumptions and hygiene gates;
- deterministic cheap screening;
- chronological OOS and walk-forward engines;
- Monte Carlo and parameter/regime robustness engines;
- a local Plotly Dash decision dashboard;
- market-data catalog and dataset manifests;
- deterministic tests and fail-closed research controls.

Implemented components are not equivalent to accepted end-to-end behavior. The current acceptance evidence, unresolved work, and later execution milestones are recorded in [MILESTONES](docs/MILESTONES.md); use that record rather than treating this component overview as a gap list.

## Repository structure

- `strategies/` — strategy definitions, fixtures, indicators and signal logic.
- `backtesting/` — experiment and validation engines.
- `market_data/` — provider, calendar, cache, validation and audit logic.
- `dashboard/` — Plotly Dash application and adapters.
- `persistence/` — local SQLite schema, repositories, and fixture-result persistence service.
- `data/manifests/` — committed dataset identities and checksums.
- `results/` — generated artifacts, excluded from Git.
- `docs/` — authoritative product, architecture and operating documentation.
- `tests/` — deterministic component and workflow tests.

## Local experiment database

Milestone 17 adds a local SQLite experiment database for strategy registry, immutable configurations, runs, parameter rows, provenance, assumptions, artifact references, and review history.

Default path:

```text
state/quant_factory.sqlite3
```

The database and SQLite sidecars are local state and are ignored by Git.

## Work allocation

Codex is the active project toolchain. The lead completes small routine work
directly, delegates only for a clear net benefit, independently validates
critical evidence, and completes repository operations; the owner is not
expected to perform Git synchronization. See the
[agent policy](docs/ai-programming-agent-policy.md) for the detailed procedure.
