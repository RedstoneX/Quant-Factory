# Cheap Strategy Screening

Milestone 10 adds a deterministic early-rejection stage after valid portfolio
simulation and metric extraction. It prevents obviously weak parameter rows
from consuming later out-of-sample, walk-forward, or stress-testing resources.
It is not final strategy approval and does not establish robustness or future
profitability.

## Lifecycle and outcome types

The experiment lifecycle is now:

1. reject invalid parameter definitions as configuration rejections;
2. stop invalid research inputs through blocking hygiene gates;
3. simulate each valid parameter combination;
4. extract the established experiment metrics;
5. apply cheap screening to the valid simulation;
6. preserve passing and screened-out rows separately and in one complete table;
7. rank passing rows first, then screened-out rows, using the configured metric
   ordering within each group.

These outcomes remain distinct:

- **configuration rejection** — parameters are invalid and no simulation runs;
- **hygiene failure** — data, signals, or assumptions are invalid and the run
  stops before simulation;
- **screening failure** — simulation is valid, but preliminary performance rules
  reject the row from expensive later validation.

No failed screening row is deleted. Each retains its metrics, stable parameter
row ID, rule counts, concise reasons, and detailed typed rule results.

## Provisional defaults

| Rule | Default | Boundary |
|---|---:|---|
| Completed trades | 20 | `>= 20`, inclusive |
| Total return | 0% | `> 0%`, exclusive |
| Annualized return | 0% | `> 0%`, exclusive |
| Sharpe ratio | 0.50 | `>= 0.50`, inclusive |
| Drawdown magnitude | 35% | `<= 35%`, inclusive |

Win rate is available as an optional inclusive threshold but is disabled by
default because the current metrics do not establish a universal win-rate
requirement. Profit factor and exposure are deferred because they are not in the
stable experiment output and are unnecessary for this bounded filter.

The suggested 25% drawdown default would reject all 27 current RSI combinations.
The provisional 35% threshold still rejects excessive losses while allowing
three baseline combinations to proceed, making the screen useful as a neutral
early filter rather than a disguised final selection rule. These are research
defaults, not live-deployment limits.

## Rules

Every row receives these rules in a fixed order:

- required screening metrics are present;
- required metrics are finite (not NaN or positive/negative infinity);
- minimum completed trades;
- positive total return;
- positive annualized return;
- minimum Sharpe ratio;
- maximum drawdown magnitude;
- optional minimum win rate when configured.

The overall decision is the conjunction of all rules, so changing evaluation
order cannot change pass/fail. Exact threshold values behave as documented in
the boundary column above.

## Output contract

The complete CSV includes:

- `parameter_row_id`;
- `screening_status` (`passed` or `screened_out`);
- `screening_passed_rule_count`;
- `screening_failed_rule_count`;
- `screening_rejection_reasons`.

`ExperimentResult` additionally exposes `passing_results`,
`screened_out_results`, the serializable `ScreeningConfig`, and full typed
`ScreeningResult` objects. The dashboard makes the status and concise reasons
visible in its existing table without adding new pages or workflows.

## Limitations

This screen uses in-sample aggregate metrics. It does not test generalization,
parameter stability, regime behavior, trade-order uncertainty, market capacity,
or future profitability. A passing row is merely eligible for Milestone 11 and
later validation; it is not approved for paper or live trading.
