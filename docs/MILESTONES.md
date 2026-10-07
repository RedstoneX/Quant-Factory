# Quant Factory Milestones

This file is the **only authority for current product direction, active work,
sequencing, blockers, and milestone status**. Supporting documents do not
create a competing queue.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable trading edges. |
| Secondary goal | Convert qualified edges into consistent income using capital-efficient execution. |
| Immediate objective | Finish and deploy the measured Results latency correction before Terry's owner walkthrough. The same sealed ORB/VWAP run must open as a usable Overview in under 2 seconds and an interactive chart in under 5 seconds on the private service. |
| Phase | **R13 remains accepted. R12 private-beta workflow correction continues under Decisions 334–335.** |
| Active work | **Revision `38ed00f` is deployed and healthy.** PR #172 removed duplicate inactive-tab trade hydration and corrected the price-chart initial trigger without changing the sealed run. The exact price chart now renders and its 1M/1W controls work, but representative cold-browser service timestamps remain about 7 seconds to Overview and 10 seconds to the chart. The supporting-chart disclosure also failed to issue its deferred Dash callback. The under-2-second/under-5-second owner target is not met. Preserve the separate Compare work. |
| Existing assets | The generic Candidate runtime, bounded parameter plans, persisted Variants grid, OOS/walk-forward/robustness/Monte Carlo engines, Plotly Dash, Dash AG Grid, and licensed VectorBT Pro 2026.4.7 are present. The private VectorBT Pro repository and v2026.10.5 source are accessible; that upgrade is selected but not installed and has breaking defaults that require a separate compatibility proof. Bitwarden Secrets Manager remains operational through the scoped `Codex` machine account. |
| Verified gap | The artifact algorithms and inactive Trades payload are no longer the dominant initial costs. The deployed trace now points to the shared mounted Dash layout and callback startup path: the browser receives a 428 KB layout, loads route-wide component bundles, and completes several unrelated initial callbacks before the selected-run detail. Separately, native `html.Details.open` did not produce the expected server callback when the operator opened the supporting charts. Plotly Resampler remains incompatible with the mixed candlestick-and-marker figure and would not correct these boundaries. The browser also cannot yet define and launch an approved bounded study. The deployed Compare empty-state defect remains separate preserved work. |
| Next action | Replace the non-firing supporting-chart trigger with an explicit Dash-controlled disclosure, then profile and reduce only the shared initial layout/callback work that precedes selected-run detail. Reprove the same sealed run against the under-2-second Overview and under-5-second chart targets and stop for Terry's checkpoint. Do not build a custom optimizer. |
| Deferred | Paid data, protected-test execution, execution-vehicle work, broker expansion, paper activation, live work, and capital exposure until their later gates and separate owner authority. |
| Hard boundaries | Candidate work remains same-session intraday only. Perform the cheap prior-work check first. Parameter search requires an approved bounded study and fixed objective; no open-ended mining, retroactive tuning of the fixed MES Candidates, protected-evidence inspection, automatic promotion, data purchase, orders, or inferred paper/live authority. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R12 | 1 | in_progress | none | **Connected workflow proof passed; Results timing and Terry's acceptance remain open.** PR #172 is deployed at revision `38ed00f`; the sealed ORB/VWAP evidence remains immutable. Price-chart rendering, 1M/1W controls, and inactive-tab trade deferral pass. Cold-browser service timestamps remain about 7 seconds to Overview and 10 seconds to the chart, and the supporting disclosure did not load. The owner target is not met. Preserve separate Compare work. |
| R14 | 2 | blocked | R12 | **Provider-neutral Agent Research Gateway ARG-0 through ARG-6 remains implemented and operational locally.** Decision 326 reuses it and adds campaign discipline/launcher guidance without changing its authority. The separate actual Grok-hosted connection proof still requires Terry's public key and is not current substitute work. |
<!-- active-work:end -->

The former gate wording, `No Codex implementation is active while Terry performs the walkthrough`,
is superseded by Terry's reported UI defects and current R12 correction authority.

## Current R12 correction sequence (2026-10-07)

- **Connected workflow:** The deployed Ideas -> Set up -> Run test -> Results
  path binds the selected approved Candidate to its immutable configuration and
  verified local data. The browser-operated ORB/VWAP proof run completed and
  sealed its full evidence. Set up remains reusable across asset classes and
  timeframes; fixed controls are locked and genuine choices must come from an
  approved contract.
