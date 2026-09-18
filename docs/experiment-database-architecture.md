# Experiment Database Architecture

## Scope

This document defines Milestone 17 before local implementation begins. The milestone adds durable local persistence for strategies, experiment configurations, runs, results, provenance, artifacts, and human review state. It does not add asynchronous orchestration, a full dashboard redesign, new strategy research, new data providers, or paper/live execution.

## Technology decision

Use SQLite through Python's standard-library `sqlite3` module.

Reasons:

- local, single-user deployment;
- no database server or external service to operate;
- transactional writes and foreign-key support;
- durable persistence across dashboard restarts;
- simple backup and migration handling;
- no additional dependency required;
- sufficient scale for the expected research metadata and artifact index.

The database stores metadata, normalized configuration, metrics, evidence state, review history, and artifact references. Large market data, equity curves, trade-series payloads, and generated reports remain external artifacts unless a later milestone explicitly changes that boundary.

## Default location

Default database path:

```text
state/quant_factory.sqlite3
```

Requirements:

- `state/` and database sidecar files are Git-ignored;
- the path is overrideable through configuration or an environment variable;
- no database file is committed;
- startup creates the directory only when required;
- tests use temporary database paths.

## Schema versioning

The initial schema version is `1`.

Use a dedicated metadata table containing:

- schema version;
- migration identifier;
- applied UTC timestamp.

Initialization rules:

- an empty database is migrated deterministically to the latest supported version;
- every migration executes transactionally;
- a newer unsupported schema fails closed with a clear error;
- a partially applied or corrupt migration state fails clearly;
- migrations are ordered, immutable after release, and covered by tests.

## Canonical serialization and identity

All JSON fields use deterministic canonical serialization:

- UTF-8;
- sorted object keys;
- compact separators;
- explicit handling of tuples, paths, dates, enums, and dataclasses;
- no `NaN`, positive infinity, or negative infinity.

Immutable experiment configuration identity is the SHA-256 hash of the canonical normalized configuration document.

Inserting the same normalized configuration twice returns the existing configuration identity. A matching stable configuration ID with different canonical content is rejected.

## Core entities

### Strategy registry

A versioned strategy record contains:

- `strategy_id`;
- `strategy_version`;
- display name;
- description;
- lifecycle classification;
- active state;
- created and updated UTC timestamps.

Allowed lifecycle classifications:

- `infrastructure_fixture`;
- `candidate`;
- `rejected`;
- `watchlist`;
- `paper_candidate`;
- `live_test_candidate`;
- `paused`;
- `retired`.

The composite strategy ID and version is immutable. Lifecycle and active state may change through an audited update method.

### Experiment configuration

An immutable configuration record contains:

- stable configuration ID;
- experiment ID;
- strategy ID and version;
- instrument and market-data configuration;
- parameter combinations or fixed parameters;
- execution assumptions;
- ranking configuration;
- screening configuration;
- complete canonical normalized configuration JSON;
- deterministic SHA-256 hash;
- created UTC timestamp.

Configurations are never silently modified. Any material change creates a new configuration identity.

### Experiment run

A run record contains:

- run ID;
- configuration ID;
- strategy identity/version copied for query convenience and validation;
- stage/type;
- status;
- started and completed UTC timestamps;
- user-readable error summary;
- software/environment metadata;
- created UTC timestamp.

Allowed run statuses:

- `created`;
- `running`;
- `succeeded`;
- `failed`;
- `cancelled`.

Allowed transitions:

- `created -> running`;
- `created -> cancelled`;
- `running -> succeeded`;
- `running -> failed`;
- `running -> cancelled`.

Terminal states cannot transition further in Milestone 17. Retry semantics belong to Milestone 18 and will create or link a separate run attempt.

### Parameter result row

Each row contains:

- run ID;
- stable row identity;
- canonical normalized parameters;
- canonical metrics;
- ranking position;
- screening/evidence status;
- rejection reasons.

Row identity is deterministic within the run from canonical parameters and relevant structural variant identity.

### Data provenance

A one-to-one run record contains:

- provider;
- provider implementation;
- symbol/instrument;
- interval;
- timezone;
- requested and actual coverage;
- adjusted-price state;
- row count;
- cache action;
- validation summary;
- optional manifest and checksum reference.

### Execution assumptions

A one-to-one run record contains the complete normalized execution model, including:

- signal timing;
- execution price;
- initial cash;
- sizing;
- fees;
- slippage;
- direction;
- leverage;
- accumulation;
- any additional existing execution fields.

