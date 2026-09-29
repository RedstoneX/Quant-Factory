# Quant Factory Milestones

This file is the **only authority for current product direction, active work,
sequencing, blockers, and milestone status**. Supporting documents do not
create a competing queue.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable trading edges. |
| Secondary goal | Convert qualified edges into consistent income using capital-efficient execution. |
| Phase | **Edge discovery and candidate selection.** |
| Active work | Obtain the owner's explicit accept/reject decision on the single predeclared MES overnight-gap reversal development-screen proposal. Do not implement or execute it merely because the runtime and data exist. |
| Existing assets | The generic candidate runtime is complete. Prior-work and primary-source audits found the proposed 09:35–10:00 MES reversal nonduplicative and fixed its source-transfer limits, signal, costs, roll exclusions, development boundary, accounting, and stop conditions in `docs/strategies/mes-overnight-gap-reversal.md`. The existing licensed VectorBT Pro 2026.4.7 runtime was located and verified with current-checkout imports; reuse it rather than install another copy. |
| Verified gap | No candidate is owner-approved and the proposed screen has not been implemented or run. The SPY turn-of-month proposal remains a legitimate but **out-of-scope multi-day swing/calendar idea** for the present intraday mandate. |
| Next action | The owner accepts or rejects the named MES proposal and its fixed boundaries. Only after acceptance may the candidate-local adapter reconnect the owned data and existing licensed runtime, execute the single development screen, and stop on pass or fail. |
| Deferred | Paid options data, broad dashboard repair, deployment, broker expansion, paper activation, and live work until a bounded experiment or qualified edge creates the requirement. |
| Hard boundaries | No protected-test execution, automatic promotion, open-ended optimization, blind data mining, unbounded data acquisition, paper/live orders, or capital exposure during this phase. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R11 | 1 | blocked | none | The fixed MES overnight-gap reversal proposal has completed prior-work, primary-source, runtime-reuse, and adversary review. Decision 306 retains the owner's explicit candidate-approval gate; no data was loaded and no backtest ran. |
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
2. **Edge discovery and candidate selection — ACTIVE**
3. Validation of surviving edge
4. Execution-vehicle comparison
5. Trader-usable dashboard repair
6. Paper operation
7. Live operation later

### Edge research — ACTIVE

The current mandate is **day trading / intraday directional edge discovery**.
The proposed first slice is the fixed MES overnight-gap reversal development
screen in `docs/strategies/mes-overnight-gap-reversal.md`. It observes the
prior cash-session close and current cash open, enters at 09:35 opposite the
gap, and exits at 10:00; the position never crosses a session boundary. It
awaits explicit owner acceptance and has no result. Swing, turn-of-month,
seasonal, and other calendar-hold strategies are not current R11 candidates
unless the owner explicitly changes the mandate.

Initial research focuses on S&P 500 and Nasdaq-100 behavior. Existing MES/MNQ
intraday history should be reused for cheap first-stage screening where it can
answer the hypothesis. A surviving signal must later be validated on the
intended SPY/QQQ/index underlying before any options edge is claimed, and 0DTE
implementation requires defensible historical option quote/execution evidence.

### Dashboard

The current dashboard is not accepted as the long-term usable interface.
Historical technical evidence and the successful chart-first UX research remain
valuable. Dashboard repair follows a promising edge or begins earlier only if a
measured UI deficiency blocks research.

When resumed, reproduce the approved UX with mature maintained components and
thin Quant Factory adapters. Do not revive the custom prototype as a second
application.

### Paper and live

Paper operation requires a qualified edge, a minimum usable operator path, and
the existing credential, execution, reconciliation, recovery, audit, and
fail-closed gates. Live remains far future and requires separate owner approval.

## Prior work that must not be repeated blindly

- MES ORB is concluded and rejected as an edge candidate.
- MSFT ORB transfer work was withdrawn.
- SPYM momentum and SPY Donchian/RSI work are historical evidence, not current candidates.
- MES overnight-gap reversal is a new, fixed 25-minute transfer proposal awaiting owner acceptance; it has not been implemented or run.
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
