# Prefect 3 Compatibility Spike

## Purpose

This spike determines whether Prefect 3 should provide Quant Factory's workflow execution, retries, scheduling, cancellation, state tracking, logs, and technical operations UI.

It is not Milestone 18 implementation. It is a bounded adopt-or-reject test.

## Fixed architectural boundary

- Plotly Dash remains the primary operator interface.
- Quant Factory's SQLite database remains authoritative for trading configuration, evidence, lifecycle, provenance, artifacts, and human review.
- Prefect, if accepted, owns technical workflow execution state, retries, schedules, cancellation, and operational logs.
- Existing strategy, backtest, and numerical logic must not be rewritten.
- The Prefect UI is a technical operations console, not the user-facing research product.

## Spike scope

Use one deterministic synthetic fixture workflow only.

The workflow must:

1. accept a stable Quant Factory configuration identifier;
2. create or reference one Quant Factory run record;
3. transition the Quant Factory run through created, running, and succeeded or failed states;
4. execute one deterministic task without market-data download or VectorBT evaluation;
5. write structured logs visible in Prefect;
6. persist a small result into the Quant Factory database;
7. expose the Prefect flow-run identifier in Quant Factory metadata without making Prefect the authoritative trading record;
8. demonstrate one controlled failure and automatic retry;
9. demonstrate timeout or cancellation behavior appropriate for local process execution;
10. leave no uncontrolled background services after the spike.

## Local server mode

Use the self-hosted local Prefect server and its default single-user SQLite backend for the spike. Do not configure PostgreSQL, Redis, Docker, cloud accounts, remote workers, or multi-worker API mode.

The spike must document:

- Prefect version installed;
- Python version compatibility;
- start command;
- API configuration used;
- default UI address;
- stop procedure;
- Prefect local database/configuration paths;
- measured idle and active resource use;
- any ports or process conflicts.

## Integration design to prove

### Identity mapping

Quant Factory run ID and Prefect flow-run ID remain distinct.

The adapter must be able to store or return both identities and retrieve the technical workflow state without replacing the Quant Factory run record.

### State mapping

At minimum demonstrate a mapping for:

- Prefect pending or scheduled -> Quant Factory created;
- Prefect running -> Quant Factory running;
- Prefect completed -> Quant Factory succeeded;
- Prefect failed or crashed -> Quant Factory failed;
- Prefect cancelled -> Quant Factory cancelled.

Retries must not create false successful Quant Factory runs or erase prior failure information.

### Logging

Prefect owns detailed technical logs. Quant Factory stores only the user-readable error summary and a reference to the Prefect run.

### Execution isolation

The spike must determine whether synchronous blocking Quant Factory workloads should run:

- directly in the flow process;
- as process-based tasks;
- through a local process work pool;
- or through another minimal Prefect-supported local execution method.

The selected method must support reliable cancellation or clearly document its limitation.

## Pass criteria

Prefect is accepted for Milestone 18 only if all of the following pass:

1. installs cleanly in the current Python 3.12 environment without breaking existing dependencies;
2. local server starts, UI loads, and server stops cleanly;
3. deterministic fixture completes and persists the expected Quant Factory result;
4. existing numerical and strategy code remains unchanged;
5. state mapping is deterministic and tested;
6. controlled retry behaves as expected;
7. failure produces both Prefect technical logs and a Quant Factory error summary;
8. cancellation or timeout behavior is adequate for the chosen execution mode;
9. repeated fixture runs do not corrupt or duplicate immutable configuration records;
10. resource usage is acceptable on the target machine;
11. focused tests and the full existing suite pass;
12. Prefect does not become a second authority for trading evidence or review state.

## Reject criteria

Reject Prefect for V1 if any of these remain unresolved after the bounded spike:

- dependency conflicts or material test regressions;
- unreliable local startup or shutdown;
- inability to map workflow state safely to Quant Factory records;
- cancellation limitations incompatible with expected long-running jobs;
- unacceptable CPU or memory use;
- substantial duplication between Prefect and the Quant Factory database;
- integration requires rewriting existing experiment runners;
- operation would require PostgreSQL, Redis, Docker, cloud services, or another permanent server stack for the single-user V1.

## Deliverables

The spike must produce:

- one isolated Prefect fixture flow and tests;
- dependency changes, if accepted;
- a short compatibility report with every pass criterion marked pass or fail;
- measured resource observations;
- a recommendation: adopt, reject, or adopt with explicit limitations;
- no implementation of the full Milestone 18 orchestration layer.

## Stop rule

Stop after the compatibility recommendation. Do not proceed into Milestone 18 without a separate approval and implementation prompt.
