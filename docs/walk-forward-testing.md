# Walk-Forward Optimization

Milestone 12 adds repeated chronological selection and evaluation. Each fold
uses only historical data to screen and select parameters, locks one survivor,
and evaluates that lock once on the immediately following unseen test window.
It measures repeated generalization and parameter stability; it is not final
strategy approval.

## Default window policy

| Setting | Default |
|---|---:|
| Training window | 756 rows (approximately three years) |
| Selection window | 252 rows (approximately one year) |
| Test window | 126 rows (approximately six months) |
| Step | 126 rows |
| Training mode | Rolling |
| Minimum rows per window | 30 |
| Training shortlist | At most 5 passing candidates |
| Incomplete final test | Drop |

Rolling mode keeps the training row count fixed and advances its boundaries.
Expanding mode keeps the first training row fixed and advances only the end.
Selection is optional; without it, the highest-ranked passing training
candidate is locked. `step_size` must be at least `test_window_size`, preventing
overlapping test windows. Data is never shuffled.

## Fold lifecycle and failures

Each fold records exact boundaries, runs the full training grid, applies the
existing screen, advances the deterministic top passing shortlist, evaluates
that shortlist on optional selection data, locks one passing choice, and tests
that immutable lock once. Screening thresholds are never relaxed.

If no candidate survives training or selection, the fold is recorded as failed
and its later stages are not called. The overall run continues because a local
performance failure does not invalidate later data. Structural configuration,
timestamp, hygiene, or data errors abort the run.

## Aggregate methodology

- Average and median metrics are explicitly fold summaries.
- Compounded return is the product of `(1 + fold total return)` minus one.
- Endpoint equity and drawdown use sequential fold returns and an initial value
  of one; endpoint drawdown does not capture within-fold paths.
- Fold-return Sharpe is mean fold return divided by sample standard deviation
  and is not presented as a daily annualized Sharpe.
- Completed trades are summed across successful unseen test folds.

Percentages are not averaged and called cumulative performance.
Failed folds contribute no fabricated zero return; compounded results cover only
successful test folds and must be read alongside the failed-fold count.

## Parameter stability

The result records selected parameters by fold, unique selected-set count,
frequency and percentage of each set, change percentage across consecutive
successful selections, maximum consecutive persistence, and failed folds.

## Leakage safeguards

- every fold is strictly ordered train → selection → test with no overlap;
- training is the only source of shortlist membership;
- selection receives only the past-data shortlist;
- the lock exists before test evaluation and test receives exactly that lock;
- test and future values cannot alter an earlier shortlist or lock;
- failed folds cannot produce test evaluations;
- test data may enter training only in a later chronological fold.

## Run the RSI workflow

```bash
.venv/bin/python backtesting/run_rsi_walk_forward.py
```

The command reuses the validated cache and writes a Git-ignored report to
`results/rsi_spy_walk_forward.json`. Failed folds retain their exact reason.
The current cached RSI run constructs 12 folds and all 12 fail training
screening, so it reports no fabricated out-of-sample performance.

## Low-frequency fixed-candidate evidence

Low-frequency candidates can be evaluated as evidence accumulation rather than
parameter selection when the approved parameter set is already fixed. The
low-frequency adapter reuses the walk-forward window splitter and partition
execution path, but each validation fold evaluates exactly one candidate and
applies the policy in `docs/low-frequency-oos-evidence-policy.md`.

Per fold, the report records train and validation boundaries, trade count,
total return, annualized return, Sharpe ratio, maximum drawdown, evidence
status, performance status, and combined status. A validation fold needs at
least eight completed trades to provide sufficient evidence; otherwise it is
`insufficient_evidence`, not a pass.

The aggregate result requires at least three sufficient-evidence folds, at
least 60% of sufficient-evidence folds passing, no fold drawdown worse than
35%, and strict exclusion of any protected held-out interval.

## Run the bounded SPY Donchian 20/10 workflow

```bash
.venv/bin/python backtesting/run_spy_donchian_low_frequency_walk_forward.py
```

The command streams only cached adjusted daily SPY rows before 2024-05-28 and
writes a Git-ignored report to
`results/spy_donchian_low_frequency_walk_forward.json`.

The 2026-07-09 bounded run evaluated five expanding validation folds from
2019-01-04 through 2024-01-05, using only data from 2016-01-04 through
2024-05-24. All five validation folds had fewer than the required eight trades,
so the aggregate result was `insufficient_evidence`. No row on or after
2024-05-28 was included in the evaluation set.

## Limitations

This milestone does not add Monte Carlo simulation, regime classification,
multiple-testing correction, confidence intervals, an experiment database,
dashboard redesign, or promotion policy. Full concatenated daily portfolio
paths are deferred until they can be preserved without inventing data.
