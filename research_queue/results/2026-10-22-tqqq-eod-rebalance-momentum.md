# 2026-10-22-tqqq-eod-rebalance-momentum: rejected

- Title: TQQQ big-move day continues into the close
- Hypothesis: Leveraged ETFs must buy after up days and sell after down days at the close, so large-move days continue into the final half hour.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_b29afc704aaf404f8375738c03797d47; tested 2026-10-22T15:10:37-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 3 / 0
- Best screen setting: {'parameters': {'min_abs_ret': 0.04}, 'sharpe_ratio': 0.3159, 'total_return': 0.2228, 'annualized_return': 0.0284, 'max_drawdown': -0.308, 'number_of_trades': 421.0, 'win_rate': 0.5273}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'QQQ VWAP side trend, reverse on cross', 6), ('candidate', 'SPY midday-range late breakout (12:00-14:30), trail, flat 15:55', 6), ('candidate', 'QQQ 15-min ORB gap-day + VWAP side, wide % trail', 6)]
- Detail: sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.31592358097591666.
