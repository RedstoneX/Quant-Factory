# 2026-10-25-mes-orb-failure-fade: rejected

- Title: MES 15-min ORB failure fade
- Hypothesis: Failed MES opening-range breaks are stop-runs that reverse once price reclaims the range; fading the reclaim captures forced-exit liquidity.
- Verdict: **rejected**; failed stage: screening; QF state: screened_out (screening)
- Data cut-off (holdout locked from): 2025-01-01T00:00:00Z; last bar seen: 2024-12-31 00:00:00+00:00
- Run: run_3a3ea5db9d384d65a87c080dbcbde967; tested 2026-10-25T00:25:35-04:00
- Stages: {'chain': 'screened_out'}
- Stable region (stress stage): None
- Settings tested / passing screen: 9 / 0
- Best screen setting: {'parameters': {'hold_bars': 18, 'stop_atr': 2.0}, 'sharpe_ratio': -0.2355, 'total_return': -0.0081, 'annualized_return': -0.0018, 'max_drawdown': -0.0241, 'number_of_trades': 551.0, 'win_rate': 0.4483}
- Locked setting: None
- Unseen 20% (pre-holdout): None
- Walk-forward: None
- Scored stage fails: []
- Prior matches: [('candidate', 'IWM 15-min ORB gap-day aligned, wide % trail', 7), ('candidate', 'SPY VWAP mean-reversion (ATR bands), TP toward VWAP', 6), ('candidate', 'SPY Bollinger mean-reversion (touch outer band), TP to mid approx', 6)]
- Detail: total_return failed: expected > 0.0 (exclusive); observed -0.008061933499105445. | annualized_return failed: expected > 0.0 (exclusive); observed -0.0017877341886849418. | sharpe_ratio failed: expected >= 0.5 (inclusive); observed -0.23551739307603492.
