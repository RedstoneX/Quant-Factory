# Out-of-Sample Testing

Milestone 11 adds a deterministic chronological holdout around the reusable
experiment runner. Its purpose is to measure one locked parameter choice on
data that played no role in that choice. It does not establish robustness by
itself and is not walk-forward optimization.

## Split policy

The default policy divides the already validated, increasing, unique market
data by row position into contiguous partitions:

| Partition | Fraction | Purpose |
|---|---:|---|
| Train | 60% | Development-period evidence for every candidate |
| Selection | 20% | Deterministic parameter ranking and selection |
| Test | 20% | One final evaluation of the locked parameters |

Integer boundaries are deterministic: train and selection use truncated row
counts and test receives the remainder. Every partition must contain at least
30 rows in the RSI entry point. Partitions are non-overlapping and satisfy
`train end < selection start < test start`.

## Progression, selection, and locking

The full configured grid first runs on training data through the existing
hygiene, portfolio, metric, screening, and deterministic ranking pipeline.
Screened-out training rows cannot advance. The first `shortlist_size` passing
training rows form the shortlist; the explicit default is five, or every
survivor when fewer than five pass. Stable experiment-runner tie breakers make
shortlist membership reproducible.

Only that training-derived shortlist runs on selection data. Selection applies
the same screen again, and only passing selection rows are eligible for locking.
The first deterministically ranked passing selection row is chosen.

The runner then creates an immutable `ParameterLock` containing the normalized
parameters, strategy identity and version, selection row ID and date range, and
ranking policy. A stable SHA-256 lock ID covers those fields. Only after the
lock exists does the test evaluator receive data, and it receives exactly one
parameter combination from the lock. Test metrics cannot trigger reselection.

If training has no passing candidates, the runner raises
`OutOfSampleProgressionError` before selection. If selection has no passing
shortlisted candidates, it raises the same typed exception before locking. In
both cases test evaluation is never called and no new report is written.
Screened-out rows can never be locked.

## Leakage safeguards

- input timestamps must be unique and strictly increasing;
- partitions are contiguous, ordered, copied, and non-overlapping;
- selection evaluation receives no test rows;
- selection receives only the bounded, training-derived passing shortlist;
- empty training or selection survivor sets fail before the next stage;
- the selected row must map to exactly one normalized parameter set;
- the parameter lock is constructed before the test evaluation call;
- the test experiment contains exactly the locked parameter set;
- changing only held-out values cannot change selection or the lock ID;
- each partition carries its exact date range, row count, and provider audit.

These controls prevent parameter-selection leakage through this runner. They do
not detect future-looking strategy implementations, survivorship bias, revised
features, or manual researcher decisions informed by prior test runs. The test
partition should be treated as spent after inspection.

## Run the RSI holdout

```bash
.venv/bin/python backtesting/run_rsi_oos.py
```

The command reuses the validated market-data cache. If candidates survive both
screens, it writes a Git-ignored report to `results/rsi_spy_oos.json` recording
split boundaries, shortlist, parameter lock, and held-out metrics. With the
current data and provisional screen, no RSI candidate survives training, so the
command currently stops clearly before selection and test rather than selecting
a screened-out row. Threshold changes require an explicit research decision.

## Run the SPY Donchian survivor holdout

```bash
.venv/bin/python backtesting/run_spy_donchian_oos.py
```

The command evaluates only the three long-only Donchian variants that passed
the baseline cheap screen. On the 2026-07-09 run, two candidates passed
training and entered selection, but no selection candidate passed the
provisional screen. The runner wrote `results/spy_donchian_oos.json` as a
Git-ignored failure artifact, did not create a parameter lock, and did not
evaluate the held-out test partition. The existing robustness lock loader
therefore rejects the artifact as valid lock evidence, which is the intended
fail-closed outcome.

## Limitations

This is one fixed split of one historical path. It does not provide repeated
adaptation, parameter-stability analysis, regime coverage, multiple-testing
correction, confidence intervals, or Monte Carlo stress. Those concerns remain
for later milestones; Milestone 12 is walk-forward optimization.
