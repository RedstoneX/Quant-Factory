# Quant Factory Milestones

This file is the **only authority for current product direction, active work,
sequencing, blockers, and milestone status**. Supporting documents do not
create a competing queue.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable trading edges. |
| Secondary goal | Convert qualified edges into consistent income using capital-efficient execution. |
| Immediate objective | Establish the provider-neutral QF Candidate v1 intake backend so ideas from Terry, external LLMs, or a future optional built-in analyzer enter Quant Factory through one readable, validated, non-executable contract. |
| Phase | **Standardized strategy intake backend; candidate research remains paused.** |
| Active work | R12 has a technical pass and remains available for Terry's walkthrough. Per owner direction, non-executing intake plumbing may proceed now: validate/import/export QF Candidate v1 packets and attach them durably to idea drafts. No source retrieval, LLM provider selection, candidate implementation, backtest, or profitability research is active. |
| Existing assets | The generic candidate runtime is complete. The Decision 310 MES screen has one valid result-bearing run using the checksum-matching owned MES file, complete Databento mapping, clean canonical Git SHA, and licensed VectorBT Pro 2026.4.7. Bitwarden Secrets Manager is operational through the `Codex` machine account scoped to the `Quant Factory` project; the named Databento secret authenticated successfully without paid data. |
| Verified gap | The dashboard has durable idea capture, but the backend previously lacked one portable structured contract for ideas produced by Terry, ChatGPT/Claude/Grok/Gemini, or other research tools. Built-in public-source retrieval/LLM analysis remains optional and is not required for standardized intake. |
| Next action | Complete and merge the minimal QF Candidate v1 backend slice: deterministic YAML/JSON validation, durable attachment to idea drafts, import/export helpers, focused migration/tests, and documentation. Then connect that contract to the Ideas workbench in a bounded UI slice before any new strategy research. |
| Deferred | Paid data, protected-test execution, execution-vehicle work, broker expansion, paper activation, live work, and capital exposure until their later gates and separate owner authority. |
| Hard boundaries | Candidate work remains same-session intraday only. Perform the cheap prior-work check first; do not repeat rejected or withdrawn work, optimize openly, inspect protected evidence, buy data, submit orders, or infer paper/live authority. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R13 | 1 | in_progress | none | **Standardized intake, not strategy research.** QF Candidate v1 is the provider-neutral, non-executable interchange contract. Implement/import/persist/export it and then expose it through the existing Ideas workbench. No LLM provider, source retrieval, candidate implementation, or backtest is authorized by this milestone. |
| R12 | 2 | blocked | none | **Connected operator workflow has a technical pass; owner handoff remains available/pending.** This owner gate does not block the explicitly authorized non-executing R13 intake plumbing. |
<!-- active-work:end -->

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
4. **Standardized QF Candidate v1 intake — ACTIVE; NON-EXECUTING**
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

- MES ORB is concluded and rejected as an edge candidate.
- MSFT ORB transfer work was withdrawn.
- SPYM momentum and SPY Donchian/RSI work are historical evidence, not current candidates.
- MES overnight-gap reversal is the Decision 310 fixed 25-minute transfer screen. Its audited development result failed the return and Sharpe gates; the candidate is rejected and must not be rerun or tuned.
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
