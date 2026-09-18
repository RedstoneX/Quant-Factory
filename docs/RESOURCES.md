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

- Plotly Dash: <https://dash.plotly.com/>
- Plotly: <https://plotly.com/python/>
- Prefect: <https://docs.prefect.io/>
- Databento: <https://databento.com/docs>
- Alpaca Trading API: <https://docs.alpaca.markets/>
- exchange-calendars: <https://github.com/gerrymanoim/exchange_calendars>

## Credentials

Only variable names and public templates belong in the repository. The current
paper examples use `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`; values must be
injected through the approved external gateway. Paper and live credentials are
separate, agents never receive unrestricted vault access, and withdrawal
permissions are prohibited.
