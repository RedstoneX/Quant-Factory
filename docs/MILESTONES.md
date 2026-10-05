# Quant Factory Milestones

This file is the **only authority for current product direction, active work,
sequencing, blockers, and milestone status**. Supporting documents do not
create a competing queue.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable trading edges. |
| Secondary goal | Convert qualified edges into consistent income using capital-efficient execution. |
| Immediate objective | Correct the owner-reported R12 operator-interface defects against the repository-owned approved references, then return the connected workflow for Terry's private walkthrough. |
| Phase | **R13 remains accepted. R12 UI correction is active; owner walkthrough acceptance is not complete. Candidate research remains paused.** |
| Active work | **Implement only the existing approved operator workflow.** Preserve the accepted Dashboard and conforming Ideas presentation; correct only verified page divergence or nonfunctional controls. Separately improve slow rendering by keeping mounted routes lightweight and loading expensive page content only when its route is active. |
| Existing assets | The generic candidate runtime is complete. The architecture remediation is complete with mechanically enforced one-way component boundaries and zero runtime dependency cycles or forbidden directions. The Decision 310 MES screen has one valid result-bearing run using the checksum-matching owned MES file, complete Databento mapping, clean canonical Git SHA, and licensed VectorBT Pro 2026.4.7. Bitwarden Secrets Manager is operational through the `Codex` machine account scoped to the `Quant Factory` project; the named Databento secret authenticated successfully without paid data. |
| Verified gap | Terry's walkthrough found material divergence from the approved page compositions, controls that are ambiguous or do not work as presented, and slow route rendering caused by unnecessary page work. The prior Candidate-identity correction remains preserved. |
| Next action | Preserve conforming pages, correct the verified Setup/Run Test/Results/Compare gaps against repository-owned references, and address shared inactive-route loading without changing accepted page compositions; then deploy one consolidated private-beta revision for Terry's walkthrough. The separate Grok-hosted proof remains blocked on Terry's public key and is not substituted while R12 is active. |
| Deferred | Paid data, protected-test execution, execution-vehicle work, broker expansion, paper activation, live work, and capital exposure until their later gates and separate owner authority. |
| Hard boundaries | Candidate work remains same-session intraday only. Perform the cheap prior-work check first; do not repeat rejected or withdrawn work, optimize openly, inspect protected evidence, buy data, submit orders, or infer paper/live authority. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R12 | 1 | in_progress | none | **UI correction active.** Preserve exact Candidate identity/version/provenance, the accepted Dashboard, and conforming Ideas presentation. Correct verified Setup/Run Test/Results/Compare visual or functional gaps and prevent heavy inactive-route rendering without redesigning conforming pages. Terry's final walkthrough remains the acceptance gate. |
| R14 | 2 | blocked | R12 | **Provider-neutral Agent Research Gateway ARG-0 through ARG-6 remains implemented and operational locally.** Decision 326 reuses it and adds campaign discipline/launcher guidance without changing its authority. The separate actual Grok-hosted connection proof still requires Terry's public key and is not current substitute work. |
<!-- active-work:end -->

The former gate wording, `No Codex implementation is active while Terry performs the walkthrough`,
is superseded by Terry's reported UI defects and current R12 correction authority.

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
5. Owner walkthrough / handoff acceptance — PENDING
6. Owner-approved candidate research
7. Validation of a surviving edge
8. Execution-vehicle comparison
9. Paper operation
10. Live operation later

### Edge research — PAUSED DURING STANDARDIZED INTAKE WORK

No candidate is active, and standardized intake work does not authorize a
strategy test. QF Candidate v1 may be produced by Terry, an external LLM, or a
future optional built-in analyzer, but importing a packet never authorizes
implementation or execution. Before research begins, Terry must explicitly
accept a bounded, source-attributed Candidate packet and its fixed evidence
contract. The current mandate remains **day trading / intraday
directional edge discovery** unless the owner explicitly changes it.
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
The earlier connected-workflow technical-pass claim is superseded by Decision
326. Terry's walkthrough proved that Candidate identity did not remain connected
after Ideas and that an infrastructure fixture could be presented and launched
instead. R12 remains active until the exact-object correction is merged,
privately deployed, and Terry completes and explicitly accepts the new
walkthrough. Idea capture remains local-only; agents use the removable Gateway
rather than an embedded provider. This acceptance does
not qualify an edge or authorize paid data, protected testing, paper/live
operation, orders, or capital exposure.

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
