# Quant Factory Milestones

This file is the **only authority for current product direction, active work,
sequencing, blockers, and milestone status**. Supporting documents do not
create a competing queue.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable trading edges. |
| Secondary goal | Convert qualified edges into consistent income using capital-efficient execution. |
| Immediate objective | Complete and hand off the single-user Quant Factory research product so Terry can initiate or accept controlled candidate work and operate approved strategy configurations through the dashboard. |
| Phase | **Dashboard and operator-product completion.** |
| Active work | Audit and complete the existing end-to-end operator workflow: idea and configuration setup; launch and status; results, charts, trades, assumptions, and evidence; saved-test comparison; review and decision recording; reproduction and failure recovery; navigation and understandable operator language. |
| Existing assets | The generic candidate runtime is complete. The Decision 310 MES screen has one valid result-bearing run using the checksum-matching owned MES file, complete Databento mapping, clean canonical Git SHA, and licensed VectorBT Pro 2026.4.7. Bitwarden Secrets Manager is operational through the `Codex` machine account scoped to the `Quant Factory` project; the named Databento secret authenticated successfully without paid data. |
| Verified gap | Historical dashboard and browser evidence is substantial, but the complete current-revision single-user workflow has not yet been reconciled against the Milestone 23 acceptance record and handed to the owner as a practical operator product. |
| Next action | Reconcile existing evidence, reproduce only genuine product gaps, complete the existing dashboard workflow, prove it with deterministic unit/integration/browser tests, and stop for Terry's final operator walkthrough and handoff acceptance. |
| Deferred | All new strategy selection, proposals, optimization, screening, and profitability tests until handoff; also paid data, external deployment, broker expansion, paper activation, live work, and capital exposure until separately authorized. |
| Hard boundaries | Product verification may use deterministic fixtures and already accepted evidence only. The already-approved SPYM infrastructure fixture may be exercised solely as deterministic product proof, never as new profitability evidence. No new candidate result, paid data, protected-test execution, deployment, paper/live orders, or capital exposure is authorized. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R12 | 1 | in_progress | none | Complete and prove the existing single-user dashboard/operator workflow using deterministic fixtures and already accepted evidence, then stop for Terry's final walkthrough and handoff acceptance. R11 concluded with no surviving edge and creates no requirement for another strategy screen before handoff. |
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
3. **Dashboard and operator-product completion — ACTIVE**
4. Owner walkthrough and handoff acceptance
5. Owner-initiated candidate research
6. Validation of a surviving edge
7. Execution-vehicle comparison
8. Paper operation
9. Live operation later

### Edge research — PAUSED UNTIL OPERATOR HANDOFF

No new candidate may be selected, proposed, optimized, screened, or
profitability-tested before operator handoff. Deterministic fixtures and
already accepted evidence may exercise strategy-shaped behavior only to verify
the product. After handoff, the current mandate remains **day trading /
intraday directional edge discovery** unless the owner explicitly changes it.
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

### Dashboard and operator product — ACTIVE

Complete the existing Plotly Dash product and the full single-owner workflow:
idea and configuration setup; test launch and status; results, charts, trades,
assumptions, and evidence; saved-test comparison; review and decision recording;
reproduction and failure recovery; and clear navigation and language. Reconcile
the historical Milestone 23 evidence before implementing changes, and repair
only reproduced gaps. Use the approved chart-first work as the UX reference,
mature maintained components, thin Quant Factory adapters, and the existing
backend. Do not build a second application, a generic arbitrary-strategy
builder, a new orchestration layer, or enterprise-scale infrastructure.

Current-revision deterministic unit, integration, and browser evidence must
prove the operator workflow without creating a new candidate result. The
already-approved SPYM infrastructure fixture may be exercised solely as
deterministic product proof and must not be represented as profitability
evidence. Stop when the product is ready for Terry's final walkthrough and
handoff acceptance.

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