- **Evidence correctness:** PR #169 replaced VectorBT's default intraday
  annualization behavior with explicit completed-session equity, calendar,
  sessions-per-year, and risk-free-rate metadata. Revision `6fd109b` is deployed
  and both dashboard and Agent Gateway containers are healthy. Existing sealed
  runs remain unchanged and are not reinterpreted.
- **Active performance correction:** PR #171 and deployed revision `b7ad084`
  decode the immutable JSON artifact directly from bytes with pinned `orjson`,
  map events to validated bars with binary search, and defer primary/supporting
  chart construction. Local server work measured about 1.77 seconds for
  Overview and 0.34 seconds for the price chart, but the first representative
  browser trace measured 15.3 seconds to usable Overview. It identified a
  duplicated 909 KB payload for the inactive Trades tab and a chart callback
  that rejected its simultaneous initial load/empty-selection event. The local
  follow-up in PR #172 gates trade hydration on the active tab, removes
  duplicate selector hydration, and allows the initial chart render. Deployed
  revision `38ed00f` confirms those corrections, including working 1M/1W chart
  controls. It also shows the remaining cold path at about 7 seconds to
  Overview and 10 seconds to the chart, with a supporting disclosure that did
  not issue its callback. The next owning boundaries are the shared mounted
  layout/callback startup path and the disclosure trigger. Plotly Resampler
  remains for future measured line-only needs; it does not safely wrap this
  mixed candlestick-and-marker figure. Do not rerun a strategy.
- **Approved study direction:** After the performance checkpoint, Set up and
  Run test may expose only Candidate-approved parameter values, search budget,
  costs, data period, and declared objective. Use VectorBT Pro conditional or
  random parameterization, chunking, and parallel execution. Return metrics
  during search; create complete portfolios and immutable evidence only for
  selected finalists.
- **Trader analysis:** Results must favor stable parameter regions over an
  isolated historical winner and expose return versus drawdown, heatmaps,
  costs, OOS/walk-forward evidence, trade diagnostics, shortlist/reopen, and
  exact finalist drilldowns. Automatic selection never means automatic edge
  approval.
- **Boundaries:** Both fixed MES proof Candidates screened out. They may not be
  tuned. No generic Candidate campaign, protected test, paid data, paper/live
  trading, broker order, or capital action is authorized. Preserve the separate
  uncommitted Compare work.

## Architecture remediation — completed 2026-10-01

The architecture acceptance criteria are satisfied. Decision 321 records
Terry's separate explicit approval to lift the development freeze and resume
only the preserved R13/R12 roadmap. Architecture completion itself was not that
approval and creates no broader authority. Strategy research, unrelated
dashboard features, LLM/provider work, broker work, paper/live work, paid or
protected-data work, and unrelated development remain paused.

Starting from canonical revision
`fe7564eac1f5838dd35ec0acd85fa943aa5a063e`, the reproducible AST graph had
three runtime strongly connected components, 90 cyclic runtime edges, and 21
forbidden runtime directions. Sequential green remediation slices established
the CI guard, inverted orchestration/Prefect ownership, removed dashboard
back-imports into the composition root, and moved validation-evidence
coordination behind an explicit persistence protocol. The final graph has zero
runtime SCCs, zero cyclic runtime edges, and zero forbidden directions. ADR
0014 records component ownership, dependency direction, independent
construction contracts, and the secondary size-growth ratchet. No database,
deployment, evidence, research, trading, or safety semantics intentionally
changed.

## Backend completion acceptance — completed 2026-09-29

The backend is ready for edge research when an already-approved candidate can
be carried through the existing research pipeline without inventing another
orchestration layer or manually composing every stage:

1. durable candidate screening launch;
2. real experiment/screening execution and persistence;
3. real runtime adapters for OOS, walk-forward, robustness/regime, and Monte Carlo;
4. persisted stop/advance decisions at each stage;
5. a passing deterministic fixture reaches **protected-test-ready** and stops;
6. failures/replays remain idempotent and fail closed;
7. the path does not depend on dashboard interaction or test-only callbacks.

Use one decisive deterministic proof after implementation. Do not turn backend
completion into repeated fixture testing or another planning exercise.

