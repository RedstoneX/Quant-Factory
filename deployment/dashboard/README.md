# Private Dashboard service

The Quant Factory Dashboard runs directly as a normal Linux service. It is not
part of the research Compose stack.

The machine-owned `/etc/quant-factory/dashboard.env` must define the external
canonical runtime state explicitly:

```text
QUANT_FACTORY_DB_PATH=/absolute/path/to/state/quant_factory.sqlite3
```

The source checkout intentionally contains no database. The service account
needs read access to the configured file. Dashboard projection opens SQLite in
read-only mode and must fail visibly if the variable is absent or invalid.

The established tailnet listener proxies port 8050 to `127.0.0.1:8050`. The
systemd service, rather than an agent shell, owns that local process so the
review URL remains available after an implementation session ends.
