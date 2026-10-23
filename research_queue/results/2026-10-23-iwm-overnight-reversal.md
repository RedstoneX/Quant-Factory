# 2026-10-23-iwm-overnight-reversal: rejected

- Title: IWM overnight gap reverses in the first half hour
- Hypothesis: Overnight retail buying/selling is unwound by arbitrageurs in the first 30 minutes, so the gap partly reverses.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_984bd36323734e2d9d3239441ebc69bc; tested 2026-10-23T10:38:38-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 9 / 0
- Best screen setting: {'parameters': {'gap_frac': 0.001, 'hold_bars': 15}, 'sharpe_ratio': -0.1931, 'total_return': -0.0845, 'annualized_return': -0.0122, 'max_drawdown': -0.1653, 'number_of_trades': 1515.0, 'win_rate': 0.4858}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'SPY first-hour trend continuation at 10:30, wide % trail', 6), ('candidate', 'SPY midday-range late breakout (12:00-14:30), trail, flat 15:55', 6), ('candidate', 'SPY intraday momentum: first half-hour predicts last half-hour', 6)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.08445875137043646. | annualized_return failed: expected > 0.0 (exclusive); observed -0.012210172019315624. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.19310140904139905.
