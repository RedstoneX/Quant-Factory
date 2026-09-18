# ADR 0006: Isolate Paper and Live Execution Systems

- **Status:** Accepted
- **Date:** 2026-07-09
- **Updated:** 2026-09-17
- **Scope:** Forward testing, brokerage connectivity, credentials, deployment, state, monitoring, promotion, and independent risk supervision

## Context

Quant Factory progresses from historical research to paper forward testing and only later to micro-size live forward testing. Paper and live may share audited broker-neutral contracts and libraries, but they must not share deployment identity, credentials, mutable state, endpoint configuration, or release authority.

Paper testing uses no real capital and should not require routine manual promotion when predeclared research gates pass. Live deployment exposes capital and therefore requires explicit human approval plus independent safety supervision.

## Decision

Quant Factory remains one Plotly Dash product with separated Research, Paper Forward Testing, Micro-Live Operations, and System modes. Paper and live execution are separate deployed systems and separate security domains, not two modes of one process.

Research cannot submit broker orders directly. The progression path is:

```text
research evidence passes
        |
        | automatic, fail-closed eligibility decision
        v
paper execution system
        |
        | automatic monitor / continue / extend / pause / reject / retire
        v
eligible-for-live state
        |
        | explicit human approval
        v
micro-live execution system
        |
        | local controls plus independent Risk Sentinel
        v
bounded live operation
```

## Shared components allowed

The following may be shared when broker-neutral, deterministic, immutable where appropriate, and independently tested:

- strategy specifications and signal logic;
- market-data and order-intent schemas;
- risk-rule and reconciliation definitions;
- audit-event schemas;
- pure calculation libraries;
- broker adapter interfaces.

Shared libraries must not contain environment-selection logic that can expose live credentials or redirect paper orders to live endpoints.

## Automatic paper deployment

A strategy may deploy to paper automatically only when every predeclared eligibility gate passes, including valid evidence and lineage, supported execution assumptions, available deployment capacity, and absence of a duplicate active deployment.

Paper deployment must be:

- fail-closed;
- globally and individually disableable;
- capacity bounded and deduplicated;
- restricted to paper credentials and endpoints;
- recorded in a paper-specific database and order journal;
- protected by paper-specific exposure limits and kill switches.

Paper monitoring uses both elapsed time and accumulated observations or trades. An arbitrary number of days alone is not sufficient evidence. Predeclared rules may automatically continue, extend, pause, reject, or retire a deployment. Structural failures such as stale data, invalid deployment identity, repeated order rejection, unexplained position mismatch, or risk breach pause immediately.

## Live execution system

The live system must have:

- a separate process or deployment;
- live-only broker credentials and endpoint allow-listing;
- a separate live secret-injection path;
- a separate live database and immutable order journal;
- separate logs, alerts, and incident records;
- least-privilege permissions and no withdrawal capability where supported;
- independent live risk limits and local kill switches;
- explicit startup confirmation of account identity, environment, deployment identity, and approved symbols;
- fail-closed behavior for missing, ambiguous, or mismatched metadata.

Research, dashboard, Codex, and paper-trading processes must not receive live credentials or submit live orders directly.

## Independent Risk Sentinel

Micro-live operation requires a lightweight Risk Sentinel deployed independently from the primary trading host, preferably on a separate low-cost VPS.

The sentinel observes authenticated heartbeats and independently checks:

- primary process and broker connectivity;
- market-data freshness;
- deployment and configuration identity;
- order rate, duplicate orders, and repeated rejections;
- approved symbols and trading hours;
- position and exposure limits;
- daily loss and drawdown limits;
- model-to-broker position reconciliation.

Its authority is deliberately narrow:

```text
observe -> warn -> block new entries -> cancel orders -> pause deployment
        -> flatten positions only when a predeclared emergency policy requires it
```

The sentinel never generates signals, selects strategies, changes parameters, or optimizes policy. The primary system retains local safety controls; the sentinel is an independent additional layer rather than the sole control.

