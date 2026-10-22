# dummy-2026-10-22-spy-insidebar-c: rejected

- Title: DUMMY loop test 4: SPY inside-bar breakout with VWAP filter
- Hypothesis: Inside-bar compression then breakout continues in the breakout direction on SPY.
- Verdict: **rejected**; failed stage: walk_forward; QF state: survivor (awaiting_owner_review)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_ffc219978fef47ef9f3a27c6e077cac8; tested 2026-10-22T13:33:54-04:00
- Stages: {'chain': 'ready_for_protected_test', 'oos': 'passed', 'walk_forward': 'failed', 'robustness': 'failed', 'monte_carlo': 'failed'}
- Stable region (stress stage): failed
- Settings tested / passing screen: 6 / 2
- Best screen setting: {'parameters': {'stop': 0.25, 'trail': 0.6}, 'sharpe_ratio': 0.5346, 'total_return': 0.2554, 'annualized_return': 0.0322, 'max_drawdown': -0.13, 'number_of_trades': 1789.0, 'win_rate': 0.37}
- Locked setting: {'stop': 0.4, 'trail': 0.7}
- Unseen 20% (pre-holdout): {'status': 'passed', 'total_return': 0.1899, 'max_drawdown': -0.0575, 'win_rate': 0.471, 'number_of_trades': 448, 'sharpe_ratio': 1.3784, 'selected_parameters': {'stop': 0.4, 'trail': 0.7}}
- Walk-forward: {'folds': 37, 'folds_passed': 0, 'median_fold_sharpe': 0.0817, 'positive_folds': 5}
- Scored stage fails: ['walk_forward', 'robustness', 'monte_carlo']
- Prior matches: [('candidate', 'DUMMY loop test 3: SPY inside-bar breakout with VWAP filter', 13), ('candidate', 'DUMMY loop test 2: SPY inside-bar breakout with VWAP filter', 13), ('candidate', 'SPY inside-bar breakout with VWAP filter', 10)]
- Detail: Protected test remains locked until separate authority is granted.
