# dummy-2026-10-22-spy-insidebar: rejected

- Title: DUMMY loop test 2: SPY inside-bar breakout with VWAP filter
- Hypothesis: Inside-bar compression then breakout continues in the breakout direction on SPY.
- Verdict: **rejected**; failed stage: oos; QF state: screened_out (oos)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_e3ebf373f5e440a2849acc12de687203; tested 2026-10-22T13:26:37-04:00
- Stages: {'chain': 'stopped', 'oos': 'invalid'}
- Stable region (stress stage): None
- Settings tested / passing screen: 6 / 2
- Best screen setting: {'parameters': {'stop': 0.25, 'trail': 0.6}, 'sharpe_ratio': 0.5346, 'total_return': 0.2554, 'annualized_return': 0.0322, 'max_drawdown': -0.13, 'number_of_trades': 1789.0, 'win_rate': 0.37}
- Unseen 20%: None
- Walk-forward: None
- Prior matches: [('candidate', 'SPY inside-bar breakout with VWAP filter', 10), ('candidate', 'DUMMY loop test: SPY first-half-hour momentum (shifted thresholds)', 7), ('candidate', 'SPY 15-min ORB gap-day aligned, wide % trail', 7)]
- Detail: source-lock run contains unavailable evidence: artifact_location_escapes_root, artifact_location_escapes_root
