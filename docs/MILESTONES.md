# Quant Factory Milestones

This file is the **only authority for current product direction, active work,
sequencing, blockers, and milestone status**. Supporting documents do not
create a competing queue.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable trading edges. |
| Secondary goal | Convert qualified edges into consistent income using capital-efficient execution. |
| Immediate objective | Await Terry's explicit decision on whether to lift the post-remediation development freeze. The pre-freeze next product objective remains the private QF Candidate v1 owner walkthrough. |
| Phase | **Architecture remediation complete; normal feature and research development paused pending explicit owner approval.** |
| Active work | No product development is authorized while the owner-controlled freeze remains in force. The pre-freeze R13 and R12 queue is preserved below, awaiting explicit owner authorization; it has not resumed. |
| Existing assets | The generic candidate runtime is complete. The architecture remediation is complete with mechanically enforced one-way component boundaries and zero runtime dependency cycles or forbidden directions. The Decision 310 MES screen has one valid result-bearing run using the checksum-matching owned MES file, complete Databento mapping, clean canonical Git SHA, and licensed VectorBT Pro 2026.4.7. Bitwarden Secrets Manager is operational through the `Codex` machine account scoped to the `Quant Factory` project; the named Databento secret authenticated successfully without paid data. |
| Verified gap | Terry has not explicitly approved lifting the development freeze. Separately, Terry has not yet used and accepted the current-revision Candidate intake in the private browser environment. |
| Next action | Await Terry's explicit approval or rejection of lifting the development freeze. Do not deploy, resume the owner walkthrough, or start any product work before that decision. |
| Deferred | Paid data, protected-test execution, execution-vehicle work, broker expansion, paper activation, live work, and capital exposure until their later gates and separate owner authority. |
| Hard boundaries | Candidate work remains same-session intraday only. Perform the cheap prior-work check first; do not repeat rejected or withdrawn work, optimize openly, inspect protected evidence, buy data, submit orders, or infer paper/live authority. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R13 | 1 | blocked | none | **Pre-freeze queue preserved; awaiting explicit owner approval to lift the development freeze.** Candidate intake and portable external-research context have a technical pass. No further Candidate, LLM/provider, or related product work is authorized by architecture completion. |
| R12 | 2 | blocked | none | **Pre-freeze queue preserved; awaiting explicit owner approval to lift the development freeze.** The connected operator workflow has a technical pass, but deployment and owner handoff do not resume automatically. |
<!-- active-work:end -->

## Architecture remediation — completed 2026-10-01

The architecture acceptance criteria are satisfied, but the owner-controlled
development freeze remains in force until Terry personally and explicitly
approves lifting it. Architecture completion is not that approval. Normal
feature and research development therefore remains paused. No QF Candidate
work, research, dashboard feature work, LLM/provider work, broker work,
paper/live work, or unrelated development is authorized by this completion.
The pre-freeze product queue is preserved above solely as work awaiting owner
authorization.

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
4. **Standardized QF Candidate v1 intake — TECHNICAL PASS; OWNER WALKTHROUGH PENDING**
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

### Dashboard and operator product — TECHNICAL PASS; OWNER HANDOFF PENDING

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
The connected workflow implementation now has a technical pass. R12 and the
operator-product handoff gate remain active until Terry completes the walkthrough
and explicitly accepts it. Idea capture remains local-only; source retrieval and
LLM-backed ingestion are deferred. This acceptance does
not qualify an edge or authorize paid data, protected testing, paper/live
operation, orders, or capital exposure.

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
