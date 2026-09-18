# Low-Frequency Out-of-Sample Evidence Policy

## Purpose

This policy prevents two opposite errors:

1. rejecting a slow-trading strategy solely because a short chronological partition cannot contain the same absolute trade count required from a full-history screen; and
2. weakening evidence rules after seeing attractive results.

It applies prospectively to all low-frequency strategy candidates. It does not automatically reopen, promote, or retest any previously inspected candidate.

## Core rule

A low trade count in an out-of-sample partition is an evidence problem, not automatically an economic failure.

The system must distinguish:

- `failed`: the strategy has enough evidence and violates an approved performance or risk threshold;
- `insufficient_evidence`: the partition does not contain enough independent trading observations to support a pass or failure decision;
- `passed`: all approved evidence and performance requirements are satisfied.

`Insufficient_evidence` never authorizes a parameter lock, held-out test evaluation, robustness, Monte Carlo, paper trading, or live trading.

## Prospective strategy-frequency declaration

Before a new OOS run, each strategy must be assigned an expected-frequency class using training data only:

- high frequency: at least 100 completed trades per year;
- medium frequency: at least 20 but fewer than 100 completed trades per year;
- low frequency: fewer than 20 completed trades per year.

The declaration must record:

- the training date range;
- completed training trades;
- annualized training trade rate;
- the selected frequency class;
- the evidence policy version;
- the decision timestamp before selection or test results are inspected.

The class cannot be changed after selection results are viewed for that run.

## Partition evidence requirements

Performance thresholds and evidence thresholds are separate.

### Performance thresholds

Unless a strategy-specific policy was approved before the run, each evaluated partition still requires:

- positive total return;
- positive annualized return;
- Sharpe ratio of at least 0.5;
- maximum drawdown no greater than 35%.

### Trade evidence thresholds

The full-history cheap screen may retain its existing absolute minimum of 20 trades.

For chronological OOS training and selection partitions, the minimum completed-trade requirement is determined prospectively by frequency class:

- high frequency: at least 20 trades in the partition;
- medium frequency: at least 12 trades in the partition;
- low frequency: at least 8 trades in the partition.

These are minimum evidence floors, not proof of robustness. A passing low-frequency selection with 8 to 11 trades must carry an explicit `limited_sample` warning and cannot skip walk-forward, robustness, or Monte Carlo stages.

A partition below its applicable trade floor is `insufficient_evidence`, even when return, Sharpe, and drawdown appear attractive.

## Fixed-candidate low-frequency walk-forward evidence

Low-frequency evidence accumulation can evaluate one fixed, pre-approved parameter set without performing parameter selection.

The workflow must:

1. declare the strategy as low frequency before validation;
2. build chronological train and validation folds with no overlap leakage;
3. evaluate only the fixed parameters on each validation fold;
4. apply the low-frequency eight-trade evidence floor to each validation fold;
5. classify each fold as `passed`, `failed`, or `insufficient_evidence`;
6. never substitute an insufficient-evidence fold as a passing lock.

A fixed-candidate aggregate passes only if all of the following are true:

- at least three validation folds have sufficient evidence;
- at least 60% of sufficient-evidence folds pass performance thresholds;
- no fold has drawdown worse than 35%;
- no data from a protected held-out interval is loaded into the evaluation set.

If historical data before a protected interval cannot produce at least three sufficient-evidence validation folds, the aggregate result is `insufficient_evidence` and no deeper validation is implied.

## Fail-closed progression

- Training may advance only rows that pass both performance and evidence requirements.
- Selection may lock only a row that passes both performance and evidence requirements.
- The held-out test may run exactly once only after a valid immutable lock exists.
- An `insufficient_evidence` row cannot be used as a fallback lock.
- Test metrics cannot change the lock or the frequency class.

## Previously inspected results

Changing this policy after viewing an earlier selection result does not retroactively convert that result into a valid pass.

A previously inspected candidate may be revisited only through a separately approved research decision that:

1. records that the original selection interval is contaminated for policy design;
2. preserves the original held-out test interval as untouched unless a valid prospective lock is later created;
3. uses new, later data or a newly predeclared walk-forward design for additional selection evidence;
4. does not reuse the inspected selection metrics to choose new parameters, thresholds, or regime rules;
5. retains the original failure or insufficient-evidence artifact unchanged.

## Donchian classification

The 2026-07-09 SPY Donchian OOS run remains invalid for progression under the policy in force at execution because selection produced no passing candidate and no lock.

The 20/10 long-only selection result is classified as:

`promising_but_insufficient_oos_selection_evidence`

This classification is descriptive only. It does not authorize access to the untouched 2024-05-28 through 2026-07-09 test partition.

The inspected 2022-04-20 through 2024-05-24 selection interval must not be reused as fresh selection evidence for a retroactively changed threshold.

## Regime-specialist candidates

Regime specialization must remain a separate hypothesis lane.

A regime rule must be declared before testing and must be observable using information available at the decision time. Historical event labels such as `COVID crash` or `2022 rate shock` may be used for diagnostics but cannot alone define a tradable regime or a cheap-screen pass.

Testing multiple regime rules counts as testing multiple hypotheses. A candidate cannot survive merely because it performed well in one retrospectively selected period.

## Governance

Any change to frequency classes, trade floors, performance thresholds, or progression rules requires:

- a documented project decision before the affected selection or test run;
- deterministic tests;
- versioned reporting of the policy used;
- no silent reinterpretation of prior artifacts.
