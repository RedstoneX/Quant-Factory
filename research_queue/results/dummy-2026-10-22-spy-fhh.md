# dummy-2026-10-22-spy-fhh: rejected

- Title: DUMMY loop test: SPY first-half-hour momentum (shifted thresholds)
- Hypothesis: Loop test only. The first half-hour return predicts the last half-hour return in SPY.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_eb636d370cd04a1698ae47a37b58d949; tested 2026-10-22T13:23:41-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 3 / 0
- Best screen setting: {'parameters': {'min_abs_ret': 0.0005}, 'sharpe_ratio': -0.4576, 'total_return': -0.1337, 'annualized_return': -0.0198, 'max_drawdown': -0.1848, 'number_of_trades': 1615.0, 'win_rate': 0.4817}
- Unseen 20%: None
- Walk-forward: None
- Prior matches: [('candidate', 'SPY first-hour trend continuation at 10:30, wide % trail', 6), ('candidate', 'SPY first-half-hour predicts last-half-hour (Gao et al.)', 6), ('candidate', 'SPY intraday momentum: first half-hour predicts last half-hour', 6)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.13025483643008684. | annualized_return failed: expected > 0.0 (exclusive); observed -0.019242219276032868. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.4865080436786949.
