# Review of the 7 re-test survivors (2026-10-22)

Evidence: read-only copy of the box QF database backup (2026-10-22), the latest
(2026-10-21) screening grid per idea, and the re-test table (deflated-Sharpe
probability, PBO). No new runs. The walk-forward, robustness and Monte Carlo
evidence files live only on the box and were not read.

## Ranking (record only)

Decision 2026-10-25: none of these goes to Grok as a holdout finalist; their screening already used data through 2026-10-20. They get a forward check on data after 2026-10-20 once it exists. New scout packets that never saw 2025+ get the normal box run and Grok holdout.

| # | Idea | Sharpe (1x cost) | Neighbours of chosen setting | Est. Sharpe at 2x slippage | Trades (per yr) | DSR prob | PBO | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | qfc_85c20168 SPY inside-bar + VWAP | 0.685 | stop 0.25: 0.632 (stable); trail 0.4: 0.30 (cliff) | ~0.61 | 2147 (~199) | 0.925 | 0.09 | Forward check later |
| 2 | qfc_752993d9 SPY 15-min ORB, tight stop + wide trail | 0.509 | stop 0.15: 0.477 (stable); trail 0.3: 0.14 (cliff) | ~0.42 | 2048 (~190) | 0.935 | 0.11 | Forward check later (weak cost margin) |
| 3 | qfc_3d505520 SPY 15-min ORB, 5-min confirm (qfc_5ae53095 is the same idea re-run: 0.539) | 0.552 | trail 1.5: 0.36, 1.0: 0.14 (edge of grid, steep) | ~0.48 | 2085 (~193) | 0.938 | 0.49 | Optional 3rd; PBO is a coin flip |
| 4 | qfc_79379251 SPY 15-min ORB from 2019-05, entries all day | 0.974 | 0.4: 0.945, 0.3: 0.964 (flat, all pass) | ~0.90 | 1480 (~198) | 0.994 | 1.00 | Not yet: start date and trail were matched to the MES survivor after seeing it; re-run from 2016 first |
| 5 | qfc_5c6f85ff QQQ 15-min ORB, 5-min confirm | 0.510 | trail 0.22: -0.02, 0.15: -0.29 | ~0.35 | 2077 (~192) | 0.697 | 0.00 | No |
| 6 | qfc_27bdd8f5 MES 15-min ORB, 5-min confirm | 0.528 (was 0.706 on 2026-10-15) | trail 15: 0.13, 10: -0.39 | ~0.17 | 1325 (~196) | 0.746 | 0.37 | No |

## Findings

- Every survivor's chosen setting is the edge of its grid (largest trail), and 6 of 7 lose most of their Sharpe one step in; only the SPY 2019-05 idea has a flat grid.
- The pipeline ran no 2x-cost stress for these ideas (cost scenarios empty in every config [measured]); the 2x column is an estimate: one extra slippage per side x trades, spread per year, removed from annual return with volatility held fixed.
- Only idea 1 (and idea 4) keep Sharpe above the 0.5 screen at 2x slippage [estimate].
- **Holdout caveat:** screening for all 7 already covered 2025-01-01 to 2026-10-20 (MES to 2026-02-13) [measured: run data coverage], so a holdout check on these ideas is not clean unless it uses data after 2026-10-20.
- Useful queue follow-ups (pre-2025 data only): widen the trail grid past the current edge for ideas 1-3; re-run idea 4 from 2016-01.