R10 is complete. `CandidatePipelineRuntime` reuses the durable candidate claim,
actual Prefect flow identity, experiment runner, OOS, walk-forward,
robustness/regime, Monte Carlo, evidence services, and filter-chain coordinator.
The deterministic non-profitability proof reaches protected-test-ready while
the protected state remains gated, persists a failing stop, and proves both
screening and validation-stage failures cannot be reinvoked. The fixture
replaces only the unavailable licensed VectorBT Pro boundary; it proves the
generic runtime orchestration and real validation engines, not deployment,
profitability, or the licensed engine itself.

## Operating sequence

1. Backend completion — COMPLETE
2. R11 fixed MES screen — COMPLETE, REJECTED, NO SURVIVOR
3. Dashboard and operator-product implementation — TECHNICAL PASS; OWNER HANDOFF AVAILABLE
4. **Standardized QF Candidate v1 intake — COMPLETE; OWNER ACCEPTED 2026-10-02**
5. Results performance correction and owner walkthrough / handoff acceptance — ACTIVE
6. Owner-approved candidate research
7. Validation of a surviving edge
8. Execution-vehicle comparison
9. Paper operation
10. Live operation later

### Edge research — LIMITED TO COMPLETED WORKFLOW-PROOF RUNS

Decisions 333–334 authorized one browser-operated run of each exact accepted
fixed MES Candidate to prove the operator path. The ORB/VWAP Candidate screened
out with 1,645 trades, +4.59% total return, 0.472 Sharpe, and 3.16% maximum
drawdown. The 10/30 SMA Candidate screened out with 1,461 trades, -4.69% total
return, and -0.485 Sharpe. Neither reached later validation or protected test;
neither is a viable-edge claim or eligible for tuning.

No generic Candidate campaign is active. QF Candidate v1 may be produced by
Terry, an external LLM, or a future optional built-in analyzer, but importing a
packet never authorizes implementation or execution. Before new research,
Terry must accept a bounded, source-attributed Candidate packet and its fixed
evidence contract. The mandate remains **day trading / intraday directional
edge discovery** unless Terry explicitly changes it.
The fixed MES overnight-gap reversal development screen in
`docs/strategies/mes-overnight-gap-reversal.md` completed and was rejected. It
observed the prior cash-session close and current cash open, entered at 09:35
opposite the gap, and exited at 10:00; no position crossed a session boundary.
Swing, turn-of-month, seasonal, and other calendar-hold strategies are not
current R11 candidates unless the owner explicitly changes the mandate.

### R11 MES development result — rejected 2026-09-30

The sole result-bearing recovery run `run_f7ce514979d64ad0b39b7f933eea7e67`
used the exact Decision 310 configuration, owned checksum-matching MES data, a
complete gap-free 20-interval `MES.c.0` mapping, and VectorBT Pro 2026.4.7. An
earlier durable v1 attempt failed on a loader implementation defect before
producing any result; it remains preserved with zero result evidence. The fixed
v2 recovery is the only accepted candidate evaluation.

- 1,114 completed 25-minute same-session trades across 1,173 sessions;
- 59 exclusions: 43 missing bars, 9 prior early closes, 6 zero gaps, and 1
  missing prior boundary;
- total return: **-4.16386%**;
- annualized return: **-0.90953%**;
- daily Sharpe: **-1.03455**;
- maximum drawdown: **-4.73226%**;
- win rate: **47.2172%**.

Trade count and drawdown passed their gates. Total return, annualized return,
and Sharpe failed, so the conjunctive screen rejected the candidate. All eight
persisted artifacts, the manifest, trade timing, fills, costs, P&L, final
equity, and VectorBT order/trade counts independently validated. No tuning,
rerun, validation, protected-data use, promotion, deployment, or trading is
authorized.

Initial research focuses on S&P 500 and Nasdaq-100 behavior. Existing MES/MNQ
intraday history should be reused for cheap first-stage screening where it can
answer the hypothesis. A surviving signal must later be validated on the
intended SPY/QQQ/index underlying before any options edge is claimed, and 0DTE
implementation requires defensible historical option quote/execution evidence.

### Dashboard and operator product — CONNECTED-WORKFLOW CORRECTION IN PROGRESS

