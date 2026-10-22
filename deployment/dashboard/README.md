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

## Results page

- One page per idea: `/results?candidate_id=<idea id>`. Ideas, Home and Factory "Open Results" go here.
- An old `/results?run_id=<run>` link opens that run's idea with its test selected and that exact run shown.
- Tests shown are the newest campaign only: the newest costs-test run, then each run handed off from it
  (`filter_handoff.source_run_id`); runs from older campaigns are never mixed in.
- Header verdict comes from the saved runs, e.g. "Failed at: unseen data — scored 0.48, needed 0.50" (the score is the
  best training result's saved rejection reason). Tests after a failed pass mark say "Not reached".
- The page opens on the furthest test the idea reached that saved a result, on the Overview tab (account value with
  the drop from peak below).
- Top line: five numbers from the unseen-data test (net profit, max drawdown, trades, win rate, profit factor); when
  the idea never traded unseen data, one plain line says why instead.
- Test strip: costs test and unseen data are pass marks; rolling, stress and shuffle tests are scores (a weak score is amber).
- Costs test and unseen data open strategy-tester tabs: Overview, Price chart and trades, the performance summary
  (read from the run's `performance_summary` artifact, never computed in the dashboard), and the settings the costs
  test tried (picking one loads that setting).
- Price chart: opens on the latest month; Plotly range buttons 1W / 1M / 1Y / All, scroll to zoom, drag to move.
  Each zoom reloads the bars in view at the finest size that fits (5-minute, 15-minute, hourly or daily). Trade
  markers show only when 300 or fewer trades are in view. The trade list sits under the chart; picking a trade
  centres the chart on its day in 5-minute bars.
- Rolling, stress and shuffle tests make no trades; they show the score tiles and their own saved periods, checks or reasons.
