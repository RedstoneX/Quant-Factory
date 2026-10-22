# dummy-2026-10-22-spy-insidebar-b: rejected (reclassified: walk_forward + stable-region failed; finalist rule added after this run)

- Title: DUMMY loop test 3: SPY inside-bar breakout with VWAP filter
- Hypothesis: Inside-bar compression then breakout continues in the breakout direction on SPY.
- Verdict: **survivor**; failed stage: none; QF state: survivor (awaiting_owner_review)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_b83edc6841704bb0acba4bfff6474690; tested 2026-10-22T13:30:04-04:00
- Stages: {'chain': 'ready_for_protected_test', 'oos': 'passed', 'walk_forward': 'failed', 'robustness': 'failed', 'monte_carlo': 'failed'}
- Stable region (stress stage): failed
- Settings tested / passing screen: 6 / 2
- Best screen setting: {'parameters': {'stop': 0.25, 'trail': 0.6}, 'sharpe_ratio': 0.5346, 'total_return': 0.2554, 'annualized_return': 0.0322, 'max_drawdown': -0.13, 'number_of_trades': 1789.0, 'win_rate': 0.37}
- Unseen 20%: None
- Walk-forward: None
- Prior matches: [('candidate', 'DUMMY loop test 2: SPY inside-bar breakout with VWAP filter', 12), ('candidate', 'SPY inside-bar breakout with VWAP filter', 9), ('candidate', 'SPY 15-min ORB gap-day aligned, wide % trail', 8)]
- Detail: Protected test remains locked until separate authority is granted.
