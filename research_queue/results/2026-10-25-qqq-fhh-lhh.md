# 2026-10-25-qqq-fhh-lhh: rejected

- Title: QQQ first-half-hour predicts last-half-hour (Gao et al.)
- Hypothesis: The first half-hour return predicts the last half-hour return in QQQ, same clientele/underreaction mechanism Gao et al. document for SPY.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_6659556f77db4ea6bc1cfbafdc50a93f; tested 2026-10-25T00:28:57-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 3 / 0
- Best screen setting: {'parameters': {'min_abs_ret': 0.002}, 'sharpe_ratio': -0.0953, 'total_return': -0.0369, 'annualized_return': -0.0052, 'max_drawdown': -0.1489, 'number_of_trades': 1322.0, 'win_rate': 0.4917}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'IWM overnight gap reverses in the first half hour', 10), ('candidate', 'SPY first-half-hour predicts last-half-hour (Gao et al.)', 10), ('candidate', 'SPY intraday momentum: first half-hour predicts last half-hour', 10)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.036933266571070544. | annualized_return failed: expected > 0.0 (exclusive); observed -0.00522575004621828. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.09525100410742107.
