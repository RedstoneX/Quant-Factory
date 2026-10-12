# Private Dashboard service

The Quant Factory Dashboard runs directly as a normal Linux service. It is not
part of the research Compose stack.

The machine-owned `/etc/quant-factory/dashboard.env` must define the external
canonical runtime state explicitly:

```text
QUANT_FACTORY_DB_PATH=/absolute/path/to/state/quant_factory.sqlite3
QF_GATEWAY_DB_PATH=/absolute/path/to/gateway/agent_gateway.sqlite3
QF_AGENT_SOCKET=/run/quant-factory/agent-gateway.sock
QF_AGENT_CREDENTIAL_FILE=/absolute/path/to/dashboard-authorized-local.token
```

The source checkout intentionally contains no database. The service account
needs read access to the configured files. Dashboard projections open SQLite in
read-only mode. The sole state-changing Dashboard action sends QF Candidate v1
packets through the authenticated Agent Research Gateway; presentation code
never writes persistence directly. Missing gateway configuration fails visibly.
The installed unit joins `qf-agent-access` for the gateway socket and
`qf-gateway` for read-only audit-state projection. Keep the gateway state
directory non-writable to those supplementary readers and the database itself
group-readable, never group-writable.

The established tailnet listener proxies port 8050 to `127.0.0.1:8050`. The
systemd service, rather than an agent shell, owns that local process so the
review URL remains available after an implementation session ends.
