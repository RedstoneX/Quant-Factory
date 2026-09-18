# ADR 0007: Portable deployment and Alpaca-first execution roadmap

- **Status:** Accepted
- **Date:** 2026-07-15
- **Scope:** Post-acceptance roadmap, deployment portability, VPS topology, venue sequencing, execution-worker isolation, and Risk Sentinel networking
- **Supersedes:** ADR 0005 sections 7–10 where they imply futures/FX infrastructure before the first operating proof or treat Hyperliquid as an approved second deployment venue
- **Supplements:** ADR 0006 paper/live execution isolation and independent Risk Sentinel requirements
- **Superseded in part by:** ADR 0009 for crypto venue ordering; portability,
  Alpaca-first execution, VPS topology, isolation, and Sentinel networking remain
  authoritative.

## Context

Quant Factory’s business objective is to prove that the platform can discover or intake defensible strategy hypotheses, reject weak candidates, preserve uncontaminated evidence, paper trade surviving strategies reliably, reconcile model and broker behavior, and eventually deploy tightly bounded capital under independent risk controls.

Building futures, crypto, and FX infrastructure before proving one complete operating path would delay that objective. Interactive Brokers adds substantial operational complexity for futures and FX. Alpaca provides the simplest first paper-execution path for US equities and ETFs. Crypto remains strategically interesting because of 24/7 markets and available open-source tooling, but venue eligibility and jurisdiction restrictions must be treated as hard deployment gates rather than networking problems to bypass.

The project also needs to move cleanly between the current Windows/WSL development machine and future VPS providers. Containerization should make the application portable without embedding persistent data or credentials in images.

## Decision

### 1. Finish the research factory before execution expansion

Milestones 22 and 23 remain the active acceptance path. Under Decision 259,
research-only Docker/Compose packaging, migration preparation, isolated OVH
target validation, and an isolated research deployment after technical checks
may proceed in parallel without interrupting that acceptance.
Broker-connected deployment, strategy profitability search, paper orders, and
live-capital work remain gated; this parallel preparation does not complete
Milestone 24.

After Milestone 23 acceptance, controlled equity research under Milestone 25 precedes the remaining Alpaca paper activation, under Decision 274. Completed deployment/execution preparation is retained; remaining R06 authenticated observer work is deferred.

### 2. Alpaca is the first execution venue

The first broker adapter and operating proof will use Alpaca Paper Trading with liquid US equities or ETFs. The initial purpose is to prove:

- broker-neutral order-intent translation;
- paper credential and endpoint isolation;
- order acknowledgement, fill, cancellation, and rejection handling;
- cash, position, and account reconciliation;
- restart, idempotency, and duplicate-order protection;
- dashboard operation and auditability;
- automated forward evidence without capital risk.

The existing SCHX whole-share fixture remains the approved low-capital infrastructure fixture. SPY, QQQ, IWM, and other liquid ETFs may become research or strategy candidates only through the post-Milestone-23 hypothesis and evidence process. SPX options are deferred until the simpler listed-equity path works.

### 3. Futures and FX are deferred to the backlog

Futures and FX remain supported future asset classes, but they are not required for Quant Factory V1. Interactive Brokers is deferred because its connection, session, and operational complexity would slow the first proof.

Futures, FX, and IBKR may be reconsidered after Alpaca paper, bounded Alpaca live, and at least one second venue prove the common execution architecture. They must not shape current implementation beyond stable broker-neutral boundaries.

### 4. Crypto is second, but the venue is conditional

A crypto execution adapter is the preferred second venue proof because it tests 24/7 operation, funding or carry, leverage where applicable, exchange precision, and different reconciliation behavior.

ADR 0009 supersedes the original Hyperliquid-first preference. WEEX is the
preferred first crypto execution target, subject to legal, account, API,
security, paper or sandbox, and operational eligibility verification.
Hyperliquid and MEXC are later comparison or fallback candidates, not approved
live venues.

A VPS, VPN, proxy, Docker container, or foreign IP address must never be used
merely to conceal or bypass an eligibility restriction. Any selected venue must
implement the same broker-neutral interface.

### 5. Preserve a market- and venue-neutral core

Strategies produce normalized signals or target-position intent. Research, validation, evidence, and strategy code do not call Alpaca, Hyperliquid, Interactive Brokers, or another venue directly.

The stable boundary is:

```text
strategy and approved deployment package
-> target position / broker-neutral order intent
-> local risk checks
-> Risk Sentinel authorization where required
-> venue-specific execution worker
-> broker-neutral acknowledgement, fill, position, and reconciliation records
```

Venue-specific SDK objects remain inside venue adapters or execution workers.

### 6. Use portable containerized deployments

Production and execution services will be packaged as portable containers. Docker Compose is the initial deployment mechanism; a more complex orchestrator is not required unless operating evidence justifies it.

Development remains native in WSL through Milestone 23. Research-only
container packaging, 24A–24D preparation, isolated OVH target
validation, and an isolated research deployment after technical checks may
proceed in parallel under Decisions 259 and 262.
Decision 266 authorizes the authoritative research runtime to migrate to the
US-based Linux VPS after documented backup, reconciliation, private-access,
restart, restore, and rollback checks. Windows/WSL remains available as a
preserved rollback or overflow-compute source. Paper execution and Milestone
24 acceptance retain their separate gates.

The portable deployment unit consists of:

- the Git repository;
- versioned Dockerfiles and Compose configuration;
- an environment-variable template containing names but no secrets;
- external persistent volumes or clearly defined host directories;
- encrypted, tested backups and restore instructions.

Container images must not contain API keys, database files, research artifacts, logs, broker sessions, private keys, or encryption secrets.

### 7. Separate deployable services

The intended service boundaries are:

```text
Quant Factory Core / dashboard
Risk Sentinel
Alpaca execution worker
future compliant crypto execution worker
persistent database and artifact storage
```

Quant Factory Core, the dashboard, Prefect, persistent services and the Alpaca paper worker may initially share the primary VPS where the security policy permits, but they remain independently deployable. Live execution and the Risk Sentinel must follow ADR 0006 separation requirements, including deployment of the Risk Sentinel on a separate host.

The main Quant Factory Core and research dashboard will be hosted on a US-based
Linux VPS under Decision 266 after the migration checks pass. That host becomes
the authoritative runtime for routine research, backtests, dashboard
operation, and orchestration. Broker-connected services remain separately
gated by Milestone 24 and ADR 0010. VPS geography is an infrastructure choice,
not evidence of account eligibility or residence, and must never be used to
bypass an eligibility restriction.

### Dashboard deployment boundaries

The primary VPS may host the Research dashboard, Quant Factory Core, Prefect,
persistent services and the isolated Alpaca paper worker, subject to service and
credential separation.

The future live dashboard and live execution worker are separate deployable
units with separate credentials, state, release authority and network policy.
They are not enabled by changing the Research or paper environment.

The independent Risk Sentinel remains on a separate host whenever live capital
is enabled. Presentation components may be shared in source code, but runtime
identities, secrets and privileged control paths remain isolated.

### 8. Externalize persistent state and secrets

Persistent state remains outside container images:

```text
/srv/quant-factory/deploy/
├── compose.yaml
├── config/
├── secrets/        # host permissions or approved secret manager; never committed
└── data/
    ├── database/
    ├── artifacts/
    ├── logs/
    └── backups/
```

SQLite remains acceptable while the factory is a single-writer deployment. It must be stopped or consistently snapshotted before migration. PostgreSQL is introduced only if independently deployed services require concurrent database access that SQLite cannot safely provide.

A provider migration should normally be:

```text
provision host
-> install Docker
-> clone approved Git revision
-> restore configuration and encrypted persistent state
-> inject secrets
-> start Compose deployment
-> run health, identity, reconciliation, and recovery checks
```

### 9. Risk Sentinel networking uses cryptographic identity

MAC-address locking is not an acceptable trust boundary between cloud hosts. The Sentinel and execution workers use:

- private networking or a WireGuard tunnel;
- mutual TLS or equivalent per-service cryptographic identity;
- cloud firewall or security-group allowlists;
- signed, expiring, replay-resistant commands;
- narrowly scoped credentials;
- no public inbound execution endpoint;
- outbound destination restrictions where practical;
- authenticated heartbeats and fail-closed timeouts;
- immutable audit evidence stored outside the primary trading host.

Loss of Sentinel communication blocks new entries according to policy. Position flattening occurs only under a predeclared emergency rule, not as an unconditional response to every network interruption.

### 10. Roadmap after Milestone 23

Decision 274 supersedes this ADR's earlier post-M23 work ordering. Dashboard
and operator acceptance is priority 1. After M23, controlled strategy intake
and research/backtesting to qualify a defensible edge precede paper activation.
Decisions 259 and 262 still permit research deployment and M24A–24D engineering
in parallel; Decision 266 authorizes research runtime authority after its
migration checks. The completed preparation remains valid, but pause/defer the
remaining R06 authenticated observer work and resume M24 paper activation only
after an edge qualifies and all execution gates pass. Paper viability may take
significant time; live work is far-future. M26 paper forward testing follows
qualified paper activation, and M27 micro-live requires successful paper
evidence and separate explicit approval. Crypto and other asset classes remain
later work. MILESTONES remains authoritative for current scope and status.

## Consequences

- The project seeks a defensible equity edge before resuming paper activation; platform preparation is retained and paper operation remains gated.
- Docker provides repeatable application packaging, but Git, backups, external volumes, and secret management remain separately required.
- Alpaca-specific code cannot enter strategy or evidence modules.
- Hyperliquid remains conditional and replaceable rather than a required dependency.
- The second venue validates real abstraction needs; the project does not predesign a universal broker framework for every future market.
- Quant Factory V1 may be economically useful with equities and compliant crypto alone. Futures and FX are optional future expansions, not completion requirements.
- A successful platform does not guarantee profit. Acceptance proves evidence quality, rejection discipline, reproducibility, execution reliability, reconciliation, and bounded risk before capital is increased.

## Deferred implementation decisions

This ADR does not yet choose:

- the VPS provider or exact server sizes;
- the final Docker image layout;
- the network topology used before live trading;
- the final `OrderIntent` and execution-event schemas;
- the exact Alpaca instrument or first profitability strategy;
- a compliant crypto venue;
- Hyperliquid eligibility;
- PostgreSQL migration timing;
- futures, FX, options, or IBKR implementation milestones.

Those decisions require bounded preflight and acceptance work at the relevant milestone.

## Isolated research implementation under Decision 259

The research-only Compose deployment implements the parallel preparation
exception without accepting M23 or M24. Dashboard and Prefect have separate
external state, non-root execution, resource limits, and no broker worker or
credential. The dashboard publishes only to loopback and has a separate
normal bridge for outbound access; Prefect remains on the internal network.
One Gunicorn process with two request threads allows health and operator
requests during computation. Cancellation is cooperative at safe checkpoints,
not a process termination facility.

Licensed VectorBT Pro is installed from a private build context without sending
GitHub credentials to the builder. The immutable build records a full source
revision for run lineage; this metadata is not a signature or a Git dirty-tree
proof. Rebuild and target verification remain necessary when environment inputs
change. The [operating runbook](../operations/ovh-research-deployment.md)
defines startup, private access, restore, and rollback. Current deployment and
acceptance status belongs only in MILESTONES.
