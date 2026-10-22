# 2026-10-22-qqq-vwap-trend: rejected

- Title: QQQ VWAP side trend, reverse on cross
- Hypothesis: Intraday QQQ trends persist on the side of the volume-weighted average price because institutions executing VWAP orders keep buying or selling through the day.
- Verdict: **rejected**; failed stage: oos; QF state: screened_out (oos)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_80d58f20c9584b9384777abce2a531bb; tested 2026-10-22T15:10:00-04:00
- Stages: {'chain': 'stopped', 'oos': 'invalid'}
- Stable region (stress stage): None
- Settings tested / passing screen: 3 / 3
- Best screen setting: {'parameters': {'band': 0.0006}, 'sharpe_ratio': 0.6836, 'total_return': 0.9879, 'annualized_return': 0.1004, 'max_drawdown': -0.2172, 'number_of_trades': 8413.0, 'win_rate': 0.2707}
- Locked setting: {'band': 0.0006}
- Unseen 20% (pre-holdout): {'status': 'screened_out', 'total_return': -0.0509, 'max_drawdown': -0.1734, 'win_rate': 0.2639, 'number_of_trades': 2137, 'sharpe_ratio': -0.1604, 'selected_parameters': {'band': 0.0006}}
- Walk-forward: None
- Scored stage fails: ['oos']
- Prior matches: [('candidate', 'QQQ EMA cross filtered by ADX trend strength', 6), ('candidate', 'SPY VWAP trendfollow: break VWAP±1ATR with VWAP slope filter', 5), ('candidate', 'SPY EMA 9/21 cross with EMA100 filter, % stop/trail', 5)]
- Detail: out-of-sample run has no single valid source-lock artifact: source-lock evidence is invalid: test did not pass