Communication uses authenticated messages and firewall allow-lists. Audit evidence must be retained outside the primary trading host. Sentinel loss, primary-engine loss, and communication loss each require explicit fail-safe behavior.

## Paper-to-live promotion boundary

Paper-to-live promotion is a controlled hand-off, not a configuration change. Micro-live activation requires:

1. a versioned immutable strategy package;
2. sufficient paper forward evidence;
3. model-to-paper reconciliation;
4. documented execution assumptions and observed deviations;
5. an eligible-for-live state;
6. explicit human approval;
7. a separately configured live risk policy;
8. verified live deployment and Risk Sentinel health;
9. proof that paper state, credentials, and endpoints cannot cross into live.

Promotion transfers only the approved package and bounded configuration. It never copies paper credentials, sessions, mutable runtime state, open orders, or positions. Automatic paper-to-live promotion is prohibited.

## Milestone impact

### Milestone 26 — Automated Alpaca Paper Forward Testing and Reconciliation

- build the paper execution service and adapter;
- implement automatic eligibility and deployment;
- implement evidence-based continue, extend, pause, reject, and retire states;
- implement idempotency, stale-signal rejection, recovery, reconciliation, risk limits, audit logs, and kill switches;
- implement heartbeat and sentinel protocols in paper simulation;
- prove crash, stale-data, duplicate-order, order-rate, mismatch, and risk-breach handling without capital risk.

### Milestone 27 — Alpaca Micro-Live Proof and Independent Risk Sentinel

- create the isolated live deployment and secret boundary;
- deploy the independent Risk Sentinel;
- verify firewall, identity, permission, heartbeat, audit, cancel, pause, and emergency-flatten controls;
- run fault-injection acceptance before activating capital;
- deploy only an explicitly approved strategy package with tightly bounded capital and positions;
- require live-versus-model reconciliation;
- prohibit automatic scaling.

## Enforcement rules

- No `environment=paper|live` switch may convert a paper deployment into live.
- No secrets file may contain both paper and live brokerage credentials.
- No paper process may receive live credential names or values.
- No research or dashboard process may submit live orders directly.
- Automatic research-to-paper progression is permitted only through predeclared fail-closed gates.
- Automatic paper-to-live progression is prohibited.
- Every live order must be attributable to an approved strategy version, live risk policy, deployment version, and account identity.
- Violations fail closed and block or stop deployment according to the declared policy.

## Dashboard and application isolation

Research, paper and live operation are part of the same Quant Factory product,
but they are not implemented as one privileged application with an environment
switch.

### Research dashboard

The graphics-rich Research dashboard supports configuration, backtests,
validation, evidence, comparison, trade analysis and approval-state review. It
has no live-broker credentials and no direct live-order capability.

### Paper operations

Paper execution uses an independently deployable paper-only worker with isolated
credentials, endpoints, mutable state and reconciliation records. Paper
interfaces may reuse presentation components from Research, but the application
cannot be converted to live operation through a dropdown, environment variable
or configuration edit.

### Live operations

Live operation uses a separate hardened dashboard or control application and a
separate live execution worker. The live application has:

- separate deployment identity, credentials, endpoints and mutable state;
- strong authentication and narrowly scoped authorization;
- no arbitrary strategy editing, parameter optimization or code execution;
- no direct access to research files or unrestricted research services;
- a deliberately small control surface for monitoring, explicit authorization,
  pause, cancellation and policy-approved emergency actions;
- complete immutable audit records.

The Research system may transfer only an approved immutable deployment package
through a narrow authenticated interface. It may not send arbitrary code,
mutable parameters or raw orders directly to the live broker.

Live broker credentials are available only to the isolated live execution
worker. Databases are not publicly exposed. Network access follows least
privilege, firewall restrictions and authenticated private service
communication.

The independent Risk Sentinel remains on a separate host and follows the
authority limits defined in this ADR.