### Artifact reference

An artifact record contains:

- run ID;
- artifact type;
- schema version;
- local path or reference;
- validation status;
- optional checksum;
- availability state;
- created UTC timestamp.

Allowed availability states:

- `available`;
- `missing`;
- `corrupt`.

The database indexes artifacts; it does not absorb large generated payloads during this milestone.

#### Milestone 23 chart evidence extension

New SPYM fixture runs retain optional `price_series`, `benchmark_curve`, and
`benchmark` fields in the existing external `equity_curve` JSON artifact.
The artifact remains bound to the run through its registered checksum and
manifest; this does not add a SQLite column or change old run artifacts.
Prices come from the same validated, immutable dataset used by the run.

The benchmark uses VectorBT Pro's same-instrument buy-and-hold engine and
records starting capital, timing, position sizing, fees, slippage, fixed fees,
and limitations alongside its values. Its fully invested allocation differs
from the fixture strategy's fixed-size trades. It is a disclosed research
comparison, not evidence of an approved strategy or an execution permission.

The dashboard reads these stored fields through artifact validation. Missing
fields in older runs produce an explicit unavailable-evidence state; viewing
a run does not fetch new prices or reconstruct a benchmark from current data.
Malformed optional chart evidence must produce a warning instead of a
misleading partial chart. Run the approved fixture again to capture new chart
evidence while preserving the original run and its lineage.

### Human review and audit history

Review targets may be a run or a parameter-result row.

Allowed review states:

- `unreviewed`;
- `reject`;
- `revise`;
- `infrastructure_fixture`;
- `watchlist`;
- `approved_for_next_evidence_stage`;
- `paper_candidate`;
- `live_test_candidate`;
- `paused`;
- `retired`.

Every review change appends an audit event containing:

- target type and ID;
- prior state;
- new state;
- note;
- operator identity or local-user marker;
- UTC timestamp.

Current state is derived from or transactionally maintained with the audit history. History is never overwritten.

## Transaction boundaries

The following operations are atomic:

- database migration;
- creation of a complete configuration record;
- creation of a run with strategy/configuration validation;
- persistence of a completed fixture result including parameter rows, provenance, execution assumptions, and artifact references;
- review-state update plus audit-history append.

Any failure rolls back the complete operation.

Foreign keys are enabled for every connection. Deletion should be restricted by default; research lineage is preserved rather than cascaded away silently.

## Typed package boundary

Implement a small persistence package with these conceptual layers:

1. **Models** — typed records, enums, validation, canonical serialization.
2. **Migrations/database** — connection creation, pragmas, schema versioning, transactions.
3. **Repositories** — SQL persistence and query methods grouped by entity.
4. **Service/facade** — multi-entity transactions and experiment-result adapter.

SQL must not appear in strategy modules or dashboard pages.

## Required read interfaces

The future dashboard requires tested methods to:

- list strategies and get strategy detail;
- list configurations and get configuration detail;
- list/filter runs by strategy, status, stage, and date;
- get complete run detail;
- list parameter rows for a run;
- retrieve provenance and execution assumptions;
- list artifact references;
- get current review state and review history;
- compare basic metadata for multiple runs.

Pagination may remain simple for Milestone 17 but query ordering must be deterministic.

## Fixture adapter boundary

Add a bounded adapter from the existing reusable experiment-result model into the persistence service.

It must demonstrate, without new strategy research:

- one strategy registered as `infrastructure_fixture`;
- one immutable experiment configuration;
- one completed fixture run;
- parameter rows and metrics;
- data provenance;
- execution assumptions;
- one artifact reference;
- one review-state transition and history.

Use synthetic or already existing deterministic test data. Do not rerun expensive or protected evaluations merely to populate the database.

Historical artifact bulk import is explicitly deferred. A future importer may consume known CSV/JSON artifacts through validation adapters after the unified artifact envelope exists.

## Milestone 17 acceptance

Milestone 17 passes when:

- schema version 1 initializes and persists across restart;
- foreign keys and transaction rollback are proven;
- immutable configuration hashing and deduplication work;
- strategy lifecycle and run-state rules are enforced;
- a complete fixture result is stored and retrieved;
- review history is durable and auditable;
- future-dashboard query methods are tested;
- corrupt and unsupported schema states fail clearly;
- the database and sidecar files remain outside Git;
- all focused and full repository tests pass.
