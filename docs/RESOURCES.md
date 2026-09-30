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

- Bitwarden Agent Access: <https://github.com/bitwarden/agent-access>
- Plotly Dash: <https://dash.plotly.com/>
- Plotly: <https://plotly.com/python/>
- Prefect: <https://docs.prefect.io/>
- Databento: <https://databento.com/docs>
- Alpaca Trading API: <https://docs.alpaca.markets/>
- exchange-calendars: <https://github.com/gerrymanoim/exchange_calendars>

## Credentials

The dedicated owner-controlled Quant Factory Bitwarden Password Manager vault
is the credential source of truth. Only variable names and public templates
belong in the repository. Official Bitwarden Agent Access (`aac`) selects an
exact approved item and injects mapped fields into a reviewed child process
with `aac run`; it must not return unrestricted vault output or persist a value
in a dotenv file. The client receives the selected full record transiently, and
pairing is not restricted to one item or command, so the client/provider is a
vault-reading trust boundary rather than a per-item capability.

Current provider examples use `DATABENTO_API_KEY`. Dormant paper examples use
`APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`. Their values remain separate vault
items. Research, paper, and live use are separate authority domains and require
separately proven provider/vault-access and OS privilege boundaries before
activation. Withdrawal permissions are prohibited.
See [`operations/bitwarden-agent-access.md`](operations/bitwarden-agent-access.md).
