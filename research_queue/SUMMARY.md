# QR tasks 1-3 summary (2026-10-22)
1. Survivor ranking (details: review-survivors.md): 1 SPY inside-bar+VWAP (85c20168), 2 SPY ORB tight stop+wide trail (752993d9), 3 SPY ORB 5-min confirm (3d505520 = 5ae53095), 4 SPY 2019-05 (79379251), 5 QQQ ORB, 6 MES ORB.
2. Decision 2026-10-25: no survivor goes to Grok's holdout (screening saw data to 2026-10-20); ranking is record only; survivors get a forward check on post-2026-10-20 data later.
3. Every chosen setting sits on the edge of its grid; 6 of 7 lose most Sharpe one step in.
4. No 2x-cost stress was run by the pipeline; estimated Sharpe at 2x slippage stays >= 0.5 only for 85c20168 (~0.61) and 79379251 (~0.90).
5. Caveat: survivors' screening already used data to 2026-10-20 (MES 2026-02-13), so a 2025+ holdout on them is not clean.
6. Sharpe standard: PR #369 (open, not merged) switches both research scripts to the VBT returns accessor; tests show equality with the pipeline metric.
7. Scout: prompt tightened (duplicate check, testable-data check, holdout ban, mechanism-first sources); validator step fixed (old venv path did not exist, check was silently skipped).
8. Scout runner now allows the validator's Python; $3 budget cap kept; cron unchanged (Tue/Fri 09:30 ET from 2026-10-27).
9. Dry run: 2 packets (TQQQ rebalance momentum, IWM gap fade), both valid; not pushed (weak sources).
10. Suggested queue follow-ups: widen trail grids past the edge for ranks 1-3; re-run 79379251 from 2016.
