# Quant Factory Milestones

This file is the **only authority for current product direction, active work,
sequencing, blockers, and milestone status**. Supporting documents do not
create a competing queue.

## Current phase

| Item | Current truth |
|---|---|
| Primary goal | Find, reject, and rigorously validate repeatable trading edges. |
| Secondary goal | Convert qualified edges into consistent income using capital-efficient execution. |
| Phase | **Finish the research backend before selecting another strategy.** |
| Active work | Complete the missing generic runtime wiring so an already-approved candidate can move from durable screening launch through screening, OOS, walk-forward, robustness/regime, Monte Carlo, and stop at the protected-test gate without test-only adapters or manual stage assembly. |
| Existing assets | The research engines, persistence, evidence artifacts, durable candidate launch claims, and filter-chain coordinator already exist and must be reused. |
| Verified gap | The current candidate service and filter chain are coordination seams that still depend on injected screening/stage adapters; existing full-chain proof uses deterministic/test seams rather than one finished production backend path. |
| Next action | Inspect the existing runners/services and implement only the missing generic runtime adapters/wiring; then prove that path once end-to-end with a deterministic non-profitability fixture. |
| Deferred | New strategy selection/backtests, paid data, broad dashboard repair, deployment, broker expansion, paper activation, and live work until backend completion is accepted or a measured blocker requires them. |
| Hard boundaries | No new edge research, protected-test execution, automatic promotion, paid data, paper/live orders, or capital exposure during this phase. |

## Active work

<!-- active-work:start -->
| ID | Priority | Status | Depends | Evidence |
|---|---:|---|---|---|
| R10 | 1 | in_progress | none | Owner correction on 2026-09-29: backend operational completion precedes candidate selection. Existing engines remain; complete only the verified runtime gap and prove it once. |
<!-- active-work:end -->

## Backend completion acceptance

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

## Operating sequence

1. **Backend completion — ACTIVE**
2. Edge discovery and candidate selection
3. Validation of surviving edge
4. Execution-vehicle comparison
5. Trader-usable dashboard repair
6. Paper operation
7. Live operation later

### Edge research — NEXT, NOT ACTIVE

After backend completion is recorded, select one genuinely new short-duration
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
- `docs/milestones/milestone-23-acceptance.md`
- `docs/QUANT_FACTORY_DASHBOARD_UI_DIRECTION.md`
- strategy specifications under `docs/strategies/`
- relevant accepted ADRs and tests
