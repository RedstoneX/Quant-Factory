# Quant Factory Resources

This page lists public project resources and safe configuration conventions.
It contains no credential inventory, account identity, or private operational
coordinates.

## Repository and runtime variables

- `QF_REPO_ROOT` — repository checkout; example `/srv/quant-factory/repo`
- `QF_DATA_ROOT` — external market-data root; example `/srv/quant-factory/data`
- `QF_DEPLOY_ROOT` — deployment root; example `/srv/quant-factory/deploy`
- `QF_STATE_ROOT` — mutable state root; example `/srv/quant-factory/state`
- `QF_BACKUP_ROOT` — encrypted backup root; example `/srv/quant-factory/backups`

Use Python 3.12. VectorBT Pro is a separately licensed dependency and is never
committed or included in public dependency manifests. Downloaded market data,
databases, generated artifacts, logs, environment files, and credentials also
remain outside Git.

## Public service references

- Bitwarden Secrets Manager CLI: <https://github.com/bitwarden/sdk-sm/tree/main/crates/bws>
- Plotly Dash: <https://dash.plotly.com/>
- Plotly: <https://plotly.com/python/>
- Prefect: <https://docs.prefect.io/>
- Databento: <https://databento.com/docs>
- Alpaca Trading API: <https://docs.alpaca.markets/>
- exchange-calendars: <https://github.com/gerrymanoim/exchange_calendars>

## Credentials

Bitwarden Secrets Manager is the Quant Factory credential source of truth.
Only variable names and public templates belong in the repository. The
project-scoped `Codex` machine account uses the official `bws` CLI through the
host's encrypted-credential launcher; neither the machine token nor a secret
value may be returned as output or persisted in a dotenv file.

Current provider examples use `DATABENTO_API_KEY`. Dormant paper examples use
`APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`. Their values remain separate vault
items. Research, paper, and live use are separate authority domains and require
separately proven project/grant and OS privilege boundaries before
activation. Withdrawal permissions are prohibited.
See [`operations/bitwarden-secrets-manager.md`](operations/bitwarden-secrets-manager.md).
