# Prefect Manual Verification

Date: 2026-07-09

## Environment

- Repository: `QF_REPO_ROOT` (example `/srv/quant-factory/repo`)
- Branch: `main`
- Git status: clean and synchronized with `origin/main`
- Python: `3.12.13`
- Prefect: `3.7.8`
- Prefect API version: `0.8.4`
- Pydantic: `2.13.4`
- Platform: Linux x86_64 under WSL

## Installation verification

The installed Prefect package imported successfully from the Quant Factory virtual environment.

`prefect version` reported:

- profile: `ephemeral`;
- server type: `ephemeral`;
- backend database: SQLite;
- SQLite version: `3.53.1`.

## Shared default database attempt

Starting a self-hosted Prefect server against the existing default `~/.prefect/prefect.db` eventually produced a healthy API response but logged an SQLite `database is locked` error while writing Prefect telemetry configuration.

After termination:

- no Prefect or Uvicorn process remained;
- no process held the database open;
- SQLite WAL and SHM sidecars remained.

This means the normal shared Prefect home should not be used for the Quant Factory spike without further investigation.

## Isolated Prefect home attempt

The server was restarted with a disposable isolated home:

```text
PREFECT_HOME=/tmp/quant-factory-prefect-spike
PREFECT_API_URL=http://127.0.0.1:4200/api
PREFECT_SERVER_ANALYTICS_ENABLED=false
DO_NOT_TRACK=1
```

Results:

- local server startup: PASS;
- API health endpoint: PASS (`true`);
- browser dashboard at `http://127.0.0.1:4200`: PASS;
- isolated SQLite database creation: PASS;
- startup time: approximately 15 seconds;
- idle resident memory: approximately 235 MB;
- measured CPU after roughly three minutes: approximately 9.6%;
- shutdown time: approximately 1 second;
- remaining Prefect processes after shutdown: none;
- remaining listener on port 4200: none;
- SQLite lock error under isolated home: none observed.

## Manual conclusion

Prefect 3.7.8 is compatible with Python 3.12.13 and can run as a local self-hosted single-user server using an isolated `PREFECT_HOME`. The API and browser dashboard both loaded successfully.

The shared default Prefect database showed a lock condition and should be treated as a limitation. The Quant Factory spike should use a dedicated Prefect home or otherwise isolate Prefect state.

This document records manual environment evidence only. Code integration, retry, state mapping, timeout/cancellation, persistence behavior, and regression tests remain part of the bounded coding spike.
