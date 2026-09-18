# Prefect 3 Compatibility Report

## Scope

This report covers the bounded Prefect 3 compatibility spike only. It does not
implement Milestone 18 orchestration, strategy discovery, market-data download,
VectorBT evaluation, dashboard changes, workers, deployments, Docker,
PostgreSQL, Redis, or Prefect Cloud.

## Manual server and resource evidence

Manual evidence supplied for the real WSL environment:

- Prefect version: 3.7.8.
- Python version: 3.12.13.
- Isolated self-hosted server starts successfully.
- Health endpoint works.
- Browser dashboard at `http://127.0.0.1:4200` loads successfully.
- Startup time is approximately 15 seconds.
- Idle RSS is approximately 235 MB.
- Idle CPU is approximately 9.6%.
- Shutdown is approximately 1 second.
- No remaining Prefect process or port listener after shutdown.

The Codex sandbox's inability to create sockets or launch an ephemeral Prefect
server is not treated as a Quant Factory compatibility failure.

## Integration shape tested in code

The spike adds an isolated synthetic fixture adapter under `prefect_spike/`.
The fixture accepts a stable Quant Factory configuration ID, creates or
references one Quant Factory run, keeps Quant Factory run ID and Prefect
flow-run ID distinct, executes one deterministic task, and persists one small
deterministic parameter-result row.

Prefect flow-run identity is not stored as a research artifact. For newly
created fixture runs it is recorded only in `experiment_runs.environment_json`
as technical run-environment metadata, and the adapter returns both identities
to the caller. If future production orchestration requires richer queryable
external execution references, that should be designed in Milestone 18 rather
than added speculatively in this spike.

## Server-independent test evidence

Server-independent tests run in the normal pytest suite without a Prefect
server. They use controlled inputs and constructed state-like objects for
mapping and persistence behavior.

Covered:

- Prefect-state to Quant-Factory-state mapping.
- Quant Factory and Prefect ID separation.
- Persistence adapter behavior using controlled inputs.
- Failed-run error-summary handling.
- Immutable configuration deduplication.
- Graceful behavior when Prefect is unavailable.
- Timeout and cancellation mapping from controlled state objects.

Latest server-independent result in Codex: 8 passed, 2 explicitly skipped live tests
when no external `PREFECT_API_URL` was configured.

## Live external-server test evidence

An explicit live verification path exists and requires `PREFECT_API_URL` to
point to an already-started isolated self-hosted Prefect server. It never starts
an ephemeral server automatically.

The live verification is designed to prove:

- one harmless deterministic fixture flow runs against the external server;
- the real Prefect flow-run ID is distinct from the Quant Factory run ID;
- Prefect logs and final state are retrievable from Prefect;
- the Quant Factory run reaches the expected final state;
- first-attempt task failure is recovered by Prefect-native retry;
- bounded task timeout maps to a failed Quant Factory run;
- the fixture performs no market-data download, VectorBT evaluation, strategy
  discovery, or real backtest.

Live WSL verification result: 10 passed in 6.20 seconds.

Verified in live WSL execution:

- real Prefect-native retry passed;
- Prefect API logs were retrieved;
- timeout mapped Quant Factory to `failed`;
- no run remained in `running`;
- Quant Factory run IDs and Prefect flow-run IDs remained distinct.

## Pass criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| Installs cleanly in Python 3.12 without breaking dependencies | Pass | Manual verification: Prefect 3.7.8 on Python 3.12.13; pytest environment starts. |
| Local server starts, UI loads, and server stops cleanly | Pass | Manual WSL evidence recorded above. |
| Deterministic fixture completes and persists expected Quant Factory result | Pass | Live WSL verification passed: 10 passed in 6.20 seconds. |
| Existing numerical and strategy code remains unchanged | Pass | Spike files are isolated under `prefect_spike/` and tests/docs only. |
| State mapping is deterministic and tested | Pass | Server-independent tests cover mapping. |
| Controlled retry behaves as expected | Pass | Live WSL verification proved real Prefect-native retry. |
| Failure produces Prefect technical logs and Quant Factory error summary | Pass | Server-independent tests cover Quant Factory error summaries; live WSL verification retrieved Prefect API logs. |
| Cancellation or timeout behavior is adequate | Limitation | Live WSL verification proved timeout-to-failed and no run remained running. Cancellation support is not yet proven. |
| Repeated fixture runs do not duplicate immutable configurations | Pass | Server-independent test covers deduplication. |
| Resource usage is acceptable on target machine | Pass | Manual WSL evidence: approximately 235 MB idle RSS and 9.6% idle CPU. |
| Focused tests and full suite pass | Pass | Live WSL focused test passed: 10 passed in 6.20 seconds. Full suite passed in Codex: 316 passed, 2 skipped, 2 Dash deprecation warnings. |
| Prefect does not become a second authority for trading evidence or review | Pass | Prefect ID is not stored as an artifact; Quant Factory database remains authoritative. |

## Reject criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| Dependency conflicts or material test regressions | Pass | Full suite passed: 316 passed, 2 skipped, 2 Dash deprecation warnings. |
| Unreliable local startup or shutdown | Pass | Manual WSL server evidence passed. |
| Inability to map workflow state safely to Quant Factory records | Pass | Deterministic mapping tests passed. |
| Cancellation limitations incompatible with long-running jobs | Limitation | Timeout-to-failed passed in live WSL verification. Cancellation remains unproven. |
| Unacceptable CPU or memory use | Pass | Manual WSL resource evidence appears acceptable for a local spike. |
| Substantial duplication between Prefect and Quant Factory database | Pass | The fixture stores only technical execution metadata and deterministic result data. |
| Integration requires rewriting existing experiment runners | Pass | No existing experiment runner rewrite was needed. |
| Requires PostgreSQL, Redis, Docker, cloud services, or permanent server stack | Pass | Only self-hosted single-user Prefect server mode is in scope. |

## Recommendation

ADOPT WITH LIMITATIONS

Limitations:

- dedicated `PREFECT_HOME` required;
- cancellation not yet proven;
- local self-hosted mode only;
- no production workers, deployments, schedules, or full Milestone 18
  implementation.
