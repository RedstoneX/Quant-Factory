# Data and Logic Hygiene Gates

Milestone 9 adds deterministic blocking validation before any VectorBT Pro
portfolio simulation. Invalid inputs are not repaired, reindexed, sorted,
filled, clipped, or silently ignored.

## Validation lifecycle

The reusable experiment lifecycle is:

1. Load or receive market data.
2. Run market-data and timestamp gates.
3. Generate strategy signals only after market data passes.
4. Safely normalize binary signal values to boolean.
5. Run signal alignment and structure gates.
6. Align signals to the configured execution bar.
7. Run execution, assumption, and bounded look-ahead gates.
8. Aggregate every blocking failure into one `ExperimentValidationError`.
9. Call `vbt.Portfolio.from_signals` only if no blocking failure exists.
10. Extract metrics and apply the separate cheap-screening stage.
11. Preserve typed gate results and concise pass status in experiment output.

The dashboard selected-portfolio adapter uses the same validated portfolio
builder, so it cannot bypass these gates.

## Implemented gates

### Market data and timestamps

- data is non-empty;
- strategy and execution price columns are present;
- timestamps contain no nulls, are increasing, and are unique;
- available OHLC price columns contain no null, non-finite, zero, or negative
  values;
- when complete OHLC is available, High is not below Low, Open, or Close, and
  Low is not above Open or Close.

Malformed data fails. It is never sorted or corrected automatically.

### Signals

- every present signal has exactly the market-data length and index;
- signals contain no nulls;
- boolean signals pass directly and binary 0/1 signals normalize safely;
- other dtypes fail;
- short entry and exit signals must be present as a pair;
- signal types must agree with long-only, short-only, or both-direction mode.

Partial-index alignment is rejected rather than delegated to Pandas or
VectorBT.

### Execution and assumptions

- the configured execution-price column exists;
- next-bar mode has at least two rows;
- every aligned order has a finite positive execution price;
- completed-close signals in `next_bar_open` equal an exact one-row forward
  shift;
- the last raw signal is deliberately discarded when there is no next row;
- `same_bar_close` is accepted only under its explicit research comparison
  name and produces a warning-severity pass result;
- mode/price, signal timing, position sizing, direction, cash, costs, leverage,
  and accumulation are checked again at experiment level.

## Aggregated failure behavior

Each `ValidationResult` records a stable gate ID, pass/fail status, severity,
message, and structured details. If multiple blocking gates fail, one
`ExperimentValidationError` lists all of them. This makes a malformed dataset
actionable without allowing simulation to begin after the first discovered
problem.

## Look-ahead scope

The layer detects timing contamination that is explicit in the current
architecture:

- a completed-close signal not shifted exactly one bar for next-open execution;
- an unsupported or contradictory execution mode;
- a fill targeting a missing or invalid execution price;
- an attempt to use an unmarked same-bar mode.

It does not prove that arbitrary strategy code is free of look-ahead. It cannot
automatically detect indicators that internally read future rows, revised
fundamental data, survivorship bias, incorrectly timestamped external features,
or manual reuse of a spent test set. The out-of-sample runner now controls
train/selection/test contamination inside its parameter-selection workflow;
the walk-forward runner repeats that past-only boundary across ordered folds.
The remaining cases require code review, provenance, and later validation.