The current Plotly Dash product contains the backend connections and owner-facing surfaces for the single-owner workflow:
idea and configuration setup; approved configuration launch and status;
results, charts, trades, assumptions, evidence and all persisted parameter
variants; saved-test comparison; review and decision recording; reproduction
and failure recovery; and clear navigation and operator language. Approved
candidate configurations connect through the completed generic runtime using
exact persisted configuration reconstruction and cache-only local data.

Focused unit, integration, and rendered-browser evidence proves the current
operator workflow without creating a new candidate or profitability result.
The implementation reused the existing application, mature components,
chart-first UX, backend and accepted evidence; it added no second frontend,
generic arbitrary-strategy builder, orchestration layer, paid-data dependency,
deployment, or trading authority. The objective technical gate is a pass.
The Research Atlas implementation merged at revision
`dbb94148712cdffae04f00ff7b0544ede869c718`, was deployed to the existing
private review service with a verified pre-deployment database backup, and
passed revision, health, and private reachability checks. Terry accepted the
rendered current-revision **overview screen** and authorized continuation on
2026-09-30. That was not acceptance of the unfinished operator workflow.
The earlier connected-workflow technical-pass claim was superseded by Decision
326 after Terry's walkthrough exposed Candidate identity loss and fixture
substitution. Decisions 333–334 then authorized the exact-object correction,
one private deployment, and one real workflow-proof run. That correction is
deployed; R12 remains active for the measured Results performance defect and
Terry's final walkthrough. Idea capture remains local-only, and agents use the
removable Gateway rather than an embedded provider. This does not qualify an
edge or authorize paid data, protected testing, paper/live operation, orders,
or capital exposure.

The current QF Candidate v1 revision is deployed through the existing
tailnet-only private review service. Before deployment, the stopped schema-4
state was captured in an authenticated encrypted backup and restored in
isolation with every retained checksum verified. The existing migration then
preserved all 45 historical runs and advanced the live database to schema 7.
Health, revision identity, private reachability, Candidate upload and
validation, readable review, both export families, the blocked Setup boundary,
zero browser errors, and restart recovery passed. Durable save and reload were
also proven against a disposable copy of the same state. On 2026-10-02 Terry
completed all seven Ideas-page checks, confirmed that the logic and interaction
were usable, and successfully used an external LLM with the exported context to
produce a Candidate YAML packet. Terry explicitly accepted the successful
outcome. R13 is complete. The broader R12 operator-product walkthrough remains
the next owner gate; no candidate research or execution authority follows from
R13 acceptance alone.

### Paper and live

Paper operation requires a qualified edge, a minimum usable operator path, and
the existing credential, execution, reconciliation, recovery, audit, and
fail-closed gates. Live remains far future and requires separate owner approval.

## Prior work that must not be repeated blindly

- MES ORB prior work covers only the documented shallow baseline matrix (range length × breakout offset × direction, session-close exit, no stop/target/retest/volume/volatility confirmation). That tested matrix screened out; the broader ORB family remains open to materially different hypotheses.
- MSFT ORB transfer work was withdrawn; it does not close the ORB family.
- SPYM momentum, SPY Donchian, and RSI fixture work are scoped historical implementations/evidence. They do not exhaust the broader momentum, intraday channel-breakout, or mean-reversion families.
- MES overnight-gap reversal Decision 310 rejected one exact 09:35→10:00 opposite-gap rule. Do not tune or rerun that rule, but do not infer that the entire gap-reversal family is exhausted.
- Turn-of-month was previously source-attributed and bounded, but its multi-day holding period fails the current intraday/day-trading mission-fit gate. Retain it for possible future swing research; do not backtest it under R11.
- Dashboard design research succeeded as UX research; its custom implementation path was shelved.

## Supporting records

Read only when needed:

- `docs/DATA_CATALOG.md`
- [`docs/milestones/milestone-23-acceptance.md`](milestones/milestone-23-acceptance.md) — historical M23 evidence and [incident history](milestones/milestone-23-acceptance.md#incident-history)
- `docs/QUANT_FACTORY_DASHBOARD_UI_DIRECTION.md`
- strategy specifications under `docs/strategies/`
- `docs/strategies/mes-overnight-gap-reversal.md`
- `docs/strategies/spy-turn-of-month.md`
- relevant accepted ADRs and tests
