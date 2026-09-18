# Minimal Visual Decision Dashboard

> **Historical guide:** this describes the former minimal dashboard. Current
> operator requirements are in [dashboard product requirements](dashboard-product-requirements.md),
> with acceptance in [MILESTONES](MILESTONES.md) and the [Milestone 23 matrix](milestones/milestone-23-acceptance.md).
> It does not claim browser acceptance.

The local dashboard turns the existing RSI experiment into a focused review
screen. It uses Plotly Dash for interaction, VectorBT Pro for selected-portfolio
analytics, and Plotly for the equity and drawdown figures.

## Run

Generate or refresh the ranked RSI result first:

```bash
$QF_REPO_ROOT/.venv/bin/python backtesting/run_rsi_demo.py
```

Then start the dashboard from the repository root:

```bash
$QF_REPO_ROOT/.venv/bin/python dashboard/app.py
```

Open <http://127.0.0.1:8050>. The app is local-only and binds to
`127.0.0.1`; it has no authentication or remote deployment configuration.

## Screen

The single page contains:

- experiment and strategy identity;
- six headline metrics;
- the complete ranked parameter table;
- selected parameter values;
- equity and drawdown charts;
- data provider, dates, adjusted status, and row count;
- signal timing, execution timing and price, cash, fees, slippage, direction,
  sizing, and leverage;
- review status and an optional short note.

Select one table row to update the metrics, parameters, equity curve, and
drawdown chart. The adapter reconstructs only that parameter combination; it
does not rerun the complete 27-combination grid on every selection.

The existing ranked table also exposes each row's screening status and concise
rejection reasons. This is a minimal data-contract update, not a new dashboard
workflow; screened-out rows remain selectable for inspection.

## Review state

Available states are `Unreviewed`, `Reject`, `Revise`, and `Watchlist`. Choose a
state, optionally add a note, and select **Save review**. State is stored at:

```text
data/reviews/dashboard_reviews.json
```

The file is ignored by Git. Each record uses a stable identity derived from the
experiment ID, strategy ID, and normalized parameters. This JSON file is a
temporary single-user mechanism, not an experiment database.

## Execution assumptions

The execution panel uses normal-language descriptions of the active model. The
default RSI experiment shows:

- Signal calculated after market close
- Order filled at next session open
- Execution price: Open
- Fees: 0.050%
- Slippage: 0.020%
- Direction: longonly
- Leverage: 1×

The dashboard reconstructs the selected portfolio using these same typed
assumptions; it does not use the historical same-bar-close model unless an
experiment is explicitly configured for that comparison mode.

## Current limitations

- The dashboard covers one local RSI experiment and is not a general catalog.
- Results remain in-sample and use a simplified market-on-open fill model.
- Review state is local and has no multi-user locking or authentication.
- Dash's built-in DataTable is adequate here but is deprecated for a future
  major Dash release; replacement is deferred until it provides concrete value.
- There are no advanced validation, paper/live, broker, AI, or remote-deployment
  features in this milestone.
