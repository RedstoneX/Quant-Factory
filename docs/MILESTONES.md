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
| Active work | Select one genuinely new short-duration S&P/Nasdaq hypothesis, predeclare its rationale, parameter boundaries, execution assumptions, data boundary, and first-stage pass/fail evidence, then run only the cheapest sufficient discovery test. |
| Existing assets | The generic candidate runtime now composes durable screening launch, real screening and validation engines, persisted evidence decisions, idempotent replay, and a fail-closed stop at the protected-test gate. Existing validated MES/MNQ data may support a cheap first-stage discovery test where appropriate. |
| Verified gap | No current candidate hypothesis has yet passed a bounded first-stage discovery test. Historical MES ORB, MSFT ORB, SPYM momentum, and SPY Donchian/RSI work do not supply a new candidate. |
| Next action | Perform the cheap prior-work check, choose one genuinely new hypothesis with a named rationale, and define the minimum experiment and data required before running it. |
| Deferred | Paid options data, broad dashboard repair, deployment, broker expansion, paper activation, and live work until a bounded experiment or qualified edge creates the requirement. |
| Hard boundaries | No protected-test execution, automatic promotion, open-ended optimization, blind data mining, unbounded data acquisition, paper/live orders, or capital exposure during this phase. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R11 | 1 | in_progress | none | Backend completion is recorded. Select and bound one genuinely new short-duration S&P/Nasdaq hypothesis after a cheap prior-work check; do not repeat withdrawn or concluded strategy work. |
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

Select one genuinely new short-duration
S&P/Nasdaq hypothesis. Existing validated MES/MNQ data may be used for cheap
first-stage discovery where appropriate. A futures result does not by itself
qualify a SPY/QQQ/SPXW options edge; surviving signals must later be validated
on the intended underlying/index and, for 0DTE execution, on defensible
historical option quote/execution data.

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
- Dashboard design research succeeded as UX research; its custom implementation path was shelved.

## Supporting records

Read only when needed:

- `docs/DATA_CATALOG.md`
- [`docs/milestones/milestone-23-acceptance.md`](milestones/milestone-23-acceptance.md) — historical M23 evidence and [incident history](milestones/milestone-23-acceptance.md#incident-history)
- `docs/QUANT_FACTORY_DASHBOARD_UI_DIRECTION.md`
- strategy specifications under `docs/strategies/`
- relevant accepted ADRs and tests
