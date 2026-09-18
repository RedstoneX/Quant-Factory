# MES five-minute opening-range breakout

## Status and hypothesis

This is an approved, exploratory second strategy archetype. The hypothesis is
that MES may continue after a completed five-minute close breaks the high or
low of its New York cash-session opening range. The experiment validates
infrastructure and performs cheap screening; it is not production evidence.

## Exact rules

- Instrument and dataset: MES from `futures_MES_5m_databento`.
- Session anchor: 09:30 `America/New_York`, using the NYSE calendar.
- Opening range: the highest high and lowest low of the completed bars beginning
  at 09:30 for 5, 15, 30, 45, or 60 minutes.
- Confirmation: a completed close strictly above the range high plus the
  configured offset for long-only, or below the range low minus the offset for
  short-only.
- Offset: 0, 1, or 2 MES ticks; one tick is 0.25 index points.
- Fill: next contiguous five-minute bar open.
- Maximum one entry per calendar session. Long and short are separate registered
  strategies, not opposing signals in one portfolio.
- Exit signal: the 15:55 bar close on a normal session, filled at the 16:00 bar
  open. The exchange calendar supplies the equivalent final two bars on early
  closes. There is no overnight carry.
- Baseline has no stop, target, trailing stop, retest, volatility filter, or
  discretionary condition.

The deterministic matrix is 5 range lengths × 3 offsets × 2 structural
directions = exactly 30 variants.

## Session interpretation and data quality

Source timestamps remain UTC. Every session boundary is obtained from the NYSE
calendar and converted explicitly to UTC from its `America/New_York`
interpretation. Verified examples are 14:30 UTC for 09:30 New York on
2025-01-15 and 13:30 UTC on 2025-07-15, demonstrating standard-time and
daylight-time handling.

Weekends and holidays are not inferred from dates with data; they are excluded
by the calendar. Calendar early closes use the published close. A session is
excluded and reported in signal metadata if its 09:30 anchor, any required
opening-range bar, the final signal bar, or the exit-fill boundary is missing.
A non-contiguous bar after breakout confirmation cannot become a fill.

Across the catalog extent, the calendar produced 1,705 sessions. The 5-minute
range had 1,676 eligible sessions and 29 explicitly reported exclusions. Each
of the 15/30/45/60-minute ranges had 1,673 eligible sessions and 32 reported
exclusions. These are data-quality exclusions, not silently synthesized bars.

## Execution and costs

Research accounting uses one fixed MES unit, the $5 MES point value, $100,000
initial normalization cash, no accumulation, and next-bar-open prices. Each
entry and exit pays the current standard IBKR non-member all-in fee of $0.62
per contract per side: $0.25 IBKR commission, $0.35 CME exchange-fee recovery,
and $0.02 NFA regulatory-fee recovery, with no separately listed mandatory
clearing charge. The baseline applies one adverse tick per side; optimistic and
stress scenarios apply 0.5 and 2 ticks. The account assumptions and official
sources are recorded in `docs/mes-execution-and-roll-investigation.md`.

Margin, financing, spread beyond modeled slippage, queue position, and fill
probability are not modeled. The experiment output predates the forensic
resolution and still records its former unresolved status; it was not rerun
because no canonical bar values or strategy inputs changed.

## Provenance and contract-series limitation

The catalog loader verifies the local Parquet size and SHA-256 against
`data/manifests/futures_MES_5m_databento.json` before use. The validated
Databento file has 476,042 five-minute rows from
2019-05-05T22:00:00+00:00 through 2026-02-13T21:55:00+00:00.

Authenticated six-window forensics confirmed the source as Databento
`MES.c.0`, calendar/front-expiry rank zero with original unadjusted prices,
aggregated from supported one-minute OHLCV to UTC five-minute bars. All 17,334
sampled `MES.c.0` OHLCV bars matched exactly. Roll discontinuities remain
unadjusted and can bias ranges, fills, returns, and screening outcomes.

## Exploratory result and interpretation limits

The earlier zero-cost run is superseded. With the documented $0.62 fee and one
tick of slippage per side, all 30 baseline variants were screened out. The top
row remained long-only with a 15-minute range and two-tick breakout offset, but
returned 5.4248% with a 0.4588 Sharpe, 4.1905% maximum drawdown magnitude, and
1,227 trades. It fails the provisional 0.5 Sharpe threshold.

The optimistic half-tick scenario produced three provisional passes; its top
row returned 6.9585% with a 0.5855 Sharpe. The two-tick stress scenario produced
no passes; its top row returned 2.3573% with a 0.2064 Sharpe. These sensitivity
results do not override baseline rejection. The contract-series construction
is now confirmed, but no baseline candidate survived screening and no deep
validation was run.

Generated CSV output is local at `results/mes_orb_5m_exploratory.csv` and is
Git-ignored. Run it with:

```bash
$QF_REPO_ROOT/.venv/bin/python backtesting/run_mes_orb.py
```

Use `--scenario optimistic`, `--scenario stress`, or `--scenario all` for the
explicit alternative slippage assumptions.
