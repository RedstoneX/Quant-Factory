# Milestone 20 Dashboard Acceptance

## Scope

This checklist supports the pending manual Milestone 20E operator browser
acceptance for deterministic fixture launch, monitoring, terminal
reconciliation, persisted-run reopening, historical relaunch, and artifact
inspection. It does not accept Milestone 21 data-provider work, real strategy
execution, run comparison, full trades analytics, or unified evidence
integration.

## Prerequisites

- Work from `QF_REPO_ROOT` on an owned branch based on `main`.
- Use the project virtual environment at `.venv`.
- Confirm the local database has the approved deterministic infrastructure
  fixture configuration.
- Do not use raw CSV, JSON, Python, or SQLite output to make the operator
  decision.

## Start The Dashboard

Run:

```bash
PYTHONPATH=. .venv/bin/python -m dashboard.app
```

Open the local Dash URL printed by the process, then select the Runs page.

## Approved Fixture

Use the saved configuration labeled for the Prefect fixture strategy and
`slice_18a_fixture`. This fixture proves orchestration, persistence, lineage,
artifact, and dashboard behavior. It is not a profitability candidate and must
not be interpreted as market evidence.

## Success Workflow

1. Select the approved fixture saved configuration.
2. Confirm the configuration preview shows immutable parameters, execution,
   strategy identity, and configuration checksum.
3. Select **Launch fixture run**.
4. Confirm the launch summary shows the new Quant Factory run ID, status,
   attempt count, timestamp, Prefect flow-run reference, and no reused run ID.
5. Watch the recent-run monitor until the run reaches a terminal status.
6. Select the run in recent history.
7. Confirm the detail view shows status, attempts, timestamps, Prefect
   reference, operator events, immutable configuration, lineage and
   reproducibility, artifact inventory, validation state, and persisted result
   summary.
8. Confirm the infrastructure-fixture warning is visible.

Expected outcome: the run is terminal, reopenable, and its displayed artifacts
and result summary are marked valid only when validation succeeds.

## Failure Workflow

Launch the controlled failure fixture through the dashboard-facing path.

Expected visible outcomes:

- the failed run remains in recent history;
- the error summary is human readable;
- operator events explain the failure;
- missing or partial artifacts are not shown as successful;
- the result summary does not imply a successful research result.

## Cancellation Workflow

Start the deterministic cancellable fixture, then request cancellation from the
selected-run detail view.

Expected visible outcomes:

- the dashboard first reports that cancellation is pending and cooperative;
- the run remains active until fixture acknowledgement;
- the terminal cancelled state appears only after acknowledgement;
- the cancelled run remains selectable and reopenable;
- cancellation events and empty/failed result state are visible.

## Stale Recovery Workflow

Create deterministic stale created/running fixture runs, enter an explicit UTC
cutoff, and use **Recover stale fixture runs**.

Expected visible outcomes:

- recovered runs become failed;
- stale-recovery and failed events are visible;
- recovered historical runs remain selectable and reopenable;
- the stale recovery error summary is displayed.

## Persisted Reopening After Restart

After a terminal fixture run exists:

1. Stop the dashboard process.
2. Start the dashboard again against the same database.
3. Open the Runs page.
4. Select the historical run.

Expected outcome: recent history, status, events, immutable configuration,
manifest metadata, artifact validation state, runtime lineage, and result
summary still render from persisted services rather than in-memory state.

## Artifact Inspection Checks

Inspect deterministic persisted fixture artifacts and verify:

- valid artifact: shown as valid/success;
- missing artifact: shown as warning, not success;
- corrupt or checksum-mismatched artifact: shown as error, not success;
- invalid artifact schema or manifest/contract mismatch: shown as error, not
  success;
- missing manifest: shown as unavailable/missing, not success;
- incomplete lineage: shown as not recorded or neutral, not reproducible.

## Historical Relaunch Check

1. Select a completed, failed, cancelled, or stale-recovered historical run.
2. Use **Launch new run from this configuration**.
3. Confirm the new run uses the selected run's immutable configuration ID.
4. Confirm the new run receives a new Quant Factory run ID.
5. Confirm the old run remains unchanged and independently inspectable.
6. Confirm the newly launched run becomes selected after refresh.

## Known Limitations

- Browser automation is not part of this repository at Milestone 20E. The
  local environment can import `dash.testing`, but Selenium, Playwright, and a
  configured browser-driver fixture are absent. Automated acceptance therefore
  exercises the Dash callback layer with real `FixtureRunService`,
  `PersistenceService`, artifact retrieval, and restart reconstruction.
- Milestone 20 does not complete real equity provider integration, full run
  comparison, durable review workflow acceptance, trades analytics, or unified
  evidence views. Those remain pending for later milestones.

## Final Pass/Fail Checklist

- [ ] Approved fixture launches from the dashboard.
- [ ] Recent monitor shows new and terminal runs.
- [ ] Selected-run detail shows status, attempts, timestamps, Prefect
      reference, configuration, lineage, artifacts, validation, and result
      summary.
- [ ] Failed runs remain visible and operator-readable.
- [ ] Cancellation is pending until fixture acknowledgement.
- [ ] Stale recovery fails stale runs and keeps them reopenable.
- [ ] Restart preserves run history and details.
- [ ] Historical relaunch creates a new run ID from the old configuration.
- [ ] Artifact warning/error states are not shown as success.
- [ ] Fixture-not-profitability warning is visible.

## Discovery Gate Reminder

Strategy discovery, profitability search, candidate optimization, paper
promotion, and live promotion remain blocked until Milestone 23 passes.
Decision 277 records owner acceptance for the current dashboard/operator
experience; the remaining objective technical gates are not yet complete.
